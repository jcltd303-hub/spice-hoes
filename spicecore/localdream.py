"""Bounded Local Dream client; installed model loading and validation remain manual."""
import base64
import hashlib
import json
import struct
import socket
import threading
import time
import urllib.request
import zlib

MAX_IMAGE_BYTES = 32 * 1024 * 1024

def _png(rgb, width, height):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + rgb[y*width*3:(y+1)*width*3] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Local Dream redirect rejected')

def _open(request, timeout):
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout)

def _read(response, size, remaining):
    # HTTPResponse.read1 performs at most one underlying read, unlike read(n).
    # Set the socket timeout for THIS read to the overall remaining budget.
    if hasattr(response, 'set_read_timeout'):
        response.set_read_timeout(remaining)
    else:
        response.fp.raw._sock.settimeout(remaining)
    return response.read1(size)

class LocalDreamClient:
    def __init__(self, *, capabilities, opener=_open, max_image_bytes=MAX_IMAGE_BYTES, timeout=300):
        if not 0 < max_image_bytes <= MAX_IMAGE_BYTES or timeout <= 0:
            raise ValueError('Invalid bounds')
        self.capabilities, self.opener = capabilities, opener
        self.limit, self.timeout = max_image_bytes, timeout

    def generate(self, settings):
        c = self.capabilities
        if c.get('validated') is not True or not c.get('version') or not c.get('model') or not c.get('fields'):
            raise ValueError('Manually validated installed version/model/fields required')
        if not isinstance(settings, dict) or not isinstance(settings.get('prompt'), str) or not settings['prompt']:
            raise ValueError('Prompt required')
        if set(settings) - set(c['fields']):
            raise ValueError('Settings unsupported by installed backend')
        started = time.monotonic()
        request = urllib.request.Request('http://127.0.0.1:8081/generate', data=json.dumps(settings, allow_nan=False).encode(), headers={'Content-Type':'application/json'}, method='POST')
        response = self.opener(request, timeout=self.timeout)
        expired = threading.Event()
        transport = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
        def expire():
            expired.set()
            if transport is not None:
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            elif hasattr(response, 'abort'):
                response.abort()
        # A watchdog shuts down the underlying socket even while HTTPResponse is
        # parsing buffered chunk framing. It performs no reads and is always joined.
        deadline = threading.Timer(max(0, self.timeout - (time.monotonic() - started)), expire)
        deadline.name = 'localdream-deadline'
        deadline.start()
        try:
            if response.status != 200 or response.headers.get('Content-Type', '').split(';')[0] != 'text/event-stream':
                raise ValueError('Local Dream returned HTTP/JSON error')
            pending, lines, total = b'', [], 0
            # Limits include previews and progress; disable previews in installed configuration.
            stream_limit = ((self.limit + 2)//3)*4 + 65536
            while True:
                remaining = self.timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('Generation deadline exceeded')
                part = _read(response, 65536, remaining)
                if time.monotonic() - started >= self.timeout:
                    raise TimeoutError('Generation deadline exceeded')
                total += len(part)
                if total > stream_limit:
                    raise ValueError('Local Dream stream exceeds limit')
                pending += part
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    line = line.rstrip(b'\r')
                    if line.startswith(b'data:'):
                        lines.append(line[5:].lstrip(b' '))
                    elif not line and lines:
                        event = json.loads(b'\n'.join(lines))
                        lines = []
                        if not isinstance(event, dict):
                            raise ValueError('Invalid SSE event')
                        if event.get('type') == 'error':
                            raise ValueError('Local Dream generation error')
                        if event.get('type') == 'complete':
                            return self._result(event, settings, started)
                if not part:
                    raise ValueError('Missing complete SSE event')
        except Exception as exc:
            if expired.is_set() or time.monotonic() - started >= self.timeout:
                raise TimeoutError('Generation deadline exceeded') from exc
            raise
        finally:
            deadline.cancel()
            deadline.join()
            response.close()

    def _result(self, event, settings, started):
        width, height = event.get('width'), event.get('height')
        if any(type(v) is not int or v <= 0 for v in (width, height)) or event.get('channels') != 3:
            raise ValueError('Invalid RGB dimensions/channels')
        expected, encoded = width * height * 3, event.get('image')
        if expected > self.limit or not isinstance(encoded, str) or len(encoded) > ((self.limit+2)//3)*4:
            raise ValueError('Image exceeds limit')
        try:
            rgb = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid image base64') from exc
        if len(rgb) != expected:
            raise ValueError('RGB byte length mismatch')
        image = _png(rgb, width, height)
        if len(image) > self.limit or not image.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Encoded PNG exceeds limit')
        source = settings.get('image')
        return dict(image=image, artifact_hash=hashlib.sha256(image).hexdigest(), seed=event.get('seed'),
                    model=self.capabilities['model'], version=self.capabilities['version'],
                    source_hash=hashlib.sha256(base64.b64decode(source, validate=True)).hexdigest() if source else None,
                    latency_ms=round((time.monotonic()-started)*1000))

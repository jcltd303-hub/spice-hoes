"""Serve sanitized public stills from an owner-configured HTTPS media directory."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import tempfile
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageOps


_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_IMAGE_PIXELS = 25_000_000
_MAX_JPEG_BYTES = 8 * 1024 * 1024
_KEY = re.compile(r'/([a-f0-9]{64}\.jpg)')


def _public_url(value, *, base=False):
    try:
        parts = urlsplit(value)
        if (not isinstance(value, str) or parts.scheme != 'https' or not parts.hostname
                or parts.username is not None or parts.password is not None or parts.fragment
                or (base and parts.query) or any(ord(c) < 33 for c in value)):
            raise ValueError
        _ = parts.port
    except (ValueError, TypeError):
        raise ValueError('Public media needs an HTTPS URL without embedded credentials') from None
    return value.rstrip('/') if base else value


class PublicDirectoryMediaDelivery:
    """Write immutable JPEGs, verify public read access, and return their URL."""

    def __init__(self, directory, base_url, timeout=30):
        self.directory = Path(directory).resolve()
        self.base_url = _public_url(base_url, base=True)
        if not 0 < timeout <= 60:
            raise ValueError('Media verification timeout must be between 0 and 60 seconds')
        self.timeout = timeout
        self.directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls):
        base = os.getenv('SPICE_MEDIA_PUBLIC_BASE_URL', '').strip()
        if not base:
            raise ValueError('Set SPICE_MEDIA_PUBLIC_BASE_URL to your HTTPS media host')
        return cls(os.getenv('SPICE_MEDIA_PUBLIC_DIR', 'data/public-media'), base)

    def readiness(self):
        ready = self.directory.is_dir() and os.access(self.directory, os.W_OK)
        return {'ready': ready, 'provider': 'public-directory', 'photo_upload': ready,
                'reason': None if ready else 'Public media directory is not writable'}

    @staticmethod
    def _jpeg(path):
        try:
            if not path.is_file() or not 0 < path.stat().st_size <= _MAX_SOURCE_BYTES:
                raise ValueError
            with Image.open(path) as image:
                if image.width * image.height > _MAX_IMAGE_PIXELS or getattr(image, 'is_animated', False):
                    raise ValueError
                image.load()
                image = ImageOps.exif_transpose(image)
                if 'A' in image.getbands() or 'transparency' in image.info:
                    rgba = image.convert('RGBA')
                    rgb = Image.new('RGB', rgba.size, 'white')
                    rgb.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    rgb = image.convert('RGB')
                result = io.BytesIO()
                rgb.save(result, format='JPEG', quality=95, subsampling=0)
                payload = result.getvalue()
            if not payload or len(payload) > _MAX_JPEG_BYTES:
                raise ValueError
            return payload
        except Exception:
            raise ValueError('Media delivery needs a readable still within photo size limits') from None

    def prepare(self, candidate):
        source = candidate.get('media_uri') or candidate.get('asset_uri')
        if not isinstance(source, str) or not source.strip():
            raise ValueError('Media candidate requires asset_uri or media_uri')
        if urlsplit(source).scheme:
            return _public_url(source)
        payload = self._jpeg(Path(source))
        digest = hashlib.sha256(payload).hexdigest()
        key = digest + '.jpg'
        destination = self.directory / key
        if destination.is_symlink():
            raise RuntimeError('Public content target cannot be a symlink')
        if destination.exists():
            if destination.read_bytes() != payload:
                raise RuntimeError('Existing public content does not match its digest')
        else:
            with tempfile.NamedTemporaryFile(dir=self.directory, prefix='.pending-', delete=False) as f:
                temporary = Path(f.name)
                try:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                    os.chmod(temporary, 0o644)
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
        url = self.base_url + '/' + key
        try:
            request = urllib.request.Request(url, headers={'Accept': 'image/jpeg'})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                public = response.read(_MAX_JPEG_BYTES + 1)
                matched = response.status == 200 and hashlib.sha256(public).hexdigest() == digest
            if not matched:
                raise RuntimeError
        except Exception:
            raise RuntimeError('Public media read verification failed; check HTTPS host and directory mapping') from None
        return url


MediaDelivery = PublicDirectoryMediaDelivery


def make_media_handler(directory):
    root = Path(directory).resolve()

    class PublicMediaHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._serve(False)

        def do_HEAD(self):
            self._serve(True)

        def _serve(self, head):
            match = _KEY.fullmatch(urlsplit(self.path).path)
            path = root / match.group(1) if match else None
            if path is None or path.is_symlink() or not path.is_file():
                self.send_error(404)
                return
            try:
                if not 0 < path.stat().st_size <= _MAX_JPEG_BYTES:
                    self.send_error(404)
                    return
                payload = path.read_bytes()
                if hashlib.sha256(payload).hexdigest() + '.jpg' != path.name:
                    self.send_error(404)
                    return
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            if not head:
                self.wfile.write(payload)

        def log_message(self, *args):
            pass

    return PublicMediaHandler


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only loopback server for approved public stills')
    parser.add_argument('--directory', default=os.getenv('SPICE_MEDIA_PUBLIC_DIR', 'data/public-media'))
    parser.add_argument('--port', type=int, default=8788)
    args = parser.parse_args(argv)
    Path(args.directory).mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_media_handler(args.directory))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

import base64
import json
import unittest
from spicecore.localdream import LocalDreamClient

class Response:
    status = 200
    headers = {'Content-Type': 'text/event-stream'}
    def __init__(self, data): self.data = data
    def read(self, n):
        chunk, self.data = self.data[:min(n, 3)], self.data[min(n, 3):]
        return chunk
    def close(self): pass
    def read1(self, n): return self.read(n)
    def set_read_timeout(self, seconds): pass

def stream(data):
    return Response(('event: complete\r\ndata: '+json.dumps(data)+'\r\n\r\n').encode())

class LocalDreamTests(unittest.TestCase):
    def client(self, response, **kw):
        return LocalDreamClient(capabilities={'validated': True, 'version': 'installed', 'model': 'manual', 'fields': ['prompt', 'seed']}, opener=lambda *a, **k: response, **kw)
    def test_fragmented_sse(self):
        data = {'type': 'complete', 'image': base64.b64encode(b'\xff\x00\x00').decode(), 'width': 1, 'height': 1, 'channels': 3, 'seed': 42}
        result = self.client(stream(data)).generate({'prompt': 'test', 'seed': 42})
        self.assertTrue(result['image'].startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(result['seed'], 42)
    def test_json_error(self):
        r = Response(b'{"error":"model missing"}'); r.status = 500; r.headers = {'Content-Type':'application/json'}
        with self.assertRaises(ValueError): self.client(r).generate({'prompt':'x'})
    def test_sse_error(self):
        with self.assertRaises(ValueError):
            self.client(stream({'type':'error','message':'failed'})).generate({'prompt':'x'})
    def test_bad_image_and_limit(self):
        for image in ('!!!', base64.b64encode(b'bad').decode()):
            data = {'type':'complete','image':image,'width':2,'height':2,'channels':3}
            with self.assertRaises(ValueError): self.client(stream(data)).generate({'prompt':'x'})
        with self.assertRaisesRegex(ValueError, 'stream exceeds limit'):
            self.client(Response(b'x'*65545), max_image_bytes=4).generate({'prompt':'x'})
        data = {'type':'complete','image':base64.b64encode(b'abcdef').decode(),'width':2,'height':1,'channels':3}
        with self.assertRaisesRegex(ValueError, 'Image exceeds limit'):
            self.client(stream(data), max_image_bytes=4).generate({'prompt':'x'})
    def test_manual_validation_required(self):
        with self.assertRaises(ValueError): LocalDreamClient(capabilities={}).generate({'prompt':'x'})
    def test_unsupported_fields(self):
        with self.assertRaises(ValueError): self.client(Response(b'')).generate({'prompt':'x','lora':'invented'})

    def test_httpresponse_trickle_respects_deadline(self):
        import http.client
        import io
        from unittest.mock import patch
        clock = [0.0]
        class Socket:
            def __init__(self): self.timeouts=[]
            def settimeout(self, timeout): self.timeouts.append(timeout)
            def makefile(self, mode):
                return io.BufferedReader(Raw(self))
        class Raw(io.RawIOBase):
            def __init__(self, sock):
                self._sock=sock
                self.header=b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\n'
                self.left=70000
            def readable(self): return True
            def readinto(self, target):
                if self.header:
                    part=self.header[:len(target)]; self.header=self.header[len(part):]
                    target[:len(part)]=part
                    return len(part)
                if not self.left: return 0
                clock[0]+=0.1
                self.left-=1
                target[0]=ord(':')
                return 1
        sock=Socket()
        response=http.client.HTTPResponse(sock)
        response.begin()
        with patch('spicecore.localdream.time.monotonic', side_effect=lambda: clock[0]):
            with self.assertRaises(TimeoutError):
                self.client(response, timeout=1).generate({'prompt':'x'})
        self.assertLessEqual(clock[0],1.2)
        self.assertTrue(sock.timeouts)
        self.assertTrue(all(0 < value <= 1 for value in sock.timeouts))

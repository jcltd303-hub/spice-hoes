import base64,tempfile,threading,unittest
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from spicecore.localdream import generate
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        pixels=bytes([255,0,0]*4); image=base64.b64encode(pixels).decode()
        self.wfile.write(b'data: {"type":"progress","step":1,"total_steps":1}\n\n')
        self.wfile.write(('data: {"type":"complete","generation_time_ms":12,"image":"'+image+'","height":2,"width":2,"channels":3}\n\n').encode()); self.wfile.write(b"data: [DONE]\n\n")
    def log_message(self,*args): pass
class LocalDreamTests(unittest.TestCase):
    def test_sse_image_is_written_as_png(self):
        server=HTTPServer(("127.0.0.1",0),H); t=threading.Thread(target=server.serve_forever,daemon=True); t.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                out=Path(d)/"asset.png"; meta=generate("test",out,size=2,steps=1,server_url=f"http://127.0.0.1:{server.server_port}")
                self.assertEqual(out.read_bytes()[:8],b"\\x89PNG\\r\\n\\x1a\\n"); self.assertEqual(meta["provider"],"local-dream"); self.assertEqual(meta["generation_time_ms"],12)
        finally: server.shutdown(); server.server_close()
if __name__=="__main__": unittest.main()

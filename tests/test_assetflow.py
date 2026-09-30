import base64,json,tempfile,threading,unittest
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from spicecore.assetflow import produce_job
from spicecore.autonomy import plan_next_batch
from spicecore.core import Store,load_personas
ROOT=Path(__file__).resolve().parents[1]
class H(BaseHTTPRequestHandler):
 def do_POST(self):
  self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers(); img=base64.b64encode(bytes([1,2,3]*4)).decode(); self.wfile.write((f'data: {{"type":"complete","image":"{img}","width":2,"height":2,"channels":3,"generation_time_ms":9}}\n\ndata: [DONE]\n\n').encode())
 def log_message(self,*args):pass
class AssetFlowTests(unittest.TestCase):
 def test_plan_generate_propose_stops_at_review(self):
  people=load_personas(ROOT/'personas'); server=HTTPServer(('127.0.0.1',0),H); threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with tempfile.TemporaryDirectory() as d:
    store=Store(Path(d)/'x.sqlite')
    try:
     plan=plan_next_batch(store,people,'city-night','TikTok',Path(d)/'jobs',7,knowledge_paths=[ROOT/'project.md',ROOT/'personas'])
     out=produce_job(store,people,plan['job'],Path(d)/'assets',f'http://127.0.0.1:{server.server_port}',2,1,1.0,candidate_count=3)
     self.assertEqual(out['status'],'awaiting_review'); self.assertEqual(len(out['assets']),3)
     self.assertTrue(all(Path(x['asset_uri']).exists() for x in out['assets']))
     self.assertEqual(len(out['candidate_ids']),3); self.assertTrue(all(store.candidate(x)['status']=='proposed' for x in out['candidate_ids']))
     saved=json.loads(Path(plan['job']).read_text()); self.assertEqual(saved['candidate_ids'],out['candidate_ids']); self.assertEqual(saved['generation_seed'],7)
     again=produce_job(store,people,plan['job'],Path(d)/'assets',f'http://127.0.0.1:{server.server_port}',2,1,1.0); self.assertTrue(again['resumed']); self.assertEqual(again['candidate_ids'],out['candidate_ids'])
     kinds=[e['kind'] for e in store.events()]; self.assertIn('asset_generated',kinds); self.assertIn('candidate_proposed',kinds)
    finally:store.close()
  finally:server.shutdown(); server.server_close()
if __name__=='__main__':unittest.main()

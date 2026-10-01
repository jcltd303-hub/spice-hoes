import tempfile,unittest
from pathlib import Path
from spicecore.core import Store,load_personas
from spicecore.identityref import select_identity
ROOT=Path(__file__).resolve().parents[1]
class IdentityReferenceTests(unittest.TestCase):
 def test_selected_candidate_is_persisted_by_hash(self):
  people=load_personas(ROOT/"personas"); p=next(x for x in people if x["id"]=="celeste_vale")
  with tempfile.TemporaryDirectory() as d:
   d=Path(d); asset=d/"face.png"; asset.write_bytes(bytes.fromhex("89504e470d0a1a0a")+"face".encode())
   store=Store(d/"x.sqlite")
   try:
    cid=store.propose(p,"identity-lock-v1","reference-portrait","internal-review","audience-test",str(asset),"prompt","local-dream:cyberrealistic-v10","42",0)
    out=select_identity(store,p["id"],cid,d/"refs")
    self.assertTrue(Path(out["reference_asset"]).exists()); self.assertTrue(Path(out["manifest"]).exists())
    self.assertEqual(store.candidate(cid)["status"],"approved")
    self.assertIn("identity_reference_selected",[e["kind"] for e in store.events()])
   finally: store.close()
if __name__=="__main__": unittest.main()

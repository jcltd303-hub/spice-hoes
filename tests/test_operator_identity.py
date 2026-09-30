import tempfile, unittest
from pathlib import Path
from spicecore.actions import ActionGate
from spicecore.core import Store, load_personas
from spicecore.identity_checks import IdentityCheck
from spicecore.operator import OperatorService
ROOT=Path(__file__).resolve().parents[1]
class OperatorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'s.db'); self.gate=ActionGate(str(Path(self.tmp.name)/'a.db')); self.identity=IdentityCheck(Path(self.tmp.name)/'i.db'); self.p=load_personas(ROOT/'personas')[0]
 def tearDown(self): self.store.close(); self.tmp.cleanup()
 def reviews(self,score=9,drift=None):
  selections=[True]*score+[False]*(10-score)
  self.identity.record(self.p['id'],'ref1','r1',selections,drift or [])
  self.identity.record(self.p['id'],'ref1','r2',selections,drift or [])
 def test_threshold_and_recurring_drift(self):
  self.reviews(8); self.assertFalse(self.identity.approved(self.p['id'],'ref1'))
  self.identity.record(self.p['id'],'ref2','r1',[True]*9+[False],['eyes']); self.identity.record(self.p['id'],'ref2','r2',[True]*9+[False],['eyes']); self.assertFalse(self.identity.approved(self.p['id'],'ref2'))
  self.identity.record(self.p['id'],'ref3','r1',[True]*9+[False],[]); self.identity.record(self.p['id'],'ref3','r2',[True]*10,[]); self.assertTrue(self.identity.approved(self.p['id'],'ref3'))
 def test_auth_and_identity_gate(self):
  cid=self.store.propose(self.p,'x','still','test','none'); svc=OperatorService(self.store,self.gate,self.identity,reviewer_check=lambda r:r=='owner')
  with self.assertRaises(PermissionError): svc.decide(cid,'intruder','approved',asset_hash='a'*64,reference_version='ref1')
  self.reviews()
  svc.decide(cid,'owner','approved',asset_hash='a'*64,reference_version='ref1'); self.assertEqual(self.store.candidate(cid)['status'],'approved')
 def test_replaced_artifact_not_implicitly_approved(self):
  self.reviews(); cid=self.store.propose(self.p,'x','still','test','none'); OperatorService(self.store,self.gate,self.identity,reviewer_check=lambda r:True).decide(cid,'owner','approved',asset_hash='a'*64,reference_version='ref1')
  self.gate.configure('acct','publish',version='ref1',daily_quota=2)
  ok=self.gate.authorize({'key':'one','account':'acct','action':'publish','policy_version':'ref1','asset_hash':'a'*64}); bad=self.gate.authorize({'key':'two','account':'acct','action':'publish','policy_version':'ref1','asset_hash':'b'*64})
  self.assertTrue(ok['authorized']); self.assertFalse(bad['authorized'])
if __name__=='__main__': unittest.main()

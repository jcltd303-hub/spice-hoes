import tempfile,unittest
from pathlib import Path
from spicecore.content import ContentService
from spicecore.core import load_personas
from spicecore.modeling import ModelingPipeline
ROOT=Path(__file__).resolve().parents[1]
class ContentModelingTests(unittest.TestCase):
 def test_content_disclosure_and_cap(self):
  people=load_personas(ROOT/'personas'); s=ContentService(people,batch_cap=3); items=s.prepare(people[0]['id'],['style','routine','story'],3)
  self.assertTrue(all(x['disclosure'] and x['owner_review_required'] and not x['published'] for x in items))
  with self.assertRaises(ValueError): s.prepare(people[0]['id'],['a','b','c'],4)
 def test_unverified_reward_claim_cannot_approve(self):
  p=load_personas(ROOT/'personas'); s=ContentService(p); item=s.prepare(p[0]['id'],['a','b','c'],1)[0]; item['reward_claim']='guaranteed bonus'
  with self.assertRaises(ValueError): s.approve(item,'owner')
 def test_modeling_evidence_and_physical_attendance(self):
  with tempfile.TemporaryDirectory() as d:
   m=ModelingPipeline(Path(d)/'m.db'); lead=m.create({})
   with self.assertRaises(ValueError): m.transition(lead['lead_id'],'qualified',{})
   m.transition(lead['lead_id'],'qualified',{'synthetic_model_accepted':True,'rights_confirmed':True})
   m.transition(lead['lead_id'],'drafted',{})
   m.transition(lead['lead_id'],'owner-approved',{'owner_approved':True})
   m.transition(lead['lead_id'],'sent',{'outreach_destination':'brand@example.invalid'})
   m.transition(lead['lead_id'],'negotiating',{})
   with self.assertRaises(ValueError): m.transition(lead['lead_id'],'contracted',{'physical_attendance_promised':True})
   contract={'deliverables':['2 images'],'territories':['US'],'term':'30d','exclusivity':'none','revisions':1,'deposit_cents':5000,'balance_cents':5000,'owner_approved_contract':True}
   r=m.transition(lead['lead_id'],'contracted',contract); self.assertEqual(r['state'],'contracted')
if __name__=='__main__': unittest.main()

import tempfile, unittest
from pathlib import Path
from spicecore.commerce import CommerceLedger
from spicecore.experiments import ExperimentPolicy
class CommerceTests(unittest.TestCase):
 def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.l=CommerceLedger(Path(self.tmp.name)/'c.db')
 def tearDown(self): self.tmp.cleanup()
 def add(self,id,kind,amount,currency='USD',customer=None,when='2026-01-01T00:00:00+00:00',cohort=None):
  return self.l.import_event({'external_id':id,'kind':kind,'amount_cents':amount,'currency':currency,'customer':customer,'occurred_at':when,'cohort_at':cohort})
 def test_duplicate_profit_and_payout(self):
  a=self.add('sale','sale',2500); b=self.add('sale','sale',2500); self.assertEqual(a['id'],b['id']); self.add('fee','fee',500); self.add('cost','distribution_cost',500); self.add('pay','payout',1500); r=self.l.contribution_report()[0]; self.assertEqual((r['gross_cents'],r['contribution_cents'],r['payout_cents']),(2500,1500,1500))
 def test_currency_separate(self):
  self.add('u','sale',100,'USD'); self.add('e','sale',200,'EUR'); self.assertEqual([r['currency'] for r in self.l.contribution_report()],['EUR','USD'])
 def test_retention_immature_is_unknown(self):
  self.add('s1','sale',100,customer='anon1',when='2026-09-20T00:00:00+00:00',cohort='2026-09-20T00:00:00+00:00'); r=self.l.cohort_report('2026-09-30T00:00:00+00:00')[0]; self.assertFalse(r['mature_30d']); self.assertIsNone(r['retention_rate'])
 def test_policy_excludes_open_windows(self):
  p=ExperimentPolicy(); r=p.recommend([{'id':'clickbait','currency':'USD','window_closed':False,'contribution_cents':99999,'trials':2},{'id':'closed','currency':'USD','window_closed':True,'contribution_cents':100,'trials':3}],seed=1,exploration=0); self.assertEqual(r['selected_arm'],'closed')
if __name__=='__main__': unittest.main()

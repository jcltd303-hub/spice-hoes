import json
import tempfile
import unittest
from pathlib import Path
from spicecore.autonomy import plan_next_batch
from spicecore.core import Store,load_personas
ROOT=Path(__file__).resolve().parents[1]
class AutonomyTests(unittest.TestCase):
    def test_next_batch_is_logged_and_materialized(self):
        people=load_personas(ROOT/'personas')
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.sqlite')
            try:
                out=plan_next_batch(store,people,'city-night','TikTok',Path(d)/'jobs',seed=7,knowledge_paths=[ROOT/'project.md',ROOT/'personas'])
                self.assertTrue(Path(out['job']).exists())
                saved=json.loads(Path(out['job']).read_text())
                self.assertEqual(saved['status'],'awaiting_generation')
                self.assertEqual(saved['persona_id'],out['allocation']['persona_id'])
                self.assertTrue(all(t['cost_cents']==0 for t in saved['production']))
                events=store.events(); self.assertEqual(events[-1]['kind'],'batch_planned')
                self.assertEqual(events[-1]['payload']['policy_version'],'epsilon-greedy-v1')
            finally: store.close()
if __name__=='__main__': unittest.main()

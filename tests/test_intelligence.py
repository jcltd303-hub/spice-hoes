import json
import tempfile
import unittest
from pathlib import Path
from spicecore.core import Store, load_personas
from spicecore.workflow import build_briefs
from spicecore.rag import LocalRAG
from spicecore.moa import deliberate
from spicecore.orchestration import n8n_workflow, write_n8n
ROOT=Path(__file__).resolve().parents[1]
class IntelligenceTests(unittest.TestCase):
    def test_rag_retrieves_persona_context(self):
        rag=LocalRAG.from_paths([ROOT/'project.md',ROOT/'personas'])
        hits=rag.search('Celeste Vale architecture curated portraits',3)
        self.assertTrue(hits); self.assertTrue(any('celeste' in h['text'].lower() for h in hits))
    def test_moa_has_four_lenses_and_policy(self):
        people=load_personas(ROOT/'personas'); p=people[0]
        brief=next(b for b in build_briefs(people,'city-night','TikTok',1) if b['persona_id']==p['id'])
        stats=[{'persona_id':x['id'],'name':x['name'],'published':0,'net_cents':0} for x in people]
        out=deliberate(p,brief,stats,[],1)
        self.assertEqual({a['agent'] for a in out['agents']},{'revenue','creative','distribution','risk'})
        self.assertIn('allocation_policy',out['synthesis'])
    def test_n8n_export_is_importable_shape(self):
        flow=n8n_workflow(); self.assertEqual(flow['active'],False); self.assertGreaterEqual(len(flow['nodes']),4)
        with tempfile.TemporaryDirectory() as d:
            p=write_n8n(Path(d)/'flow.json'); self.assertEqual(json.loads(p.read_text())['name'],flow['name'])
if __name__=='__main__': unittest.main()

import tempfile
import unittest
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from spicecore.core import Store, load_personas
from spicecore.workflow import build_briefs, render_dashboard, apply_review
from spicecore.web import make_handler
from spicecore.production import FREE_TOOLS, free_production_plan, write_job


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'ledger.sqlite')
        self.people = load_personas(ROOT / 'personas')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_briefs_cover_five_distinct_adults_without_claiming_observed_demand(self):
        briefs = build_briefs(self.people, 'outfit-choice', 'Instagram', seed=4)
        self.assertEqual(len(briefs), 5)
        self.assertEqual({b['persona_id'] for b in briefs}, {p['id'] for p in self.people})
        self.assertTrue(all(b['prompt'].startswith('Original fictional AI-generated adult') for b in briefs))
        self.assertTrue(all(b['evidence_level'] == 'hypothesis' for b in briefs))
        self.assertTrue(all(b['reference_version'] for b in briefs))

    def test_dashboard_escapes_untrusted_prompts_and_shows_review_queue(self):
        p = self.people[0]
        cid = self.store.propose(p, 'night', 'still', 'Instagram', 'portrait',
                                 prompt='<script>alert(1)</script>')
        page = render_dashboard(self.store, self.people, csrf_token='test-token')
        self.assertIn(cid, page)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('test-token', page)

    def test_review_action_requires_matching_token(self):
        p = self.people[0]
        cid = self.store.propose(p, 'night', 'still', 'Instagram', 'portrait')
        with self.assertRaises(PermissionError):
            apply_review(self.store, cid, 'approved', 'operator', '', 'wrong', 'right')
        self.assertEqual(self.store.candidate(cid)['status'], 'proposed')
        apply_review(self.store, cid, 'approved', 'operator', '', 'right', 'right')
        self.assertEqual(self.store.candidate(cid)['status'], 'approved')

    def test_local_http_review_rejects_missing_token_and_records_decision(self):
        cid = self.store.propose(self.people[0], 'night', 'still', 'Instagram', 'portrait')
        server = HTTPServer(('127.0.0.1', 0), make_handler(self.store, self.people, 'secret'))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(base + '/')
            self.assertEqual(denied.exception.code, 403)
            page = urllib.request.urlopen(base + '/?token=secret').read().decode()
            self.assertIn(cid, page)
            body = urllib.parse.urlencode({'candidate_id': cid, 'decision': 'approved',
                                           'reviewer': 'owner', 'note': 'ok', 'token': 'secret'}).encode()
            urllib.request.urlopen(urllib.request.Request(base + '/review', body))
            self.assertEqual(self.store.candidate(cid)['status'], 'approved')
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_cli_outputs_five_creative_briefs(self):
        run = subprocess.run([sys.executable, '-m', 'spicecore.cli', '--personas',
                              str(ROOT / 'personas'), '--db', str(Path(self.tmp.name) / 'cli.sqlite'),
                              'briefs', '--theme', 'outfit-choice', '--channel', 'Instagram', '--seed', '5'],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(json.loads(run.stdout)), 5)

    def test_free_plan_uses_guide_zero_cost_stack(self):
        brief = build_briefs(self.people, 'outfit-choice', 'Instagram', seed=4)[0]
        plan = free_production_plan(brief)
        self.assertEqual([step['cost_cents'] for step in plan], [0] * len(plan))
        tools = {step['tool'] for step in plan}
        self.assertIn(FREE_TOOLS['image'], tools)
        self.assertIn(FREE_TOOLS['motion'], tools)
        self.assertIn(FREE_TOOLS['assembly'], tools)
        self.assertIn(FREE_TOOLS['orchestrator'], tools)

    def test_avatar_plan_can_use_pavo(self):
        brief = build_briefs(self.people, 'talking-head', 'TikTok', seed=2)[0]
        plan = free_production_plan(brief, use_avatar=True)
        self.assertIn(FREE_TOOLS['avatar'], {step['tool'] for step in plan})

    def test_job_manifest_is_machine_readable(self):
        brief = build_briefs(self.people, 'city-night', 'TikTok', seed=1)[0]
        path = write_job(brief, Path(self.tmp.name) / 'job.json')
        payload = json.loads(path.read_text())
        self.assertEqual(payload['brief']['persona_id'], brief['persona_id'])
        self.assertTrue(payload['production'])


if __name__ == '__main__':
    unittest.main()

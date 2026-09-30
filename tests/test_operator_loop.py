import asyncio
import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store, load_personas
from spicecore.operator_loop import action_request_for_candidate, plan_cycle

ROOT = Path(__file__).resolve().parents[1]


class FakeKnowledge:
    def search(self, query, scope, limit):
        return [{'chunk_id': 'persona-1', 'text': 'approved persona facts', 'persona_id': scope['persona']}]


class FakeBudget:
    def reserve(self, run_id, maximum_cents):
        return 'reservation-1'
    def settle(self, reservation_id, actual_cents):
        self.actual = actual_cents


class FakeClient:
    async def complete(self, role, messages, limits):
        evidence = ['persona-1']
        if role in ('commerce', 'persona'):
            output = {'evidence_ids': evidence, 'rationale': 'Grounded proposal',
                      'proposal': role}
        elif role.endswith('_critic'):
            output = {'evidence_ids': evidence, 'rationale': 'Grounded critique',
                      'critique': role}
        else:
            output = {
                'evidence_ids': evidence, 'rationale': 'Grounded choice',
                'chosen_proposal': 'commerce', 'alternatives': ['persona'],
                'disagreement': 'Minor voice tradeoff',
                'action_request': {'type': 'publish'},
                'expected_cost_cents': 2,
                'confidence_qualifier': 'Hypothesis pending observed outcomes',
            }
        return {'output': output, 'actual_cents': 1, 'deployment_id': 'fake',
                'usage': {'input_tokens': 1, 'output_tokens': 1}}


class OperatorLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'ledger.sqlite')
        self.people = load_personas(ROOT / 'personas')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_cycle_uses_feedback_and_stops_at_review(self):
        result = asyncio.run(plan_cycle(
            self.store, self.people, FakeKnowledge(), FakeClient(), FakeBudget(),
            objective='test premium portrait interest', channel='TikTok',
            offer='profile visit', audit_db=Path(self.tmp.name) / 'audit.sqlite',
            knowledge_scope={'tenant': 'owner', 'owner': 'owner'}, seed=4,
        ))
        self.assertEqual(result['status'], 'review_required')
        self.assertFalse(result['execute'])
        self.assertEqual(self.store.candidate(result['candidate_id'])['status'], 'proposed')
        events = self.store.events()
        self.assertEqual(events[-1]['kind'], 'cycle_planned')
        self.assertEqual(events[-1]['payload']['candidate_id'], result['candidate_id'])

    def test_action_request_requires_owner_review(self):
        p = self.people[0]
        cid = self.store.propose(p, 'test', 'still', 'TikTok', 'profile visit')
        with self.assertRaises(ValueError):
            action_request_for_candidate(self.store, cid, account='acct', action='publish',
                                         policy_version='v1')
        self.store.review(cid, 'approved', 'owner')
        req = action_request_for_candidate(self.store, cid, account='acct', action='publish',
                                           policy_version='v1', asset_hash='a' * 64)
        self.assertEqual(req['candidate_id'], cid)
        self.assertEqual(req['asset_hash'], 'a' * 64)
        self.assertNotIn('execute', req)


if __name__ == '__main__':
    unittest.main()

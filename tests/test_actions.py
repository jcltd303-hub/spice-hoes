import tempfile
import unittest
from spicecore.actions import ActionGate


class ActionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gate = ActionGate(self.tmp.name + '/actions.db')
        self.gate.configure('account', 'publish', version='v1', daily_quota=1)
        self.request = dict(account='account', action='publish', policy_version='v1', key='a', asset_hash='a' * 64)
    def tearDown(self):
        self.tmp.cleanup()
    def test_stop(self):
        self.gate.approve_asset('a' * 64, 'v1')
        self.gate.set_controls(emergency_stop=True)
        self.assertFalse(self.gate.authorize(self.request)['authorized'])
    def test_unapproved_asset(self):
        self.assertFalse(self.gate.authorize(self.request)['authorized'])
    def test_agent_permissions(self):
        self.request['allowed_actions'] = ['publish']
        self.request['account'] = 'unknown'
        self.assertFalse(self.gate.authorize(self.request)['authorized'])
    def test_dry_run_quota_and_replay(self):
        self.gate.approve_asset('a' * 64, 'v1')
        receipt = self.gate.authorize(self.request)
        self.assertTrue(receipt['authorized'])
        self.assertTrue(receipt['dry_run'])
        self.assertFalse(receipt['execute'])
        self.assertEqual(receipt, self.gate.authorize(self.request))
        self.assertFalse(self.gate.authorize(dict(self.request, key='b'))['authorized'])
        with self.assertRaises(ValueError):
            self.gate.authorize(dict(self.request, asset_hash='b' * 64))
    def test_stop_blocks_receipt_replay(self):
        self.gate.approve_asset('a' * 64, 'v1')
        self.assertTrue(self.gate.authorize(self.request)['authorized'])
        self.gate.set_controls(emergency_stop=True)
        self.assertFalse(ActionGate(self.gate.path).authorize(self.request)['authorized'])
    def test_stale_version_and_live_prerequisites(self):
        self.gate.approve_asset('a' * 64, 'v1')
        self.assertFalse(self.gate.authorize(dict(self.request, policy_version='v2'))['authorized'])
        with self.assertRaises(ValueError):
            self.gate.configure('account', 'publish', version='v1', daily_quota=1, live=True)
    def live_setup(self):
        from spicecore.budget import BudgetLedger
        self.gate.runtime_config = {'dry_run': False, 'credit': {'eligible': True, 'evidence': 'owner verification', 'expires_at': '2099-01-01T00:00:00+00:00'}, 'daily_cap_cents': 10, 'region': 'eastus', 'approved_regions': ['eastus']}
        self.gate.ledger = BudgetLedger(self.tmp.name + '/budget.db', 10)
        self.request.update(run_id='run', reservation_id=self.gate.ledger.reserve('run', 5), maximum_action_cents=5)
        verified = dict.fromkeys(('authentication', 'ownership', 'platform_permission', 'end_to_end_test', 'owner_authorization'), True)
        self.gate.configure('account', 'publish', version='v1', daily_quota=1, live=True, verified=verified)
        self.gate.approve_asset('a' * 64, 'v1')
    def test_mode_change_applies_to_receipt_replay(self):
        self.live_setup()
        self.assertFalse(self.gate.authorize(self.request)['dry_run'])
        self.gate.configure('account', 'publish', version='v1', daily_quota=1)
        self.assertTrue(self.gate.authorize(self.request)['dry_run'])
    def test_live_preflight_fails_closed_and_rechecks_replay(self):
        self.live_setup()
        self.assertTrue(self.gate.authorize(self.request)['authorized'])
        self.gate.runtime_config['credit']['eligible'] = False
        self.assertFalse(self.gate.authorize(self.request)['authorized'])
        self.gate.runtime_config['credit']['eligible'] = True
        self.gate.ledger.settle(self.request['reservation_id'], 0)
        self.assertFalse(self.gate.authorize(self.request)['authorized'])
    def test_live_requires_runtime_and_budget(self):
        self.live_setup()
        self.gate.ledger = None
        self.assertFalse(self.gate.authorize(self.request)['authorized'])
    def test_live_unapproved_region_and_expired_credit(self):
        self.live_setup()
        self.gate.runtime_config['approved_regions'] = []
        self.assertFalse(self.gate.authorize(self.request)['authorized'])
        self.gate.runtime_config['approved_regions'] = ['eastus']
        self.gate.runtime_config['credit']['expires_at'] = '2000-01-01T00:00:00+00:00'
        self.assertFalse(self.gate.authorize(self.request)['authorized'])
    def test_each_live_prerequisite_required(self):
        verified = dict.fromkeys(('authentication', 'ownership', 'platform_permission', 'end_to_end_test', 'owner_authorization'), True)
        for missing in verified:
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                self.gate.configure('account', 'publish', version='v1', daily_quota=1, live=True, verified=dict(verified, **{missing: False}))

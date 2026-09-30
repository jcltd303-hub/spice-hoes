"""Offline behavioral contracts; no Azure resources are created."""
import copy
import datetime as dt
import unittest
from spicecore.azure_backend import AzureBudgetLedger, AzureJobStore, Conflict, preflight
from spicecore.control_plane import CloudJobAPI

class MemoryState:
    def __init__(self):
        self.value, self.version, self.conflict = {}, 0, None
    def read(self):
        return copy.deepcopy(self.value), self.version
    def replace(self, value, version):
        if self.conflict:
            action, self.conflict = self.conflict, None
            action()
        if version != self.version:
            raise Conflict()
        self.value, self.version = copy.deepcopy(value), self.version + 1

class Assets:
    def signed_upload(self, job):
        return {'blob': 'jobs/' + job + '/image', 'expires_in': 600}
    def verify(self, job, digest):
        return {'job_id': job, 'artifact_hash': digest}

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.state = MemoryState()
        self.now = 1000
        self.jobs = AzureJobStore(self.state, clock=lambda: self.now)
        self.api = CloudJobAPI(self.jobs, Assets(), {'phone-sub': {'worker_id':'worker','device_id':'phone'}}, {'operator-sub'})
        self.job = self.jobs.enqueue('image', {'device_id':'phone','settings':{}}, 'key')
        self.identity = {'subject':'phone-sub'}
    def call(self, op, body, identity=None):
        return self.api.handle(op, body, identity)
    def claim(self):
        code, job = self.call('claim', {'device_id':'phone','worker_id':'worker'}, self.identity)
        self.assertEqual(code, 200)
        return job
    def test_unauthenticated(self):
        self.assertEqual(self.call('claim', {'device_id':'phone'})[0],401)
        self.assertEqual(self.state.value['jobs'][self.job]['status'],'queued')
    def test_wrong_worker(self):
        self.assertEqual(self.call('claim', {'device_id':'phone','worker_id':'other'}, self.identity)[0],403)
    def test_cross_device_completion_and_expiry(self):
        job = self.claim()
        body = {'job_id':self.job,'lease_token':job['lease_token'],'result':{'artifact_hash':'a'*64}}
        self.assertEqual(self.call('complete',body,{'subject':'unknown'})[0],403)
        self.now += 121
        self.assertEqual(self.call('complete',body,self.identity)[0],409)
    def test_single_device_lease(self):
        self.jobs.enqueue('image', {'device_id':'phone','settings':{'seed':2}}, 'second')
        self.claim()
        self.assertIsNone(self.claim())
    def test_etag_conflict_claim(self):
        winner=[]
        self.state.conflict=lambda: winner.append(self.jobs.claim('worker', device_id='phone'))
        self.assertIsNone(self.jobs.claim('worker',device_id='phone'))
        self.assertEqual(winner[0]['id'],self.job)
        self.assertEqual(self.state.value['jobs'][self.job]['claims'],1)
    def test_historical_checkpoint_prevents_regeneration(self):
        job=self.claim()
        self.now += 121
        code, result=self.call('reconcile',{'job_id':self.job,'lease_token':job['lease_token'],'result':{'artifact_hash':'a'*64}},self.identity)
        self.assertEqual((code,result['status']),(200,'reconciliation_pending'))
        self.assertIsNone(self.jobs.claim('worker',device_id='phone'))
    def test_completion_idempotency(self):
        job=self.claim()
        body={'job_id':self.job,'lease_token':job['lease_token'],'result':{'artifact_hash':'a'*64}}
        self.assertTrue(self.call('complete',body,self.identity)[1]['deliver'])
        self.assertFalse(self.call('complete',body,self.identity)[1]['deliver'])
    def test_claims_bounded(self):
        for _ in range(3):
            self.assertIsNotNone(self.jobs.claim('worker',device_id='phone'))
            self.now += 121
        self.assertIsNone(self.jobs.claim('worker',device_id='phone'))
        self.assertEqual(self.state.value['jobs'][self.job]['status'],'deadletter')

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.state=MemoryState()
        self.ledger=AzureBudgetLedger(self.state,100)
    def test_etag_conflict_cannot_overspend(self):
        self.state.conflict=lambda: self.ledger.reserve('winner',70)
        with self.assertRaises(ValueError):
            self.ledger.reserve('loser',70)
        self.assertEqual(self.ledger.committed_cents(),70)
    def test_stricter_cap_and_attempt_consumption(self):
        token=self.ledger.reserve('run',90)
        with self.assertRaises(ValueError):
            self.ledger.validate_reservation(token,'run',10,consume=True,owner_cap_cents=80)
        self.ledger.validate_reservation(token,'run',60,consume=True)
        with self.assertRaises(ValueError):
            self.ledger.validate_reservation(token,'run',40,consume=True)
        with self.assertRaises(ValueError):
            self.ledger.validate_reservation(token,'other',1)
    def test_overrun_durable_and_settlement_full_cost(self):
        token=self.ledger.reserve('run',50)
        self.ledger.record_overrun(token,'run',120)
        self.assertEqual(self.ledger.committed_cents(),120)
        with self.assertRaises(ValueError):
            self.ledger.reserve('next',1)
        self.ledger.settle(token,120)
        self.assertEqual(self.ledger.committed_cents(),120)
        with self.assertRaises(ValueError):
            self.ledger.settle(token,50)
    def test_negative_attempt_rejected(self):
        token=self.ledger.reserve('run',50)
        with self.assertRaises(ValueError):
            self.ledger.validate_reservation(token,'run',-10,consume=True)

class ProvisionTests(unittest.TestCase):
    def evidence(self):
        return {'subscription_id':'subscription','credit':{'eligible':True,'evidence':'receipt','expires_at':'2099-01-01T00:00:00+00:00','eligible_services':['Functions','Storage','KeyVault']},'region':'uksouth','approved_regions':['uksouth'],'capacity':{'verified':True,'evidence':'capacity-receipt','region':'uksouth'},'daily_cap_cents':100,'dry_run':False}
    def test_expired_credit_preflight(self):
        config=self.evidence()
        config['credit']['expires_at']='2000-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):
            preflight(config)
    def test_missing_capacity_service_and_owner_cap(self):
        for key in ('capacity','daily_cap_cents','subscription_id'):
            config=self.evidence()
            del config[key]
            with self.assertRaises(ValueError):
                preflight(config)
        config=self.evidence()
        config['credit']['eligible_services']=[]
        with self.assertRaises(ValueError):
            preflight(config)
    def test_verified_evidence(self):
        self.assertEqual(preflight(self.evidence())['status'],'eligible')

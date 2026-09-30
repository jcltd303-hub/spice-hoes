import tempfile
import unittest
from pathlib import Path
from spicecore.phone_worker import PhoneWorker

STATE = dict(online=True, battery=80, charging=False, thermal_severity=0)
class Cloud:
    authenticated = True
    def __init__(self): self.claims=0; self.fail=True; self.reconciled=[]; self.uploads=0
    def claim(self, worker_id, now, *, device_id):
        self.claims+=1
        return dict(id='job', kind='image', device_id=device_id, worker_id=worker_id, lease_token='token', payload={'settings':{'prompt':'x'}})
    def renew(self, *args): pass
    def upload(self, job, image, result): self.uploads+=1; return {'private_url':'scoped'}
    def complete(self, *args):
        if self.fail: raise ValueError('lease lost')
        return {'status':'completed'}
    def reconcile_artifact(self, *args): self.reconciled.append(args); return {'status':'reconciled'}
class Generator:
    def __init__(self): self.calls=0
    def generate(self, settings):
        self.calls+=1
        return {'image':b'\x89PNG\r\n\x1a\nfixture', 'seed':1, 'model':'manual', 'source_hash':None, 'latency_ms':1}
class PhoneTests(unittest.TestCase):
    def test_offline(self):
        with tempfile.TemporaryDirectory() as p:
            c=Cloud(); g=Generator(); w=PhoneWorker(c,g,p,worker_id='w',device_id='d')
            for s in ({},dict(STATE,online=False),dict(STATE,battery=24),dict(STATE,thermal_severity=3),dict(STATE,battery=True)):
                self.assertEqual(w.tick(s)['status'],'deferred')
            self.assertEqual((c.claims,g.calls),(0,0))
    def test_lease_loss(self):
        with tempfile.TemporaryDirectory() as p:
            c=Cloud(); g=Generator(); w=PhoneWorker(c,g,p,worker_id='w',device_id='d')
            self.assertEqual(w.tick(STATE)['status'],'reconciliation_pending')
            self.assertTrue(list(Path(p).glob('*.json')))
            w=PhoneWorker(c,g,p,worker_id='w',device_id='d')
            self.assertEqual(w.tick(STATE)['status'],'reconciliation_pending')
            self.assertEqual(g.calls,1)
            self.assertEqual(c.claims,1)
    def test_checkpoint_before_upload(self):
        with tempfile.TemporaryDirectory() as p:
            c=Cloud(); c.fail=False; g=Generator()
            original=c.upload
            def upload(job, image, result):
                self.assertEqual(len(list(Path(p).glob('*.json'))),1)
                self.assertEqual(len(list(Path(p).glob('*.png'))),1)
                return original(job,image,result)
            c.upload=upload
            self.assertEqual(PhoneWorker(c,g,p,worker_id='w',device_id='d').tick(STATE)['status'],'completed')
            self.assertFalse(list(Path(p).glob('*.json')))
    def test_dry_run(self):
        with tempfile.TemporaryDirectory() as p:
            c=Cloud(); g=Generator()
            self.assertEqual(PhoneWorker(c,g,p,worker_id='w',device_id='d',dry_run=True).tick(STATE)['status'],'dry_run')
            self.assertEqual(c.claims,0)

import datetime as dt
import hashlib
import unittest
from spicecore.cloud_storage import AssetStore, PhoneCloudAdapter

class Blob:
    def __init__(self, name, owner):
        self.name,self.owner=name,owner
        self.url='https://account.blob.core.windows.net/assets/'+name
    def upload_blob(self, content, **kwargs):
        if self.name in self.owner.data:
            raise ValueError('immutable')
        self.owner.data[self.name]=content
        return {'etag':'etag','version_id':'version'}
    def download_blob(self):
        return self
    def readall(self):
        return self.owner.data[self.name]
    def get_blob_properties(self):
        return type('Properties',(),{'size':len(self.owner.data[self.name]),'version_id':'version'})()

class Service:
    account_name='account'
    def __init__(self):
        self.data={}
    def get_blob_client(self, container, blob):
        return Blob(blob,self)
    def get_user_delegation_key(self, start, expiry):
        return 'delegation'

class AssetTests(unittest.TestCase):
    def setUp(self):
        self.service=Service()
        self.calls=[]
        def signer(**kwargs):
            self.calls.append(kwargs)
            return 'signature'
        self.assets=AssetStore(self.service,'assets',signer=signer,permission_factory=lambda **kw:kw)
    def test_signed_scope(self):
        signed=self.assets.signed_upload('job1')
        call=self.calls[0]
        self.assertEqual(call['blob_name'],'jobs/job1/image')
        self.assertEqual((call['expiry']-call['start']).total_seconds(),600)
        self.assertEqual(call['permission'],{'create':True})
        self.assertEqual(call['protocol'],'https')
        self.assertNotIn('job2',signed['url'])
        with self.assertRaises(ValueError):
            self.assets.signed_upload('../job2')
    def test_private_hash_verified_and_immutable(self):
        content=b'\x89PNG\r\n\x1a\nbody'
        result=self.assets.put('job1',content)
        self.assertEqual(result['artifact_hash'],hashlib.sha256(content).hexdigest())
        self.assertEqual(self.assets.verify('job1',result['artifact_hash'])['version_id'],'version')
        with self.assertRaises(ValueError):
            self.assets.verify('job1','a'*64)
        with self.assertRaises(ValueError):
            self.assets.put('job1',b'changed')
    def test_adapter_requires_https_and_identity(self):
        for url in ('http://localhost','https://host/path?token=secret'):
            with self.assertRaises(ValueError):
                PhoneCloudAdapter(url,lambda:'token',worker_id='w',device_id='d',blob_host='account.blob.core.windows.net')
        with self.assertRaises(ValueError):
            PhoneCloudAdapter('https://host',None,worker_id='w',device_id='d',blob_host='account.blob.core.windows.net')

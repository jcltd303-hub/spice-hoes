"""Private Azure Blob assets and authenticated outbound phone transport."""
import datetime as dt
import hashlib
import json
import re
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .localdream import MAX_IMAGE_BYTES

class AssetStore:
    def __init__(self, service, container, *, signer=None, permission_factory=None):
        if not container:
            raise ValueError('Private container required')
        if signer is None or permission_factory is None:
            from azure.storage.blob import generate_blob_sas, BlobSasPermissions
            signer, permission_factory = generate_blob_sas, BlobSasPermissions
        self.service,self.container = service,container
        self.signer,self.permission_factory = signer,permission_factory

    @staticmethod
    def blob_name(job_id):
        if not isinstance(job_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',job_id):
            raise ValueError('Unsafe job ID')
        return 'jobs/' + job_id + '/image'

    def _blob(self,job_id):
        return self.service.get_blob_client(container=self.container,blob=self.blob_name(job_id))

    def signed_upload(self,job_id):
        blob=self._blob(job_id)
        start=dt.datetime.now(dt.timezone.utc)
        expiry=start+dt.timedelta(minutes=10)
        key=self.service.get_user_delegation_key(start,expiry)
        token=self.signer(account_name=self.service.account_name,container_name=self.container,
                          blob_name=self.blob_name(job_id),user_delegation_key=key,
                          permission=self.permission_factory(create=True),start=start,expiry=expiry,protocol='https')
        return {'job_id':job_id,'url':blob.url+'?'+token,'expires_at':expiry.isoformat(),'expires_in':600,'blob':self.blob_name(job_id)}

    def put(self,job_id,content):
        self._validate_image(content)
        receipt=self._blob(job_id).upload_blob(content,overwrite=False)
        return {'job_id':job_id,'artifact_hash':hashlib.sha256(content).hexdigest(),'version_id':receipt.get('version_id')}

    @staticmethod
    def _validate_image(content):
        if not isinstance(content,bytes) or not 0<len(content)<=MAX_IMAGE_BYTES or not (content.startswith(b'\x89PNG\r\n\x1a\n') or content.startswith(b'\xff\xd8\xff')):
            raise ValueError('Bounded PNG or JPEG required')

    def verify(self,job_id,digest):
        blob=self._blob(job_id)
        properties=blob.get_blob_properties()
        if not 0<properties.size<=MAX_IMAGE_BYTES:
            raise ValueError('Invalid artifact size')
        # Create-only SAS and immutable server uploads prevent overwrite during read.
        content=blob.download_blob().readall()
        self._validate_image(content)
        if hashlib.sha256(content).hexdigest()!=digest:
            raise ValueError('Private artifact hash mismatch')
        return {'job_id':job_id,'artifact_hash':digest,'version_id':properties.version_id}

    def append_event(self,job_id,event):
        """An immutable event object; retries deduplicate by canonical event hash."""
        from azure.core.exceptions import ResourceExistsError
        self.blob_name(job_id)
        data=json.dumps(event,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        if len(data)>32768:
            raise ValueError('Event exceeds bound')
        digest=hashlib.sha256(data).hexdigest()
        blob=self.service.get_blob_client(container=self.container,blob='events/'+job_id+'/'+digest+'.json')
        try:
            blob.upload_blob(data,overwrite=False)
        except ResourceExistsError:
            pass
        return digest

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('Redirect refused')

class PhoneCloudAdapter:
    authenticated=True
    def __init__(self,base_url,token_provider,*,worker_id,device_id,blob_host,opener=None):
        url=urlsplit(base_url)
        if (url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment
                or not callable(token_provider) or not worker_id or not device_id
                or not re.fullmatch(r'[a-z0-9]+\.blob\.core\.windows\.net',blob_host)):
            raise ValueError('HTTPS service, token provider, paired identity and Azure blob host required')
        self.base_url=base_url.rstrip('/')
        self.token_provider,self.worker_id,self.device_id=token_provider,worker_id,device_id
        self.blob_host=blob_host
        self.opener=opener or build_opener(_NoRedirect())

    def _call(self,operation,body):
        token=self.token_provider()
        if not isinstance(token,str) or not token or '\r' in token or '\n' in token:
            raise ValueError('Authentication token required')
        request=Request(self.base_url+'/'+operation,data=json.dumps(body,allow_nan=False).encode(),
                        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
        with self.opener.open(request,timeout=30) as response:
            content=response.read(1024*1024+1)
        if len(content)>1024*1024:
            raise ValueError('Response exceeds bound')
        return json.loads(content)

    def claim(self,worker_id,now,*,device_id):
        if worker_id!=self.worker_id or device_id!=self.device_id:
            raise ValueError('Paired identity mismatch')
        return self._call('claim',{'worker_id':worker_id,'device_id':device_id})

    def renew(self,job_id,lease_token):
        return self._call('renew',{'job_id':job_id,'lease_token':lease_token})

    def upload(self,job,image,result):
        AssetStore._validate_image(image)
        digest=hashlib.sha256(image).hexdigest()
        if (job.get('worker_id')!=self.worker_id or job.get('device_id')!=self.device_id
                or result.get('artifact_hash')!=digest):
            raise ValueError('Artifact or lease identity mismatch')
        signed=self._call('upload',{'job_id':job['id'],'lease_token':job['lease_token']})
        url=urlsplit(signed['url'])
        expected='/'+signed.get('container','assets')+'/'+AssetStore.blob_name(job['id'])
        if (url.scheme!='https' or url.hostname!=self.blob_host or url.port not in (None,443)
                or url.username or url.password or url.fragment or url.path!=expected
                or parse_qs(url.query).get('sp')!=['c']):
            raise ValueError('Upload URL outside exact job scope')
        request=Request(signed['url'],data=image,method='PUT',headers={'x-ms-blob-type':'BlockBlob','If-None-Match':'*','Content-Type':'application/octet-stream'})
        with self.opener.open(request,timeout=60) as response:
            if response.status!=201:
                raise ValueError('Upload not acknowledged')
        return {'job_id':job['id'],'artifact_hash':digest}

    def complete(self,job_id,lease_token,result):
        return self._call('complete',{'job_id':job_id,'lease_token':lease_token,'result':result})

    def reconcile_artifact(self,job_id,lease_token,result):
        return self._call('reconcile',{'job_id':job_id,'lease_token':lease_token,'result':result})

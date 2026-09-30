"""Transport-neutral authenticated control boundary; never uses SQLite."""
from .azure_backend import Conflict

class CloudJobAPI:
    def __init__(self,jobs,assets,devices,operators):
        self.jobs,self.assets,self.devices,self.operators=jobs,assets,devices,set(operators)

    def handle(self,operation,body,identity=None):
        if not isinstance(identity,dict) or not identity.get('subject'):
            return 401,{'error':'Authentication required'}
        subject=identity['subject']
        if not isinstance(body,dict):
            return 400,{'error':'JSON object required'}
        try:
            if operation in ('enqueue','controls'):
                if subject not in self.operators:
                    return 403,{'error':'Operator identity required'}
                if operation=='controls':
                    self.jobs.set_controls(paused=body.get('paused',False),emergency_stop=body.get('emergency_stop',False))
                    return 200,{'status':'updated'}
                job=self.jobs.enqueue(body['kind'],body['payload'],body['key'])
                return 200,{'job_id':job,'status':'queued'}
            device=self.devices.get(subject)
            if not device:
                return 403,{'error':'Paired device identity required'}
            worker_id,device_id=device['worker_id'],device['device_id']
            if operation=='claim':
                if body.get('worker_id')!=worker_id or body.get('device_id')!=device_id:
                    return 403,{'error':'Paired identity mismatch'}
                return 200,self.jobs.claim(worker_id,device_id=device_id)
            job_id,token=body['job_id'],body['lease_token']
            scope={'worker_id':worker_id,'device_id':device_id}
            if operation=='renew':
                self.jobs.renew(job_id,token,**scope)
                return 200,{'status':'renewed'}
            if operation=='upload':
                self.jobs.authorize(job_id,token,**scope)
                signed=self.assets.signed_upload(job_id)
                signed['container']=getattr(self.assets,'container','assets')
                return 200,signed
            if operation=='complete':
                # Verify authority before reading private data; completion CAS rechecks.
                value=self.jobs.state.read()[0]
                self.jobs._owned(value,job_id,token,worker_id,device_id,historical=True)
                result=body['result']
                self.assets.verify(job_id,result['artifact_hash'])
                receipt=self.jobs.complete(job_id,token,result,**scope)
                if hasattr(self.assets,'append_event'):
                    self.assets.append_event(job_id,{'operation':'complete','receipt':receipt,'artifact_hash':result['artifact_hash']})
                return 200,receipt
            if operation=='reconcile':
                return 200,self.jobs.reconcile_artifact(job_id,token,body['result'],**scope)
            return 404,{'error':'Unknown operation'}
        except PermissionError:
            return 403,{'error':'Worker or device mismatch'}
        except (ValueError,Conflict):
            return 409,{'error':'Lease, artifact or control conflict'}
        except (KeyError,TypeError,AttributeError):
            return 400,{'error':'Invalid request'}

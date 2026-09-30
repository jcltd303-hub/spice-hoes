"""Azure Table ETag transactions for a bounded, single-owner control plane.

One aggregate entity serializes device leases and budgets. Payloads are bounded;
capacity exhaustion fails closed, never silently shards an atomic invariant.
"""
import copy
import datetime as dt
import hashlib
import json
import uuid
from .jobs import canonical

class Conflict(RuntimeError):
    pass

class TableState:
    def __init__(self, client, partition='owner', row='control'):
        self.client, self.partition, self.row = client, partition, row

    def read(self):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            entity = self.client.get_entity(partition_key=self.partition, row_key=self.row)
        except ResourceNotFoundError:
            return {}, None
        return json.loads(entity['state']), entity.metadata['etag']

    def replace(self, value, version):
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceExistsError, ResourceModifiedError
        encoded = canonical(value)
        if len(encoded.encode('utf-16-le')) > 60000:
            raise ValueError('Control aggregate capacity reached; operator archival required')
        entity = {'PartitionKey':self.partition,'RowKey':self.row,'state':encoded}
        try:
            if version is None:
                self.client.create_entity(entity=entity)
            else:
                self.client.update_entity(entity=entity,mode='replace',etag=version,match_condition=MatchConditions.IfNotModified)
        except (ResourceExistsError, ResourceModifiedError) as exc:
            raise Conflict('Concurrent control mutation') from exc

def mutate(state, operation):
    for _ in range(8):
        value, version = state.read()
        result = operation(value)
        try:
            state.replace(value, version)
            return copy.deepcopy(result)
        except Conflict:
            continue
    raise Conflict('Control state busy; retry later')

def _positive(value):
    return type(value) is int and value > 0

def preflight(config):
    """Validate operator evidence before ANY provisioning call; never deploy."""
    now = dt.datetime.now(dt.timezone.utc)
    try:
        credit, capacity = config['credit'], config['capacity']
        expiry = dt.datetime.fromisoformat(credit['expires_at'].replace('Z','+00:00'))
        services = set(credit['eligible_services'])
        valid = (config.get('dry_run',True) is False
                 and isinstance(config['subscription_id'],str) and bool(config['subscription_id'])
                 and credit['eligible'] is True and bool(credit['evidence'])
                 and expiry.tzinfo is not None and expiry > now
                 and {'Functions','Storage','KeyVault'} <= services
                 and config['region'] in config['approved_regions']
                 and capacity['verified'] is True and bool(capacity['evidence'])
                 and capacity['region'] == config['region']
                 and _positive(config['daily_cap_cents']))
    except (KeyError,TypeError,ValueError,AttributeError):
        valid = False
    if not valid:
        raise ValueError('Deployment disabled: verified subscription, credit, services, region, capacity and owner ceiling required')
    return {'status':'eligible','subscription_id':config['subscription_id'],'region':config['region'],'daily_cap_cents':config['daily_cap_cents']}

class AzureBudgetLedger:
    def __init__(self, state, daily_cap_cents, *, clock=None):
        if not _positive(daily_cap_cents):
            raise ValueError('Positive owner ceiling required')
        self.state, self.daily_cap_cents = state, daily_cap_cents
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc).date().isoformat())

    def _committed(self, value):
        return sum(r['actual'] if r['actual'] is not None else max(r['maximum'],r['observed'])
                   for r in value.get('budget',{}).values()
                   if r['day'] == self.clock() or r['actual'] is None)

    def committed_cents(self):
        return self._committed(self.state.read()[0])

    def reserve(self, run_id, maximum_cents):
        if not isinstance(run_id,str) or not run_id or not _positive(maximum_cents):
            raise ValueError('Invalid reservation')
        reservation = uuid.uuid4().hex
        def operation(value):
            if value.get('budget_halt') or self._committed(value) + maximum_cents > self.daily_cap_cents:
                raise ValueError('Daily budget exhausted or halted')
            value.setdefault('budget',{})[reservation] = dict(run_id=run_id,day=self.clock(),maximum=maximum_cents,actual=None,claimed=0,observed=0)
            return reservation
        return mutate(self.state,operation)

    def validate_reservation(self, reservation_id, run_id, minimum_cents, *, consume=False, owner_cap_cents=None):
        if not _positive(minimum_cents) or (owner_cap_cents is not None and not _positive(owner_cap_cents)):
            raise ValueError('Positive attempt and owner ceiling required')
        cap = min(self.daily_cap_cents,owner_cap_cents or self.daily_cap_cents)
        def operation(value):
            row = value.get('budget',{}).get(reservation_id)
            if (not row or row['run_id'] != run_id or row['actual'] is not None
                    or row['maximum'] - row['claimed'] < minimum_cents
                    or value.get('budget_halt') or self._committed(value) > cap):
                raise ValueError('Active sufficient reservation required')
            if consume:
                row['claimed'] += minimum_cents
        mutate(self.state,operation)

    def record_overrun(self, reservation_id, run_id, actual_cents):
        if type(actual_cents) is not int or actual_cents < 0:
            raise ValueError('Invalid observed charge')
        def operation(value):
            row=value.get('budget',{}).get(reservation_id)
            if not row or row['run_id'] != run_id or row['actual'] is not None:
                raise ValueError('Active reservation required')
            row['observed'] += actual_cents
            value['budget_halt'] = 'Observed model bound overrun'
        mutate(self.state,operation)

    def settle(self, reservation_id, actual_cents):
        if type(actual_cents) is not int or actual_cents < 0:
            raise ValueError('Invalid settlement')
        def operation(value):
            row=value.get('budget',{}).get(reservation_id)
            if not row or actual_cents < row['observed'] or (row['actual'] is not None and row['actual'] != actual_cents):
                raise ValueError('Invalid settlement')
            if row['actual'] is not None:
                return
            row['actual'], row['day'] = actual_cents, self.clock()
            if actual_cents > row['maximum']:
                value['budget_halt'] = 'Observed reservation overrun'
        mutate(self.state,operation)

class AzureJobStore:
    lease_seconds = 120
    maximum_claims = 3

    def __init__(self, state, *, clock=None, queue=None):
        self.state, self.queue = state, queue
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc).timestamp())

    def enqueue(self, kind, payload, key):
        if kind != 'image' or not isinstance(payload,dict) or not isinstance(payload.get('device_id'),str) or not payload['device_id'] or not key:
            raise ValueError('Paired image job and idempotency key required')
        digest = hashlib.sha256(canonical([kind,payload]).encode()).hexdigest()
        job_id = uuid.uuid4().hex
        def operation(value):
            jobs=value.setdefault('jobs',{})
            for job in jobs.values():
                if job['key'] == key:
                    if job['hash'] != digest:
                        raise ValueError('Idempotency payload conflict')
                    return job['id']
            jobs[job_id] = dict(id=job_id,key=key,kind=kind,payload=payload,hash=digest,device_id=payload['device_id'],status='queued',claims=0,history={})
            return job_id
        result=mutate(self.state,operation)
        if self.queue is not None:
            # Queue delivery is advisory; polling durable state recovers lost hints.
            try:
                self.queue.send_message(canonical({'job_id':result}))
            except Exception:
                pass
        return result

    def set_controls(self, *, paused=False, emergency_stop=False):
        def operation(value):
            value['controls']={'paused':bool(paused),'stopped':bool(emergency_stop)}
        mutate(self.state,operation)

    def claim(self, worker_id, now=None, *, device_id):
        if not worker_id or not device_id:
            raise ValueError('Paired worker and device required')
        # Caller wall-clock is never authoritative.
        current = self.clock()
        def operation(value):
            if any(value.get('controls',{}).values()):
                return None
            jobs=value.get('jobs',{})
            for job in jobs.values():
                if job['status']=='leased' and job['expires'] <= current and job['claims'] >= self.maximum_claims:
                    job['status']='deadletter'
            if any(j['device_id']==device_id and j['status']=='leased' and j['expires']>current for j in jobs.values()):
                return None
            for job in jobs.values():
                if (job['device_id'] != device_id or job.get('artifact') or job['claims'] >= self.maximum_claims
                        or not (job['status']=='queued' or (job['status']=='leased' and job['expires'] <= current))):
                    continue
                token=uuid.uuid4().hex
                job.update(status='leased',worker_id=worker_id,lease_token=token,expires=current+self.lease_seconds,claims=job['claims']+1)
                job['history'][token]={'worker_id':worker_id,'device_id':device_id}
                return {k:job[k] for k in ('id','kind','payload','device_id','worker_id','lease_token','claims')} | {'lease_expires':job['expires']}
            return None
        return mutate(self.state,operation)

    def _owned(self,value,job_id,token,worker_id,device_id,*,historical=False):
        job=value.get('jobs',{}).get(job_id)
        known=job and job['history'].get(token)
        if not known or known['worker_id']!=worker_id or known['device_id']!=device_id:
            raise PermissionError('Lease belongs to another worker or device')
        if not historical and (job['status']!='leased' or job['lease_token']!=token or job['expires'] <= self.clock()):
            raise ValueError('Active fenced lease required')
        return job

    def authorize(self,job_id,token,*,worker_id,device_id):
        self._owned(self.state.read()[0],job_id,token,worker_id,device_id)

    def renew(self,job_id,lease_token,*,worker_id,device_id):
        def operation(value):
            job=self._owned(value,job_id,lease_token,worker_id,device_id)
            if any(value.get('controls',{}).values()):
                raise ValueError('Operator pause or stop')
            job['expires']=self.clock()+self.lease_seconds
        mutate(self.state,operation)

    @staticmethod
    def _artifact(job,result):
        digest=result.get('artifact_hash')
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('SHA256 artifact hash required')
        if job.get('artifact') and job['artifact'] != digest:
            raise ValueError('Checkpoint hash conflict')
        job['artifact']=digest

    def complete(self,job_id,lease_token,result,*,worker_id,device_id):
        encoded=canonical(result)
        def operation(value):
            job=self._owned(value,job_id,lease_token,worker_id,device_id,historical=True)
            if job['status']=='completed' and job['lease_token']==lease_token and job['result']==encoded:
                return {'job_id':job_id,'status':'completed','deliver':False}
            self._owned(value,job_id,lease_token,worker_id,device_id)
            if any(value.get('controls',{}).values()):
                raise ValueError('Operator pause or stop')
            self._artifact(job,result)
            job.update(status='completed',result=encoded)
            return {'job_id':job_id,'status':'completed','deliver':True}
        return mutate(self.state,operation)

    def reconcile_artifact(self,job_id,lease_token,result,*,worker_id,device_id):
        def operation(value):
            job=self._owned(value,job_id,lease_token,worker_id,device_id,historical=True)
            self._artifact(job,result)
            # Fence any newer lease. Operator must verify the private blob before
            # resolving pending history. Never acknowledge missing bytes as delivered.
            if job['status']!='completed':
                job['status']='reconciliation_pending'
            return {'job_id':job_id,'artifact_hash':job['artifact'],'status':'reconciliation_pending','deliver':False}
        return mutate(self.state,operation)

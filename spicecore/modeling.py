"""Synthetic-model opportunity pipeline with evidence-gated transitions."""
import sqlite3, json, uuid

STATES=('discovered','qualified','drafted','owner-approved','sent','negotiating','contracted','fulfilled','paid')
class ModelingPipeline:
 def __init__(self,path):
  if not path or path==':memory:': raise ValueError('Persistent path required')
  self.path=str(path)
  with sqlite3.connect(self.path) as db:
   db.execute('CREATE TABLE IF NOT EXISTS modeling_leads(id TEXT PRIMARY KEY,state TEXT,evidence TEXT)')
 def create(self,evidence):
  lid=uuid.uuid4().hex
  with sqlite3.connect(self.path) as db: db.execute('INSERT INTO modeling_leads VALUES (?,?,?)',(lid,'discovered',json.dumps(evidence or {},sort_keys=True)))
  return {'lead_id':lid,'state':'discovered'}
 def transition(self,lead_id,next_state,evidence):
  if next_state not in STATES or not isinstance(evidence,dict): raise ValueError('Valid state and evidence required')
  with sqlite3.connect(self.path) as db:
   row=db.execute('SELECT state,evidence FROM modeling_leads WHERE id=?',(lead_id,)).fetchone()
   if not row: raise ValueError('Unknown lead')
   cur=STATES.index(row[0]); nxt=STATES.index(next_state)
   if nxt!=cur+1: raise ValueError('Transitions must be sequential')
   merged={**json.loads(row[1]),**evidence}
   required={
    'qualified':('synthetic_model_accepted','rights_confirmed'),
    'owner-approved':('owner_approved',),
    'sent':('owner_approved','outreach_destination'),
    'contracted':('deliverables','territories','term','exclusivity','revisions','deposit_cents','balance_cents','owner_approved_contract'),
    'fulfilled':('digital_delivery_receipt',),
    'paid':('settled_payment_id',)}
   for k in required.get(next_state,()):
    if merged.get(k) in (None,False,'',[]): raise ValueError(f'Missing evidence: {k}')
   if merged.get('physical_attendance_promised') is True: raise ValueError('Synthetic persona cannot promise physical attendance')
   db.execute('UPDATE modeling_leads SET state=?,evidence=? WHERE id=?',(next_state,json.dumps(merged,sort_keys=True),lead_id))
   return {'lead_id':lead_id,'state':next_state,'evidence':merged}

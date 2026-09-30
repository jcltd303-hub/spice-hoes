"""Idempotent commerce ledger with explicit currencies and cohort maturity."""
import datetime as dt, json, sqlite3, uuid

KINDS={'sale','fee','refund','chargeback','inference_cost','production_cost','storage_cost','distribution_cost','labor_cost','payout'}
COSTS={'fee','refund','chargeback','inference_cost','production_cost','storage_cost','distribution_cost','labor_cost'}

class CommerceLedger:
 def __init__(self,path):
  if not path or path==':memory:': raise ValueError('Persistent path required')
  self.path=str(path)
  with sqlite3.connect(self.path) as db:
   db.execute('''CREATE TABLE IF NOT EXISTS commerce_events(
    id TEXT PRIMARY KEY, external_id TEXT UNIQUE, kind TEXT, amount_cents INTEGER, currency TEXT,
    customer TEXT, occurred_at TEXT, cohort_at TEXT, attribution TEXT, payload TEXT)''')
 def import_event(self,event):
  if not isinstance(event,dict): raise ValueError('Event required')
  for k in ('external_id','kind','currency','occurred_at'):
   if not isinstance(event.get(k),str) or not event[k].strip(): raise ValueError('Stable ID, kind, currency and time required')
  if event['kind'] not in KINDS or type(event.get('amount_cents')) is not int or event['amount_cents']<=0: raise ValueError('Positive supported commerce amount required')
  if len(event['currency'])!=3 or event['currency'].upper()!=event['currency']: raise ValueError('ISO-style uppercase currency required')
  dt.datetime.fromisoformat(event['occurred_at'])
  normalized={k:event.get(k) for k in ('kind','amount_cents','currency','customer','occurred_at','cohort_at','attribution')}
  with sqlite3.connect(self.path) as db:
   old=db.execute('SELECT id,payload FROM commerce_events WHERE external_id=?',(event['external_id'],)).fetchone()
   body=json.dumps(normalized,sort_keys=True,separators=(',',':'))
   if old:
    if old[1]!=body: raise ValueError('External ID conflict')
    return {'id':old[0],**normalized}
   eid=uuid.uuid4().hex
   db.execute('INSERT INTO commerce_events VALUES (?,?,?,?,?,?,?,?,?,?)',(eid,event['external_id'],event['kind'],event['amount_cents'],event['currency'],event.get('customer'),event['occurred_at'],event.get('cohort_at'),event.get('attribution'),body))
   return {'id':eid,**normalized}
 def contribution_report(self):
  with sqlite3.connect(self.path) as db: rows=db.execute('SELECT kind,amount_cents,currency FROM commerce_events').fetchall()
  out={}
  for kind,amount,currency in rows:
   r=out.setdefault(currency,{'currency':currency,'gross_cents':0,'cost_cents':0,'payout_cents':0,'contribution_cents':0})
   if kind=='sale': r['gross_cents']+=amount
   elif kind=='payout': r['payout_cents']+=amount
   elif kind in COSTS: r['cost_cents']+=amount
  for r in out.values(): r['contribution_cents']=r['gross_cents']-r['cost_cents']
  return sorted(out.values(),key=lambda x:x['currency'])
 def cohort_report(self,as_of):
  now=dt.datetime.fromisoformat(as_of)
  with sqlite3.connect(self.path) as db: rows=db.execute("SELECT customer,occurred_at,cohort_at,currency FROM commerce_events WHERE kind='sale' AND customer IS NOT NULL").fetchall()
  groups={}
  for customer,occurred,cohort,currency in rows:
   start=dt.datetime.fromisoformat(cohort or occurred); key=(start.date().isoformat(),currency)
   g=groups.setdefault(key,{'cohort':key[0],'currency':currency,'customers':set(),'repeat_customers':set(),'mature_30d':now>=start+dt.timedelta(days=30)})
   if customer in g['customers']: g['repeat_customers'].add(customer)
   g['customers'].add(customer)
  return [{**{k:v for k,v in g.items() if k not in ('customers','repeat_customers')},'customers':len(g['customers']),'repeat_customers':len(g['repeat_customers']),'retention_rate':(len(g['repeat_customers'])/len(g['customers']) if g['mature_30d'] and g['customers'] else None)} for g in groups.values()]

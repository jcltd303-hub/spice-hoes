"""Versioned visual identity review records for generated persona assets."""
import json, sqlite3, uuid
from datetime import datetime, timezone

class IdentityCheck:
    def __init__(self, path):
        if not path or path == ':memory:': raise ValueError('Persistent path required')
        self.path=str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS identity_reviews (
              id TEXT PRIMARY KEY, persona TEXT, reference_version TEXT, reviewer TEXT,
              score INTEGER, drift TEXT, created_at TEXT)''')
    def record(self, persona_id, reference_version, reviewer, selections, drift):
        if not all(isinstance(x,str) and x.strip() for x in (persona_id,reference_version,reviewer)):
            raise ValueError('Persona, reference version and reviewer required')
        if not isinstance(selections,list) or len(selections)!=10 or any(type(x) is not bool for x in selections):
            raise ValueError('Exactly ten boolean identity checks required')
        if not isinstance(drift,list) or any(not isinstance(x,str) or not x.strip() for x in drift):
            raise ValueError('Drift labels must be nonempty strings')
        row={'id':uuid.uuid4().hex,'persona_id':persona_id,'reference_version':reference_version,
             'reviewer':reviewer,'score':sum(selections),'drift':sorted(set(drift)),
             'created_at':datetime.now(timezone.utc).isoformat()}
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO identity_reviews VALUES (?,?,?,?,?,?,?)',
                       (row['id'],persona_id,reference_version,reviewer,row['score'],json.dumps(row['drift']),row['created_at']))
        return row
    def approved(self, persona_id, reference_version, *, reviewers=2, minimum=9):
        with sqlite3.connect(self.path) as db:
            rows=db.execute('SELECT reviewer,score,drift FROM identity_reviews WHERE persona=? AND reference_version=? ORDER BY rowid DESC',
                            (persona_id,reference_version)).fetchall()
        latest={}
        for reviewer,score,drift in rows:
            latest.setdefault(reviewer,(score,json.loads(drift)))
        passing=[v for v in latest.values() if v[0]>=minimum]
        recurring={}
        for score,drift in latest.values():
            for label in drift: recurring[label]=recurring.get(label,0)+1
        return len(passing)>=reviewers and not any(n>=2 for n in recurring.values())

"""Durable development queue. Azure adapters must provide the same atomic contract."""
import datetime as dt
import hashlib
import json
import sqlite3
import uuid
from typing import Protocol


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def timestamp(value=None):
    if value is None:
        return dt.datetime.now(dt.timezone.utc).timestamp()
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone required')
    return parsed.timestamp()


class JobBackend(Protocol):
    def enqueue(self, kind: str, payload: dict, key: str) -> str: ...
    def claim(self, worker_id: str, now: str) -> dict | None: ...
    def renew(self, job_id: str, lease_token: str) -> None: ...
    def complete(self, job_id: str, lease_token: str, result: dict) -> dict: ...


class JobStore:
    lease_seconds = 120
    heartbeat_seconds = 30
    maximum_claims = 3

    def __init__(self, path, *, clock=timestamp):
        if not path or path == ':memory:':
            raise ValueError('Persistent path required')
        self.path, self.clock = path, clock
        with self._connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, key TEXT UNIQUE, kind TEXT, payload TEXT, hash TEXT,
                device TEXT, status TEXT, claims INTEGER DEFAULT 0, worker TEXT,
                token TEXT, expires REAL, result TEXT);
                CREATE TABLE IF NOT EXISTS job_claims (token TEXT PRIMARY KEY, job TEXT, worker TEXT);
                CREATE TABLE IF NOT EXISTS job_artifacts (job TEXT PRIMARY KEY, hash TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS job_controls (id INTEGER PRIMARY KEY, paused INTEGER, stopped INTEGER);
                INSERT OR IGNORE INTO job_controls VALUES (1,0,0);''')

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def set_controls(self, *, paused=False, emergency_stop=False):
        with self._connect() as db:
            db.execute('UPDATE job_controls SET paused=?, stopped=? WHERE id=1', (bool(paused), bool(emergency_stop)))

    def enqueue(self, kind, payload, key):
        if not isinstance(payload, dict) or not kind or not key:
            raise ValueError('Kind, payload and idempotency key required')
        encoded = canonical(payload)
        digest = hashlib.sha256(canonical([kind, payload]).encode()).hexdigest()
        device = payload.get('device_id')
        if kind == 'image' and (not isinstance(device, str) or not device):
            raise ValueError('Image device_id required')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT id, hash FROM jobs WHERE key=?', (key,)).fetchone()
            if old:
                if old['hash'] != digest:
                    raise ValueError('Idempotency payload conflict')
                return old['id']
            job = uuid.uuid4().hex
            db.execute('INSERT INTO jobs (id,key,kind,payload,hash,device,status) VALUES (?,?,?,?,?,?,?)', (job,key,kind,encoded,digest,device,'queued'))
            return job

    def claim(self, worker_id, now, *, device_id=None):
        if not worker_id:
            raise ValueError('Worker identity required')
        current = timestamp(now)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            control = db.execute('SELECT * FROM job_controls').fetchone()
            if control['paused'] or control['stopped']:
                return None
            db.execute("UPDATE jobs SET status='deadletter' WHERE status='leased' AND expires<=? AND claims>=?", (current,self.maximum_claims))
            row = db.execute("""SELECT * FROM jobs j WHERE (status='queued' OR (status='leased' AND expires<=?))
                AND claims<? AND NOT EXISTS (SELECT 1 FROM job_artifacts a WHERE a.job=j.id) AND (? IS NULL OR device=?) AND NOT EXISTS
                (SELECT 1 FROM jobs busy WHERE busy.id<>j.id AND busy.kind='image' AND j.kind='image'
                 AND busy.device=j.device AND busy.status='leased' AND busy.expires>?) ORDER BY rowid LIMIT 1""", (current,self.maximum_claims,device_id,device_id,current)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            db.execute("UPDATE jobs SET status='leased',claims=claims+1,worker=?,token=?,expires=? WHERE id=?", (worker_id,token,current+self.lease_seconds,row['id']))
            db.execute('INSERT INTO job_claims VALUES (?,?,?)', (token,row['id'],worker_id))
            return dict(id=row['id'], kind=row['kind'], payload=json.loads(row['payload']), device_id=row['device'], worker_id=worker_id, lease_token=token, lease_expires=current+self.lease_seconds, claims=row['claims']+1)

    def _active(self, db, job, token, now):
        row = db.execute('SELECT * FROM jobs WHERE id=?', (job,)).fetchone()
        if row is None or row['status'] != 'leased' or row['token'] != token or row['expires'] <= now:
            raise ValueError('Active lease token required')
        return row

    def renew(self, job_id, lease_token, *, now=None):
        current = self.clock() if now is None else timestamp(now)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._active(db, job_id, lease_token, current)
            db.execute('UPDATE jobs SET expires=? WHERE id=?', (current+self.lease_seconds,job_id))

    def complete(self, job_id, lease_token, result, *, now=None):
        encoded = canonical(result)
        current = self.clock() if now is None else timestamp(now)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row and row['status'] == 'completed' and row['token'] == lease_token and row['result'] == encoded:
                return dict(job_id=job_id, status='completed', deliver=False)
            self._active(db,job_id,lease_token,current)
            artifact = db.execute('SELECT hash FROM job_artifacts WHERE job=?', (job_id,)).fetchone()
            if artifact and result.get('artifact_hash') != artifact['hash']:
                raise ValueError('Completion conflicts with checkpointed artifact')
            if result.get('artifact_hash'):
                self._record_artifact(db, job_id, result)
            db.execute("UPDATE jobs SET status='completed', result=? WHERE id=?", (encoded,job_id))
            return dict(job_id=job_id, status='completed', deliver=True)

    def _record_artifact(self, db, job_id, result):
        digest = result.get('artifact_hash')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('SHA256 artifact hash required')
        old = db.execute('SELECT hash FROM job_artifacts WHERE job=?', (job_id,)).fetchone()
        if old and old['hash'] != digest:
            raise ValueError('Artifact conflict')
        db.execute('INSERT OR IGNORE INTO job_artifacts VALUES (?,?,?)', (job_id,digest,canonical(result)))

    def reconcile_artifact(self, job_id, lease_token, result):
        digest = result.get('artifact_hash')
        if not isinstance(digest,str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('SHA256 artifact hash required')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM job_claims WHERE job=? AND token=?', (job_id,lease_token)).fetchone():
                raise ValueError('Known claim required')
            self._record_artifact(db, job_id, result)
            # Checkpoint only: no ownership mutation and no public delivery.
            return dict(job_id=job_id, artifact_hash=digest, status='reconciled', deliver=False)

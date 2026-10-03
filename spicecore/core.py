"""Local persona registry and auditable experiment ledger."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_personas(directory: str | Path) -> list[dict]:
    personas = []
    for path in sorted(Path(directory).glob('*.yaml')):
        raw = path.read_bytes()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict) or not all(data.get(k) for k in ('id', 'name', 'type', 'disclosure')):
            raise ValueError(f'Invalid persona: {path}')
        if not isinstance(data.get('age'), int) or data['age'] < 18 or data.get('fictional') is not True:
            raise ValueError(f'Persona must be a fictional adult: {path}')
        data['version'] = hashlib.sha256(raw).hexdigest()
        personas.append(data)
    ids = [p['id'] for p in personas]
    if len(ids) != len(set(ids)) or len(personas) != 5 or set(p['type'] for p in personas) != {'Scary', 'Sporty', 'Baby', 'Ginger', 'Posh'}:
        raise ValueError('Expected five unique original personas, one per type')
    return personas


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,
                external_id TEXT UNIQUE,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY,
                persona_id TEXT NOT NULL,
                persona_version TEXT NOT NULL,
                theme TEXT NOT NULL,
                format TEXT NOT NULL,
                channel TEXT NOT NULL,
                offer TEXT NOT NULL,
                asset_uri TEXT,
                prompt TEXT,
                model TEXT,
                seed TEXT,
                cost_cents INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'proposed',
                created_at TEXT NOT NULL
            );
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def _mirror_event(self, event: dict) -> None:
        if not __import__("os").environ.get("SUPABASE_URL"):
            return
        try:
            from .cloud import SupabaseArchive
            SupabaseArchive().record_event(
                event_id=event["id"],
                ts=event["ts"],
                kind=event["kind"],
                payload=event["payload"],
                external_id=event.get("external_id"),
            )
        except Exception:
            if __import__("os").environ.get("SUPABASE_MIRROR_REQUIRED", "").lower() in ("1", "true", "yes"):
                raise

    def _event(self, kind: str, payload: dict, external_id: str | None = None) -> dict:
        event = {'id': str(uuid.uuid4()), 'ts': datetime.now(timezone.utc).isoformat(), 'kind': kind,
                 'external_id': external_id, 'payload': payload}
        self.db.execute('INSERT INTO events(id,ts,kind,external_id,payload) VALUES(?,?,?,?,?)',
                        (event['id'], event['ts'], kind, external_id, json.dumps(payload, sort_keys=True)))
        self._mirror_event(event)
        return event

    def record_event(self, kind: str, payload: dict, external_id: str | None = None) -> dict:
        if external_id:
            existing = self.db.execute('SELECT * FROM events WHERE external_id=?', (external_id,)).fetchone()
            if existing:
                old = json.loads(existing['payload'])
                if existing['kind'] != kind or old != payload:
                    raise ValueError('External ID already used for a different event')
                return {'id': existing['id'], 'ts': existing['ts'], 'kind': kind,
                        'external_id': external_id, 'payload': old}
        with self.db:
            return self._event(kind, payload, external_id)

    def propose(self, persona: dict, theme: str, format: str, channel: str, offer: str,
                asset_uri: str | None = None, prompt: str | None = None,
                model: str | None = None, seed: str | None = None, cost_cents: int = 0) -> str:
        if cost_cents < 0 or not all((theme, format, channel, offer)):
            raise ValueError('Invalid candidate fields')
        cid, ts = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute('''INSERT INTO candidates
                (id,persona_id,persona_version,theme,format,channel,offer,asset_uri,prompt,model,seed,cost_cents,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (cid, persona['id'], persona['version'], theme, format, channel, offer,
                 asset_uri, prompt, model, seed, cost_cents, ts))
            self._event('candidate_proposed', {'candidate_id': cid, 'persona_id': persona['id'],
                        'persona_version': persona['version'], 'theme': theme, 'format': format,
                        'channel': channel, 'offer': offer, 'asset_uri': asset_uri, 'prompt': prompt,
                        'model': model, 'seed': seed, 'cost_cents': cost_cents})
        return cid

    def candidate(self, cid: str) -> dict:
        row = self.db.execute('SELECT * FROM candidates WHERE id=?', (cid,)).fetchone()
        if row is None:
            raise ValueError('Unknown candidate')
        return dict(row)

    def review(self, cid: str, decision: str, reviewer: str, note: str = '') -> dict:
        if decision not in ('approved', 'rejected', 'revise') or not reviewer.strip():
            raise ValueError('Invalid review')
        current = self.candidate(cid)
        if current['status'] != 'proposed':
            raise ValueError('Candidate already reviewed; create a new revision')
        with self.db:
            self.db.execute('UPDATE candidates SET status=? WHERE id=?', (decision, cid))
            self._event('asset_reviewed', {'candidate_id': cid, 'persona_id': current['persona_id'],
                         'decision': decision, 'reviewer': reviewer, 'note': note})
        return self.candidate(cid)

    def publish(self, cid: str, url: str, external_id: str | None = None) -> dict:
        current = self.candidate(cid)
        if current['status'] != 'approved' or not url.strip():
            raise ValueError('Publishing requires an approved candidate and URL')
        payload = {'candidate_id': cid, 'persona_id': current['persona_id'], 'url': url}
        with self.db:
            self.db.execute("UPDATE candidates SET status='published' WHERE id=?", (cid,))
            return self._event('content_published', payload, external_id)

    def record_outcome(self, cid: str, kind: str, amount_cents: int = 0,
                       external_id: str | None = None) -> dict:
        if kind not in ('impression', 'click', 'purchase', 'refund', 'distribution_cost', 'commerce_cost') or amount_cents < 0:
            raise ValueError('Invalid outcome')
        current = self.candidate(cid)
        if current['status'] != 'published':
            raise ValueError('Outcomes require published candidates')
        if kind in ('purchase', 'refund', 'distribution_cost', 'commerce_cost') and amount_cents == 0:
            raise ValueError('Monetary outcome requires a positive amount')
        return self.record_event(kind, {'candidate_id': cid, 'persona_id': current['persona_id'],
                                       'amount_cents': amount_cents}, external_id)

    def stats(self, personas: list[dict]) -> list[dict]:
        result = []
        for p in personas:
            published = self.db.execute("SELECT COUNT(*) FROM candidates WHERE persona_id=? AND status='published'", (p['id'],)).fetchone()[0]
            cost = self.db.execute('SELECT COALESCE(SUM(cost_cents),0) FROM candidates WHERE persona_id=?', (p['id'],)).fetchone()[0]
            rows = self.db.execute('SELECT kind,payload FROM events WHERE kind IN (\'impression\',\'click\',\'purchase\',\'refund\',\'distribution_cost\',\'commerce_cost\')').fetchall()
            sums = {'impression': 0, 'click': 0, 'purchase': 0, 'refund': 0, 'distribution_cost': 0, 'commerce_cost': 0}
            for row in rows:
                item = json.loads(row['payload'])
                if item['persona_id'] == p['id']:
                    sums[row['kind']] += item['amount_cents'] if row['kind'] in ('purchase', 'refund', 'distribution_cost', 'commerce_cost') else int(item.get('count', 1))
            result.append({'persona_id': p['id'], 'name': p['name'], 'published': published,
                           'impressions': sums['impression'], 'clicks': sums['click'],
                           'revenue_cents': sums['purchase'], 'refund_cents': sums['refund'],
                           'cost_cents': cost + sums['distribution_cost'] + sums['commerce_cost'],
                           'commerce_cost_cents': sums['commerce_cost'],
                           'net_cents': sums['purchase'] - sums['refund'] - cost - sums['distribution_cost'] - sums['commerce_cost']})
        return result

    def events(self) -> list[dict]:
        return [dict(id=r['id'], ts=r['ts'], kind=r['kind'], external_id=r['external_id'],
                     payload=json.loads(r['payload'])) for r in self.db.execute('SELECT * FROM events ORDER BY seq')]

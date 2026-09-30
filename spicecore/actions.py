"""Persistent owner policy and audit receipts. This module never executes tools."""
import datetime as dt
import hashlib
import json
import sqlite3
import uuid
from .jobs import canonical


class ActionGate:
    def __init__(self, path, *, runtime_config=None, ledger=None):
        if not path or path == ':memory:':
            raise ValueError('Persistent path required')
        self.path = path
        self.runtime_config, self.ledger = runtime_config, ledger
        with self._connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS action_policy (
                account TEXT, action TEXT, version TEXT, quota INTEGER, live INTEGER,
                PRIMARY KEY(account,action));
                CREATE TABLE IF NOT EXISTS asset_approvals (hash TEXT, version TEXT, PRIMARY KEY(hash,version));
                CREATE TABLE IF NOT EXISTS action_receipts (key TEXT PRIMARY KEY, hash TEXT, account TEXT, action TEXT, day TEXT, receipt TEXT);
                CREATE TABLE IF NOT EXISTS action_controls (id INTEGER PRIMARY KEY, paused INTEGER, stopped INTEGER);
                INSERT OR IGNORE INTO action_controls VALUES (1,0,0);''')

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def configure(self, account, action, *, version, daily_quota, live=False, verified=None):
        """Operator-only configuration; never populate from agent output.

        A live scope requires all independently verified prerequisites.
        Authorization still returns execute=False; connectors must recheck controls.
        """
        if not account or not action or not version or type(daily_quota) is not int or daily_quota <= 0:
            raise ValueError('Explicit scope, version and positive quota required')
        prerequisites = ('authentication', 'ownership', 'platform_permission', 'end_to_end_test', 'owner_authorization')
        if live and (not isinstance(verified, dict) or any(verified.get(k) is not True for k in prerequisites)):
            raise ValueError('Verified live prerequisites required')
        with self._connect() as db:
            db.execute('INSERT OR REPLACE INTO action_policy VALUES (?,?,?,?,?)', (account,action,version,daily_quota,bool(live)))

    def approve_asset(self, asset_hash, version):
        if not isinstance(asset_hash,str) or len(asset_hash) != 64 or any(c not in '0123456789abcdef' for c in asset_hash) or not version:
            raise ValueError('Asset hash and approval version required')
        with self._connect() as db:
            db.execute('INSERT OR IGNORE INTO asset_approvals VALUES (?,?)', (asset_hash,version))

    def set_controls(self, *, paused=False, emergency_stop=False):
        with self._connect() as db:
            db.execute('UPDATE action_controls SET paused=?, stopped=? WHERE id=1', (bool(paused),bool(emergency_stop)))

    def _live_preflight(self, request):
        config = self.runtime_config
        if not isinstance(config, dict) or config.get('dry_run', True) is not False:
            raise ValueError('Live runtime required')
        credit = config.get('credit', {})
        expiry = dt.datetime.fromisoformat(credit.get('expires_at', ''))
        if credit.get('eligible') is not True or not credit.get('evidence') or expiry.tzinfo is None or expiry <= dt.datetime.now(dt.timezone.utc):
            raise ValueError('Verified unexpired credit required')
        cap = config.get('daily_cap_cents')
        if type(cap) is not int or cap <= 0 or not config.get('region') or config['region'] not in config.get('approved_regions', []):
            raise ValueError('Owner ceiling and region required')
        maximum = request.get('maximum_action_cents')
        if type(maximum) is not int or maximum <= 0 or maximum > cap or self.ledger is None:
            raise ValueError('Bounded paid action reservation required')
        self.ledger.validate_reservation(request.get('reservation_id'), request.get('run_id'), maximum, owner_cap_cents=cap)

    def authorize(self, request):
        if not isinstance(request,dict) or any(not isinstance(request.get(k),str) or not request[k] for k in ('key','account','action','policy_version')):
            raise ValueError('Explicit action scope, version and key required')
        digest = hashlib.sha256(canonical(request).encode()).hexdigest()
        day = dt.datetime.now(dt.timezone.utc).date().isoformat()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM action_receipts WHERE key=?', (request['key'],)).fetchone()
            if old and old['hash'] != digest:
                raise ValueError('Idempotency payload conflict')
            controls = db.execute('SELECT * FROM action_controls').fetchone()
            policy = db.execute('SELECT * FROM action_policy WHERE account=? AND action=?', (request['account'],request['action'])).fetchone()
            reason = None
            if controls['stopped'] or controls['paused']:
                reason = 'Operator stop or pause'
            elif policy is None or policy['version'] != request['policy_version']:
                reason = 'Unconfigured scope or stale policy'
            elif request['action'] in ('publish','outreach','offer','contract') and not db.execute('SELECT 1 FROM asset_approvals WHERE hash=? AND version=?', (request.get('asset_hash'),policy['version'])).fetchone():
                reason = 'Owner asset approval required'
            if reason is None and policy['live']:
                try:
                    self._live_preflight(request)
                except (ValueError, TypeError, KeyError, AttributeError):
                    reason = 'Live runtime or budget preflight failed'
            if reason:
                return dict(authorized=False, execute=False, dry_run=True, reason=reason)
            if old:
                receipt = json.loads(old['receipt'])
                receipt['dry_run'] = not bool(policy['live'])
                return receipt
            used = db.execute('SELECT COUNT(*) FROM action_receipts WHERE account=? AND action=? AND day=?', (request['account'],request['action'],day)).fetchone()[0]
            if used >= policy['quota']:
                return dict(authorized=False, execute=False, dry_run=not bool(policy['live']), reason='Daily quota exhausted')
            receipt = dict(authorized=True, execute=False, dry_run=not bool(policy['live']), receipt_id=uuid.uuid4().hex, account=request['account'], action=request['action'], policy_version=policy['version'], key=request['key'])
            db.execute('INSERT INTO action_receipts VALUES (?,?,?,?,?,?)', (request['key'],digest,request['account'],request['action'],day,canonical(receipt)))
            return receipt

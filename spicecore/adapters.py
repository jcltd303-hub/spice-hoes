"""Platform-neutral delivery and outcome adapters with durable idempotency.

Adapters receive an ActionGate receipt; they cannot authorize themselves. Live adapters
must be explicitly configured by the operator and should use official platform APIs.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Protocol

from .jobs import canonical


class PlatformAdapter(Protocol):
    def deliver(self, request: dict, receipt: dict) -> dict: ...


class DeliveryLedger:
    def __init__(self, path):
        if not path or path == ':memory:':
            raise ValueError('Persistent path required')
        self.path = str(path)
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS deliveries (
                key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, receipt_id TEXT NOT NULL,
                result TEXT NOT NULL)''')

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def deliver(self, adapter: PlatformAdapter, request: dict, receipt: dict) -> dict:
        if not receipt.get('authorized') or receipt.get('execute') is not False:
            raise PermissionError('Valid non-executing gate receipt required')
        if receipt.get('dry_run') is not False:
            return {'status': 'dry_run', 'delivered': False, 'receipt_id': receipt.get('receipt_id')}
        if receipt.get('key') != request.get('key') or receipt.get('account') != request.get('account') or receipt.get('action') != request.get('action'):
            raise PermissionError('Receipt scope mismatch')
        key = request['key']
        digest = hashlib.sha256(canonical(request).encode()).hexdigest()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM deliveries WHERE key=?', (key,)).fetchone()
            if old:
                if old['request_hash'] != digest or old['receipt_id'] != receipt['receipt_id']:
                    raise ValueError('Delivery idempotency conflict')
                return json.loads(old['result'])
            result = adapter.deliver(request, receipt)
            if not isinstance(result, dict) or result.get('delivered') is not True:
                raise ValueError('Adapter must return a delivered result')
            encoded = canonical(result)
            db.execute('INSERT INTO deliveries VALUES (?,?,?,?)',
                       (key, digest, receipt['receipt_id'], encoded))
            return result


class RecordingAdapter:
    """Test/development adapter. It records a delivery but performs no network I/O."""
    def __init__(self):
        self.calls = []

    def deliver(self, request, receipt):
        self.calls.append((request, receipt))
        return {'status': 'recorded', 'delivered': True,
                'external_id': 'mock:' + request['key']}

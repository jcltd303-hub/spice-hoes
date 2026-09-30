"""Platform-neutral outbound adapter and normalized outcome ingestion.

Adapters receive only an ActionGate receipt that has already been authorized. They
cannot mint authorization, and dry-run receipts are never dispatched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PlatformAdapter(Protocol):
    def dispatch(self, request: dict) -> dict: ...


@dataclass(frozen=True)
class NormalizedOutcome:
    candidate_id: str
    kind: str
    external_id: str
    amount_cents: int = 0


def dispatch_authorized(gate, adapter: PlatformAdapter, request: dict) -> dict:
    """Authorize immediately before dispatch and fail closed on dry-run."""
    receipt = gate.authorize(request)
    if not receipt.get('authorized'):
        return {'status': 'blocked', 'execute': False, 'reason': receipt.get('reason', 'not authorized')}
    if receipt.get('dry_run') or receipt.get('execute') is not False:
        return {'status': 'dry_run', 'execute': False, 'receipt_id': receipt.get('receipt_id')}

    # ActionGate intentionally never returns execute=True. A future production
    # executor must use a separately verified, narrowly scoped execution token.
    return {'status': 'awaiting_executor', 'execute': False, 'receipt_id': receipt.get('receipt_id')}


def normalize_outcome(raw: dict, *, candidate_id: str, source: str) -> NormalizedOutcome:
    """Normalize trusted connector observations into the experiment ledger schema."""
    if not isinstance(raw, dict) or not candidate_id or not source:
        raise ValueError('Raw outcome, candidate and source required')
    kind = raw.get('kind')
    if kind not in ('impression', 'click', 'purchase', 'refund', 'distribution_cost'):
        raise ValueError('Unsupported outcome kind')
    external = raw.get('external_id')
    if not isinstance(external, str) or not external.strip():
        raise ValueError('Stable external outcome ID required')
    amount = raw.get('amount_cents', 0)
    if type(amount) is not int or amount < 0:
        raise ValueError('Outcome amount must be a nonnegative integer')
    if kind in ('purchase', 'refund', 'distribution_cost') and amount <= 0:
        raise ValueError('Monetary outcomes require a positive amount')
    return NormalizedOutcome(candidate_id, kind, f'{source}:{external}', amount)


def ingest_outcomes(store, *, candidate_id: str, source: str, observations: list[dict]) -> list[dict]:
    """Idempotently ingest connector observations; raw payloads are not retained."""
    if not isinstance(observations, list):
        raise ValueError('Observations must be a list')
    events = []
    for raw in observations:
        item = normalize_outcome(raw, candidate_id=candidate_id, source=source)
        events.append(store.record_outcome(
            item.candidate_id, item.kind, item.amount_cents, external_id=item.external_id))
    return events

"""Normalize externally observed campaign outcomes into the experiment ledger."""
from __future__ import annotations

_ALLOWED = {'impression', 'click', 'purchase', 'refund', 'distribution_cost'}


def ingest_outcome(store, event: dict) -> dict:
    """Validate an adapter event and idempotently attach it to a published candidate."""
    if not isinstance(event, dict):
        raise ValueError('Outcome must be an object')
    required = ('candidate_id', 'kind', 'external_id', 'source')
    if any(not isinstance(event.get(k), str) or not event[k].strip() for k in required):
        raise ValueError('Candidate, kind, source and external ID are required')
    if event['kind'] not in _ALLOWED:
        raise ValueError('Unsupported outcome kind')
    amount = event.get('amount_cents', 0)
    if type(amount) is not int or amount < 0:
        raise ValueError('amount_cents must be a nonnegative integer')
    external = f"{event['source']}:{event['external_id']}"
    return store.record_outcome(event['candidate_id'], event['kind'], amount,
                                external_id=external)


def ingest_batch(store, events: list[dict]) -> list[dict]:
    if not isinstance(events, list) or len(events) > 1000:
        raise ValueError('Outcome batch must contain at most 1000 events')
    return [ingest_outcome(store, event) for event in events]

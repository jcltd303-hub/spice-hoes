"""Auditable operator loop: outcomes -> allocation -> MoA proposal -> review queue.

This module deliberately stops before external execution. Model output may propose an
action, but ActionGate remains the only path to live authorization.
"""
from __future__ import annotations

import uuid

from .moa import run_moa
from .policy import recommend


def _persona(personas, persona_id):
    for person in personas:
        if person['id'] == persona_id:
            return person
    raise ValueError('Selected persona is not in the registry')


def _evidence_query(knowledge, persona, objective, limit, knowledge_scope):
    if not isinstance(knowledge_scope, dict):
        raise ValueError('Explicit knowledge scope required')
    scope = {**knowledge_scope, 'persona': persona['id']}
    query = f"{persona['name']} {objective} {persona.get('voice','')} {persona.get('bio','')}"
    return knowledge.search(query, scope, limit=limit)


async def plan_cycle(store, personas, knowledge, client, budget, *, objective,
                     channel, offer, audit_db, knowledge_scope, seed=None, evidence_limit=8,
                     limits=None):
    """Create one bounded experiment candidate from observed outcomes and RAG evidence."""
    if not objective.strip() or not channel.strip() or not offer.strip():
        raise ValueError('Objective, channel and offer are required')
    if type(evidence_limit) is not int or not 1 <= evidence_limit <= 20:
        raise ValueError('Evidence limit must be 1..20')

    allocation = recommend(store.stats(personas), seed=seed)
    persona = _persona(personas, allocation['persona_id'])
    evidence = _evidence_query(knowledge, persona, objective, evidence_limit, knowledge_scope)
    if not evidence:
        raise ValueError('No scoped evidence available for selected persona')

    task_id = uuid.uuid4().hex
    task = {
        'task_id': task_id,
        'persona': persona['id'],
        'persona_version': persona['version'],
        'task_type': 'commerce',
        'allowed_actions': ['publish', 'outreach', 'offer'],
        'deliverable': (
            f"Propose one {channel} experiment for objective {objective!r} and offer "
            f"{offer!r}. Preserve the fictional-persona disclosure and do not claim "
            "unobserved demand or fabricate outcomes."
        ),
        'audit_db': str(audit_db),
        'limits': limits or {
            'max_attempts': 2, 'timeout_seconds': 30, 'max_input_tokens': 50000,
            'max_output_tokens': 1200, 'maximum_call_cents': 5,
        },
    }
    decision = await run_moa(task, evidence, client, budget)
    if decision.get('status') != 'complete':
        store.record_event('cycle_failed', {
            'task_id': task_id, 'persona_id': persona['id'],
            'objective': objective, 'error': decision.get('error', 'unknown'),
        }, external_id=f'cycle:{task_id}:failed')
        return {'status': 'failed', 'task_id': task_id, 'allocation': allocation,
                'decision': decision}

    proposal = decision['selected_proposal']
    cid = store.propose(
        persona, objective, 'moa-proposal', channel, offer,
        prompt=proposal, model='moa', seed=str(seed) if seed is not None else None,
        cost_cents=decision.get('expected_cost_cents', 0),
    )
    action = decision.get('action_request')
    store.record_event('cycle_planned', {
        'task_id': task_id, 'candidate_id': cid, 'persona_id': persona['id'],
        'persona_version': persona['version'], 'allocation_policy': allocation,
        'evidence_ids': decision['evidence_ids'], 'action_request': action,
        'reservation_id': decision.get('reservation_id'),
    }, external_id=f'cycle:{task_id}:planned')
    return {
        'status': 'review_required', 'task_id': task_id, 'candidate_id': cid,
        'allocation': allocation, 'decision': decision, 'action_request': action,
        'execute': False,
    }


def action_request_for_candidate(store, cid, *, account, action, policy_version,
                                 asset_hash=None):
    """Translate an approved candidate into a gate request; never authorize it here."""
    candidate = store.candidate(cid)
    if candidate['status'] != 'approved':
        raise ValueError('Owner review required before requesting an action')
    if action not in ('publish', 'outreach', 'offer'):
        raise ValueError('Unsupported campaign action')
    request = {
        'key': f"candidate:{cid}:{action}",
        'account': account,
        'action': action,
        'policy_version': policy_version,
        'candidate_id': cid,
        'persona_id': candidate['persona_id'],
    }
    if asset_hash is not None:
        if not isinstance(asset_hash, str) or len(asset_hash) != 64:
            raise ValueError('SHA-256 asset hash required')
        request['asset_hash'] = asset_hash
    return request

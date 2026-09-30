"""Owner review service binding approvals to immutable asset identity."""
import hashlib

class OperatorService:
    def __init__(self, store, gate, identity, *, reviewer_check):
        if not callable(reviewer_check): raise ValueError('Reviewer authentication required')
        self.store,self.gate,self.identity,self.reviewer_check=store,gate,identity,reviewer_check
    def decide(self, candidate_id, reviewer, decision, *, asset_hash, reference_version, note=''):
        if self.reviewer_check(reviewer) is not True: raise PermissionError('Authenticated reviewer required')
        if not isinstance(asset_hash,str) or len(asset_hash)!=64 or any(c not in '0123456789abcdef' for c in asset_hash):
            raise ValueError('Immutable SHA-256 asset hash required')
        candidate=self.store.candidate(candidate_id)
        if decision=='approved' and not self.identity.approved(candidate['persona_id'],reference_version):
            raise ValueError('Identity threshold not satisfied')
        reviewed=self.store.review(candidate_id,decision,reviewer,note)
        if decision=='approved':
            self.gate.approve_asset(asset_hash, reference_version)
            self.store.record_event('operator_asset_approved',
              {'candidate_id':candidate_id,'persona_id':candidate['persona_id'],'asset_hash':asset_hash,
               'reference_version':reference_version,'reviewer':reviewer})
        return reviewed

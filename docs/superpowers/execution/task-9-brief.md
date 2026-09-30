### Task 9: TikTok content and modeling workflows
**Files:** Create: `spicecore/content.py`, `spicecore/modeling.py`. Tests: `tests/test_content.py`, `tests/test_modeling.py`.
**Interfaces:** ContentService.prepare(persona_id: str, pillars: list[str], count: int) -> list[dict]; ModelingPipeline.transition(lead_id: str, next_state: str, evidence: dict) -> dict.
**Consumes:** Tasks 1, 2, 4, 7, 8 knowledge, proposals, approvals and measurements.
- [ ] Write failing unittest cases: test_missing_disclosure: cannot approve; test_no_reward_claim: eligibility unknown reported explicitly; test_unsupported_lead: cannot qualify without synthetic acceptance; test_contract: approval mandatory; test_physical_modeling: reject promise of attendance.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_content.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Prepare three persona pillars, hook variants, original scripts/storyboards/captions, AI labeling and campaign attribution. Limit batch count to configured cap. Add deterministic video assembly interface for phone assets; no generative-video fallback. Model media kit and leads through discovered/qualified/drafted/owner-approved/sent/negotiating/contracted/fulfilled/paid. Require synthetic-model acceptance, rights, deliverables, territories, term, exclusivity, revisions, deposit/balance. External outreach and contracts remain reviewed.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: tiktok content and modeling workflows`; exclude secrets, local databases, references and generated assets.


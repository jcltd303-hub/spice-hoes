### Task 7: Authenticated operator review and identity validation
**Files:** Create: `spicecore/operator.py`, `spicecore/identity_checks.py`. Tests: `tests/test_operator.py`, `tests/test_identity_checks.py`.
**Interfaces:** IdentityCheck.record(persona_id: str, reference_version: str, reviewer: str, selections: list[bool], drift: list[str]) -> dict; OperatorService.decide(candidate_id: str, reviewer: str, decision: str) -> dict.
**Consumes:** Tasks 1, 4, 6 evidence, assets and action receipts.
- [ ] Write failing unittest cases: test_replaced_artifact: prior approval invalidated; test_threshold: 8/10 fails, two 9/10 passes only without recurring drift; test_auth: review endpoint requires identity; test_rollback: published historical receipt not rewritten.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_operator.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Keep existing loopback web.py for local use. Add authenticated Azure operator endpoints and mobile view for evidence, jobs, spend, review, pause, stop and rollback of unpublished work. Approvals bind artifact hash and persona/reference version. Celeste needs two reviewers each >=9/10 and no recurring drift; store prompts and rejected outputs. Never infer a pass from img2img.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: authenticated operator review and identity validation`; exclude secrets, local databases, references and generated assets.


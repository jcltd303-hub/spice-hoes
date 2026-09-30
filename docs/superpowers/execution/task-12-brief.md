### Task 12: Live canary and controlled rollout
**Files:** Create: `docs/live-acceptance.md`, `docs/operations.md`. Tests: `tests/test_live_preflight.py`.
**Interfaces:** preflight(config: dict, receipts: dict) -> dict; rollout action policy -> versioned receipt.
**Consumes:** Earlier task interfaces and approved spec.
- [ ] Write failing unittest cases: test_missing_receipt: preflight reports blocked; test_connector_permission: action cannot enable from offline test; test_rollout_version: stale policy denied; test_credit_expiry: pending paid calls halted.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_live_preflight.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: After real Azure credit/account access, device pairing and canonical references are available, run bounded Azure inference, phone generation, private upload, mobile review and one reviewed commercial loop. Verify actual fees, identity and connector permissions. Record live receipts separately from offline tests. Enable permitted publishing and replies per account/action only after explicit configuration and successful live test. Test restore/deletion and emergency stop. If accounts or phone are absent, mark live checks blocked, ship implementation PR with that limitation rather than claiming production readiness.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: live canary and controlled rollout`; exclude secrets, local databases, references and generated assets.


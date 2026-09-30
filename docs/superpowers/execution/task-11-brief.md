### Task 11: Runnable integration and documentation
**Files:** Create: `spicecore/cli.py`, `README.md`, `.github/workflows/ci.yml`, `tests/test_end_to_end.py`. Tests: `tests/test_end_to_end.py`.
**Interfaces:** CLI commands: knowledge, moa, worker, jobs, campaign, modeling, dm, commerce, operator; dry-run demo fixture -> structured report.
**Consumes:** Earlier task interfaces and approved spec.
- [ ] Write failing unittest cases: test_complete_loop: evidence IDs connect every stage; test_no_credentials: live mode fails visibly; test_existing_suite: all previous tests pass; test_demo_labels: never reports live Azure/device/publishing success.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_end_to_end.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Wire services with explicit config and shared task/experiment IDs. Add isolated temp-database demo: retrieve canon/offer, run fake Azure MoA, lease job, simulate Local Dream artifact, approve, prepare post, import sale/renewal, compute contribution and draft grounded DM. CI runs unittest on Python 3.11+ with no credentials. Report fixture/mock status on every demo; production never selects fake client automatically.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: runnable integration and documentation`; exclude secrets, local databases, references and generated assets.


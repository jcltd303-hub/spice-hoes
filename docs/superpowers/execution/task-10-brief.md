### Task 10: Grounded DM drafting and privacy
**Files:** Create: `spicecore/dms.py`. Tests: `tests/test_dms.py`.
**Interfaces:** DMService.ingest(message: dict) -> dict; draft(message_id: str) -> dict; opt_out(conversation_id: str) -> None; authorize_reply(draft_id: str, policy: dict) -> dict.
**Consumes:** Tasks 1, 2, 4 approved offers, MoA and action gate.
- [ ] Write failing unittest cases: test_cross_customer_memory: cannot retrieve; test_opt_out: suppress even queued reply; test_price_expired: abstain/escalate; test_duplicate_message: one draft; test_unverified_connector: no outbound send; test_dm_injection: cannot invoke tools.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_dms.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Authenticated inbound interface, private per-recipient RAG scope, duplicate suppression, cooldown and opt-out. Voice is witty, selective and luxury-minded; disclose fictional identity and ground offers in approved current facts. Default draft-only. Escalate uncertain age, disputes, sensitive requests, bespoke commitments, unsupported facts. No false availability/exclusivity, fabricated emergencies, guilt or vulnerability targeting. No live connector is fabricated.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: grounded dm drafting and privacy`; exclude secrets, local databases, references and generated assets.


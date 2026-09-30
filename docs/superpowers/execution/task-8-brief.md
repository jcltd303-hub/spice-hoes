### Task 8: Commerce and cohort evidence
**Files:** Create: `spicecore/commerce.py`, `spicecore/experiments.py`. Tests: `tests/test_commerce.py`, `tests/test_experiments.py`.
**Interfaces:** CommerceLedger.import_event(event: dict) -> dict; cohort_report(as_of: str) -> list[dict]; ExperimentPolicy.recommend(arms: list[dict], seed: int) -> dict.
**Consumes:** Existing Store event IDs and Task 3 cost records.
- [ ] Write failing unittest cases: test_duplicate_payment: idempotent; test_profit: 2500 gross -500 fee -500 other costs =1500 contribution; test_payout: payout is not additional sales; test_currency: mixed currencies separated; test_delayed_window: open windows cannot become winners; test_retention: denominator excludes immature cohorts.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_commerce.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Add gross, fees, chargebacks/refunds, inference, rejected production, storage, distribution, labor and separate settled payouts. Migrate existing ledger without interpreting old gross as net. Currency is explicit and reports never sum different currencies. Track pseudonymous cohorts, renewal and repeat purchases, attribution method/window. Comparable arms with closed outcome windows and randomized bounded exploration; clicks cannot create profit. Promote evidence with sample size and uncertainty labels.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: commerce and cohort evidence`; exclude secrets, local databases, references and generated assets.


# Spice Hoes Core Implementation Plan

> For agentic workers: implement the tasks in order and verify the complete loop.

**Goal:** Deliver a runnable five-persona experiment loop with durable evidence, approval, and recommendation.

**Architecture:** Python standard-library CLI and SQLite append-only event store; YAML persona files parsed by PyYAML. Generation and publishing remain manual/import adapters so credentials and unsupported platform APIs are not invented.

**Tech Stack:** Python 3.11+, PyYAML, SQLite, unittest.

**Spec:** `project.md`

## Global Constraints

- Five original adults mapped to Scary, Sporty, Baby, Ginger, Posh.
- No autonomous public publishing or private messaging without platform integration and approval.
- Keep action context, policy version, probability, reward, and asset provenance.
- Keep all data local by default; no secret in source control.

## Review Focus

- Duplicate external event IDs must not double-count purchases.
- A rejected candidate must not be approved later without an explicit new revision.
- A candidate cannot publish before approval.
- Empty observations should keep five-way exploration.
- A recommendation must use observed net outcomes, not raw clicks alone.

### Task 1: Persona registry and evidence store

**Files:** `personas/*.yaml`, `spicecore/core.py`, `tests/test_core.py`

**Interfaces:** `load_personas(path)`, `Store(db_path)`, `Store.record_event(kind, payload, external_id=None)`.

- [ ] Add tests for five personas, valid adult ages, unique IDs, and duplicate event IDs.
- [ ] Implement YAML loading and SQLite event/candidate tables.
- [ ] Run `python -m unittest discover -s tests -v`.

### Task 2: Review and event-based experiment scoring

**Files:** `spicecore/core.py`, `tests/test_core.py`

**Interfaces:** `Store.propose`, `Store.review`, `Store.publish`, `Store.record_outcome`, `Store.stats`.

- [ ] Add tests for review transitions, publish gate, and revenue-cost-refund score.
- [ ] Implement durable state transitions and event emission in one transaction.
- [ ] Run tests.

### Task 3: Decision engine and CLI

**Files:** `spicecore/policy.py`, `spicecore/cli.py`, `tests/test_policy.py`, `README.md`

**Interfaces:** `recommend(stats, seed, exploration=0.30)`, CLI `init`, `propose`, `review`, `publish`, `outcome`, `recommend`, `events`.

- [ ] Test unobserved exploration, seeded reproducibility, and preference for a profitable arm.
- [ ] Implement a smoothed epsilon-greedy policy with logged selection probabilities and uncertainty ranges.
- [ ] Exercise CLI end to end and document exact commands.

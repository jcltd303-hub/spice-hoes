# SDD ledger — plan: docs/superpowers/plans/2026-09-30-azure-localdream-moa.md

Baseline local 9855f52 / upstream a5b0fa9; implementation/azure-localdream-moa. Reviewed Tasks 1–4 remote checkpoint1f5afcc. Runtime outage interrupted Task5; ROOT sole tree/commit/ref writer, agents blob-only. Reports/briefs migrate here to preserve reviewability.

## Preflight task self-consistency
|Task|Files/tests agreement|Finding|
|---|---|---|
|1|Owned behavioral tests agree with public contract.|Existing cli.py must extend, not recreate.|
|2|Owned behavioral tests agree with public contract.|No internal conflict.|
|3|Owned behavioral tests agree with public contract.|No internal conflict.|
|4|Owned behavioral tests agree with public contract.|No internal conflict.|
|5|Owned behavioral tests agree with public contract.|No internal conflict.|
|6|Owned behavioral tests agree with public contract.|No internal conflict.|
|7|Owned behavioral tests agree with public contract.|No internal conflict.|
|8|Owned behavioral tests agree with public contract.|No internal conflict.|
|9|Owned behavioral tests agree with public contract.|No internal conflict.|
|10|Owned behavioral tests agree with public contract.|No internal conflict.|
|11|Owned behavioral tests agree with public contract.|Existing cli.py must extend, not recreate.|
|12|Owned behavioral tests agree with public contract.|Missing implementation module; add live_preflight.py.|

## Shared interface preflight
|Tasks|Producer/consumer|Finding|
|---|---|---|
|1, 2|Task 1 contract consumed by 2|Compatible staged interface; preserve API and fail closed.|
|1, 7|Task 1 contract consumed by 7|Compatible staged interface; preserve API and fail closed.|
|1, 9|Task 1 contract consumed by 9|Compatible staged interface; preserve API and fail closed.|
|1, 10|Task 1 contract consumed by 10|Compatible staged interface; preserve API and fail closed.|
|1, 11|Task 1 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|2, 3|Task 2 contract consumed by 3|Compatible staged interface; preserve API and fail closed.|
|2, 9|Task 2 contract consumed by 9|Compatible staged interface; preserve API and fail closed.|
|2, 10|Task 2 contract consumed by 10|Compatible staged interface; preserve API and fail closed.|
|2, 11|Task 2 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|3, 4|Task 3 contract consumed by 4|Compatible staged interface; preserve API and fail closed.|
|3, 6|Task 3 contract consumed by 6|Compatible staged interface; preserve API and fail closed.|
|3, 8|Task 3 contract consumed by 8|Compatible staged interface; preserve API and fail closed.|
|3, 11|Task 3 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|3, 12|Task 3 contract consumed by 12|Compatible staged interface; preserve API and fail closed.|
|4, 5|Task 4 contract consumed by 5|Compatible staged interface; preserve API and fail closed.|
|4, 6|Task 4 contract consumed by 6|Compatible staged interface; preserve API and fail closed.|
|4, 7|Task 4 contract consumed by 7|Compatible staged interface; preserve API and fail closed.|
|4, 9|Task 4 contract consumed by 9|Compatible staged interface; preserve API and fail closed.|
|4, 10|Task 4 contract consumed by 10|Compatible staged interface; preserve API and fail closed.|
|4, 11|Task 4 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|4, 12|Task 4 contract consumed by 12|Compatible staged interface; preserve API and fail closed.|
|5, 6|Task 5 contract consumed by 6|Compatible staged interface; preserve API and fail closed.|
|5, 11|Task 5 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|5, 12|Task 5 contract consumed by 12|Compatible staged interface; preserve API and fail closed.|
|6, 7|Task 6 contract consumed by 7|Compatible staged interface; preserve API and fail closed.|
|6, 11|Task 6 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|6, 12|Task 6 contract consumed by 12|Compatible staged interface; preserve API and fail closed.|
|7, 9|Task 7 contract consumed by 9|Compatible staged interface; preserve API and fail closed.|
|7, 11|Task 7 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|7, 12|Task 7 contract consumed by 12|Compatible staged interface; preserve API and fail closed.|
|8, 9|Task 8 contract consumed by 9|Compatible staged interface; preserve API and fail closed.|
|8, 11|Task 8 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|9, 11|Task 9 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|9, 12|Task 9 contract consumed by 12|Compatible staged interface; preserve API and fail closed.|
|10, 11|Task 10 contract consumed by 11|Compatible staged interface; preserve API and fail closed.|
|10, 12|Task 10 contract consumed by 12|Compatible staged interface; preserve API and fail closed.|
|11, 12|Task 11 contract consumed by 12|Compatible staged interface; preserve API and fail closed.|

## Rulings (chronological)
Ruling: Extend existing cli.py in Tasks 1/11 — preserve local commands — wrong interpretation costs CLI integration rework.
Ruling: Add spicecore/live_preflight.py for Task12 — plan omits implementation module — wrong placement costs module move.
Ruling: Task6 real Azure adapters with fail-closed deployment gating; live receipts blocked — absent credentials cannot justify simulation — wrong SDK costs adapter rework.
Ruling: Preserve local workspace until root reads reports/rulings — explicitly required reviewability — costs ignored temporary disk.
Ruling: Route research/creative/commerce to same specialist plus persona, persona to persona+research; unknown types rejected — relevant roles with two proposers — costs role-map adjustment if wrong.
Ruling: max_attempts means total attempts, defaults two/30 seconds/1024 output tokens, required bounded input/per-attempt cents — prevent off-by-one budgets — costs interface adjustment.
Ruling: Require durable SQLite audit or explicit sink and conservatively charge missing usage — no silently lost records/undercharge — costs audit adapter rework.
Ruling: Azure adapter one attempt/no reservation, MoA retries/reserve/settle, SDK failures charge invalid output — prevent multiplication — costs accounting adapter rework.
Ruling: MoA supplies run/reservation IDs and adapter validates active funds — direct-call bypass otherwise — costs small cross-module adjustment.
Ruling: ActionGate runtime/ledger injected and live eligibility/reservation checked every authorization/replay — task consumes budget guards — costs downstream wiring.
Ruling: Decode documented Local Dream raw RGB and encode bounded validated PNG — official API differs from assumed encoded image — costs installed-version decoder adjustment.
Ruling: Continue through GitHub source blobs/ROOT commits and existing Actions CI after shared exec-server outage; preserve public execution reports in branch — authorized reversible source work remains possible — costs extra source/report commits and slower CI feedback.
Ruling: Phone historical checkpoint may report reconciliation_pending until authenticated cloud finalization — never regenerate or claim unsupported recovery success — costs operator recovery until adapter implemented.

## Execution
Task 1: complete (local9855f52..890eb06, review clean; remote314c801).
Task 1: minor (deferred): populated-vector deletion regression coverage; final reviewer triage.
Task 2: complete (local890eb06..78af97f, review clean).
Task 2: minor (deferred): external cancellation terminal audit; route tests research-only.
Task 2: cannot-verify resolved: provider guards Task3; filtered knowledge Task1; explicit audit sink contract/file store.
Task 3: fix round1/5 (2 addressed, 0 open; local1e3486e..a05939e): cap binding and full usage overrun charging/halt; midnight attribution also fixed.
Task 3: complete (local78af97f..a05939e, review clean).
Task 3: production validate_reservation owner_cap_cents, consume=True and record_overrun/settle contract assigned Task6; live pricing/account validity blocked Task12.
Task 4: fix round1/5 (3 addressed, 0 open; local870a481..5288d15): completion artifact conflict, stale mode receipt, live runtime/reservation guards.
Task 4: complete (locala05939e..5288d15, review clean).
Task 4: heartbeat assigned Task5; specialist inference-only model interface established Task2; individual live prerequisites covered.
Task 5: in progress; local pending operations terminated, remote blob implementation. ROOT parent1f5afccf905500681f8816ed950cc63b31d916c2. No confirmed Task5 local writes/commit.

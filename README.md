# Spice Hoes experiment core

This is a runnable local loop from [project.md](project.md). It contains five **fictional adult** YAML personas, a local SQLite evidence ledger, generated creative briefs, a browser review queue, an approval gate, and an exploratory recommendation policy. It does not create images, email reviewers, publish posts, or message anyone automatically. Those integrations need real accounts, credentials, provider terms, and verified content workflows.

## Start locally

Requires Python 3.11+ and PyYAML:

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m spicecore.cli init
python3 -m spicecore.cli recommend --seed 42
python3 -m spicecore.cli briefs --theme outfit-choice --channel Instagram --seed 42
python3 -m spicecore.cli serve
```

`serve` prints a loopback URL with a random token. Open that exact URL on the same machine to see the queue and record approve/revise/reject decisions. It is a **local operator tool**, not a public deployment target. On another device, run it in a development environment with an appropriately authenticated tunnel; do not expose the tokenized page directly to the Internet.

Import a generated candidate by referring to an asset URI. Replace the example values with your own approved platform and real post URL:

```bash
python3 -m spicecore.cli propose --persona zara_voss --theme city-nights --format still --channel test --offer set --asset-uri assets/example.png --prompt 'Original adult character on a neon street' --model manual --seed 12 --cost-cents 20
python3 -m spicecore.cli review CANDIDATE_ID approved --reviewer operator
python3 -m spicecore.cli publish CANDIDATE_ID --url https://example.org/post
python3 -m spicecore.cli outcome CANDIDATE_ID impression --external-id impression-1
python3 -m spicecore.cli outcome CANDIDATE_ID purchase --amount-cents 500 --external-id payment-1
python3 -m spicecore.cli stats
python3 -m spicecore.cli recommend --seed 43
python3 -m spicecore.cli events
```

Creative briefs are hypotheses for an external generator or a human creator. `propose` records the prompt, model, seed, asset URI, and cost once an asset exists. Candidate IDs come from `propose`; the `data/` SQLite database stays on your machine unless you deliberately copy it. Use unique external IDs to make payment imports idempotent. The append-only event record is local experiment evidence; do not import private messages or payment card data into it. Its current policy is a heuristic with no calibrated uncertainty estimate. Recommendations are proposals for human approval and do not trigger posting.

## Boundaries and next adapters

Add a generation adapter and asset-quality review, an authenticated review app with email notifications, approved distribution integrations, and a private cloud object store. Preserve the `policy_decision` event so changes can be audited. GitHub Actions may test the code and run small scheduled imports; it is not a production database or persistent worker. Keep credentials and private content outside the repository.

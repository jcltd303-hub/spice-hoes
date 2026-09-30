# Spice Hoes experiment core

This is a runnable local loop from [project.md](project.md). It contains five **fictional adult** YAML personas, a local SQLite evidence ledger, generated creative briefs, a browser review queue, an approval gate, and an exploratory recommendation policy. The default production path now follows the guide's free stack. Browser-only generators are emitted as auditable jobs rather than treated as imaginary APIs; local assembly is automated with FFmpeg. Publishing and account actions still require approved platform integrations and credentials.

## Start locally

Requires Python 3.11+ and PyYAML:

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 -m spicecore.cli init
python3 -m spicecore.cli recommend --seed 42
python3 -m spicecore.cli briefs --theme outfit-choice --channel Instagram --seed 42
python3 -m spicecore.cli free-plan --theme outfit-choice --channel TikTok --seed 42
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


## Free production stack

`free-plan` materializes one JSON job per persona under `jobs/`. The default route mirrors the source guide's zero-cost workflow:

1. Local Dream on the S24 Ultra — primary still generation over its loopback HTTP/SSE API.
2. Local Dream/native on-device processing — keep image production and available upscaling on the phone.
3. Google Flow / VEO 3.1 Fast — Frames-to-Video motion. Pass `--avatar` to substitute Pavo AI for a free talking-avatar route.
4. FFmpeg — local clip joining and caption burn-in.
5. n8n Community Edition — self-hosted task/approval/publishing handoff orchestration.

Example:

```bash
python3 -m spicecore.cli free-plan --theme city-nights --channel TikTok --persona zara_voss --output-dir jobs
python3 -m spicecore.cli free-plan --theme talking-head --channel TikTok --persona zara_voss --avatar
```

All generated production stages declare `cost_cents: 0`. This means **tooling cost in the planner**, not a guarantee that a third-party service will remain free or available. The paid Higgsfield, ElevenLabs, and Fal.ai routes are no longer required by the core architecture.

## Evidence-driven next batch

The complete local planning path is now one command:

```bash
python3 -m spicecore.cli next-batch --theme city-nights --channel TikTok --seed 42 --output-dir jobs
```

It reads the SQLite outcome ledger, selects an experiment with the logged exploration policy, retrieves relevant local project/persona knowledge, runs the four-lens MoA planner, and writes the free production manifest. The manifest remains `awaiting_generation`; generation and publication do not bypass the existing review gate. Use `--avatar` to choose the Pavo talking-avatar production route.

The current learner is intentionally a contextual allocation heuristic rather than a claimed deep-RL model. Every planned batch and observed outcome creates the trajectory data needed to evaluate a future longer-horizon policy against this baseline.

## Local Dream HTTP production

After opening Local Dream and selecting/loading a model, its backend is available at `http://127.0.0.1:8081`. From Termux on the same phone:

```bash
export LOCAL_DREAM_URL=http://127.0.0.1:8081
python3 -m spicecore.cli generate-local --prompt "production portrait prompt" --output assets/test.png --size 1024 --steps 8 --cfg 1 --seed 42
```

For a computer connected through ADB, first run `adb forward tcp:8081 tcp:8081` and use the same URL. The adapter calls `POST /generate`, consumes the SSE progress/completion stream, writes the returned image to PNG, and records generation lineage in the experiment ledger. Model-specific size/steps/CFG should follow the loaded Local Dream model; the CLI values are explicit and overrideable.

# Master reference packs

Master references are built in two stages so the generator never silently replaces a persona's canonical identity.

## 1. Build a staged pack

```bash
export LOCAL_DREAM_URL='http://127.0.0.1:7860'

python3 -m spicecore.reference_cli build \
  --persona zara_voss \
  --seed 1000
```

The builder:

1. Generates three front-facing candidates.
2. Scores each candidate against the other two and selects the identity-consensus medoid.
3. Uses that selected front portrait as the conditioning anchor.
4. Generates two attempts for each remaining reference view.
5. Keeps the highest identity-scored attempt per view.
6. Requires every selected view to meet the identity threshold before the pack is eligible for promotion.

The six canonical views are front, left profile, right profile, hair/back view, eye close-up, and full body.

Staged files and `manifest.json` are written below:

```text
data/reference_candidates/<persona_id>/<run_id>/
```

The event ledger receives `master_reference_pack_proposed`.

## 2. Promote an approved pack

Review the staged images, then promote the manifest:

```bash
python3 -m spicecore.reference_cli promote \
  data/reference_candidates/zara_voss/RUN_ID/manifest.json
```

Promotion installs the selected six-view pack under:

```text
data/references/<persona_id>/
```

Future asset generation automatically loads that directory for reference conditioning and identity gating.

Promotion is refused if any selected view is below the configured identity threshold. The event ledger receives `master_reference_pack_promoted`.

## Tuning

The defaults are conservative:

```text
identity threshold: 0.84
reference strength: 0.90
front anchor candidates: 3
attempts per remaining view: 2
```

Increase candidate/attempt counts for difficult identities at the cost of more local generation time.

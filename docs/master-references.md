# Master reference packs

Master references serve two different jobs and must not be conflated:

1. **Visual conditioning** — preserve hair, face, body proportions, styling, and outfit continuity across generation.
2. **Identity gating** — provide reliable face embeddings for SCRFD + ArcFace numerical verification.

The uploaded influencer guide recommends a multi-angle master character board. This project keeps that idea, but the production gate only uses images that produce stable face detections and embeddings.

## Canonical six-view visual board

Maintain these visual references for each persona:

- front portrait
- left profile
- right profile
- hair/back view
- eye/detail close-up
- full body / outfit

These images may all condition generation, but they are **not automatically all ArcFace gate references**. Back views, extreme profiles, and detail crops commonly fail face detection or distort similarity.

Store promoted references under:

```text
data/references/<persona_id>/
```

Do not commit private identity packs to the public repository.

## Production identity path

The canonical media/identity path is native S24 Go/QNN:

```text
persona YAML
  -> prompt + reference conditioning
  -> QNN generate
  -> SCRFD face detect
  -> 5-point align
  -> ArcFace embed
  -> reference comparison
  -> quality score
  -> accept/retry/reject
  -> save image + metadata
```

Use face-detectable, stable references for the ArcFace gate pack. Keep non-face visual references available for conditioning only.

## Build and review workflow

1. Generate several front-facing candidates.
2. Select a visually correct adult fictional identity.
3. Generate the remaining canonical views from that anchor.
4. Run every face-detectable candidate through the production SCRFD + ArcFace path.
5. Separate conditioning-only images from identity-gate images.
6. Calibrate thresholds with `spicecalibrate`.
7. Human-review the board and promote it to `data/references/<persona_id>/`.
8. Record the promoted pack/version in the evidence ledger.

A reference pack is not considered locked merely because all images look similar to a human reviewer; the numerical gate must also be calibrated against same-person and impostor distributions.

## Calibration

Run:

```bash
go run ./cmd/spicecalibrate -root data/references -out calibration.json
```

See [identity-calibration.md](identity-calibration.md).

Do not use the old hard-coded `0.84` identity threshold as a universal default. Thresholds are model-, crop-, and reference-pack-specific.

## Legacy builder

The historical Python `spicecore.reference_cli` / Local Dream reference builder may still be useful for comparison or migration. It is not the canonical production path. New documentation and acceptance criteria should target the native `spicemedia` + QNN + SCRFD + ArcFace pipeline described in [architecture.md](architecture.md).

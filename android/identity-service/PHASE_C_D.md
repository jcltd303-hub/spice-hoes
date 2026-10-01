# Phase C/D — Identity inference

## Hard gates

Production identity inference is split into three independent gates:

1. **Generator rights** — exact model weights must permit the intended commercial use.
2. **Runtime compatibility** — the exact graph must execute correctly on Android and preserve target composition.
3. **Acceleration proof** — QNN/HTP must actually execute inference before the API reports `accelerated=true`.

A permissive source-code license alone does not clear model weights.

## Current generator candidate

`ghost_1_256.onnx` from the ai-forever Ghost family is the current candidate. FaceFusion's current model registry labels `ghost_1_256` vendor `ai-forever` and license `Apache-2.0`. The exact artifact used by Spice still requires checksum and upstream weight-license verification before `commercialUse` may become true.

Rejected for the commercial production path unless separately licensed:
- InsightFace INSwapper — non-commercial model license.
- SimSwap — academic/non-commercial.
- HyperSwap 1a — ResearchRAIL.
- HyperSwap 1b/1c — commercial rights not confirmed.

## Android execution

Do not revive the Termux PyTorch path. The intended production route is an ONNX graph executed inside the Android application.

Target provider order:
1. QNN HTP/NPU
2. QNN GPU where useful
3. NNAPI/vendor fallback
4. CPU/reference fallback

Android QNN requires a custom ONNX Runtime/QNN build and Qualcomm AI Engine Direct SDK build inputs. Proprietary SDK files must not be committed.

## Truthful health semantics

Until the real graph is loaded and transfer succeeds:
- `identity_applied=false`
- `accelerated=false`

After CPU/reference transfer succeeds:
- `identity_applied=true`
- `accelerated=false`

Only after an accelerated self-test and transfer succeed:
- `identity_applied=true`
- `accelerated=true`

## Identity QA

A separate identity embedding model should score canonical-reference/output similarity. MobileFaceNet is the current QA candidate. It is not the generator.

## Acceptance

Canonical reference A + target scene B must produce C where:
- dimensions(C) == dimensions(B)
- scene/pose/clothing/background remain governed by B
- identity similarity(C, A) improves over similarity(B, A)
- output is not byte-identical to B
- model ID/SHA/provider/timings are recorded

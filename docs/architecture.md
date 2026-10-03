# Canonical architecture

**Status:** current implementation map · **Updated:** 2026-10-02

This document reconciles the project proposal, operator README, identity docs, and the uploaded AI-influencer production guide. When implementation details disagree with older notes, use this document plus the code on `main`.

## Source-of-truth order

1. `project.md` — objective, constraints, experiment policy, portfolio model.
2. `docs/architecture.md` — current technical architecture and responsibility boundaries.
3. `README.md` — runnable operator commands.
4. `docs/master-references.md` and `docs/identity-calibration.md` — identity/reference procedures.
5. Persona YAML under `personas/` — versioned fictional canon.
6. `docs/celeste-textual-inversion.md` and historical Superpowers plans — optional/legacy implementation notes, not production architecture.

The uploaded influencer guide is research input. Its character-consistency, vertical-content, voice-consistency, automation, and monetization ideas become hypotheses in the evidence/RAG system; named third-party tools in that guide are not production dependencies unless explicitly adopted and measured.

## Objective

Optimize attributable **net revenue**, not raw engagement:

```text
reward =
  attributable revenue
  - production cost
  - distribution cost
  - refunds
  - variable commerce cost
  + measured longer-horizon repeat/retention value
```

Clicks, watch time, replies, and follows are intermediate signals. They may help predict revenue but do not replace it.

Every recommendation must retain evidence/provenance, uncertainty, policy/model version, and the observation that would change the recommendation. The system does not fabricate hidden chain-of-thought.

## Current end-to-end loop

```text
signals + approved RAG knowledge + persona YAML
        |
        v
Mixture of Agents
(revenue / creative / growth / risk -> aggregator)
        |
        v
experiment proposal + offer + channel + content brief
        |
        v
human/runtime policy gate
        |
        v
S24 media lane
persona YAML -> prompt -> QNN generate
             -> SCRFD face detect
             -> 5-point align
             -> ArcFace embed
             -> reference comparison
             -> quality score
             -> save image + metadata
        |
        v
review -> approved publishing queue -> permitted platform adapter
        |
        v
impressions / engagement / purchase / refund / repeat outcome
        |
        v
SQLite evidence ledger + RAG summary
        |
        +--> contextual bandit (early allocation)
        |
        `--> gated DeepRL once minimum trustworthy experience is reached
```

## Responsibility boundaries

| Layer | Canonical responsibility |
| --- | --- |
| Persona registry | Versioned fictional biography, adult status, voice, visual anchors, boundaries, offers. |
| RAG/evidence | Approved knowledge, source provenance, experiment summaries, retrieval references. |
| MoA | Independent revenue, creative, growth, and risk proposals; aggregator produces a recommendation. |
| Policy | Immutable/versioned limits for budget, queue size, learning thresholds, identity, quality, and reference strength. |
| S24 media runtime | Native Go orchestration plus QNN/HTP generation and face inference. |
| Identity verification | SCRFD -> five-point alignment -> ArcFace -> calibrated similarity gates. |
| Review | Human approve/revise/reject before release. |
| Distribution | Platform-permitted publish/send adapters; separated from generation and review. |
| Commerce/outcomes | Idempotent attribution for clicks, purchases, costs, refunds, repeat behavior. |
| Learning | Contextual bandit first; DQN-style DeepRL only after the configured evidence threshold. |
| Infrastructure | Durable/private services where local execution is insufficient; adapters remain portable. |

## Device vs cloud

### S24 Ultra: media and identity lane

The canonical media path is native:

```text
bin/spicemedia (Go)
  -> runtime/bin/spice-qnn-core (C++)
  -> Qualcomm QNN / Hexagon HTP
```

Production face identity uses the same device lane:

```text
SCRFD detection -> five landmarks -> aligned crop -> ArcFace embedding -> calibrated comparison
```

No Python runtime is required on the phone. Python is permitted in CI/model-conversion and offline analysis workflows.

### Durable control-plane capacity

When durable/private infrastructure is needed, use authenticated APIs, queues/workers, private object storage, scheduled jobs, and explicitly adopted model endpoints behind replaceable interfaces. No single cloud provider is part of the canonical architecture.

GitHub remains source control/CI. Vercel/Pages-style hosting may be used only where its current plan and terms fit the workload; it is not the system of record.

## Identity consistency

The guide's multi-angle character board maps to two separate artifacts:

1. **Visual conditioning board** — front, left/right profile, hair/back, eye/detail, and full-body/outfit references for appearance continuity.
2. **ArcFace gate pack** — face-detectable, identity-stable references used for numerical similarity. Profile/back/detail images that do not produce reliable face embeddings are conditioning references, not gate references.

The canonical generation/verification path is:

```text
persona YAML
  -> prompt + reference conditioning
  -> QNN generation
  -> SCRFD
  -> 5-point alignment
  -> ArcFace embedding
  -> max/mean reference comparison
  -> quality scoring
  -> accept/retry/reject
  -> image + sidecar metadata + ledger event
```

Thresholds are empirical. Use `spicecalibrate`; do not copy generic similarity values from old docs.

## Content and monetization hypotheses

The uploaded guide reports strong performance for talking-head advice, mirror/outfit videos, product demonstrations/unboxings, POV product clips, localized cultural content, affiliate commerce, digital products, sponsorship/UGC, and subscriptions. In this project these are **testable hypotheses**, not guaranteed winners.

Store guide-derived claims in RAG with source labels, then test them through the same attribution loop. Do not hard-code third-party benchmark revenue as expected project revenue.

## Engagement

Persona voice can be warm, selective, aspirational, and commercially aware, but monetization cannot depend on deceptive claims of being human, coercive spending pressure, implying that payment proves affection, or soliciting banking/card data. Inbound replies remain reviewable and attributable to the same evidence system.

## Learning policy

The contextual bandit remains the default allocation policy while data is sparse. DeepRL is enabled only after the runtime policy's minimum experience threshold is met and transitions contain trustworthy observed outcomes.

The learner may optimize within the eligible action set; it cannot silently change the reward function, historical evidence, disclosure requirements, permissions, or safety boundaries.

## Legacy/optional paths

Local Dream, textual inversion, InSwapper experiments, and third-party generation stacks may remain useful for benchmarking, migration, or offline comparison. They are not the canonical production media path unless a later measured experiment and explicit architecture update promotes them.

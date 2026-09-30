# Profit-first learning loop

The learning layer treats views, likes and followers as diagnostics rather than the business objective.

## Policy
1. Build experiment arms from persona × geo/language × format × offer × revenue model.
2. Start with bounded contextual exploration. Default exploration is 15%.
3. Reward attributed contribution margin: revenue minus refunds, production/inference/distribution costs and explicit risk cost. Predicted LTV is discounted. Engagement shaping is capped at 25 cents per experience.
4. Reallocate budget toward demonstrated contribution while retaining an exploration floor.
5. Deep-RL stays disabled until the configured minimum number of mature, attributed rewards exists. Offline tests or raw engagement never unlock it.
6. When enabled, train/evaluate sequential policies offline first. Promotion to online policy requires a versioned acceptance receipt and the existing owner/action gates.

## Source priors
Initial format priors should include talking-head, mirror/outfit and POV/unboxing experiments. Monetization heads should include affiliate, digital products, sponsorship/UGC and subscription. These are priors only; observed attributed economics supersede them.

## Required event lineage
Every reward must be traceable: commerce event -> candidate/post -> campaign/experiment -> arm -> persona/offer -> generation/model run. Cross-currency values are not combined without an explicit FX normalization record.

## Deep-RL state/action contract
State: persona, audience, platform, geo/language, recent outcomes, offer economics, funnel/cohort state, model cost/availability and retrieved scoped evidence.
Action: topic/hook/format, CTA/offer, platform/time, model route and bounded generation/distribution budget.

# Spice Hoes — Project Proposal

**Status:** design proposal · **Date:** 2026-09-25

## Aim

Create a portfolio of fictional, clearly disclosed adult AI influencers and a learning system that discovers which personas, content, channels, and offers produce sustainable net revenue. Welcome varied adult audiences while retaining one measurable objective: make money by creating influence, with repeat customers and costs included in the score.

The five starting characters are hypotheses. Their biographies are invented creative canon, not conclusions drawn from market data. The system measures whether each idea works and evolves the portfolio accordingly.

## Operating loop

1. **Observe:** Collect permitted public signals and first-party results. Keep the raw source, collection date, provenance, and usage rights.
2. **Propose:** Generate candidate persona changes, content themes, formats, channels, schedules, and offers.
3. **Produce:** Generate assets and copy with versioned prompts, seeds, models, and reference material. Use the S24 Ultra only if a measured quality and throughput trial supports it; route other jobs to metered compute.
4. **Review:** Email a preview and approval link. Revisions return to production; approved assets enter a publishing queue.
5. **Publish and engage:** Use each platform's permitted publishing and messaging methods. Keep AI identity clear. Initially review replies and custom requests with a human.
6. **Measure:** Join exposure, engagement, paid conversions, repeat purchases, refunds, costs, and approvals to the originating experiment.
7. **Learn:** Allocate the next opportunities across current winners and new experiments. Retain every result, including failed generations and rejected posts.

## The decision engine

Start with a **contextual bandit** that chooses among eligible experiments: persona × theme × format × channel × offer. Reserve exposure for exploration. Upgrade to longer-horizon reinforcement learning only when there is enough trustworthy longitudinal data to show it improves on simpler policies in held-out or controlled evaluations.

The primary reward is attributable revenue minus production and distribution costs and refunds, evaluated over short and longer windows. Clicks, attention, anticipation, and conversation are useful signals and potential mechanisms; they can predict sales but do not by themselves settle whether an experiment succeeded. Include repeat purchase and customer retention so a tactic that burns trust for a brief spike is measured honestly.

The network's internal reasoning need not be intelligible. **Do not ask it to invent an explanation of its thoughts.** Preserve an auditable decision record: available actions, context, model and policy version, selection probabilities, outcome estimates, uncertainty, chosen action, approval, cost, and observed results. Show what evidence supports a recommendation and which future outcome would reverse its ranking. This is decision accounting, not mind reading.

Keep the objective fixed and versioned by a human owner. The model can propose new metrics, experiments, and reward revisions, but it cannot silently change the scoring rule, edit historical events, or modify its own permissions. Disclosed fictional identities, adult-only audiences, consented outreach, original likenesses, and platform rules define the eligible action set.

## System components

| Component | Responsibility |
| --- | --- |
| Evidence vault | Append-only events; raw assets and source snapshots; provenance, rights, and privacy retention controls. |
| Persona registry | Versioned biography, visual anchors, voice, boundaries, offers, and identity tests. |
| Generation router | Queue jobs to phone or metered providers; record cost, latency, quality, and model lineage. |
| Review desk | Email notification and authenticated approve/revise/reject actions. |
| Distribution adapters | Platform-specific formats, schedules, disclosure, and permitted API operations. |
| Commerce ledger | Attribute purchases, refunds, repeat purchases, and fulfillment cost. |
| Experiment service | Randomized allocation, policy logging, outcome windows, and comparisons. |
| Operator view | Portfolio performance, pending reviews, spend, evidence, and policy changes. |

Keep a stable event schema for `source_collected`, `hypothesis_created`, `asset_generated`, `asset_reviewed`, `content_published`, `exposure_recorded`, `engagement_recorded`, `purchase_recorded`, `refund_recorded`, and `policy_decision`. Each event has an ID, timestamp, persona and experiment IDs where applicable, provenance, and an immutable payload reference. Mark each field as **fictional biography**, **observed**, **inferred**, or **hypothesis**. Keep personal conversation data only where necessary and under an explicit retention policy; an append-only experiment ledger does not imply indefinite retention of private messages.

## Starting portfolio: research the original five, build five new people

The archetypes have specific histories worth learning from. The members' height figures are approximate public reports, not standardized measurements; only some are self-reported. Interests below come from the members' own interviews. The original group [describes the five distinct types](https://thespicegirls.com/about/) as a central part of its appeal.

| Original type | Real member | Approximate reported height | Documented background and interests | Brand lesson |
| --- | --- | --- | --- | --- |
| Scary | Melanie Brown | ~165 cm / 5 ft 5 in; [secondary report](https://www.lifeandstylemag.com/posts/victoria-beckham-height-156695/) | [Mel B describes](https://www.theguardian.com/music/2014/nov/29/mel-b-x-factor) a high-energy childhood in Leeds and being sent to dance classes, where she fell in love with performance. Her bold presence turned an imposed nickname into a confident persona. | Unfiltered energy, directness, movement, and expressive hair can anchor a recognizable character. |
| Sporty | Melanie Chisholm | ~168 cm / 5 ft 6 in; [reported self-description](https://www.celebheights.com/s/Melanie-Chisholm-47709.html) | In a [first-person interview](https://www.vogue.com/article/mel-c-sporty-style-interview), she recalls football, hockey, tennis, netball, dance training, working-class practical sportswear, and early rave culture. | The athletic styling had an authentic everyday origin, rather than being an arbitrary costume. |
| Baby | Emma Bunton | ~155 cm / 5 ft 1 in; [self-reported](https://www.independent.co.uk/arts-entertainment/music/features/emma-bunton-the-q-interview-93281.html) | She [describes](https://people.com/emma-bunton-baby-spice-platforms-spice-girls-audtion-12065105) using platform shoes at her audition to meet a stated height requirement. Her [interview](https://www.theguardian.com/music/2019/mar/23/emma-bunton-interview-the-spice-girls-victoria-bathroom) traces a career through music, radio, and television. | Warmth, sweetness, and a memorable silhouette made her instantly legible; for this adult project, translate warmth without childlike sexual styling. |
| Ginger | Geri Halliwell | ~155 cm / 5 ft 1 in; [public listing](https://www.imdb.com/name/nm0001312/bio/), not independently verified | Geri [describes](https://www.cbsnews.com/news/spice-girl-geri-halliwell-horner-journey-pop-star-bestselling-author/) studying literature and loving reading and writing before music. Her [memoir description](https://books.google.com/books/about/If_Only.html?id=90EePwAACAAJ) recounts a modest Watford upbringing and multiple auditions before the band. | Strong opinions, a vivid symbolic look, and storytelling can connect individual posts into a larger narrative. |
| Posh | Victoria Beckham | ~163 cm / 5 ft 4 in; [Vogue profile](https://www.vogue.com/article/victoria-beckham-the-victoria-line) | Victoria describes deliberate, flattering silhouettes and a disciplined move into fashion design in her [Vogue interview](https://www.vogue.com/article/victoria-beckham-the-victoria-line). | A coherent taste level and selective presentation can make each appearance feel like an event. |

**Creative translation:** Borrow the structure of five sharply differentiated roles, their contrast as a group, and the lesson that each persona's look should arise from her own interests. Do not copy the members' personal histories, exact likenesses, signature outfits, voices, or relationships into adult fictional accounts. Changing only their names would leave recognizable impersonations.

| Type | New ID and name | Adult age | Fictional height | Original interests and backstory | First content test |
| --- | --- | ---: | ---: | --- | --- |
| Scary | `zara_voss` — Zara Voss | 29 | 169 cm | High-energy percussionist and night-market organizer; learned to command a room after her first music collective dissolved. | Fast, candid city-night stories and rhythmic performance. |
| Sporty | `tess_wilder` — Tess Wilder | 27 | 171 cm | Climber, rec-league keeper, and retro-game competitor; rebuilt her confidence after a serious team fallout. | Training diaries, playful challenges, and practical gear. |
| Baby | `lila_hart` — Lila Hart | 28 | 160 cm | Warm ceramic artist who hosts dinner parties and grows herbs; moved on from a partner who wanted her to abandon her studio. | Adult pastel lifestyle, pottery reveals, and generous humor. |
| Ginger | `ruby_wren` — Ruby Wren | 30 | 164 cm | Fiery zine writer and amateur astronomer; started publishing after a failed gallery collaboration. | Opinionated miniature essays and bold, colorful visual stories. |
| Posh | `celeste_vale` — Celeste Vale | 32 | 166 cm | Exacting boutique hotel designer and jazz collector; chose an independent practice over a prestigious but controlling employer. | Architecture, tailored styling, and highly curated portraits. |

Each new persona gets a versioned YAML dossier for type, appearance, voice, hobbies, favorites, fictional heartbreak, content pillars, offer hypotheses, and visual references. The five test distinct audience interests; do not spend equally forever. Give each a comparable initial opportunity, then expand or revise according to results with uncertainty and exposure accounted for.

## Infrastructure and budget

**Free tiers first, Azure credits for the gaps.** Keep the orchestration interfaces portable so a free quota ending or a provider changing terms requires an adapter swap, not a rewrite. Use GitHub for source control and Actions for tests, packaging, and scheduled low-volume jobs. Public-repository Actions have free standard runner usage; private repositories have account-specific quotas. Keep identity references, private prompts, customer data, tokens, and generated adult assets out of the repository and build logs. Codespaces' personal monthly allowance is for development sessions, not an always-on production worker.

Host the operator dashboard and small approval API on Cloudflare Pages and Workers Free when its current terms fit the content and workload. Put authenticated approval, signed links, throttling, and idempotent writes in the API. Use Azure Functions and Storage for jobs, private assets, and event records that exceed practical free-host limits, funded by eligible startup credits. GitHub Actions can trigger bounded scheduled batches, but cannot serve as a durable queue, database, private asset store, or interactive API. Keep generation behind a replaceable queue/provider interface.

Use Vercel Hobby only for noncommercial prototypes: its Hobby terms restrict commercial use. Do not make it the production host for this revenue-seeking project without a suitable paid plan. GitHub Pages can host public technical documentation or a demo, but its terms do not allow using it as free hosting for a commercial transaction site or SaaS. This division uses free services where they actually fit rather than betting production on a trial or prohibited use.

Avoid an always-on GPU or large managed database while the budget is $200. Set per-provider request and dollar quotas in the application as well as cloud cost alerts; an alert alone does not stop a charge. Check free-tier limits, content policies, and credit eligibility again when provisioning because they change.

**Initial $200 allocation ceiling:** up to $25 for control plane and storage after free quotas; $90 image generation or phone-versus-cloud trials; $20 text/model calls; $25 one bounded video test; $40 reserve. Unused hosting allocation returns to the reserve. These are planning caps, not provider price quotes. Startup credits, if awarded, extend the experiment but do not justify fixed costs that become unaffordable when credits expire.

The S24 Ultra earns a production role only after a varied, identity-consistency test measures usable outputs, turnaround, thermal behavior, and real cost. It can always serve as an operator review device. There is no assumption that on-device generation meets a photorealistic, identity-locked production spec.

## Delivery sequence

1. Establish the event schema, five YAML dossiers, and comparable experimental briefs.
2. Build the smallest complete loop: generation → review → publication → outcome ingestion → next recommendation.
3. Run balanced tests across five personas and several themes; report sample sizes, costs, uncertainty, and attribution limits.
4. Improve identity consistency and production volume for credible winners. Add video and paid custom fulfillment only after the economics are measured.
5. Add more autonomous decisions and deeper RL only when offline evaluation and controlled live tests justify them.

**First acceptance milestone:** The system completes a round for all five personas and recommends the next batch from recorded outcomes, while the operator can inspect the action ledger and approve every release. No revenue or model-quality result is presumed before the experiment runs.

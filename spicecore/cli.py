"""Command-line entry point for the reviewed experiment and autonomy loop."""

import argparse
import json
import secrets
from http.server import HTTPServer
from pathlib import Path

from .assetgen import AssetGenerator
from .autonomy import AutonomyEngine
from .deeprl import DeepRLPolicy
from .experiments import ExperimentPlanner
from .core import Store, load_personas
from .memory import KnowledgeBase
from .moa import MixtureOfAgents
from .policy import recommend
from .providers import AzureChatProvider, LocalDreamProvider
from .web import make_handler
from .workflow import build_briefs


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spicecore")
    parser.add_argument("--db", default="data/experiments.sqlite")
    parser.add_argument("--personas", default="personas")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("personas")
    sub.add_parser("stats")
    sub.add_parser("events")

    briefs = sub.add_parser("briefs")
    briefs.add_argument("--theme", required=True)
    briefs.add_argument("--channel", required=True)
    briefs.add_argument("--seed", type=int)

    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)

    rec = sub.add_parser("recommend")
    rec.add_argument("--seed", type=int)

    prop = sub.add_parser("propose")
    for field in ("persona", "theme", "format", "channel", "offer"):
        prop.add_argument("--" + field, required=True)
    for field in ("asset-uri", "prompt", "model", "seed"):
        prop.add_argument("--" + field)
    prop.add_argument("--cost-cents", type=int, default=0)

    gen = sub.add_parser("generate")
    gen.add_argument("--persona", required=True)
    gen.add_argument("--theme", required=True)
    gen.add_argument("--channel", required=True)
    gen.add_argument("--offer", required=True)
    gen.add_argument("--scene", default="")
    gen.add_argument("--seed", type=int)
    gen.add_argument("--width", type=int, default=768)
    gen.add_argument("--height", type=int, default=1024)
    gen.add_argument("--cost-cents", type=int, default=0)
    gen.add_argument("--asset-dir", default="data/assets")

    batch = sub.add_parser("generate-batch")
    batch.add_argument("--theme", required=True)
    batch.add_argument("--channel", required=True)
    batch.add_argument("--offer", required=True)
    batch.add_argument("--count-per-persona", type=int, default=1)
    batch.add_argument("--seed", type=int)
    batch.add_argument("--width", type=int, default=768)
    batch.add_argument("--height", type=int, default=1024)
    batch.add_argument("--cost-cents", type=int, default=0)
    batch.add_argument("--asset-dir", default="data/assets")

    review = sub.add_parser("review")
    review.add_argument("candidate_id")
    review.add_argument("decision", choices=("approved", "rejected", "revise"))
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", default="")

    pub = sub.add_parser("publish")
    pub.add_argument("candidate_id")
    pub.add_argument("--url", required=True)

    outcome = sub.add_parser("outcome")
    outcome.add_argument("candidate_id")
    outcome.add_argument("kind", choices=("impression", "click", "purchase", "refund", "distribution_cost"))
    outcome.add_argument("--amount-cents", type=int, default=0)
    outcome.add_argument("--external-id")

    kadd = sub.add_parser("knowledge-add")
    kadd.add_argument("--source", required=True)
    kadd.add_argument("--title", required=True)
    kadd.add_argument("--body", required=True)
    kadd.add_argument("--tags", default="")

    ksearch = sub.add_parser("knowledge-search")
    ksearch.add_argument("query")
    ksearch.add_argument("--limit", type=int, default=6)

    moa = sub.add_parser("moa")
    moa.add_argument("objective")
    moa.add_argument("--persona")

    auto = sub.add_parser("autonomy-cycle")
    auto.add_argument("objective")
    auto.add_argument("--theme", required=True)
    auto.add_argument("--channel", required=True)
    auto.add_argument("--offer", required=True)
    auto.add_argument("--scene", default="")
    auto.add_argument("--seed", type=int)
    auto.add_argument("--cost-cents", type=int, default=0)

    settle = sub.add_parser("autonomy-settle")
    settle.add_argument("cycle_id")
    settle.add_argument("--done", action="store_true")

    rltrain = sub.add_parser("rl-train")
    rltrain.add_argument("--epochs", type=int, default=20)
    rltrain.add_argument("--learning-rate", type=float, default=0.01)

    sub.add_parser("rl-status")

    eplan = sub.add_parser("experiment-plan")
    eplan.add_argument("objective")
    eplan.add_argument("--persona", required=True)
    eplan.add_argument("--channel", required=True)
    eplan.add_argument("--offer", required=True)
    eplan.add_argument("--variants", type=int, default=3)

    erun = sub.add_parser("experiment-run")
    erun.add_argument("plan_id")
    erun.add_argument("--seed", type=int)
    erun.add_argument("--cost-cents-per-asset", type=int, default=0)

    eget = sub.add_parser("experiment-show")
    eget.add_argument("plan_id")

    args = parser.parse_args(argv)
    personas = load_personas(args.personas)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    store = Store(args.db)
    try:
        if args.command == "init":
            output = {"database": args.db, "personas": len(personas)}
        elif args.command == "personas":
            output = personas
        elif args.command == "stats":
            output = store.stats(personas)
        elif args.command == "events":
            output = store.events()
        elif args.command == "briefs":
            output = build_briefs(personas, args.theme, args.channel, args.seed)
        elif args.command == "serve":
            token = secrets.token_urlsafe(24)
            server = HTTPServer(("127.0.0.1", args.port), make_handler(store, personas, token))
            print(f"Local review: http://127.0.0.1:{server.server_port}/?token={token}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return
        elif args.command == "recommend":
            output = recommend(store.stats(personas), seed=args.seed)
            store.record_event("policy_decision", output)
        elif args.command == "propose":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            output = {"candidate_id": store.propose(
                persona, args.theme, args.format, args.channel, args.offer,
                args.asset_uri, args.prompt, args.model, args.seed, args.cost_cents
            )}
        elif args.command == "generate":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            output = AssetGenerator(
                store, provider=LocalDreamProvider(), asset_dir=args.asset_dir
            ).generate(
                persona=persona,
                theme=args.theme,
                channel=args.channel,
                offer=args.offer,
                scene=args.scene,
                seed=args.seed,
                width=args.width,
                height=args.height,
                cost_cents=args.cost_cents,
            )
        elif args.command == "generate-batch":
            output = AssetGenerator(
                store, provider=LocalDreamProvider(), asset_dir=args.asset_dir
            ).batch(
                personas=personas,
                theme=args.theme,
                channel=args.channel,
                offer=args.offer,
                count_per_persona=args.count_per_persona,
                seed=args.seed,
                width=args.width,
                height=args.height,
                cost_cents=args.cost_cents,
            )
        elif args.command == "review":
            output = store.review(args.candidate_id, args.decision, args.reviewer, args.note)
        elif args.command == "publish":
            output = store.publish(args.candidate_id, args.url)
        elif args.command == "outcome":
            output = store.record_outcome(args.candidate_id, args.kind, args.amount_cents, args.external_id)
        elif args.command == "knowledge-add":
            kb = KnowledgeBase(store)
            tags = [x.strip() for x in args.tags.split(",") if x.strip()]
            output = kb.add(args.source, args.title, args.body, tags)
        elif args.command == "knowledge-search":
            output = KnowledgeBase(store).search(args.query, limit=args.limit)
        elif args.command == "moa":
            persona = None
            if args.persona:
                persona = next((p for p in personas if p["id"] == args.persona), None)
                if persona is None:
                    parser.error("Unknown persona")
            output = MixtureOfAgents(AzureChatProvider(), store).deliberate(args.objective, persona)
        elif args.command == "autonomy-cycle":
            engine = AutonomyEngine(
                store,
                personas,
                MixtureOfAgents(AzureChatProvider(), store),
                AssetGenerator(store, provider=LocalDreamProvider()),
            )
            output = engine.run_cycle(
                args.objective,
                args.theme,
                args.channel,
                args.offer,
                scene=args.scene,
                seed=args.seed,
                cost_cents=args.cost_cents,
            )
        elif args.command == "autonomy-settle":
            engine = AutonomyEngine(
                store,
                personas,
                MixtureOfAgents(AzureChatProvider(), store),
                AssetGenerator(store, provider=LocalDreamProvider()),
            )
            output = engine.settle_cycle(args.cycle_id, done=args.done)
        elif args.command == "rl-train":
            policy = DeepRLPolicy(store, [p["id"] for p in personas])
            output = policy.train(
                epochs=args.epochs,
                learning_rate=args.learning_rate,
            )
        elif args.command == "rl-status":
            policy = DeepRLPolicy(store, [p["id"] for p in personas])
            row = store.db.execute(
                "SELECT * FROM rl_policy_snapshot ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            output = {
                "experiences": policy.count(),
                "minimum_experiences": policy.min_experiences,
                "ready": policy.count() >= policy.min_experiences,
                "latest_snapshot": dict(row) if row else None,
            }
        elif args.command == "experiment-plan":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            provider = AzureChatProvider()
            deliberation = MixtureOfAgents(provider, store).deliberate(
                args.objective, persona
            )
            output = ExperimentPlanner(provider, store).plan(
                args.objective,
                persona,
                args.channel,
                args.offer,
                deliberation=deliberation,
                variant_count=args.variants,
            )
        elif args.command == "experiment-run":
            planner = ExperimentPlanner(AzureChatProvider(), store)
            plan = planner.get(args.plan_id)
            persona = next(
                (p for p in personas if p["id"] == plan["persona_id"]),
                None,
            )
            if persona is None:
                parser.error("Plan references unknown persona")
            output = planner.execute(
                plan,
                persona,
                AssetGenerator(store, provider=LocalDreamProvider()),
                base_seed=args.seed,
                cost_cents_per_asset=args.cost_cents_per_asset,
            )
        elif args.command == "experiment-show":
            output = ExperimentPlanner(AzureChatProvider(), store).get(args.plan_id)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    finally:
        store.close()


if __name__ == "__main__":
    main()

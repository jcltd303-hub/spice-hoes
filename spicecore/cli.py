"""Command-line entry point for the reviewed experiment and autonomy loop."""

import argparse
import json
import os
import secrets
import signal
import threading
from http.server import HTTPServer
from pathlib import Path

from .assetgen import AssetGenerator
from .autonomy import AutonomyEngine
from .autopilot import CoreAutopilot
from .deeprl import DeepRLPolicy
from .experiments import ExperimentPlanner
from .engagement import EngagementAgent
from .core import Store, load_personas, OUTCOME_KINDS
from .memory import KnowledgeBase
from .learning import LearningController
from .moa import MixtureOfAgents
from .offers import OfferRegistry, OFFER_KINDS
from .operations import Operations
from .runtime_policy import RuntimePolicy
from .policy import recommend
from .providers import OpenAICompatibleChatProvider, OpenAICompatibleEmbeddingProvider, ProviderError, media_provider
from .web import make_handler
from .workflow import build_briefs
from .distribution.nextdoor import generate_campaign
from .campaign_moa import engineer_campaign
from .gold_digger import dig_report
from .autoresponder import AutoResponder
from .knowledge_audit import audit_knowledge
from .identity_master import (
    PORTRAIT_VIEWS, CENTER_VIEW, ROTATION_VIEWS,
    generate_master_views,
    composite_portrait_board, promote_master,
)
from .ui import SpiceUI
from .media_benchmark import benchmark_media


def _optional_embedder():
    try:
        return OpenAICompatibleEmbeddingProvider()
    except ProviderError:
        return None


def _parse_policy_changes(items):
    changes = {}
    for item in items:
        if "=" not in item:
            raise ValueError("policy changes must use key=value")
        key, raw = item.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if not key:
            raise ValueError("policy key cannot be empty")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        changes[key] = value
    return changes


def _runtime_values(store):
    return RuntimePolicy(store).current()["values"]


def _asset_generator(store, asset_dir="data/assets"):
    values = _runtime_values(store)
    return AssetGenerator(
        store,
        provider=media_provider(),
        asset_dir=asset_dir,
        identity_threshold=values["identity_threshold"],
        reference_strength=values["reference_strength"],
        quality_threshold=values["quality_threshold"],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spicecore")
    parser.add_argument("--db", default="data/experiments.sqlite")
    parser.add_argument("--personas", default="personas")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    parser.add_argument("--no-color", action="store_true", help="disable terminal color")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("personas")
    sub.add_parser("stats")
    sub.add_parser("events")

    briefs = sub.add_parser("briefs")
    briefs.add_argument("--theme", required=True)
    briefs.add_argument("--channel", required=True)
    briefs.add_argument("--seed", type=int)

    camp = sub.add_parser("campaign")
    camp.add_argument("--channel", default="nextdoor", choices=("nextdoor",))
    camp.add_argument("--persona", required=True)
    camp.add_argument("--goal", required=True, help="what the campaign should achieve")
    camp.add_argument("--cause", required=True, help="the cause, offer, or event being promoted")
    camp.add_argument("--neighborhood", required=True)
    camp.add_argument("--offer", default="none", help="offer name or URL; 'none' for no link")
    camp.add_argument("--seed", type=int)
    camp.add_argument("--variants", type=int, default=3, choices=(1, 2, 3))

    cmoa = sub.add_parser("campaign-moa")
    cmoa.add_argument("--persona", required=True)
    cmoa.add_argument("--goal", required=True, help="what the campaign should achieve")
    cmoa.add_argument("--cause", required=True, help="the cause, offer, or event being promoted")
    cmoa.add_argument("--neighborhood", required=True)
    cmoa.add_argument("--offer", default="none", help="offer name or URL; 'none' for no link")
    cmoa.add_argument("--seed", type=int)
    cmoa.add_argument("--variants", type=int, default=3, choices=(1, 2, 3))

    gd = sub.add_parser("gold-digger")
    gd.add_argument("--goal", default=None, help="campaign goal prefix to filter candidates")
    gd.add_argument("--channel", default="nextdoor", choices=("nextdoor",))
    gd.add_argument("--seed", type=int)
    gd.add_argument("--min-impressions", type=int, default=100)

    ar = sub.add_parser("auto-respond")
    ar.add_argument("--persona", required=True)
    ar.add_argument("--channel", default=None)
    ar.add_argument("--conversation-id", default=None)
    ar.add_argument("--message-id", default=None)
    ar.add_argument("--body", default=None)
    ar.add_argument("--poll", action="store_true",
                    help="process all inbound messages with no draft yet")
    ar.add_argument("--limit", type=int, default=50)
    ar.add_argument("--max-per-day", type=int, default=10)

    ka = sub.add_parser("knowledge-audit")
    ka.add_argument("--stale-days", type=int, default=180)
    ka.add_argument("--probes", default="",
                    help="semicolon-separated probe queries; default: most common tags")
    ka.add_argument("--max-probes", type=int, default=5)

    im = sub.add_parser("identity-master")
    im.add_argument("--persona", required=True)
    im.add_argument("--seed", type=int)
    im.add_argument("--size", type=int, default=1024)
    im.add_argument("--out", default=None,
                    help="output dir for views+board; default data/identity-masters/<persona_id>")
    im.add_argument("--reference-root", default="data/references")
    im.add_argument("--no-promote", action="store_true",
                    help="generate and composite only; skip identity gating and promotion")
    im.add_argument("--identity-threshold", type=float, default=0.82)

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
    outcome.add_argument("kind", choices=OUTCOME_KINDS)
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

    kbackfill = sub.add_parser("knowledge-backfill")
    kbackfill.add_argument("--limit", type=int)

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

    eres = sub.add_parser("experiment-results")
    eres.add_argument("plan_id")

    ap = sub.add_parser("autopilot-run")
    ap.add_argument("objective")
    ap.add_argument("--channel", required=True)
    ap.add_argument("--offer", required=True)
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--cost-cents-per-asset", type=int, default=0)
    ap.add_argument("--max-pending-review", type=int)
    ap.add_argument("--daily-budget-cents", type=int)

    apsettle = sub.add_parser("autopilot-settle")
    apsettle.add_argument("run_id")
    apsettle.add_argument("--min-impressions", type=int)

    sub.add_parser("autopilot-status")

    bench = sub.add_parser("media-benchmark")
    bench.add_argument("--prompt", required=True)
    bench.add_argument("--negative-prompt", default="")
    bench.add_argument("--seed", type=int, default=42)
    bench.add_argument("--width", type=int, default=768)
    bench.add_argument("--height", type=int, default=1024)

    eingest = sub.add_parser("engagement-ingest")
    eingest.add_argument("--persona", required=True)
    eingest.add_argument("--channel", required=True)
    eingest.add_argument("--conversation-id", required=True)
    eingest.add_argument("--message-id", required=True)
    eingest.add_argument("--body", required=True)

    edraft = sub.add_parser("engagement-draft")
    edraft.add_argument("--persona", required=True)
    edraft.add_argument("--message-id", required=True)

    ereview = sub.add_parser("engagement-review")
    ereview.add_argument("draft_id")
    ereview.add_argument("decision", choices=("approved", "rejected", "revise"))
    ereview.add_argument("--reviewer", required=True)
    ereview.add_argument("--note", default="")

    eoutbox = sub.add_parser("engagement-outbox")
    eoutbox.add_argument("--limit", type=int, default=50)

    ocreate = sub.add_parser("offer-create")
    ocreate.add_argument("--name", required=True)
    ocreate.add_argument("--kind", required=True, choices=sorted(OFFER_KINDS))
    ocreate.add_argument("--expected-payout-cents", type=int, default=0)
    ocreate.add_argument("--variable-cost-cents", type=int, default=0)

    oregister = sub.add_parser("offer-register")
    oregister.add_argument("candidate_id")
    oregister.add_argument("offer_id")
    oregister.add_argument("--url", required=True)

    oevent = sub.add_parser("offer-event")
    oevent.add_argument("tracking_token")
    oevent.add_argument("kind", choices=("click", "purchase", "refund"))
    oevent.add_argument("--external-id", required=True)
    oevent.add_argument("--amount-cents", type=int)

    operf = sub.add_parser("offer-performance")
    operf.add_argument("offer_id")

    ostatus = sub.add_parser("offer-status")
    ostatus.add_argument("offer_id")
    ostatus.add_argument("state", choices=("active", "inactive"))

    sub.add_parser("doctor")

    backup = sub.add_parser("backup")
    backup.add_argument("destination")

    sub.add_parser("policy-show")

    phistory = sub.add_parser("policy-history")
    phistory.add_argument("--limit", type=int, default=20)

    pset = sub.add_parser("policy-set")
    pset.add_argument("--set", dest="changes", action="append", required=True)
    pset.add_argument("--actor", required=True)
    pset.add_argument("--note", default="")

    swarm_status = sub.add_parser("swarm-status")
    swarm_status.add_argument("--config", default=os.getenv("SPICE_SWARM_CONFIG"))
    swarm_run = sub.add_parser("swarm-run")
    swarm_run.add_argument("--config", default=os.getenv("SPICE_SWARM_CONFIG"))
    swarm_run.add_argument("--once", action="store_true")
    swarm_run.add_argument("--interval", type=int, default=60)
    commerce_serve = sub.add_parser("commerce-serve")
    commerce_serve.add_argument("--host", default="127.0.0.1")
    commerce_serve.add_argument("--port", type=int, default=8766)

    args = parser.parse_args(argv)
    ui = SpiceUI(force_json=args.json, no_color=args.no_color)
    ui.header(args.command)
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
        elif args.command in ("swarm-status", "swarm-run"):
            from .swarm import SwarmConfig
            from .swarm_factory import make_swarm
            config = SwarmConfig.load(args.config) if args.config else SwarmConfig()
            runtime = make_swarm(store, personas, config)
            if args.command == "swarm-status":
                output = runtime.status()
            elif args.once:
                output = runtime.tick()
            else:
                if not 1 <= args.interval <= 3600:
                    parser.error("--interval must be 1..3600 seconds")
                stop = threading.Event()
                previous = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
                for s in previous:
                    signal.signal(s, lambda *_: stop.set())
                try:
                    while not stop.is_set():
                        try:
                            report = runtime.tick()
                        except Exception as exc:
                            report = {"status": "failed", "error_type": type(exc).__name__}
                        print(json.dumps(report, sort_keys=True), flush=True)
                        stop.wait(args.interval)
                finally:
                    for s, handler in previous.items():
                        signal.signal(s, handler)
                return
        elif args.command == "commerce-serve":
            from .commerce_web import make_commerce_handler
            secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
            if not secret:
                parser.error("STRIPE_WEBHOOK_SECRET is required")
            server = HTTPServer((args.host, args.port), make_commerce_handler(args.db, secret))
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return
        elif args.command == "briefs":
            output = build_briefs(personas, args.theme, args.channel, args.seed)
        elif args.command == "campaign":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            variants = generate_campaign(
                persona=persona,
                goal=args.goal,
                cause=args.cause,
                neighborhood=args.neighborhood,
                offer=args.offer,
                seed=args.seed,
                count=args.variants,
            )
            proposed = []
            for v in variants:
                if v.violations:
                    raise ValueError(f"generated copy failed policy check: {v.violations}")
                cid = store.propose(
                    persona,
                    theme=f"{args.goal} [{v.kind}]",
                    format="post",
                    channel="nextdoor",
                    offer=args.offer,
                    prompt=v.body,
                    model="campaign-generator",
                    seed=str(args.seed) if args.seed is not None else None,
                    cost_cents=0,
                )
                proposed.append({"candidate_id": cid, **v.to_dict()})
            output = {"channel": "nextdoor", "goal": args.goal, "variants": proposed}
        elif args.command == "campaign-moa":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            if not os.getenv("MOA_API_KEY"):
                parser.error("MoA provider not configured: set MOA_API_KEY (and MOA_BASE_URL); see README")
            output = engineer_campaign(
                store,
                OpenAICompatibleChatProvider(),
                persona,
                args.goal,
                args.cause,
                args.neighborhood,
                offer=args.offer,
                seed=args.seed,
                count=args.variants,
                embedder=_optional_embedder(),
            )
        elif args.command == "gold-digger":
            output = dig_report(
                store,
                goal=args.goal,
                channel=args.channel,
                seed=args.seed,
                min_impressions=args.min_impressions,
            )
        elif args.command == "auto-respond":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            if not os.getenv("MOA_API_KEY"):
                parser.error("Chat provider not configured: set MOA_API_KEY (and MOA_BASE_URL); see README")
            agent = EngagementAgent(
                OpenAICompatibleChatProvider(),
                store,
                KnowledgeBase(store, embedder=_optional_embedder()),
            )
            responder = AutoResponder(agent, max_auto_per_day=args.max_per_day)
            if args.poll:
                output = {"processed": responder.poll(persona, channel=args.channel, limit=args.limit)}
            else:
                if not all((args.channel, args.conversation_id, args.message_id, args.body)):
                    parser.error("--poll or --channel/--conversation-id/--message-id/--body is required")
                output = responder.process_inbound(
                    persona, args.channel, args.conversation_id, args.message_id, args.body
                )
        elif args.command == "knowledge-audit":
            probes = [p.strip() for p in args.probes.split(";") if p.strip()] or None
            output = audit_knowledge(
                store,
                probe_queries=probes,
                stale_days=args.stale_days,
                max_probes=args.max_probes,
                embedder=_optional_embedder(),
            )
        elif args.command == "identity-master":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            provider = media_provider()
            views = generate_master_views(provider, persona, seed=args.seed, size=args.size)
            board = composite_portrait_board(views)
            out_dir = Path(args.out) if args.out else Path("data/identity-masters") / persona["id"]
            out_dir.mkdir(parents=True, exist_ok=True)
            for view_id, raw in views.items():
                (out_dir / f"{view_id}.png").write_bytes(raw)
            board_path = out_dir / "portrait_board.png"
            board.save(board_path)
            view_list = [v for v, _ in PORTRAIT_VIEWS] + [CENTER_VIEW[0]] + [v for v, _ in ROTATION_VIEWS]
            output = {
                "persona_id": persona["id"],
                "views": view_list,
                "out_dir": str(out_dir),
                "board": str(board_path),
                "model": provider.model_name,
            }
            if not args.no_promote:
                output["promotion"] = promote_master(
                    store, provider, persona, views, board,
                    reference_root=args.reference_root,
                    identity_threshold=args.identity_threshold,
                )
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
            output = _asset_generator(store, asset_dir=args.asset_dir).generate(
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
            output = _asset_generator(store, asset_dir=args.asset_dir).batch(
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
            kb = KnowledgeBase(store, embedder=_optional_embedder())
            tags = [x.strip() for x in args.tags.split(",") if x.strip()]
            output = kb.add(args.source, args.title, args.body, tags)
        elif args.command == "knowledge-search":
            output = KnowledgeBase(store, embedder=_optional_embedder()).search(args.query, limit=args.limit)
        elif args.command == "knowledge-backfill":
            embedder = _optional_embedder()
            if embedder is None:
                parser.error("MOA_EMBEDDING_MODEL is not configured")
            output = KnowledgeBase(store, embedder=embedder).backfill_embeddings(limit=args.limit)
        elif args.command == "moa":
            persona = None
            if args.persona:
                persona = next((p for p in personas if p["id"] == args.persona), None)
                if persona is None:
                    parser.error("Unknown persona")
            output = MixtureOfAgents(OpenAICompatibleChatProvider(), store, embedder=_optional_embedder()).deliberate(args.objective, persona)
        elif args.command == "autonomy-cycle":
            engine = AutonomyEngine(
                store,
                personas,
                MixtureOfAgents(OpenAICompatibleChatProvider(), store, embedder=_optional_embedder()),
                _asset_generator(store),
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
                MixtureOfAgents(OpenAICompatibleChatProvider(), store, embedder=_optional_embedder()),
                _asset_generator(store),
            )
            output = engine.settle_cycle(args.cycle_id, done=args.done)
        elif args.command == "rl-train":
            values = _runtime_values(store)
            policy = DeepRLPolicy(
                store,
                [p["id"] for p in personas],
                min_experiences=values["rl_min_experiences"],
            )
            output = policy.train(
                epochs=args.epochs,
                learning_rate=args.learning_rate,
            )
        elif args.command == "rl-status":
            values = _runtime_values(store)
            policy = DeepRLPolicy(
                store,
                [p["id"] for p in personas],
                min_experiences=values["rl_min_experiences"],
            )
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
            provider = OpenAICompatibleChatProvider()
            deliberation = MixtureOfAgents(provider, store, embedder=_optional_embedder()).deliberate(
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
            planner = ExperimentPlanner(OpenAICompatibleChatProvider(), store)
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
                _asset_generator(store),
                base_seed=args.seed,
                cost_cents_per_asset=args.cost_cents_per_asset,
            )
        elif args.command == "experiment-show":
            output = ExperimentPlanner(OpenAICompatibleChatProvider(), store).get(args.plan_id)
        elif args.command == "experiment-results":
            output = ExperimentPlanner(OpenAICompatibleChatProvider(), store).results(args.plan_id)
        elif args.command == "autopilot-run":
            values = _runtime_values(store)
            provider = OpenAICompatibleChatProvider()
            planner = ExperimentPlanner(provider, store)
            engine = CoreAutopilot(
                store,
                personas,
                MixtureOfAgents(provider, store, embedder=_optional_embedder()),
                planner,
                _asset_generator(store),
                min_experiences=values["rl_min_experiences"],
            )
            ui.start_progress("Starting autopilot")
            try:
                output = engine.run_once(
                args.objective,
                args.channel,
                args.offer,
                variant_count=args.variants,
                seed=args.seed,
                cost_cents_per_asset=args.cost_cents_per_asset,
                max_pending_review=(
                    args.max_pending_review
                    if args.max_pending_review is not None
                    else values["max_pending_review"]
                ),
                daily_budget_cents=(
                    args.daily_budget_cents
                    if args.daily_budget_cents is not None
                    else values["daily_budget_cents"]
                ),
                progress=ui.update_progress,
                )
            finally:
                ui.stop_progress()
        elif args.command == "autopilot-settle":
            values = _runtime_values(store)
            provider = OpenAICompatibleChatProvider()
            planner = ExperimentPlanner(provider, store)
            knowledge = KnowledgeBase(store, embedder=_optional_embedder())
            output = LearningController(
                store,
                personas,
                planner,
                knowledge,
                min_experiences=values["rl_min_experiences"],
            ).settle_autopilot_run(
                args.run_id,
                min_impressions_per_published_variant=(
                    args.min_impressions
                    if args.min_impressions is not None
                    else values["min_impressions_to_learn"]
                ),
            )
        elif args.command == "autopilot-status":
            values = _runtime_values(store)
            provider = OpenAICompatibleChatProvider()
            engine = CoreAutopilot(
                store,
                personas,
                MixtureOfAgents(provider, store, embedder=_optional_embedder()),
                ExperimentPlanner(provider, store),
                _asset_generator(store),
                min_experiences=values["rl_min_experiences"],
            )
            output = {
                "pending_review": engine.pending_review_count(),
                "spent_today_cents": engine.spend_today_cents(),
                "rl_experiences": engine.policy.count(),
                "rl_minimum_experiences": engine.policy.min_experiences,
                "rl_ready": engine.policy.count() >= engine.policy.min_experiences,
            }
        elif args.command == "media-benchmark":
            ui.start_progress("Benchmarking media providers")
            try:
                output = benchmark_media(
                    prompt=args.prompt,
                    negative_prompt=args.negative_prompt,
                    seed=args.seed,
                    width=args.width,
                    height=args.height,
                )
            finally:
                ui.stop_progress()
        elif args.command == "engagement-ingest":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            agent = EngagementAgent(
                OpenAICompatibleChatProvider(),
                store,
                KnowledgeBase(store, embedder=_optional_embedder()),
            )
            output = agent.ingest_inbound(
                persona,
                args.channel,
                args.conversation_id,
                args.message_id,
                args.body,
            )
        elif args.command == "engagement-draft":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            agent = EngagementAgent(
                OpenAICompatibleChatProvider(),
                store,
                KnowledgeBase(store, embedder=_optional_embedder()),
            )
            output = agent.draft_reply(persona, args.message_id)
        elif args.command == "engagement-review":
            agent = EngagementAgent(
                OpenAICompatibleChatProvider(),
                store,
                KnowledgeBase(store, embedder=_optional_embedder()),
            )
            output = agent.review_draft(
                args.draft_id,
                args.decision,
                args.reviewer,
                args.note,
            )
        elif args.command == "engagement-outbox":
            agent = EngagementAgent(
                OpenAICompatibleChatProvider(),
                store,
                KnowledgeBase(store, embedder=_optional_embedder()),
            )
            output = agent.approved_outbox(limit=args.limit)
        elif args.command == "offer-create":
            output = OfferRegistry(store).create(
                args.name,
                args.kind,
                expected_payout_cents=args.expected_payout_cents,
                variable_cost_cents=args.variable_cost_cents,
            )
        elif args.command == "offer-register":
            output = OfferRegistry(store).register_candidate(
                args.candidate_id,
                args.offer_id,
                args.url,
            )
        elif args.command == "offer-event":
            output = OfferRegistry(store).ingest(
                args.tracking_token,
                args.kind,
                args.external_id,
                amount_cents=args.amount_cents,
            )
        elif args.command == "offer-performance":
            output = OfferRegistry(store).performance(args.offer_id)
        elif args.command == "offer-status":
            output = OfferRegistry(store).set_active(
                args.offer_id,
                args.state == "active",
            )
        elif args.command == "policy-show":
            output = RuntimePolicy(store).current()
        elif args.command == "policy-history":
            output = RuntimePolicy(store).history(limit=args.limit)
        elif args.command == "policy-set":
            output = RuntimePolicy(store).update(
                _parse_policy_changes(args.changes),
                actor=args.actor,
                note=args.note,
            )
        elif args.command == "doctor":
            output = Operations(store, personas).doctor()
        elif args.command == "backup":
            output = Operations(store, personas).backup(args.destination)
        ui.result(output, args.command)
    finally:
        store.close()


if __name__ == "__main__":
    main()

"""JSON control-plane adapter for the TypeScript operator desk.

Each invocation reads one JSON object from stdin and writes one JSON value to stdout.
The canonical state remains in the existing spicecore SQLite ledger.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .analytics.ingest import AnalyticsIngestor
from .analytics.normalize import NormalizedMetrics
from .assetgen import AssetGenerator
from .autopilot import CoreAutopilot
from .core import Store, load_personas
from .deeprl import DeepRLPolicy
from .experiments import ExperimentPlanner
from .media.repository import MediaJobRepository
from .memory import KnowledgeBase
from .moa import MixtureOfAgents
from .operations import Operations
from .policy import recommend
from .providers import AzureChatProvider, AzureEmbeddingProvider, LocalDreamProvider, ProviderError
from .runtime_policy import RuntimePolicy
from .thompson_sampling import recommend_thompson_sampling
from .workflow import build_briefs


DB_PATH = os.environ.get("SPICE_DB", "data/experiments.sqlite")
PERSONAS_PATH = os.environ.get("SPICE_PERSONAS", "personas")


def _optional_embedder():
    try:
        return AzureEmbeddingProvider()
    except ProviderError:
        return None


def _asset_generator(store: Store):
    values = RuntimePolicy(store).current()["values"]
    return AssetGenerator(
        store,
        provider=LocalDreamProvider(),
        asset_dir="data/assets",
        identity_threshold=values["identity_threshold"],
        reference_strength=values["reference_strength"],
        quality_threshold=values["quality_threshold"],
    )


def _payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("request payload must be a JSON object")
    return value


def _candidate_list(store: Store, personas: list[dict], status: str | None = None) -> list[dict]:
    params: tuple = ()
    sql = "SELECT * FROM candidates"
    if status:
        sql += " WHERE status=?"
        params = (status,)
    sql += " ORDER BY created_at DESC"
    rows = [dict(row) for row in store.db.execute(sql, params)]
    names = {p["id"]: p["name"] for p in personas}

    review_by_candidate: dict[str, dict] = {}
    publish_by_candidate: dict[str, dict] = {}
    for event in store.events():
        payload = event.get("payload") or {}
        cid = payload.get("candidate_id")
        if not cid:
            continue
        if event["kind"] == "asset_reviewed":
            review_by_candidate[cid] = payload
        elif event["kind"] == "content_published":
            publish_by_candidate[cid] = payload

    for row in rows:
        row["persona_name"] = names.get(row["persona_id"], row["persona_id"])
        review = review_by_candidate.get(row["id"], {})
        published = publish_by_candidate.get(row["id"], {})
        if review:
            row["reviewer"] = review.get("reviewer")
            row["review_note"] = review.get("note", "")
        if published:
            row["published_url"] = published.get("url")
    return rows


def _knowledge_list(store: Store) -> list[dict]:
    KnowledgeBase(store)
    rows = store.db.execute(
        "SELECT id,ts,source,title,body,tags,approved,embedding_model "
        "FROM knowledge WHERE approved=1 ORDER BY ts DESC,id DESC"
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item["tags"])
        item["approved"] = bool(item["approved"])
        result.append(item)
    return result


def _bounded_count(value, default: int, *, maximum: int = 10000) -> int:
    count = default if value is None else int(value)
    if count < 0 or count > maximum:
        raise ValueError(f"count must be between 0 and {maximum}")
    return count


def dispatch(action: str, payload: dict, store: Store, personas: list[dict]):
    if action == "health":
        return {
            "status": "ok",
            "service": "spicecore-control-plane",
            "database": DB_PATH,
            "personas": len(personas),
            "runtime_policy_version": RuntimePolicy(store).current()["version"],
        }

    if action == "personas":
        return personas

    if action == "candidates":
        status = payload.get("status")
        return _candidate_list(store, personas, str(status) if status else None)

    if action == "propose":
        persona_id = str(payload.get("persona_id", ""))
        persona = next((p for p in personas if p["id"] == persona_id), None)
        if persona is None:
            raise ValueError("Unknown persona")
        cid = store.propose(
            persona,
            str(payload.get("theme", "")),
            str(payload.get("format", "")),
            str(payload.get("channel", "")),
            str(payload.get("offer", "")),
            payload.get("asset_uri"),
            payload.get("prompt"),
            payload.get("model"),
            str(payload["seed"]) if payload.get("seed") is not None else None,
            int(payload.get("cost_cents", 0)),
        )
        return store.candidate(cid)

    if action == "review":
        return store.review(
            str(payload.get("candidate_id", "")),
            str(payload.get("decision", "")),
            str(payload.get("reviewer", "")),
            str(payload.get("note", "")),
        )

    if action == "publish":
        event = store.publish(
            str(payload.get("candidate_id", "")),
            str(payload.get("url", "")),
            payload.get("external_id"),
        )
        return {"event": event, "candidate": store.candidate(str(payload.get("candidate_id", "")))}

    if action == "outcome":
        return store.record_outcome(
            str(payload.get("candidate_id", "")),
            str(payload.get("kind", "")),
            int(payload.get("amount_cents", 0)),
            payload.get("external_id"),
        )

    if action == "simulate":
        cid = str(payload.get("candidate_id", ""))
        impressions = _bounded_count(payload.get("impressions"), 20)
        clicks = _bounded_count(payload.get("clicks"), 3)
        purchases = _bounded_count(payload.get("purchases"), 1)
        refunds = _bounded_count(payload.get("refunds"), 0)
        purchase_cents = int(payload.get("purchaseCents", payload.get("purchase_cents", 2500)))
        refund_cents = int(payload.get("refundCents", payload.get("refund_cents", 0)))
        if purchases and purchase_cents <= 0:
            raise ValueError("purchase amount must be positive")
        if refunds and refund_cents <= 0:
            raise ValueError("refund amount must be positive")
        for _ in range(impressions):
            store.record_outcome(cid, "impression")
        for _ in range(clicks):
            store.record_outcome(cid, "click")
        for _ in range(purchases):
            store.record_outcome(cid, "purchase", purchase_cents)
        for _ in range(refunds):
            store.record_outcome(cid, "refund", refund_cents)
        return {"success": True, "stats": store.stats(personas)}

    if action == "stats":
        return store.stats(personas)

    if action == "events":
        limit = int(payload.get("limit", 100))
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        return list(reversed(store.events()))[:limit]

    if action == "recommend":
        exploration = float(payload.get("exploration", 0.30))
        seed = payload.get("seed")
        result = recommend(
            store.stats(personas),
            seed=int(seed) if seed is not None else None,
            exploration=exploration,
        )
        if bool(payload.get("audit", False)):
            store.record_event("policy_decision", result)
        return result

    if action == "recommend_thompson":
        seed = payload.get("seed")
        recent_history = payload.get("recent_history") or []
        if not isinstance(recent_history, list):
            raise ValueError("recent_history must be an array")
        result = recommend_thompson_sampling(
            store.stats(personas),
            recent_history=[str(x) for x in recent_history],
            seed=int(seed) if seed is not None else None,
            fatigue_decay_rate=float(payload.get("fatigue_decay_rate", 0.20)),
        )
        if bool(payload.get("audit", False)):
            store.record_event("policy_decision", result)
        return result

    if action == "analytics_ingest":
        metrics_payload = payload.get("metrics")
        if not isinstance(metrics_payload, dict):
            raise ValueError("metrics must be an object")
        metrics = NormalizedMetrics.from_dict(metrics_payload)
        candidate = store.candidate(metrics.candidate_id)
        if candidate["persona_id"] != metrics.persona_id:
            raise ValueError("metrics persona_id does not match candidate")
        if candidate["status"] != "published":
            raise ValueError("analytics can only be ingested for published candidates")
        result = AnalyticsIngestor(store).ingest(metrics)
        return {
            "result": result,
            "stats": store.stats(personas),
        }

    if action == "capabilities":
        env = os.environ
        return {
            "analytics": {
                "normalized_ingest": True,
                "idempotent_external_ids": True,
            },
            "distribution": {
                "instagram": bool(env.get("INSTAGRAM_ACCESS_TOKEN")),
                "tiktok": bool(env.get("TIKTOK_ACCESS_TOKEN")),
                "youtube": bool(env.get("YOUTUBE_ACCESS_TOKEN")),
            },
            "media": {
                "ffmpeg": bool(__import__("shutil").which("ffmpeg")),
                "luma": False,
                "elevenlabs": False,
                "synclabs": False,
                "local_dream": bool(env.get("LOCAL_DREAM_URL")),
                "configured": {
                    "luma": bool(env.get("LUMA_API_KEY")),
                    "elevenlabs": bool(env.get("ELEVENLABS_API_KEY")),
                    "synclabs": bool(env.get("SYNCLABS_API_KEY")),
                },
            },
            "policy": {
                "epsilon_greedy": True,
                "thompson_sampling": True,
                "deeprl": True,
            },
        }

    if action == "briefs":
        return build_briefs(
            personas,
            str(payload.get("theme", "")),
            str(payload.get("channel", "")),
            int(payload["seed"]) if payload.get("seed") is not None else None,
        )

    if action == "media_jobs":
        status = str(payload.get("status", "")).strip() or None
        return MediaJobRepository(store).list(status=status)

    if action == "media_create":
        candidate_id = str(payload.get("candidate_id", ""))
        candidate = store.candidate(candidate_id)
        persona_id = str(payload.get("persona_id", ""))
        if candidate["persona_id"] != persona_id:
            raise ValueError("media job persona_id does not match candidate")
        source_asset_uri = str(payload.get("source_asset_uri") or candidate.get("asset_uri") or "").strip()
        if not source_asset_uri:
            raise ValueError("source_asset_uri is required")
        script = str(payload.get("script", "")).strip()
        if not script:
            raise ValueError("script is required")
        return MediaJobRepository(store).create(
            persona_id=persona_id,
            candidate_id=candidate_id,
            source_asset_uri=source_asset_uri,
            script=script,
            aspect_ratio=str(payload.get("aspect_ratio", "9:16")),
            soundtrack=payload.get("soundtrack"),
            cta=payload.get("cta"),
            offer=payload.get("offer") or candidate.get("offer"),
            product_id=payload.get("product_id"),
        )

    if action == "media_review":
        return MediaJobRepository(store).review(
            str(payload.get("media_job_id", "")),
            str(payload.get("decision", "")),
            str(payload.get("reviewer", "")),
            str(payload.get("note", "")),
        )

    if action == "knowledge":
        query = str(payload.get("query", "")).strip()
        kb = KnowledgeBase(store)
        if query:
            return kb.search(query, limit=int(payload.get("limit", 20)))
        return _knowledge_list(store)

    if action == "policy":
        return RuntimePolicy(store).current()

    if action == "policy_update":
        changes = payload.get("changes") or {}
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object")
        return RuntimePolicy(store).update(
            changes,
            actor=str(payload.get("actor", "")).strip(),
            note=str(payload.get("note", "")),
        )

    if action == "rl_status":
        runtime = RuntimePolicy(store).current()["values"]
        policy = DeepRLPolicy(
            store,
            [p["id"] for p in personas],
            min_experiences=runtime["rl_min_experiences"],
        )
        row = store.db.execute(
            "SELECT * FROM rl_policy_snapshot ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return {
            "policy_version": policy.POLICY_VERSION,
            "experiences": policy.count(),
            "minimum_experiences": policy.min_experiences,
            "ready": policy.count() >= policy.min_experiences,
            "latest_snapshot": dict(row) if row else None,
        }

    if action == "rl_train":
        runtime = RuntimePolicy(store).current()["values"]
        policy = DeepRLPolicy(
            store,
            [p["id"] for p in personas],
            min_experiences=runtime["rl_min_experiences"],
        )
        return policy.train(
            epochs=int(payload.get("epochs", 20)),
            learning_rate=float(payload.get("learning_rate", 0.01)),
        )

    if action == "doctor":
        return Operations(store, personas).doctor()

    if action == "autopilot_run":
        runtime = RuntimePolicy(store).current()["values"]
        objective = str(payload.get("objective", ""))
        channel = str(payload.get("channel", ""))
        offer = str(payload.get("offer", ""))
        variants = int(payload.get("variants", 3))
        cost_cents_per_asset = int(payload.get("cost_cents_per_asset", 0))
        seed = int(payload["seed"]) if payload.get("seed") is not None else None

        preflight_engine = CoreAutopilot(
            store,
            personas,
            None,
            None,
            None,
            min_experiences=runtime["rl_min_experiences"],
        )
        gate = preflight_engine.preflight(
            objective,
            channel,
            offer,
            variant_count=variants,
            cost_cents_per_asset=cost_cents_per_asset,
            max_pending_review=runtime["max_pending_review"],
            daily_budget_cents=runtime["daily_budget_cents"],
        )
        if not gate["allowed"]:
            return preflight_engine.run_once(
                objective,
                channel,
                offer,
                variant_count=variants,
                seed=seed,
                cost_cents_per_asset=cost_cents_per_asset,
                max_pending_review=runtime["max_pending_review"],
                daily_budget_cents=runtime["daily_budget_cents"],
            )

        provider = AzureChatProvider()
        planner = ExperimentPlanner(provider, store)
        engine = CoreAutopilot(
            store,
            personas,
            MixtureOfAgents(provider, store, embedder=_optional_embedder()),
            planner,
            _asset_generator(store),
            min_experiences=runtime["rl_min_experiences"],
        )
        return engine.run_once(
            objective,
            channel,
            offer,
            variant_count=variants,
            seed=seed,
            cost_cents_per_asset=cost_cents_per_asset,
            max_pending_review=runtime["max_pending_review"],
            daily_budget_cents=runtime["daily_budget_cents"],
        )

    if action == "autopilot_status":
        from datetime import datetime, timezone
        runtime = RuntimePolicy(store).current()
        today = datetime.now(timezone.utc).date().isoformat()
        pending = int(store.db.execute(
            "SELECT COUNT(*) FROM candidates WHERE status='proposed'"
        ).fetchone()[0])
        spent = int(store.db.execute(
            "SELECT COALESCE(SUM(cost_cents),0) FROM candidates WHERE substr(created_at,1,10)=?",
            (today,),
        ).fetchone()[0])
        table = store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='autopilot_run'"
        ).fetchone()
        recent = []
        if table:
            rows = store.db.execute(
                "SELECT id,ts,objective,status,reason,persona_id,plan_id,created_candidates,estimated_cost_cents "
                "FROM autopilot_run ORDER BY ts DESC LIMIT 10"
            ).fetchall()
            recent = [dict(row) for row in rows]
        return {
            "pending_review": pending,
            "max_pending_review": runtime["values"]["max_pending_review"],
            "spent_today_cents": spent,
            "daily_budget_cents": runtime["values"]["daily_budget_cents"],
            "recent_runs": recent,
        }

    if action == "knowledge_add":
        kb = KnowledgeBase(store)
        tags = payload.get("tags") or []
        if isinstance(tags, str):
            tags = [x.strip() for x in tags.split(",") if x.strip()]
        if not isinstance(tags, list):
            raise ValueError("tags must be an array or comma-delimited string")
        return kb.add(
            str(payload.get("source", "")),
            str(payload.get("title", "")),
            str(payload.get("body", "")),
            [str(x) for x in tags],
            approved=True,
        )

    raise ValueError(f"Unknown action: {action}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        raise SystemExit("usage: python -m spicecore.control_plane ACTION")

    action = argv[0]
    payload = _payload()
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    personas = load_personas(PERSONAS_PATH)
    store = Store(DB_PATH)
    try:
        output = dispatch(action, payload, store, personas)
        print(json.dumps(output, ensure_ascii=False))
    finally:
        store.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": exc.__class__.__name__}), file=sys.stderr)
        raise SystemExit(1)

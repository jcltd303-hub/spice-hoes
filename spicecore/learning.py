"""Close completed autopilot experiments into RL replay and durable RAG evidence."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .deeprl import DeepRLPolicy


class LearningNotReady(RuntimeError):
    pass


class LearningController:
    MONETARY_FIELDS = (
        "revenue_cents", "refund_cents", "chargeback_cents", "chargeback_reversal_cents",
        "distribution_cost_cents", "commerce_cost_cents", "commerce_cost_reversal_cents",
        "generation_cost_cents", "net_cents",
    )

    def __init__(self, store, personas, planner, knowledge, min_experiences: int = 128, *,
                 verified_revenue_only: bool = False):
        if not isinstance(verified_revenue_only, bool):
            raise ValueError("verified_revenue_only must be a boolean")
        self.store = store
        self.personas = list(personas)
        self.planner = planner
        self.knowledge = knowledge
        self.verified_revenue_only = verified_revenue_only
        self.policy = DeepRLPolicy(
            store,
            [p["id"] for p in self.personas],
            min_experiences=min_experiences,
            verified_experiences_only=verified_revenue_only,
        )
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS learning_closure (
                run_id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                experience_id TEXT NOT NULL,
                knowledge_id TEXT NOT NULL,
                reward_cents INTEGER NOT NULL,
                total_impressions INTEGER NOT NULL,
                summary_json TEXT NOT NULL
            );
            """
        )
        self.store.db.commit()

    def _existing(self, run_id: str) -> dict | None:
        row = self.store.db.execute(
            "SELECT * FROM learning_closure WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        summary = json.loads(row["summary_json"])
        return {
            "run_id": row["run_id"],
            "plan_id": row["plan_id"],
            "persona_id": row["persona_id"],
            "experience_id": row["experience_id"],
            "knowledge_id": row["knowledge_id"],
            "reward_cents": row["reward_cents"],
            "total_impressions": row["total_impressions"],
            "total_views": summary.get("total_views", 0),
            "exposure_metric": summary.get("exposure_metric", "impressions"),
            "verified_revenue_only": summary.get("verified_revenue_only", False),
            "summary": summary,
            "status": "settled",
        }

    def settle_autopilot_run(self, run_id: str,
                             min_impressions_per_published_variant: int = 100,
                             done: bool = True, *, exposure_metric: str = "impressions") -> dict:
        """Commit replay, evidence, and closure together after the exposure gate."""
        if min_impressions_per_published_variant < 0:
            raise ValueError("minimum impressions cannot be negative")
        if exposure_metric not in ("impressions", "views"):
            raise ValueError("exposure_metric must be impressions or views")

        with self._learning_transaction():
            existing = self._existing(run_id)
            if existing:
                return existing
            row = self.store.db.execute(
                "SELECT * FROM autopilot_run WHERE id=?", (run_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Unknown autopilot run")
            if row["status"] != "created":
                raise LearningNotReady("Only created autopilot runs can be settled")
            if not row["plan_id"] or not row["persona_id"]:
                raise LearningNotReady("Autopilot run has no experiment plan")

            payload = json.loads(row["payload_json"])
            state = (payload.get("policy") or {}).get("state")
            if not isinstance(state, list) or len(state) != 6:
                raise LearningNotReady("Autopilot run is missing its original portfolio state")

            projection = {"verified_revenue_only": True} if self.verified_revenue_only else {}
            results = self.planner.results(row["plan_id"], **projection)
            variants = results["variants"]
            if not variants:
                raise LearningNotReady("Experiment has no generated variants")
            for variant in variants:
                if variant["status"] in {"not_generated", "proposed", "approved"}:
                    raise LearningNotReady(
                        f"Variant {variant['variant_id']} is not terminal: {variant['status']}"
                    )
                if (variant["status"] == "published"
                        and variant.get(exposure_metric, 0) < min_impressions_per_published_variant):
                    raise LearningNotReady(
                        f"Variant {variant['variant_id']} needs at least "
                        f"{min_impressions_per_published_variant} {exposure_metric}"
                    )

            reward_cents = sum(int(v["net_cents"]) for v in variants)
            total_impressions = sum(int(v["impressions"]) for v in variants)
            total_views = sum(int(v.get("views", 0)) for v in variants)
            next_state = DeepRLPolicy.features(self.store.stats(self.personas, **projection))
            ts = datetime.now(timezone.utc).isoformat()
            experience_id = self._record_episode(
                run_id, state, row["persona_id"], reward_cents, next_state, done, ts,
            )
            self._sync_episode_verification(experience_id)
            summary = {
                "plan_id": row["plan_id"],
                "run_id": run_id,
                "persona_id": row["persona_id"],
                "objective": row["objective"],
                "primary_metric": results["primary_metric"],
                "reversal_condition": results["reversal_condition"],
                "observed_leader_by_net_cents": results["observed_leader_by_net_cents"],
                "reward_cents": reward_cents,
                "total_impressions": total_impressions,
                "total_views": total_views,
                "exposure_metric": exposure_metric,
                "verified_revenue_only": self.verified_revenue_only,
                "variants": variants,
                "interpretation": (
                    "Observed experiment outcomes recorded from first-party event data. "
                    "Descriptive evidence only; use repeated experiments before treating a pattern as stable."
                ),
            }
            superseded_ids = self._supersede_knowledge(row["plan_id"])
            knowledge_id = self._add_knowledge(summary, ts)
            self.store.db.execute(
                """INSERT INTO learning_closure
                   (run_id,ts,plan_id,persona_id,experience_id,knowledge_id,
                    reward_cents,total_impressions,summary_json)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (run_id, ts, row["plan_id"], row["persona_id"], experience_id, knowledge_id,
                 reward_cents, total_impressions, json.dumps(summary, sort_keys=True)),
            )
            self.store.db.execute("UPDATE autopilot_run SET status='settled' WHERE id=?", (run_id,))
            self.store._event("autopilot_learning_closed", {
                "run_id": run_id,
                "plan_id": row["plan_id"],
                "persona_id": row["persona_id"],
                "experience_id": experience_id,
                "knowledge_id": knowledge_id,
                "superseded_knowledge_ids": superseded_ids,
                "reward_cents": reward_cents,
                "total_impressions": total_impressions,
                "total_views": total_views,
                "exposure_metric": exposure_metric,
                "verified_revenue_only": self.verified_revenue_only,
            })
            return self._existing(run_id)

    @contextmanager
    def _learning_transaction(self):
        """Serialize learning writes and respect an enclosing caller transaction."""
        db = self.store.db
        savepoint = "learning_" + uuid.uuid4().hex if db.in_transaction else None
        if savepoint:
            db.execute(f"SAVEPOINT {savepoint}")
        else:
            db.execute("BEGIN IMMEDIATE")
        try:
            if savepoint:
                db.execute("UPDATE learning_closure SET reward_cents=reward_cents WHERE 0")
            yield
            if savepoint:
                db.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                db.commit()
        except Exception:
            if savepoint:
                db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                db.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                db.rollback()
            raise

    def _record_episode(self, run_id, state, persona_id, reward_cents, next_state, done, ts):
        """Write replay directly, reusing any partial episode left by an older release."""
        if persona_id not in self.policy.action_ids:
            raise ValueError("Unknown action")
        external_id = f"autopilot-learning:{run_id}"
        prior = self.store.db.execute("SELECT kind,payload FROM events WHERE external_id=?", (external_id,)).fetchone()
        if prior:
            payload = json.loads(prior["payload"])
            if prior["kind"] != "rl_experience_recorded" or payload.get("action_id") != persona_id:
                raise ValueError("External ID already used for a different learning episode")
            experience_id = payload["experience_id"]
            replay = self.store.db.execute("SELECT * FROM rl_experience WHERE id=?", (experience_id,)).fetchone()
            if replay is None or replay["action_id"] != persona_id or json.loads(replay["state_json"]) != state:
                raise ValueError("Partial learning episode is missing or mismatched")
            self.store.db.execute(
                "UPDATE rl_experience SET reward=?,next_state_json=? WHERE id=?",
                (reward_cents / 100.0, json.dumps(next_state), experience_id),
            )
            return experience_id

        experience_id = str(uuid.uuid4())
        self.store.db.execute(
            """INSERT INTO rl_experience(id,ts,state_json,action_id,reward,next_state_json,done)
               VALUES(?,?,?,?,?,?,?)""",
            (experience_id, ts, json.dumps(state), persona_id, reward_cents / 100.0,
             json.dumps(next_state), int(bool(done))),
        )
        self.store._event("rl_experience_recorded", {
            "experience_id": experience_id, "action_id": persona_id,
            "reward_cents": reward_cents, "done": bool(done),
        }, external_id)
        return experience_id

    def _sync_episode_verification(self, experience_id):
        if self.verified_revenue_only:
            self.store.db.execute(
                "INSERT OR IGNORE INTO rl_verified_experience(experience_id) VALUES(?)", (experience_id,),
            )
        else:
            self.store.db.execute("DELETE FROM rl_verified_experience WHERE experience_id=?", (experience_id,))

    def _supersede_knowledge(self, plan_id):
        source = f"experiment:{plan_id}"
        rows = self.store.db.execute(
            "SELECT id FROM knowledge WHERE source=? AND approved=1 ORDER BY ts,id", (source,),
        ).fetchall()
        self.store.db.execute("UPDATE knowledge SET approved=0 WHERE source=? AND approved=1", (source,))
        return [row["id"] for row in rows]

    @classmethod
    def _monetary_evidence(cls, summary: dict) -> list[dict]:
        """Ignore exposure, click rate, and leader changes when deciding to correct."""
        return [
            {
                "variant_id": variant["variant_id"],
                "candidate_id": variant.get("candidate_id"),
                **{name: int(variant.get(name, 0)) for name in cls.MONETARY_FIELDS},
            }
            for variant in sorted(summary.get("variants", []), key=lambda item: item["variant_id"])
        ]

    def _add_knowledge(self, summary: dict, ts: str, *, corrected: bool = False) -> str:
        """Insert lexical evidence atomically; embedding backfill is a separate step.

        KnowledgeBase.add commits its own context and may call a remote embedder,
        so it cannot be used inside a multi-table learning correction.
        """
        knowledge_id = str(uuid.uuid4())
        source = f"experiment:{summary['plan_id']}"
        title = f"Observed experiment results: {summary['plan_id']}"
        tags = {"observed", "experiment", f"persona:{summary['persona_id']}", f"plan:{summary['plan_id']}"}
        if corrected:
            tags.add("corrected")
        tags = sorted(tags)
        self.store.db.execute(
            """INSERT INTO knowledge
               (id,ts,source,title,body,tags,approved,embedding_json,embedding_model)
               VALUES(?,?,?,?,?,?,1,NULL,NULL)""",
            (knowledge_id, ts, source, title, json.dumps(summary, ensure_ascii=False, sort_keys=True),
             json.dumps(tags)),
        )
        self.store._event("knowledge_added", {
            "knowledge_id": knowledge_id,
            "source": source,
            "title": title,
            "tags": tags,
            "approved": True,
            "embedding_model": None,
        })
        return knowledge_id

    def reconcile_autopilot_run(self, run_id: str) -> dict:
        """Correct settled monetary learning in place without adding replay samples.

        Return status='unchanged' with no writes when only exposure changed, or
        status='corrected' after replacing the approved evidence and replay reward.
        Append-only outcome and original settlement events remain intact. This
        method performs no embedding or training calls.
        """
        with self._learning_transaction():
            run = self.store.db.execute("SELECT * FROM autopilot_run WHERE id=?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Unknown autopilot run")
            existing = self._existing(run_id)
            if existing is None:
                raise LearningNotReady("Autopilot run has no settled learning to reconcile")

            projection = {"verified_revenue_only": True} if self.verified_revenue_only else {}
            results = self.planner.results(existing["plan_id"], **projection)
            reward_cents = sum(int(variant["net_cents"]) for variant in results["variants"])
            total_impressions = sum(int(variant["impressions"]) for variant in results["variants"])
            total_views = sum(int(variant.get("views", 0)) for variant in results["variants"])
            summary = {
                **existing["summary"],
                "primary_metric": results["primary_metric"],
                "reversal_condition": results["reversal_condition"],
                "observed_leader_by_net_cents": results["observed_leader_by_net_cents"],
                "reward_cents": reward_cents,
                "total_impressions": total_impressions,
                "total_views": total_views,
                "exposure_metric": existing["exposure_metric"],
                "verified_revenue_only": self.verified_revenue_only,
                "variants": results["variants"],
            }
            before = self._monetary_evidence(existing["summary"])
            after = self._monetary_evidence(summary)
            result = {**existing, "reward_cents": reward_cents, "summary": summary,
                      "total_impressions": total_impressions, "total_views": total_views,
                      "verified_revenue_only": self.verified_revenue_only,
                      "status": "unchanged", "changed": False}
            marker = self.store.db.execute(
                "SELECT 1 FROM rl_verified_experience WHERE experience_id=?", (existing["experience_id"],),
            ).fetchone()
            promotion = self.verified_revenue_only and (not existing["verified_revenue_only"] or marker is None)
            if before == after and existing["reward_cents"] == reward_cents and not promotion:
                return result

            experience = self.store.db.execute(
                "SELECT action_id FROM rl_experience WHERE id=?", (existing["experience_id"],),
            ).fetchone()
            if experience is None or experience["action_id"] != existing["persona_id"]:
                raise ValueError("Learning closure references a missing or mismatched experience")
            knowledge = self.store.db.execute(
                "SELECT source FROM knowledge WHERE id=?", (existing["knowledge_id"],),
            ).fetchone()
            if knowledge is None or knowledge["source"] != f"experiment:{existing['plan_id']}":
                raise ValueError("Learning closure references missing knowledge")

            ts = datetime.now(timezone.utc).isoformat()
            superseded_ids = self._supersede_knowledge(existing["plan_id"])
            knowledge_id = self._add_knowledge(summary, ts, corrected=True)
            next_state = DeepRLPolicy.features(self.store.stats(self.personas, **projection))
            self.store.db.execute(
                "UPDATE rl_experience SET reward=?,next_state_json=? WHERE id=?",
                (reward_cents / 100.0, json.dumps(next_state), existing["experience_id"]),
            )
            self._sync_episode_verification(existing["experience_id"])
            self.store.db.execute(
                """UPDATE learning_closure
                   SET ts=?,knowledge_id=?,reward_cents=?,total_impressions=?,summary_json=?
                   WHERE run_id=?""",
                (ts, knowledge_id, reward_cents, total_impressions, json.dumps(summary, sort_keys=True), run_id),
            )
            correction = self.store._event("autopilot_learning_corrected", {
                "run_id": run_id,
                "plan_id": existing["plan_id"],
                "persona_id": existing["persona_id"],
                "experience_id": existing["experience_id"],
                "superseded_knowledge_id": existing["knowledge_id"],
                "superseded_knowledge_ids": superseded_ids,
                "knowledge_id": knowledge_id,
                "previous_reward_cents": existing["reward_cents"],
                "reward_cents": reward_cents,
                "reward_delta_cents": reward_cents - existing["reward_cents"],
                "monetary_before": before,
                "monetary_after": after,
                "verified_revenue_only": self.verified_revenue_only,
                "verification_promotion": promotion,
            })
            result.update(status="corrected", changed=True, knowledge_id=knowledge_id,
                          previous_reward_cents=existing["reward_cents"], correction_event_id=correction["id"])
            return result

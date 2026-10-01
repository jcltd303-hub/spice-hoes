"""Close completed autopilot experiments into RL replay and durable RAG evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .deeprl import DeepRLPolicy


class LearningNotReady(RuntimeError):
    pass


class LearningController:
    def __init__(self, store, personas, planner, knowledge, min_experiences: int = 128):
        self.store = store
        self.personas = list(personas)
        self.planner = planner
        self.knowledge = knowledge
        self.policy = DeepRLPolicy(
            store,
            [p["id"] for p in self.personas],
            min_experiences=min_experiences,
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
        return {
            "run_id": row["run_id"],
            "plan_id": row["plan_id"],
            "persona_id": row["persona_id"],
            "experience_id": row["experience_id"],
            "knowledge_id": row["knowledge_id"],
            "reward_cents": row["reward_cents"],
            "total_impressions": row["total_impressions"],
            "summary": json.loads(row["summary_json"]),
            "status": "settled",
        }

    def settle_autopilot_run(self, run_id: str,
                             min_impressions_per_published_variant: int = 100,
                             done: bool = True) -> dict:
        if min_impressions_per_published_variant < 0:
            raise ValueError("minimum impressions cannot be negative")

        existing = self._existing(run_id)
        if existing:
            return existing

        row = self.store.db.execute(
            "SELECT * FROM autopilot_run WHERE id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Unknown autopilot run")
        if row["status"] != "created":
            raise LearningNotReady("Only created autopilot runs can be settled")
        if not row["plan_id"] or not row["persona_id"]:
            raise LearningNotReady("Autopilot run has no experiment plan")

        payload = json.loads(row["payload_json"])
        policy_info = payload.get("policy") or {}
        state = policy_info.get("state")
        if not isinstance(state, list) or len(state) != 6:
            raise LearningNotReady("Autopilot run is missing its original portfolio state")

        results = self.planner.results(row["plan_id"])
        variants = results["variants"]
        if not variants:
            raise LearningNotReady("Experiment has no generated variants")

        blocking_statuses = {"not_generated", "proposed", "approved"}
        for variant in variants:
            if variant["status"] in blocking_statuses:
                raise LearningNotReady(
                    f"Variant {variant['variant_id']} is not terminal: {variant['status']}"
                )
            if (
                variant["status"] == "published"
                and variant["impressions"] < min_impressions_per_published_variant
            ):
                raise LearningNotReady(
                    f"Variant {variant['variant_id']} needs at least "
                    f"{min_impressions_per_published_variant} impressions"
                )

        reward_cents = sum(int(v["net_cents"]) for v in variants)
        total_impressions = sum(int(v["impressions"]) for v in variants)
        next_state = DeepRLPolicy.features(self.store.stats(self.personas))
        experience_id = self.policy.record(
            state,
            row["persona_id"],
            reward_cents,
            next_state,
            done=done,
            external_id=f"autopilot-learning:{run_id}",
        )

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
            "variants": variants,
            "interpretation": (
                "Observed experiment outcomes recorded from first-party event data. "
                "Descriptive evidence only; use repeated experiments before treating a pattern as stable."
            ),
        }
        body = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        knowledge_item = self.knowledge.add(
            source=f"experiment:{row['plan_id']}",
            title=f"Observed experiment results: {row['plan_id']}",
            body=body,
            tags=[
                "observed",
                "experiment",
                f"persona:{row['persona_id']}",
                f"plan:{row['plan_id']}",
            ],
            approved=True,
        )

        ts = datetime.now(timezone.utc).isoformat()
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO learning_closure
                   (run_id,ts,plan_id,persona_id,experience_id,knowledge_id,
                    reward_cents,total_impressions,summary_json)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    ts,
                    row["plan_id"],
                    row["persona_id"],
                    experience_id,
                    knowledge_item["id"],
                    reward_cents,
                    total_impressions,
                    json.dumps(summary, sort_keys=True),
                ),
            )
            self.store.db.execute(
                "UPDATE autopilot_run SET status='settled' WHERE id=?",
                (run_id,),
            )
            self.store._event("autopilot_learning_closed", {
                "run_id": run_id,
                "plan_id": row["plan_id"],
                "persona_id": row["persona_id"],
                "experience_id": experience_id,
                "knowledge_id": knowledge_item["id"],
                "reward_cents": reward_cents,
                "total_impressions": total_impressions,
            })

        return {
            "run_id": run_id,
            "plan_id": row["plan_id"],
            "persona_id": row["persona_id"],
            "experience_id": experience_id,
            "knowledge_id": knowledge_item["id"],
            "reward_cents": reward_cents,
            "total_impressions": total_impressions,
            "summary": summary,
            "status": "settled",
        }

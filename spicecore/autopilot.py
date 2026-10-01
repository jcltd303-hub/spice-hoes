"""Budgeted core autopilot for controlled experiment creation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from .deeprl import DeepRLPolicy, InsufficientExperience
from .policy import recommend


class CoreAutopilot:
    def __init__(self, store, personas, moa, planner, generator, min_experiences=128):
        self.store = store
        self.personas = list(personas)
        self.by_id = {p["id"]: p for p in self.personas}
        self.moa = moa
        self.planner = planner
        self.generator = generator
        self.policy = DeepRLPolicy(
            store, [p["id"] for p in self.personas],
            min_experiences=min_experiences,
        )
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.executescript("""
            CREATE TABLE IF NOT EXISTS autopilot_run (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                objective TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                persona_id TEXT,
                plan_id TEXT,
                created_candidates INTEGER NOT NULL DEFAULT 0,
                estimated_cost_cents INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL
            );
        """)
        self.store.db.commit()

    def pending_review_count(self):
        return self.store.db.execute(
            "SELECT COUNT(*) FROM candidates WHERE status='proposed'"
        ).fetchone()[0]

    def spend_today_cents(self):
        today = datetime.now(timezone.utc).date().isoformat()
        return int(self.store.db.execute(
            "SELECT COALESCE(SUM(cost_cents),0) FROM candidates WHERE substr(created_at,1,10)=?",
            (today,),
        ).fetchone()[0])

    def _select_persona(self, seed=None):
        stats = self.store.stats(self.personas)
        state = DeepRLPolicy.features(stats)
        try:
            decision = self.policy.select(state, seed=seed)
            return {**decision, "source": "deeprl", "persona_id": decision["action_id"], "state": state}
        except InsufficientExperience:
            decision = recommend(stats, seed=seed)
            return {**decision, "source": "contextual_bandit", "state": state}

    def _record(self, objective, status, reason, persona_id, plan_id,
                created_candidates, estimated_cost_cents, payload):
        run_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO autopilot_run
                   (id,ts,objective,status,reason,persona_id,plan_id,
                    created_candidates,estimated_cost_cents,payload_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (run_id, ts, objective, status, reason, persona_id, plan_id,
                 created_candidates, estimated_cost_cents,
                 json.dumps(payload, sort_keys=True)),
            )
            self.store._event("autopilot_run_recorded", {
                "run_id": run_id,
                "status": status,
                "reason": reason,
                "persona_id": persona_id,
                "plan_id": plan_id,
                "created_candidates": created_candidates,
                "estimated_cost_cents": estimated_cost_cents,
            })
        return {
            "run_id": run_id,
            "status": status,
            "reason": reason,
            "persona_id": persona_id,
            "plan_id": plan_id,
            "created_candidates": created_candidates,
            "estimated_cost_cents": estimated_cost_cents,
            **payload,
        }

    def run_once(self, objective, channel, offer, variant_count=3, seed=None,
                 cost_cents_per_asset=0, max_pending_review=12,
                 daily_budget_cents=5000):
        if not all(str(x).strip() for x in (objective, channel, offer)):
            raise ValueError("objective, channel and offer are required")
        if variant_count < 2 or variant_count > 6:
            raise ValueError("variant_count must be 2..6")
        if cost_cents_per_asset < 0 or daily_budget_cents < 0:
            raise ValueError("costs cannot be negative")
        if max_pending_review < 1:
            raise ValueError("max_pending_review must be positive")

        pending = self.pending_review_count()
        spent = self.spend_today_cents()
        requested_cost = cost_cents_per_asset * variant_count

        if pending + variant_count > max_pending_review:
            return self._record(
                objective, "blocked", "review_queue_limit", None, None, 0, 0,
                {"pending_review": pending, "max_pending_review": max_pending_review,
                 "spent_today_cents": spent, "daily_budget_cents": daily_budget_cents},
            )

        if spent + requested_cost > daily_budget_cents:
            return self._record(
                objective, "blocked", "daily_budget_limit", None, None, 0, 0,
                {"pending_review": pending, "spent_today_cents": spent,
                 "requested_cost_cents": requested_cost,
                 "daily_budget_cents": daily_budget_cents},
            )

        decision = self._select_persona(seed)
        persona = self.by_id[decision["persona_id"]]
        deliberation = self.moa.deliberate(objective, persona)
        plan = self.planner.plan(
            objective, persona, channel, offer,
            deliberation=deliberation,
            variant_count=variant_count,
        )
        outputs = self.planner.execute(
            plan, persona, self.generator,
            base_seed=seed,
            cost_cents_per_asset=cost_cents_per_asset,
        )
        reviewable = sum(1 for x in outputs if x["asset"]["status"] == "proposed")
        rejected = sum(1 for x in outputs if x["asset"]["status"] == "rejected")
        return self._record(
            objective, "created", None, persona["id"], plan["plan_id"],
            len(outputs), requested_cost,
            {"policy": decision, "pending_review_before": pending,
             "reviewable_candidates": reviewable,
             "auto_rejected_candidates": rejected,
             "spent_today_before_cents": spent,
             "daily_budget_cents": daily_budget_cents,
             "outputs": outputs},
        )

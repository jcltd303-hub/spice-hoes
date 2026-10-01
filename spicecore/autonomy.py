"""Core autonomy cycle: choose -> deliberate -> generate -> review queue -> settle reward."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from .deeprl import DeepRLPolicy, InsufficientExperience
from .policy import recommend


class AutonomyEngine:
    def __init__(self, store, personas: list[dict], moa, generator,
                 min_experiences: int = 128):
        self.store = store
        self.personas = list(personas)
        self.persona_by_id = {p["id"]: p for p in self.personas}
        self.moa = moa
        self.generator = generator
        self.policy = DeepRLPolicy(
            store,
            [p["id"] for p in self.personas],
            min_experiences=min_experiences,
        )
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS autonomy_cycle (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                state_json TEXT NOT NULL,
                action_id TEXT NOT NULL,
                policy_json TEXT NOT NULL,
                objective TEXT NOT NULL,
                candidate_id TEXT,
                settled INTEGER NOT NULL DEFAULT 0,
                settled_at TEXT
            );
            """
        )
        self.store.db.commit()

    def _choose(self, seed: int | None = None) -> tuple[dict, list[float]]:
        stats = self.store.stats(self.personas)
        state = DeepRLPolicy.features(stats)
        try:
            decision = self.policy.select(state, seed=seed)
            decision["source"] = "deeprl"
            decision["persona_id"] = decision["action_id"]
        except InsufficientExperience:
            decision = recommend(stats, seed=seed)
            decision["source"] = "contextual_bandit"
        return decision, state

    def run_cycle(self, objective: str, theme: str, channel: str, offer: str,
                  scene: str = "", seed: int | None = None,
                  cost_cents: int = 0) -> dict:
        if not all(x.strip() for x in (objective, theme, channel, offer)):
            raise ValueError("objective, theme, channel and offer are required")

        decision, state = self._choose(seed)
        persona_id = decision["persona_id"]
        persona = self.persona_by_id[persona_id]

        deliberation = self.moa.deliberate(objective, persona)
        asset = self.generator.generate(
            persona=persona,
            theme=theme,
            channel=channel,
            offer=offer,
            scene=scene,
            seed=seed,
            cost_cents=cost_cents,
        )

        cycle_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO autonomy_cycle
                   (id,ts,state_json,action_id,policy_json,objective,candidate_id)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    cycle_id,
                    ts,
                    json.dumps(state),
                    persona_id,
                    json.dumps(decision, sort_keys=True),
                    objective,
                    asset["candidate_id"],
                ),
            )
            self.store._event("autonomy_cycle_created", {
                "cycle_id": cycle_id,
                "persona_id": persona_id,
                "candidate_id": asset["candidate_id"],
                "policy_source": decision["source"],
                "objective": objective,
            })

        return {
            "cycle_id": cycle_id,
            "policy": decision,
            "persona_id": persona_id,
            "deliberation": deliberation,
            "asset": asset,
            "requires_human_review": asset["status"] == "proposed",
        }

    def _candidate_reward_cents(self, candidate_id: str) -> int:
        candidate = self.store.candidate(candidate_id)
        revenue = refunds = distribution = commerce = 0
        rows = self.store.db.execute(
            """SELECT kind,payload FROM events
               WHERE kind IN ('purchase','refund','distribution_cost','commerce_cost')"""
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            if payload.get("candidate_id") != candidate_id:
                continue
            amount = int(payload.get("amount_cents", 0))
            if row["kind"] == "purchase":
                revenue += amount
            elif row["kind"] == "refund":
                refunds += amount
            elif row["kind"] == "distribution_cost":
                distribution += amount
            else:
                commerce += amount
        return revenue - refunds - distribution - commerce - int(candidate["cost_cents"])

    def settle_cycle(self, cycle_id: str, done: bool = True) -> dict:
        row = self.store.db.execute(
            "SELECT * FROM autonomy_cycle WHERE id=?", (cycle_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Unknown autonomy cycle")

        candidate_id = row["candidate_id"]
        reward_cents = self._candidate_reward_cents(candidate_id)
        next_state = DeepRLPolicy.features(self.store.stats(self.personas))
        experience_id = self.policy.record(
            json.loads(row["state_json"]),
            row["action_id"],
            reward_cents,
            next_state,
            done=done,
            external_id=f"rl-cycle:{cycle_id}",
        )

        if not row["settled"]:
            settled_at = datetime.now(timezone.utc).isoformat()
            with self.store.db:
                self.store.db.execute(
                    "UPDATE autonomy_cycle SET settled=1, settled_at=? WHERE id=?",
                    (settled_at, cycle_id),
                )
                self.store._event("autonomy_cycle_settled", {
                    "cycle_id": cycle_id,
                    "candidate_id": candidate_id,
                    "experience_id": experience_id,
                    "reward_cents": reward_cents,
                    "done": bool(done),
                })

        return {
            "cycle_id": cycle_id,
            "candidate_id": candidate_id,
            "experience_id": experience_id,
            "reward_cents": reward_cents,
            "next_state": next_state,
            "done": bool(done),
        }

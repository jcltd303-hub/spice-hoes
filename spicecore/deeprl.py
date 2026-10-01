"""Minimal auditable Deep-Q learner for later-stage portfolio allocation.

The learner is deliberately gated: it does not replace the contextual bandit until
there is a real replay buffer. It uses a one-hidden-layer neural network implemented
with the standard library to avoid a heavyweight runtime dependency.
"""

from __future__ import annotations

import json
import math
import random
import uuid
from datetime import datetime, timezone


class InsufficientExperience(RuntimeError):
    pass


class DeepRLPolicy:
    def __init__(self, store, action_ids: list[str], hidden: int = 12, seed: int = 7,
                 min_experiences: int = 128, gamma: float = 0.92):
        if len(action_ids) < 2:
            raise ValueError("DeepRL requires at least two actions")
        self.store = store
        self.action_ids = list(action_ids)
        self.hidden = hidden
        self.gamma = gamma
        self.min_experiences = min_experiences
        self.rng = random.Random(seed)
        self.input_size = 6
        self._ensure_schema()
        self.w1 = [[self.rng.uniform(-0.1, 0.1) for _ in range(self.hidden)]
                   for _ in range(self.input_size)]
        self.b1 = [0.0] * self.hidden
        self.w2 = [[self.rng.uniform(-0.1, 0.1) for _ in self.action_ids]
                   for _ in range(self.hidden)]
        self.b2 = [0.0] * len(self.action_ids)

    def _ensure_schema(self):
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS rl_experience (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                state_json TEXT NOT NULL,
                action_id TEXT NOT NULL,
                reward REAL NOT NULL,
                next_state_json TEXT NOT NULL,
                done INTEGER NOT NULL
            );
            """
        )
        self.store.db.commit()

    @staticmethod
    def features(stats: list[dict]) -> list[float]:
        published = sum(s.get("published", 0) for s in stats)
        impressions = sum(s.get("impressions", 0) for s in stats)
        clicks = sum(s.get("clicks", 0) for s in stats)
        revenue = sum(s.get("revenue_cents", 0) for s in stats)
        cost = sum(s.get("cost_cents", 0) for s in stats)
        net = sum(s.get("net_cents", 0) for s in stats)
        return [
            math.tanh(published / 25),
            math.tanh(impressions / 10000),
            math.tanh(clicks / 1000),
            math.tanh(revenue / 100000),
            math.tanh(cost / 100000),
            math.tanh(net / 100000),
        ]

    def record(self, state: list[float], action_id: str, reward_cents: int,
               next_state: list[float], done: bool = False) -> str:
        if action_id not in self.action_ids:
            raise ValueError("Unknown action")
        if len(state) != self.input_size or len(next_state) != self.input_size:
            raise ValueError("Unexpected state width")
        item_id = str(uuid.uuid4())
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO rl_experience(id,ts,state_json,action_id,reward,next_state_json,done) VALUES(?,?,?,?,?,?,?)",
                (item_id, datetime.now(timezone.utc).isoformat(), json.dumps(state), action_id,
                 reward_cents / 100.0, json.dumps(next_state), 1 if done else 0),
            )
            self.store._event("rl_experience_recorded", {
                "experience_id": item_id, "action_id": action_id,
                "reward_cents": reward_cents, "done": bool(done),
            })
        return item_id

    def count(self) -> int:
        return self.store.db.execute("SELECT COUNT(*) FROM rl_experience").fetchone()[0]

    def _forward(self, x):
        hidden = []
        for j in range(self.hidden):
            z = self.b1[j] + sum(x[i] * self.w1[i][j] for i in range(self.input_size))
            hidden.append(max(0.0, z))
        out = []
        for a in range(len(self.action_ids)):
            out.append(self.b2[a] + sum(hidden[j] * self.w2[j][a] for j in range(self.hidden)))
        return hidden, out

    def train(self, epochs: int = 20, learning_rate: float = 0.01) -> dict:
        n = self.count()
        if n < self.min_experiences:
            raise InsufficientExperience(f"need {self.min_experiences} experiences, have {n}")
        rows = self.store.db.execute("SELECT * FROM rl_experience ORDER BY ts,id").fetchall()
        losses = []
        for _ in range(epochs):
            epoch_loss = 0.0
            for row in rows:
                state = json.loads(row["state_json"])
                next_state = json.loads(row["next_state_json"])
                action = self.action_ids.index(row["action_id"])
                hidden, q = self._forward(state)
                _, next_q = self._forward(next_state)
                target = row["reward"] if row["done"] else row["reward"] + self.gamma * max(next_q)
                err = q[action] - target
                epoch_loss += err * err

                old_w2 = [self.w2[j][action] for j in range(self.hidden)]
                for j in range(self.hidden):
                    self.w2[j][action] -= learning_rate * err * hidden[j]
                self.b2[action] -= learning_rate * err

                for j in range(self.hidden):
                    if hidden[j] <= 0:
                        continue
                    grad_hidden = err * old_w2[j]
                    for i in range(self.input_size):
                        self.w1[i][j] -= learning_rate * grad_hidden * state[i]
                    self.b1[j] -= learning_rate * grad_hidden
            losses.append(epoch_loss / len(rows))
        result = {
            "policy_version": "tiny-dqn-v1",
            "experiences": n,
            "epochs": epochs,
            "final_mse": round(losses[-1], 6),
        }
        self.store.record_event("rl_training_completed", result)
        return result

    def select(self, state: list[float], epsilon: float = 0.05, seed: int | None = None) -> dict:
        if self.count() < self.min_experiences:
            raise InsufficientExperience(
                f"need {self.min_experiences} experiences before DeepRL allocation"
            )
        _, q = self._forward(state)
        rng = random.Random(seed)
        if rng.random() < epsilon:
            index = rng.randrange(len(self.action_ids))
            method = "explore"
        else:
            index = max(range(len(q)), key=lambda i: (q[i], -i))
            method = "exploit"
        result = {
            "policy_version": "tiny-dqn-v1",
            "method": method,
            "action_id": self.action_ids[index],
            "q_values": {aid: round(value, 6) for aid, value in zip(self.action_ids, q)},
            "epsilon": epsilon,
        }
        self.store.record_event("rl_policy_decision", result)
        return result

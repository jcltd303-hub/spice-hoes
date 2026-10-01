"""Versioned runtime policy for auditable operating limits."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone


DEFAULT_POLICY = {
    "daily_budget_cents": 5000,
    "max_pending_review": 12,
    "min_impressions_to_learn": 100,
    "rl_min_experiences": 128,
    "identity_threshold": 0.82,
    "quality_threshold": 0.78,
    "reference_strength": 0.85,
}


class RuntimePolicy:
    def __init__(self, store):
        self.store = store
        self._ensure_schema()
        if self._active_row() is None:
            self.create(DEFAULT_POLICY, actor="system", note="bootstrap defaults")

    def _ensure_schema(self):
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS runtime_policy (
                id TEXT PRIMARY KEY,
                version INTEGER NOT NULL UNIQUE,
                ts TEXT NOT NULL,
                values_json TEXT NOT NULL,
                actor TEXT NOT NULL,
                note TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        self.store.db.commit()

    @staticmethod
    def validate(values: dict) -> dict:
        merged = {**DEFAULT_POLICY, **values}
        ints = (
            "daily_budget_cents",
            "max_pending_review",
            "min_impressions_to_learn",
            "rl_min_experiences",
        )
        for key in ints:
            if not isinstance(merged[key], int) or merged[key] < 0:
                raise ValueError(f"{key} must be a non-negative integer")
        if merged["max_pending_review"] < 1:
            raise ValueError("max_pending_review must be positive")
        if merged["rl_min_experiences"] < 1:
            raise ValueError("rl_min_experiences must be positive")
        for key in ("identity_threshold", "quality_threshold", "reference_strength"):
            value = float(merged[key])
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{key} must be between 0 and 1")
            merged[key] = value
        unknown = set(values) - set(DEFAULT_POLICY)
        if unknown:
            raise ValueError(f"unknown runtime policy keys: {sorted(unknown)}")
        return merged

    def _active_row(self):
        return self.store.db.execute(
            "SELECT * FROM runtime_policy WHERE active=1 ORDER BY version DESC LIMIT 1"
        ).fetchone()

    def current(self) -> dict:
        row = self._active_row()
        if row is None:
            raise RuntimeError("runtime policy not initialized")
        return {
            "id": row["id"],
            "version": row["version"],
            "ts": row["ts"],
            "actor": row["actor"],
            "note": row["note"],
            "values": json.loads(row["values_json"]),
        }

    def create(self, values: dict, actor: str, note: str = "") -> dict:
        if not actor.strip():
            raise ValueError("actor is required")
        validated = self.validate(values)
        version = self.store.db.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM runtime_policy"
        ).fetchone()[0]
        pid = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.store.db:
            self.store.db.execute("UPDATE runtime_policy SET active=0 WHERE active=1")
            self.store.db.execute(
                """INSERT INTO runtime_policy
                   (id,version,ts,values_json,actor,note,active)
                   VALUES(?,?,?,?,?,?,1)""",
                (
                    pid, version, ts, json.dumps(validated, sort_keys=True),
                    actor.strip(), note.strip(),
                ),
            )
            self.store._event("runtime_policy_activated", {
                "policy_id": pid,
                "version": version,
                "actor": actor.strip(),
                "note": note.strip(),
                "values": validated,
            })
        return self.current()

    def update(self, changes: dict, actor: str, note: str = "") -> dict:
        current = self.current()["values"]
        return self.create({**current, **changes}, actor=actor, note=note)

    def history(self, limit: int = 20) -> list[dict]:
        rows = self.store.db.execute(
            """SELECT * FROM runtime_policy
               ORDER BY version DESC LIMIT ?""",
            (max(1, limit),),
        ).fetchall()
        return [{
            "id": row["id"],
            "version": row["version"],
            "ts": row["ts"],
            "actor": row["actor"],
            "note": row["note"],
            "active": bool(row["active"]),
            "values": json.loads(row["values_json"]),
        } for row in rows]

"""Operational health, integrity checks, and safe SQLite backups."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .deeprl import DeepRLPolicy


class Operations:
    def __init__(self, store, personas: list[dict]):
        self.store = store
        self.personas = list(personas)

    def integrity(self) -> dict:
        quick = self.store.db.execute("PRAGMA quick_check").fetchone()[0]
        foreign = self.store.db.execute("PRAGMA foreign_key_check").fetchall()
        journal = self.store.db.execute("PRAGMA journal_mode").fetchone()[0]
        timeout = self.store.db.execute("PRAGMA busy_timeout").fetchone()[0]
        return {
            "quick_check": quick,
            "foreign_key_violations": len(foreign),
            "journal_mode": journal,
            "busy_timeout_ms": int(timeout),
            "healthy": quick == "ok" and not foreign,
        }

    def doctor(self) -> dict:
        def table_exists(name: str) -> bool:
            return self.store.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchone() is not None

        counts = {
            "candidates_total": self.store.db.execute(
                "SELECT COUNT(*) FROM candidates"
            ).fetchone()[0],
            "pending_review": self.store.db.execute(
                "SELECT COUNT(*) FROM candidates WHERE status='proposed'"
            ).fetchone()[0],
            "approved_not_published": self.store.db.execute(
                "SELECT COUNT(*) FROM candidates WHERE status='approved'"
            ).fetchone()[0],
            "published": self.store.db.execute(
                "SELECT COUNT(*) FROM candidates WHERE status='published'"
            ).fetchone()[0],
            "events": self.store.db.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0],
        }

        if table_exists("autopilot_run"):
            counts["autopilot_created_unsettled"] = self.store.db.execute(
                "SELECT COUNT(*) FROM autopilot_run WHERE status='created'"
            ).fetchone()[0]
        else:
            counts["autopilot_created_unsettled"] = 0

        if table_exists("knowledge"):
            counts["knowledge_total"] = self.store.db.execute(
                "SELECT COUNT(*) FROM knowledge"
            ).fetchone()[0]
            cols = {
                row["name"]
                for row in self.store.db.execute("PRAGMA table_info(knowledge)")
            }
            counts["knowledge_unembedded"] = (
                self.store.db.execute(
                    "SELECT COUNT(*) FROM knowledge WHERE embedding_json IS NULL"
                ).fetchone()[0]
                if "embedding_json" in cols else counts["knowledge_total"]
            )
        else:
            counts["knowledge_total"] = 0
            counts["knowledge_unembedded"] = 0

        if table_exists("engagement_draft"):
            counts["approved_engagement_outbox"] = self.store.db.execute(
                "SELECT COUNT(*) FROM engagement_draft WHERE status='approved'"
            ).fetchone()[0]
            counts["engagement_waiting_review"] = self.store.db.execute(
                "SELECT COUNT(*) FROM engagement_draft WHERE status='proposed'"
            ).fetchone()[0]
        else:
            counts["approved_engagement_outbox"] = 0
            counts["engagement_waiting_review"] = 0

        if table_exists("offer"):
            counts["active_offers"] = self.store.db.execute(
                "SELECT COUNT(*) FROM offer WHERE active=1"
            ).fetchone()[0]
        else:
            counts["active_offers"] = 0

        policy = DeepRLPolicy(
            self.store,
            [p["id"] for p in self.personas],
        )
        integrity = self.integrity()
        warnings = []
        if counts["pending_review"] >= 12:
            warnings.append("review_queue_high")
        if counts["autopilot_created_unsettled"] >= 10:
            warnings.append("learning_backlog_high")
        if counts["approved_engagement_outbox"] >= 25:
            warnings.append("engagement_outbox_high")
        if not integrity["healthy"]:
            warnings.append("database_integrity_failed")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "integrity": integrity,
            "counts": counts,
            "rl": {
                "experiences": policy.count(),
                "minimum_experiences": policy.min_experiences,
                "ready": policy.count() >= policy.min_experiences,
            },
            "warnings": warnings,
            "healthy": integrity["healthy"],
        }

    def backup(self, destination: str | Path) -> dict:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError("backup destination already exists")

        target = sqlite3.connect(str(destination))
        try:
            with target:
                self.store.db.backup(target)
        finally:
            target.close()

        raw = destination.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        verify = sqlite3.connect(str(destination))
        try:
            quick = verify.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            verify.close()
        if quick != "ok":
            destination.unlink(missing_ok=True)
            raise RuntimeError("backup integrity check failed")

        result = {
            "path": str(destination),
            "bytes": len(raw),
            "sha256": sha256,
            "quick_check": quick,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.store.record_event("database_backup_created", result)
        return result

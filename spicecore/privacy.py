"""Privacy-oriented data lifecycle controls for engagement content."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


PURGED = "[PURGED_BY_RETENTION]"


class DataLifecycle:
    def __init__(self, store):
        self.store = store

    def engagement_plan(self, retention_days: int = 30) -> dict:
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat()

        messages = self.store.db.execute(
            """SELECT m.id
               FROM engagement_message m
               WHERE m.ts < ?
                 AND m.body <> ?
                 AND NOT EXISTS (
                     SELECT 1 FROM engagement_draft d
                     WHERE d.inbound_message_id=m.id
                       AND d.status='proposed'
                 )""",
            (cutoff, PURGED),
        ).fetchall()

        drafts = self.store.db.execute(
            """SELECT id FROM engagement_draft
               WHERE ts < ?
                 AND body <> ?
                 AND status IN ('approved','rejected','revise')""",
            (cutoff, PURGED),
        ).fetchall()

        return {
            "retention_days": retention_days,
            "cutoff": cutoff,
            "message_ids": [row["id"] for row in messages],
            "draft_ids": [row["id"] for row in drafts],
            "messages_to_purge": len(messages),
            "drafts_to_purge": len(drafts),
        }

    def purge_engagement(self, retention_days: int = 30,
                         apply: bool = False, actor: str = "operator") -> dict:
        if not actor.strip():
            raise ValueError("actor is required")
        plan = self.engagement_plan(retention_days)
        result = {
            "retention_days": retention_days,
            "cutoff": plan["cutoff"],
            "messages_purged": 0,
            "drafts_purged": 0,
            "dry_run": not apply,
        }
        if not apply:
            result["messages_to_purge"] = plan["messages_to_purge"]
            result["drafts_to_purge"] = plan["drafts_to_purge"]
            return result

        with self.store.db:
            if plan["message_ids"]:
                placeholders = ",".join("?" for _ in plan["message_ids"])
                cursor = self.store.db.execute(
                    f"UPDATE engagement_message SET body=? WHERE id IN ({placeholders})",
                    (PURGED, *plan["message_ids"]),
                )
                result["messages_purged"] = cursor.rowcount
            if plan["draft_ids"]:
                placeholders = ",".join("?" for _ in plan["draft_ids"])
                cursor = self.store.db.execute(
                    f"UPDATE engagement_draft SET body=? WHERE id IN ({placeholders})",
                    (PURGED, *plan["draft_ids"]),
                )
                result["drafts_purged"] = cursor.rowcount

            self.store._event("engagement_retention_applied", {
                "retention_days": retention_days,
                "cutoff": plan["cutoff"],
                "messages_purged": result["messages_purged"],
                "drafts_purged": result["drafts_purged"],
                "actor": actor.strip(),
            })
        return result

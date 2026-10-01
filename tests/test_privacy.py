import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from spicecore.core import Store, load_personas
from spicecore.engagement import EngagementAgent
from spicecore.memory import KnowledgeBase
from spicecore.privacy import DataLifecycle, PURGED

ROOT = Path(__file__).resolve().parents[1]


class FakeProvider:
    model_name = "fake"

    def chat(self, system, user, temperature=0.4):
        return json.dumps({
            "reply": "A reviewed draft reply.",
            "intent": "general",
            "commerce_relevant": False,
            "handoff_reason": "",
        })


class DataLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "privacy.sqlite")
        self.persona = load_personas(ROOT / "personas")[0]
        self.agent = EngagementAgent(
            FakeProvider(), self.store, KnowledgeBase(self.store)
        )
        self.lifecycle = DataLifecycle(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def age(self, table, row_id, days=60):
        ts = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.store.db:
            self.store.db.execute(
                f"UPDATE {table} SET ts=? WHERE id=?",
                (ts, row_id),
            )

    def test_dry_run_does_not_modify_content(self):
        inbound = self.agent.ingest_inbound(
            self.persona, "Instagram", "conv-a", "msg-a", "old message"
        )
        draft = self.agent.draft_reply(self.persona, inbound["id"])
        self.agent.review_draft(draft["draft_id"], "approved", "operator")
        self.age("engagement_message", inbound["id"])
        self.age("engagement_draft", draft["draft_id"])

        result = self.lifecycle.purge_engagement(30, apply=False)
        self.assertEqual(result["messages_to_purge"], 1)
        self.assertEqual(result["drafts_to_purge"], 1)
        body = self.store.db.execute(
            "SELECT body FROM engagement_message WHERE id=?", (inbound["id"],)
        ).fetchone()[0]
        self.assertEqual(body, "old message")

    def test_apply_redacts_old_reviewed_content_but_preserves_rows(self):
        inbound = self.agent.ingest_inbound(
            self.persona, "Instagram", "conv-b", "msg-b", "old message"
        )
        draft = self.agent.draft_reply(self.persona, inbound["id"])
        self.agent.review_draft(draft["draft_id"], "rejected", "operator")
        self.age("engagement_message", inbound["id"])
        self.age("engagement_draft", draft["draft_id"])

        result = self.lifecycle.purge_engagement(
            30, apply=True, actor="privacy-job"
        )
        self.assertEqual(result["messages_purged"], 1)
        self.assertEqual(result["drafts_purged"], 1)
        message = self.store.db.execute(
            "SELECT body FROM engagement_message WHERE id=?", (inbound["id"],)
        ).fetchone()[0]
        reviewed = self.store.db.execute(
            "SELECT body,status FROM engagement_draft WHERE id=?",
            (draft["draft_id"],),
        ).fetchone()
        self.assertEqual(message, PURGED)
        self.assertEqual(reviewed["body"], PURGED)
        self.assertEqual(reviewed["status"], "rejected")
        self.assertEqual(
            self.store.events()[-1]["kind"],
            "engagement_retention_applied",
        )

    def test_pending_review_protects_inbound_context(self):
        inbound = self.agent.ingest_inbound(
            self.persona, "Instagram", "conv-c", "msg-c", "needs review"
        )
        draft = self.agent.draft_reply(self.persona, inbound["id"])
        self.age("engagement_message", inbound["id"])
        self.age("engagement_draft", draft["draft_id"])

        result = self.lifecycle.purge_engagement(
            30, apply=True, actor="privacy-job"
        )
        self.assertEqual(result["messages_purged"], 0)
        self.assertEqual(result["drafts_purged"], 0)


if __name__ == "__main__":
    unittest.main()

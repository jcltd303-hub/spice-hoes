import json
import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store, load_personas
from spicecore.engagement import EngagementAgent
from spicecore.memory import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]


class FakeProvider:
    model_name = "fake-engagement:v1"

    def __init__(self):
        self.calls = []

    def chat(self, system, user, temperature=0.4):
        self.calls.append((system, user, temperature))
        request = json.loads(user)
        latest = request["latest_inbound"].lower()
        return json.dumps({
            "reply": (
                "Yep — I’m an AI character. I can still help with the product details."
                if "are you ai" in latest
                else "That item is in the current product guide. I can help with the details."
            ),
            "intent": "product_question",
            "commerce_relevant": True,
            "handoff_reason": "",
        })


class EngagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "engagement.sqlite")
        self.people = load_personas(ROOT / "personas")
        self.persona = self.people[0]
        self.kb = KnowledgeBase(self.store)
        self.kb.add(
            "catalog",
            "Current product guide",
            "The current affiliate item is the black travel tote.",
            ["product", "affiliate"],
        )
        self.provider = FakeProvider()
        self.agent = EngagementAgent(self.provider, self.store, self.kb)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_inbound_is_idempotent_and_redacts_sensitive_data(self):
        first = self.agent.ingest_inbound(
            self.persona,
            "Instagram",
            "conversation-1",
            "message-1",
            "Email me at person@example.com and my card is 4111 1111 1111 1111",
        )
        second = self.agent.ingest_inbound(
            self.persona,
            "Instagram",
            "conversation-1",
            "message-1",
            "duplicate should not replace",
        )
        self.assertEqual(first["id"], second["id"])
        self.assertIn("[REDACTED_EMAIL]", first["body"])
        self.assertIn("[REDACTED_PAYMENT_NUMBER]", first["body"])
        count = self.store.db.execute(
            "SELECT COUNT(*) FROM engagement_message"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_draft_requires_review_and_approved_outbox_only_contains_approved(self):
        inbound = self.agent.ingest_inbound(
            self.persona,
            "Instagram",
            "conversation-2",
            "message-2",
            "Are you AI? What product is that?",
        )
        draft = self.agent.draft_reply(self.persona, inbound["id"])
        self.assertTrue(draft["requires_human_review"])
        self.assertEqual(draft["status"], "proposed")
        self.assertIn("AI character", draft["reply"])
        self.assertTrue(draft["retrieval"])
        self.assertEqual(self.agent.approved_outbox(), [])

        reviewed = self.agent.review_draft(
            draft["draft_id"],
            "approved",
            "operator",
            "safe to send",
        )
        self.assertEqual(reviewed["status"], "approved")
        outbox = self.agent.approved_outbox()
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox[0]["id"], draft["draft_id"])

    def test_rejected_draft_never_enters_outbox(self):
        inbound = self.agent.ingest_inbound(
            self.persona,
            "TikTok",
            "conversation-3",
            "message-3",
            "Tell me about the item",
        )
        draft = self.agent.draft_reply(self.persona, inbound["id"])
        self.agent.review_draft(draft["draft_id"], "rejected", "operator")
        self.assertEqual(self.agent.approved_outbox(), [])


if __name__ == "__main__":
    unittest.main()

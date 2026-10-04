import json
import tempfile
import unittest
from pathlib import Path

from spicecore.autoresponder import AutoResponder, validate_reply
from spicecore.core import Store
from spicecore.engagement import EngagementAgent
from spicecore.memory import KnowledgeBase


PERSONA = {
    "id": "zara_voss",
    "version": 3,
    "name": "Zara Voss",
    "age": 29,
    "voice": "warm, direct",
    "hobbies": ["music"],
    "disclosure": "Fictional AI persona",
}

CLEAN = "Hey! Great to hear from you. Fictional AI persona"
DIRTY = "Act now! Last chance, send me money via your bank account!"


class FakeChatProvider:
    model_name = "fake:test"

    def __init__(self, reply=CLEAN, handoff=""):
        self.reply = reply
        self.handoff = handoff
        self.calls = 0

    def chat(self, system, user, temperature=0.4):
        self.calls += 1
        return json.dumps({
            "reply": self.reply,
            "intent": "greeting",
            "commerce_relevant": False,
            "handoff_reason": self.handoff,
        })


def _setup(reply=CLEAN, handoff="", max_per_day=10):
    tmp = tempfile.TemporaryDirectory()
    store = Store(Path(tmp.name) / "ar.sqlite")
    agent = EngagementAgent(FakeChatProvider(reply, handoff), store, KnowledgeBase(store))
    responder = AutoResponder(agent, max_auto_per_day=max_per_day)
    return tmp, store, agent, responder


def _process(responder, conv="c", n="1", body="hello?"):
    return responder.process_inbound(
        PERSONA, "instagram", f"conv-{conv}", f"msg-{conv}-{n}", body
    )


class AutoResponderTests(unittest.TestCase):
    def test_clean_reply_auto_approved(self):
        tmp, store, agent, responder = _setup()
        try:
            result = _process(responder)
            self.assertEqual(result["action"], "auto_approved")
            self.assertEqual(result["status"], "approved")
            row = store.db.execute(
                "SELECT * FROM engagement_draft WHERE id=?", (result["draft_id"],)
            ).fetchone()
            self.assertEqual(row["status"], "approved")
            self.assertEqual(row["reviewer"], "auto-responder")
            self.assertIn("Fictional AI persona", row["body"])
            outbox = agent.approved_outbox()
            self.assertEqual(len(outbox), 1)
            self.assertEqual(outbox[0]["id"], result["draft_id"])
            kinds = [e["kind"] for e in store.events()]
            self.assertIn("auto_reply_approved", kinds)
        finally:
            store.close(); tmp.cleanup()

    def test_dirty_reply_held_for_human(self):
        tmp, store, agent, responder = _setup(reply=DIRTY)
        try:
            result = _process(responder)
            self.assertEqual(result["action"], "held")
            self.assertEqual(result["status"], "proposed")
            self.assertTrue(any("policy" in r for r in result["reasons"]))
            row = store.db.execute(
                "SELECT * FROM engagement_draft WHERE id=?", (result["draft_id"],)
            ).fetchone()
            self.assertEqual(row["status"], "proposed")  # still in review queue
            self.assertEqual(agent.approved_outbox(), [])  # not sendable
            kinds = [e["kind"] for e in store.events()]
            self.assertIn("auto_reply_held", kinds)
        finally:
            store.close(); tmp.cleanup()

    def test_handoff_reason_held(self):
        tmp, store, agent, responder = _setup(handoff="user seems distressed")
        try:
            result = _process(responder)
            self.assertEqual(result["action"], "held")
            self.assertTrue(any("handoff" in r for r in result["reasons"]))
        finally:
            store.close(); tmp.cleanup()

    def test_disclosure_appended_when_missing(self):
        tmp, store, agent, responder = _setup(reply="Hey there, good to see you!")
        try:
            result = _process(responder)
            self.assertEqual(result["action"], "auto_approved")
            self.assertIn("Fictional AI persona", result["reply"])
            self.assertEqual(validate_reply(result["reply"], PERSONA["disclosure"]), [])
        finally:
            store.close(); tmp.cleanup()

    def test_rate_limit_holds_overflow(self):
        tmp, store, agent, responder = _setup(max_per_day=1)
        try:
            first = _process(responder, conv="a", n="1")
            second = _process(responder, conv="a", n="2")
            self.assertEqual(first["action"], "auto_approved")
            self.assertEqual(second["action"], "held")
            self.assertIn("rate_limit", second["reasons"][0])
            # Held overflow is still drafted for the human queue.
            self.assertEqual(second["status"], "proposed")
        finally:
            store.close(); tmp.cleanup()

    def test_idempotent_per_external_message(self):
        tmp, store, agent, responder = _setup()
        try:
            first = _process(responder)
            second = _process(responder)
            self.assertEqual(second["action"], "already_processed")
            self.assertEqual(first["draft_id"], second["draft_id"])
            count = store.db.execute("SELECT COUNT(*) FROM engagement_draft").fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            store.close(); tmp.cleanup()

    def test_poll_processes_unhandled_only(self):
        tmp, store, agent, responder = _setup()
        try:
            agent.ingest_inbound(PERSONA, "instagram", "conv-a", "ext-1", "hi")
            agent.ingest_inbound(PERSONA, "instagram", "conv-b", "ext-2", "hello")
            results = responder.poll(PERSONA)
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r["action"] == "auto_approved" for r in results))
            # Second poll finds nothing left.
            self.assertEqual(responder.poll(PERSONA), [])
        finally:
            store.close(); tmp.cleanup()

    def test_requires_persona_disclosure(self):
        tmp, store, agent, responder = _setup()
        try:
            with self.assertRaises(ValueError):
                responder.process_inbound(
                    {"id": "x"}, "instagram", "c", "m", "hi"
                )
        finally:
            store.close(); tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

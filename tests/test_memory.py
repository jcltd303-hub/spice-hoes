import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.memory import KnowledgeBase


class FakeEmbedder:
    model_name = "fake-embed:v1"

    def embed(self, text):
        value = text.lower()
        if any(word in value for word in ("mirror", "outfit", "fashion", "garment")):
            return [1.0, 0.0, 0.0]
        if any(word in value for word in ("revenue", "profit", "money", "margin")):
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "memory.sqlite")
        self.kb = KnowledgeBase(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_approved_knowledge_is_retrieved_and_audited(self):
        one = self.kb.add("guide", "Mirror video", "Mirror outfit videos convert well", ["content"])
        self.kb.add("scratch", "Unverified", "Secret unrelated idea", approved=False)
        hits = self.kb.search("mirror outfit conversion")
        self.assertEqual(hits[0]["id"], one["id"])
        self.assertTrue(all(h["title"] != "Unverified" for h in hits))
        self.assertEqual(self.store.events()[-1]["kind"], "knowledge_added")

    def test_hybrid_search_recovers_semantic_match_without_token_overlap(self):
        kb = KnowledgeBase(self.store, embedder=FakeEmbedder())
        target = kb.add(
            "guide", "Mirror video", "Outfit clips perform as visual content.", ["content"]
        )
        kb.add("finance", "Margin tracking", "Revenue and profit reporting.", ["metrics"])
        hits = kb.search("fashion garment")
        self.assertEqual(hits[0]["id"], target["id"])
        self.assertEqual(hits[0]["retrieval_method"], "hybrid")
        self.assertGreater(hits[0]["semantic_score"], 0.9)
        self.assertEqual(hits[0]["lexical_score"], 0.0)

    def test_embedding_backfill_upgrades_existing_lexical_rows(self):
        item = self.kb.add("guide", "Mirror video", "Outfit clips perform well.", ["content"])
        hybrid = KnowledgeBase(self.store, embedder=FakeEmbedder())
        result = hybrid.backfill_embeddings()
        self.assertEqual(result["embedded"], 1)
        row = self.store.db.execute(
            "SELECT embedding_model FROM knowledge WHERE id=?", (item["id"],)
        ).fetchone()
        self.assertEqual(row["embedding_model"], "fake-embed:v1")


if __name__ == "__main__":
    unittest.main()

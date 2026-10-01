import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.memory import KnowledgeBase


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


if __name__ == "__main__":
    unittest.main()

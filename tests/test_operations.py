import sqlite3
import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store, load_personas
from spicecore.memory import KnowledgeBase
from spicecore.operations import Operations

ROOT = Path(__file__).resolve().parents[1]


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "ops.sqlite"
        self.store = Store(self.db_path)
        self.people = load_personas(ROOT / "personas")
        self.ops = Operations(self.store, self.people)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_integrity_reports_wal_and_busy_timeout(self):
        result = self.ops.integrity()
        self.assertTrue(result["healthy"])
        self.assertEqual(result["quick_check"], "ok")
        self.assertEqual(result["foreign_key_violations"], 0)
        self.assertEqual(result["journal_mode"].lower(), "wal")
        self.assertGreaterEqual(result["busy_timeout_ms"], 5000)

    def test_doctor_surfaces_review_and_embedding_backlogs(self):
        for i in range(12):
            self.store.propose(
                self.people[0],
                f"theme-{i}",
                "still",
                "TikTok",
                "affiliate",
            )
        KnowledgeBase(self.store).add(
            "guide", "Unembedded knowledge", "Observed project note.", ["test"]
        )
        result = self.ops.doctor()
        self.assertEqual(result["counts"]["pending_review"], 12)
        self.assertEqual(result["counts"]["knowledge_unembedded"], 1)
        self.assertIn("review_queue_high", result["warnings"])
        self.assertTrue(result["healthy"])

    def test_online_backup_is_verified_and_reopenable(self):
        self.store.propose(
            self.people[0], "studio", "still", "social", "set"
        )
        destination = Path(self.tmp.name) / "backup.sqlite"
        result = self.ops.backup(destination)
        self.assertTrue(destination.exists())
        self.assertGreater(result["bytes"], 0)
        self.assertEqual(len(result["sha256"]), 64)
        self.assertEqual(result["quick_check"], "ok")

        backup = sqlite3.connect(str(destination))
        try:
            count = backup.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        finally:
            backup.close()
        self.assertEqual(count, 1)

        with self.assertRaises(ValueError):
            self.ops.backup(destination)


if __name__ == "__main__":
    unittest.main()

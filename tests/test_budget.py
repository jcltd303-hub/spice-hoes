import concurrent.futures
import tempfile
import unittest
from spicecore.budget import BudgetLedger


class BudgetTests(unittest.TestCase):
    def test_concurrent_reservations(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = BudgetLedger(folder+'/budget.db', 100)
            def reserve(i):
                try:
                    return ledger.reserve(str(i), 30)
                except ValueError:
                    return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                reservations = list(pool.map(reserve, range(8)))
            self.assertEqual(sum(x is not None for x in reservations), 3)
            self.assertEqual(ledger.committed_cents(), 90)

    def test_settle_releases_unused_and_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = BudgetLedger(folder+'/budget.db', 100)
            rid = ledger.reserve('run', 80)
            ledger.settle(rid, 12)
            ledger.settle(rid, 12)
            self.assertEqual(BudgetLedger(folder+'/budget.db', 100).committed_cents(), 12)
            with self.assertRaises(ValueError):
                ledger.settle(rid, 13)

    def test_invalid_amounts_and_memory_rejected(self):
        with self.assertRaises(ValueError):
            BudgetLedger(':memory:', 100)

    def test_overrun_is_charged_beyond_reservation_and_halts(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = BudgetLedger(folder+'/budget.db', 100)
            rid = ledger.reserve('run', 2)
            ledger.record_overrun(rid, 'run', 120)
            self.assertEqual(ledger.committed_cents(), 120)
            with self.assertRaises(ValueError):
                ledger.reserve('next', 1)
            ledger.settle(rid, 120)
            self.assertEqual(BudgetLedger(folder+'/budget.db', 100).committed_cents(), 120)
            with self.assertRaises(ValueError):
                BudgetLedger(folder+'/budget.db', 1000).reserve('restart', 1)

    def test_cross_midnight_settlement_counts_current_day(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = BudgetLedger(folder+'/budget.db', 100)
            rid = ledger.reserve('run', 80)
            with ledger._connect() as db:
                db.execute("UPDATE budget SET day='2000-01-01' WHERE id=?", (rid,))
            self.assertEqual(ledger.committed_cents(), 80)
            ledger.settle(rid, 20)
            self.assertEqual(ledger.committed_cents(), 20)

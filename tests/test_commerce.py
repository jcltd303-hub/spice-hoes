import hashlib
import hmac
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from spicecore.commerce import StripeCommerce
from spicecore.core import Store, load_personas
from spicecore.offers import OfferRegistry


ROOT = Path(__file__).resolve().parents[1]
SECRET = "whsec_test_local_fixture"


def signed(event, timestamp=None):
    raw = json.dumps(event, sort_keys=True).encode()
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(SECRET.encode(), str(timestamp).encode() + b"." + raw,
                      hashlib.sha256).hexdigest()
    return raw, f"t={timestamp},v1={digest}"


def event(eid, kind, obj, live=True):
    return {"id": eid, "type": kind, "livemode": live,
            "created": int(time.time()), "data": {"object": obj}}


class StripeCommerceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "commerce.sqlite"
        self.store = Store(self.path)
        self.registry = OfferRegistry(self.store)
        self.personas = load_personas(ROOT / "personas")
        self.offer = self.registry.create("Actual Checkout", "digital_product",
                                          expected_payout_cents=99999,
                                          variable_cost_cents=100)
        self.cid = self.store.propose(self.personas[0], "travel", "still", "test",
                                      "digital_product", cost_cents=50)
        self.store.review(self.cid, "approved", "tester")
        self.store.publish(self.cid, "https://example.test/post")
        self.link = self.registry.register_candidate(self.cid, self.offer["id"],
                                                     "https://example.test/buy")
        self.commerce = StripeCommerce(self.store, SECRET)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def checkout(self, eid="evt_checkout", session="cs_checkout", intent="pi_checkout",
                 **overrides):
        obj = {"id": session, "object": "checkout.session", "payment_intent": intent,
               "status": "complete", "payment_status": "paid", "amount_total": 1200,
               "currency": "usd", "client_reference_id": self.link["tracking_token"]}
        obj.update(overrides)
        return event(eid, "checkout.session.completed", obj)

    def ingest(self, item):
        return self.commerce.ingest(*signed(item))

    def outcomes(self, kind):
        return [e for e in self.store.events() if e["kind"] == kind]

    def test_signed_actual_payment_and_unit_cost_are_recorded_once(self):
        first = self.ingest(self.checkout())
        self.assertEqual(first["state"], "processed")
        self.assertEqual(first["amount_cents"], 1200)
        again = self.ingest(self.checkout())
        self.assertTrue(again["duplicate"])
        self.assertEqual(len(self.outcomes("purchase")), 1)
        self.assertEqual(self.outcomes("purchase")[0]["payload"]["amount_cents"], 1200)
        self.assertEqual(len(self.outcomes("commerce_cost")), 1)
        report = self.commerce.status()
        self.assertEqual(report["verified_gross_cents"], 1200)
        self.assertEqual(report["cost_basis_cents"], 150)
        self.assertEqual(report["net_contribution_cents"], 1050)
        self.assertEqual(report["cash_payout_cents"], 0)
        self.assertEqual(report["unknown_fee_transactions"], 1)

    def test_operating_contribution_includes_content_that_did_not_convert(self):
        nonconverting = self.store.propose(self.personas[0], "no-sale", "still", "test",
                                           "digital_product", cost_cents=500)
        self.store.review(nonconverting, "approved", "tester")
        self.store.publish(nonconverting, "https://example.test/no-sale")
        self.store.record_outcome(nonconverting, "distribution_cost", 300)
        self.ingest(self.checkout())
        report = self.commerce.status()
        self.assertEqual(report["transaction_contribution_cents"], 1050)
        self.assertEqual(report["operating_contribution_cents"], 250)
        self.assertEqual(report["net_contribution_cents"], 250)
        self.assertEqual(report["generation_cost_basis_cents"], 550)
        self.assertEqual(report["distribution_cost_basis_cents"], 300)
        self.assertEqual(report["cost_basis_cents"], 950)
        self.assertEqual(report["transaction_cost_basis_cents"], 150)
        self.assertFalse(report["net_contribution_complete"])
        self.assertEqual(report["cost_basis_scope"], "all_recorded_store_costs")

    def test_rejected_asset_costs_are_reported_even_without_sales(self):
        rejected = self.store.propose(self.personas[1], "rejected", "still", "test",
                                      "digital_product", cost_cents=175)
        self.store.review(rejected, "rejected", "tester")
        report = self.commerce.status()
        self.assertEqual(report["verified_gross_cents"], 0)
        self.assertEqual(report["transaction_contribution_cents"], 0)
        self.assertEqual(report["operating_contribution_cents"], -225)
        self.assertFalse(report["net_contribution_complete"])
        self.assertIsNone(report["unrecorded_costs_cents"])
        self.assertTrue(report["cost_basis_limitations"])

    def test_provider_reconciliation_does_not_claim_all_costs_are_known(self):
        self.ingest(self.checkout())
        self.ingest(event("evt_zero_fee", "charge.updated", {
            "id": "ch_checkout", "payment_intent": "pi_checkout", "currency": "usd",
            "balance_transaction": {"id": "txn_zero_fee", "currency": "usd", "fee": 0}}))
        report = self.commerce.status()
        self.assertTrue(report["provider_reconciliation_complete"])
        self.assertFalse(report["net_contribution_complete"])

    def test_scoped_totals_select_verified_transactions_and_exclude_manual_estimates(self):
        self.ingest(self.checkout())
        self.store.record_outcome(self.cid, "purchase", 99999)
        other = self.store.propose(self.personas[1], "other-sale", "still", "test",
                                   "digital_product", cost_cents=70)
        self.store.review(other, "approved", "tester")
        self.store.publish(other, "https://example.test/other-sale")
        other_link = self.registry.register_candidate(other, self.offer["id"],
                                                       "https://example.test/other-buy")
        self.ingest(self.checkout("evt_other_sale", session="cs_other_sale", intent="pi_other_sale",
                                  amount_total=1700, client_reference_id=other_link["tracking_token"]))
        self.ingest(event("evt_scoped_fee", "charge.updated", {
            "id": "ch_checkout", "payment_intent": "pi_checkout", "currency": "usd",
            "balance_transaction": {"id": "txn_scoped_fee", "currency": "usd", "fee": 65}}))
        self.ingest(event("evt_scoped_refund", "refund.updated", {
            "id": "re_scoped", "payment_intent": "pi_checkout", "charge": "ch_checkout",
            "currency": "usd", "amount": 200, "status": "succeeded"}))
        self.ingest(event("evt_scoped_dispute", "charge.dispute.funds_withdrawn", {
            "id": "dp_scoped", "payment_intent": "pi_checkout", "charge": "ch_checkout",
            "currency": "usd", "amount": 300, "status": "needs_response"}))
        scoped = self.commerce.verified_totals([self.cid])
        self.assertEqual(scoped["verified_gross_cents"], 1200)
        self.assertEqual(scoped["verified_refund_cents"], 200)
        self.assertEqual(scoped["verified_chargeback_cents"], 300)
        self.assertEqual(scoped["known_fee_cents"], 65)
        self.assertEqual(scoped["configured_unit_cost_basis_cents"], 100)
        self.assertEqual(scoped["transactions"], 1)
        self.assertEqual(scoped["unknown_fee_transactions"], 0)
        self.assertEqual(self.commerce.verified_totals()["verified_gross_cents"], 2900)
        self.assertEqual(self.commerce.verified_totals([])["verified_gross_cents"], 0)

    def test_only_authenticated_canonical_money_events_are_whitelisted(self):
        self.ingest(self.checkout())
        ids = {row["event_id"] for row in self.store.db.execute("SELECT event_id FROM verified_money_event")}
        self.assertIn(self.outcomes("purchase")[0]["id"], ids)
        self.assertIn(self.outcomes("commerce_cost")[0]["id"], ids)
        manual = self.store.record_outcome(self.cid, "purchase", 2000)
        self.assertNotIn(manual["id"], ids)
        fixture = self.checkout("evt_unverified_fixture", session="cs_test_fixture", intent="pi_test_fixture")
        fixture["livemode"] = False
        self.ingest(fixture)
        self.assertEqual(len(ids), self.store.db.execute("SELECT COUNT(*) FROM verified_money_event").fetchone()[0])

    def test_signature_uses_original_bytes_and_bounded_timestamp(self):
        raw, header = signed(self.checkout())
        with self.assertRaises(PermissionError):
            self.commerce.ingest(raw + b" ", header)
        for ts in (int(time.time()) - 301, int(time.time()) + 301):
            with self.assertRaises(PermissionError):
                self.commerce.ingest(*signed(self.checkout(), ts))
        with self.assertRaises(PermissionError):
            self.commerce.ingest(raw, header.replace("v1=", "v0="))
        self.commerce.ingest(raw, "v1=" + "0" * 64 + "," + header)
        self.assertEqual(len(self.outcomes("purchase")), 1)

    def test_event_id_conflict_is_durable_and_session_types_do_not_duplicate(self):
        self.ingest(self.checkout())
        with self.assertRaises(ValueError):
            self.ingest(self.checkout(amount_total=1300))
        later = self.checkout("evt_async")
        later["type"] = "checkout.session.async_payment_succeeded"
        self.ingest(later)
        self.store.close()
        self.store = Store(self.path)
        self.commerce = StripeCommerce(self.store, SECRET)
        self.assertTrue(self.ingest(later)["duplicate"])
        self.assertEqual(len(self.outcomes("purchase")), 1)
        with self.assertRaises(ValueError):
            self.ingest(self.checkout("evt_conflict", amount_total=1000))
        with self.assertRaises(ValueError):
            self.ingest(self.checkout("evt_pi_reuse", session="cs_other"))

    def test_only_actual_integer_usd_paid_checkout_creates_revenue(self):
        self.assertEqual(self.ingest(self.checkout(payment_status="unpaid"))["state"],
                         "ignored")
        for amount in (None, "1200", 1200.0, True, -1):
            with self.assertRaises(ValueError):
                self.ingest(self.checkout("evt_invalid", amount_total=amount))
        with self.assertRaises(ValueError):
            self.ingest(self.checkout("evt_eur", currency="eur"))
        no_charge = self.checkout("evt_zero", amount_total=0)
        self.assertEqual(self.ingest(no_charge)["state"], "ignored")
        self.assertFalse(self.outcomes("purchase"))

    def test_signed_test_payments_are_audit_only_including_explicit_test_mode(self):
        item = self.checkout()
        item["livemode"] = False
        self.assertEqual(self.ingest(item)["state"], "test")
        self.commerce = StripeCommerce(self.store, SECRET, live_mode=False)
        item["id"] = "evt_sandbox"
        self.assertEqual(self.ingest(item)["state"], "test")
        self.assertFalse(self.outcomes("purchase"))
        self.assertFalse(self.outcomes("commerce_cost"))
        self.assertEqual(self.commerce.status()["verified_gross_cents"], 0)
        self.assertEqual(self.commerce.status()["verified_test_events"], 2)

    def test_metadata_reference_works_and_customer_fields_are_discarded(self):
        item = self.checkout(client_reference_id="customer@example.test",
                             metadata={"spice_ref": self.link["tracking_token"],
                                       "email": "pii@example.test"},
                             customer_details={"name": "Private Person",
                                               "email": "pii@example.test"})
        self.ingest(item)
        tables = [r["name"] for r in self.store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'stripe_%'")]
        for table in tables + ["events"]:
            serialized = repr([tuple(r) for r in self.store.db.execute(f"SELECT * FROM {table}")])
            self.assertNotIn("@example.test", serialized)
            self.assertNotIn("Private Person", serialized)
        self.assertEqual(len(self.outcomes("purchase")), 1)

    def test_pending_attribution_retries_after_register_and_publish(self):
        other = self.store.propose(self.personas[0], "other", "still", "test", "offer")
        self.store.review(other, "approved", "tester")
        link = self.registry.register_candidate(other, self.offer["id"],
                                                "https://example.test/other")
        item = self.checkout(client_reference_id=link["tracking_token"])
        self.assertEqual(self.ingest(item)["state"], "pending")
        self.assertFalse(self.outcomes("purchase"))
        self.store.publish(other, "https://example.test/post2")
        result = self.commerce.retry_pending()
        self.assertEqual(result["remaining"], 0)
        self.assertEqual(len(self.outcomes("purchase")), 1)

        future = self.checkout("evt_future", session="cs_future", intent="pi_future",
                               client_reference_id="future_token")
        self.assertEqual(self.ingest(future)["state"], "pending")
        self.store.db.execute("UPDATE candidate_offer SET tracking_token=? WHERE candidate_id=?",
                              ("future_token", other))
        self.store.db.commit()
        self.assertEqual(self.commerce.retry_pending()["remaining"], 0)
        self.assertEqual(len(self.outcomes("purchase")), 2)

    def test_refund_before_purchase_is_durable_and_reconciled(self):
        refund = event("evt_refund", "charge.refunded",
                       {"id": "ch_checkout", "payment_intent": "pi_checkout",
                        "currency": "usd", "amount": 1200, "amount_refunded": 200})
        self.assertEqual(self.ingest(refund)["state"], "pending")
        self.store.close()
        self.store = Store(self.path)
        self.commerce = StripeCommerce(self.store, SECRET)
        self.ingest(self.checkout())
        self.assertEqual(self.commerce.retry_pending()["remaining"], 0)
        self.assertEqual(self.commerce.status()["verified_refund_cents"], 200)
        self.assertEqual(len(self.outcomes("refund")), 1)

    def test_cumulative_partial_refunds_and_individual_statuses_never_double_count(self):
        self.ingest(self.checkout())
        base = {"id": "ch_checkout", "payment_intent": "pi_checkout",
                "currency": "usd", "amount": 1200}
        self.ingest(event("evt_partial1", "charge.refunded", {**base, "amount_refunded": 200}))
        self.ingest(event("evt_partial2", "charge.refunded", {**base, "amount_refunded": 500}))
        self.ingest(event("evt_stale", "charge.refunded", {**base, "amount_refunded": 200}))
        refund = {"id": "re_one", "payment_intent": "pi_checkout", "charge": "ch_checkout",
                  "currency": "usd", "amount": 200, "status": "succeeded"}
        self.ingest(event("evt_refund_obj", "refund.updated", refund))
        self.assertEqual(self.commerce.status()["verified_refund_cents"], 500)
        self.assertEqual([e["payload"]["amount_cents"] for e in self.outcomes("refund")], [200, 300])
        refund.update(id="re_two", amount=600, status="pending")
        self.ingest(event("evt_refund_pending", "refund.created", refund))
        self.assertEqual(self.commerce.status()["verified_refund_cents"], 500)
        refund["status"] = "succeeded"
        self.ingest(event("evt_refund_success", "refund.updated", refund))
        self.assertEqual(self.commerce.status()["verified_refund_cents"], 800)
        self.commerce.retry_pending()
        self.assertEqual(self.commerce.status()["verified_refund_cents"], 800)

    def test_verified_fees_chargeback_and_cash_payout_are_separate(self):
        self.ingest(self.checkout())
        charge = {"id": "ch_checkout", "payment_intent": "pi_checkout", "currency": "usd",
                  "balance_transaction": {"id": "txn_checkout", "currency": "usd", "fee": 65}}
        self.ingest(event("evt_charge", "charge.updated", charge))
        self.ingest(event("evt_charge_again", "charge.succeeded", charge))
        dispute = {"id": "dp_checkout", "charge": "ch_checkout", "payment_intent": "pi_checkout",
                   "currency": "usd", "amount": 300, "status": "needs_response"}
        self.ingest(event("evt_dispute", "charge.dispute.funds_withdrawn", dispute))
        self.ingest(event("evt_payout", "payout.paid",
                          {"id": "po_fixture", "currency": "usd", "amount": 500, "status": "paid"}))
        report = self.commerce.status()
        self.assertEqual(report["verified_gross_cents"], 1200)
        self.assertEqual(report["known_fee_cents"], 65)
        self.assertEqual(report["verified_chargeback_cents"], 300)
        self.assertEqual(report["net_contribution_cents"], 685)
        self.assertEqual(report["cash_payout_cents"], 500)
        self.assertEqual(report["unknown_fee_transactions"], 0)
        self.assertEqual(len(self.outcomes("chargeback")), 1)
        self.assertFalse(self.outcomes("refund"))
        stats = next(s for s in self.store.stats(self.personas)
                     if s["persona_id"] == self.personas[0]["id"])
        self.assertEqual(stats["net_cents"], 685)
        self.assertEqual(stats["chargeback_cents"], 300)
        self.assertEqual(stats["refund_cents"], 0)
        self.ingest(event("evt_won", "charge.dispute.funds_reinstated", {**dispute, "status": "won"}))
        self.assertEqual(self.commerce.status()["verified_chargeback_cents"], 0)
        self.assertEqual(self.commerce.status()["net_contribution_cents"], 985)
        self.assertEqual(len(self.outcomes("chargeback_reversal")), 1)
        self.assertEqual(len(self.outcomes("purchase")), 1)
        stats = next(s for s in self.store.stats(self.personas)
                     if s["persona_id"] == self.personas[0]["id"])
        self.assertEqual(stats["net_cents"], 985)

    def test_known_fee_credit_corrects_cost_without_creating_a_purchase(self):
        self.ingest(self.checkout())
        refund = {"id": "re_credit", "payment_intent": "pi_checkout", "charge": "ch_checkout",
                  "currency": "usd", "amount": 200, "status": "succeeded",
                  "balance_transaction": {"id": "txn_fee_credit", "currency": "usd", "fee": -25}}
        self.ingest(event("evt_credit", "refund.updated", refund))
        self.assertEqual(self.commerce.status()["known_fee_cents"], -25)
        self.assertEqual(self.commerce.status()["net_contribution_cents"], 875)
        self.assertEqual(len(self.outcomes("commerce_cost_reversal")), 1)
        self.assertEqual(len(self.outcomes("purchase")), 1)
        stats = next(s for s in self.store.stats(self.personas)
                     if s["persona_id"] == self.personas[0]["id"])
        self.assertEqual(stats["net_cents"], 875)

    def test_refunds_are_economic_evidence_before_attribution(self):
        checkout = self.checkout(client_reference_id="not_yet_registered")
        self.ingest(checkout)
        self.ingest(event("evt_unattributed_refund", "charge.refunded", {
            "id": "ch_checkout", "payment_intent": "pi_checkout", "currency": "usd",
            "amount_refunded": 250}))
        self.assertFalse(self.outcomes("purchase"))
        self.assertFalse(self.outcomes("refund"))
        self.assertEqual(self.commerce.status()["verified_gross_cents"], 1200)
        self.assertEqual(self.commerce.status()["verified_refund_cents"], 250)
        self.assertEqual(self.commerce.status()["unattributed_gross_cents"], 1200)
        self.store.db.execute("UPDATE candidate_offer SET tracking_token=? WHERE candidate_id=?",
                              ("not_yet_registered", self.cid))
        self.store.db.commit()
        self.assertEqual(self.commerce.retry_pending()["remaining"], 0)
        self.assertEqual(len(self.outcomes("refund")), 1)
        self.assertEqual(self.outcomes("refund")[0]["payload"]["amount_cents"], 250)

    def test_reordered_dispute_credits_are_balanced_and_payout_failures_remove_cash(self):
        self.ingest(self.checkout())
        dispute = {"id": "dp_checkout", "payment_intent": "pi_checkout", "charge": "ch_checkout",
                   "currency": "usd", "amount": 300, "status": "won"}
        self.ingest(event("evt_dispute_credit", "charge.dispute.funds_reinstated", dispute))
        self.ingest(event("evt_dispute_debit", "charge.dispute.funds_withdrawn", dispute))
        self.ingest(event("evt_dispute_duplicate", "charge.dispute.closed", {**dispute, "status": "lost"}))
        self.assertEqual(len(self.outcomes("chargeback")), 1)
        self.assertEqual(len(self.outcomes("chargeback_reversal")), 1)
        self.assertEqual(self.commerce.status()["verified_chargeback_cents"], 0)
        payout = {"id": "po_one", "currency": "usd", "amount": 500, "status": "paid"}
        self.ingest(event("evt_paid", "payout.paid", payout))
        self.ingest(event("evt_failed", "payout.failed", {**payout, "status": "failed"}))
        self.ingest(event("evt_old_paid", "payout.paid", payout))
        self.assertEqual(self.commerce.status()["cash_payout_cents"], 0)

    def test_complete_charge_refund_list_identifies_overlap_before_new_snapshot(self):
        self.ingest(self.checkout())
        first = {"id": "re_first", "charge": "ch_checkout", "payment_intent": "pi_checkout",
                 "currency": "usd", "amount": 200, "status": "succeeded"}
        second = {**first, "id": "re_second", "amount": 300}
        charge = {"id": "ch_checkout", "payment_intent": "pi_checkout", "currency": "usd",
                  "amount_refunded": 200, "refunds": {"has_more": False, "data": [first]}}
        self.ingest(event("evt_complete_snapshot", "charge.refunded", charge))
        self.ingest(event("evt_new_individual", "refund.updated", second))
        self.assertEqual(self.commerce.status()["verified_refund_cents"], 500)
        charge["amount_refunded"] = 500
        charge["refunds"]["data"].append(second)
        self.ingest(event("evt_updated_snapshot", "charge.refunded", charge))
        self.assertEqual(self.commerce.status()["verified_refund_cents"], 500)
        self.assertEqual(sum(e["payload"]["amount_cents"] for e in self.outcomes("refund")), 500)
        self.assertEqual(self.commerce.retry_pending()["remaining"], 0)
        self.assertEqual(self.commerce.status()["refund_reconciliation_incomplete_transactions"], 0)

    def test_concurrent_duplicate_deliveries_create_one_transaction(self):
        raw, header = signed(self.checkout())

        def deliver(_):
            store = Store(self.path)
            try:
                return StripeCommerce(store, SECRET).ingest(raw, header)
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(deliver, range(4)))
        self.assertEqual(sum(not r["duplicate"] for r in results), 1)
        self.assertEqual(len(self.outcomes("purchase")), 1)
        self.assertEqual(self.commerce.status()["transactions"], 1)

    def test_local_receipt_payment_and_outcomes_roll_back_together(self):
        original = self.store._event

        def fail_cost(kind, payload, external_id=None):
            if kind == "commerce_cost":
                raise RuntimeError("local failure")
            return original(kind, payload, external_id)

        with patch.object(self.store, "_event", side_effect=fail_cost):
            with self.assertRaises(RuntimeError):
                self.ingest(self.checkout())
        self.assertFalse(self.outcomes("purchase"))
        self.assertEqual(self.commerce.status()["verified_gross_cents"], 0)
        self.assertEqual(self.commerce.status()["received_events"], 0)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM verified_money_event").fetchone()[0], 0)
        self.assertEqual(self.ingest(self.checkout())["state"], "processed")
        self.assertEqual(len(self.outcomes("purchase")), 1)


if __name__ == "__main__":
    unittest.main()

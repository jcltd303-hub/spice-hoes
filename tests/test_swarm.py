import json
import hashlib
import hmac
import time
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from spicecore.autopilot import CoreAutopilot
from spicecore.core import Store, load_personas
from spicecore.experiments import ExperimentPlanner
from spicecore.learning import LearningController
from spicecore.memory import KnowledgeBase
from spicecore.offers import OfferRegistry
from spicecore.runtime_policy import RuntimePolicy
from spicecore.swarm import SwarmConfig, SwarmRuntime
from spicecore.commerce import StripeCommerce
from spicecore.distribution.base import PublishResult, PlatformMetrics, pending_publish_result


ROOT = Path(__file__).resolve().parents[1]


class PlanProvider:
    def chat(self, system, user, **kwargs):
        request = json.loads(user)
        return json.dumps({
            "hypothesis": "An outfit framing changes attributed contribution.",
            "primary_metric": "net contribution cents",
            "reversal_condition": "Repeated costs exceed verified sales.",
            "variants": [{"id": f"v{i}", "theme": f"outfit-{i}",
                          "creative_angle": f"framing-{i}", "scene": "studio"}
                         for i in range(request["variant_count"])],
        })


class Deliberator:
    def deliberate(self, objective, persona):
        return {"synthesis": {"evidence": [], "proposed_action": "test outfits"}}


class Generator:
    def __init__(self, store, root):
        self.store, self.root = store, root
        self.calls = 0
        self.fail = False
        self.identity_passed = True

    def generate(self, persona, theme, channel, offer, scene="", seed=None, cost_cents=0):
        self.calls += 1
        if self.fail:
            raise RuntimeError("worker unavailable")
        path = self.root / f"asset-{self.calls}.png"
        path.write_bytes(b"test media bytes")
        cid = self.store.propose(persona, theme, "still", channel, offer,
                                 asset_uri=str(path), cost_cents=cost_cents)
        self.store.record_event("identity_checked", {
            "candidate_id": cid, "scored": True, "passed": self.identity_passed,
            "score": 0.95, "threshold": 0.82,
        })
        self.store.record_event("quality_checked", {
            "candidate_id": cid, "passed": True, "score": 0.96, "threshold": 0.78,
        })
        return {"candidate_id": cid, "status": "proposed"}


class ReceiptPublisher:
    def __init__(self, now):
        self.now = now
        self.calls = 0

    def publish(self, **kwargs):
        self.calls += 1
        return PublishResult(True, "instagram", external_post_id=f"post-{self.calls}",
                             canonical_url=f"https://www.instagram.com/p/shortcode-{self.calls}/",
                             published_at=self.now.isoformat())

    def fetch_metrics(self, post_id, account_id):
        return PlatformMetrics("instagram", post_id, views=150, link_clicks=4,
                               fetched_at=self.now.isoformat())


class HostedMedia:
    def prepare(self, candidate):
        if not Path(candidate["asset_uri"]).is_file():
            raise ValueError("missing test asset")
        return "https://media.example/" + candidate["id"] + ".jpg"


class SwarmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "swarm.sqlite"
        self.store = Store(self.path)
        self.people = load_personas(ROOT / "personas")
        self.generator = Generator(self.store, self.root)
        self.planner = ExperimentPlanner(PlanProvider(), self.store)
        self.autopilot = CoreAutopilot(self.store, self.people, Deliberator(),
                                       self.planner, self.generator)
        self.learning = LearningController(self.store, self.people, self.planner,
                                            KnowledgeBase(self.store), verified_revenue_only=True)
        self.offer = OfferRegistry(self.store).create("Style guide", "digital_product",
                                                     metadata={"facts": ["A PDF style guide"]})
        self.config = SwarmConfig(
            campaign_id="test-launch", offer_id=self.offer["id"],
            destination_url="https://buy.stripe.com/test_checkout",
            accounts={p["id"]: "123456789" for p in self.people},
            generation_enabled=True, auto_approve=True, variants=2,
            generation_reservation_cents=80, asset_cost_cents=10,
            generation_interval_seconds=3600, observation_window_seconds=3600,
        )
        self.now = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def runtime(self, **kwargs):
        kwargs.setdefault("media_delivery", HostedMedia())
        return SwarmRuntime(self.store, self.people, self.config,
                            autopilot=self.autopilot, learning=self.learning, **kwargs)

    def test_missing_configuration_reports_blockers_without_model_calls(self):
        empty = SwarmConfig(generation_enabled=True)
        runtime = SwarmRuntime(self.store, self.people, empty)
        report = runtime.tick(now=self.now)
        self.assertEqual(report["generation"]["status"], "blocked")
        self.assertIn("offer_id", report["blockers"])
        self.assertIn("accounts", report["blockers"])
        self.assertEqual(self.generator.calls, 0)

    def test_batch_links_offers_and_only_scored_assets_are_auto_approved(self):
        result = self.runtime().tick(now=self.now)
        self.assertEqual(result["generation"]["status"], "created")
        self.assertEqual(self.generator.calls, 2)
        rows = self.store.db.execute("SELECT * FROM candidates").fetchall()
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["status"], "approved")
            content = self.store.db.execute(
                "SELECT * FROM swarm_content WHERE candidate_id=?", (row["id"],)).fetchone()
            self.assertIn("Style guide", content["caption"])
            self.assertIn("client_reference_id=", content["tracked_url"])
            self.assertIn("spice_ref=", content["tracked_url"])
        self.assertIn("uncertainty_note", result["recommendation"])

    def test_failed_identity_is_held_for_review(self):
        self.generator.identity_passed = False
        result = self.runtime().tick(now=self.now)
        self.assertEqual(result["release"]["held"], 2)
        self.assertEqual({r[0] for r in self.store.db.execute("SELECT status FROM candidates")},
                         {"proposed"})

    def test_restart_preserves_generation_cadence(self):
        self.runtime().tick(now=self.now)
        restarted = self.runtime()
        result = restarted.tick(now=self.now + timedelta(seconds=30))
        self.assertEqual(result["generation"]["reason"], "generation_interval")
        self.assertEqual(self.generator.calls, 2)

    def test_failed_batch_consumes_reservation_and_backs_off(self):
        RuntimePolicy(self.store).update({"daily_budget_cents": 100}, actor="test")
        self.generator.fail = True
        first = self.runtime().tick(now=self.now)
        self.assertEqual(first["generation"]["status"], "failed")
        self.assertEqual(first["budget"]["reserved_today_cents"], 80)
        second = self.runtime().tick(now=self.now + timedelta(hours=2))
        self.assertEqual(second["generation"]["reason"], "daily_budget_limit")
        self.assertEqual(self.generator.calls, 1)

    def test_monthly_ceiling_persists_between_days(self):
        self.config.monthly_budget_cents = 100
        self.runtime().tick(now=self.now)
        result = self.runtime().tick(now=self.now + timedelta(days=1))
        self.assertEqual(result["generation"]["reason"], "monthly_budget_limit")
        self.assertEqual(self.generator.calls, 2)

    def test_generation_off_does_not_disable_other_phases(self):
        self.config.generation_enabled = False
        runtime = self.runtime()
        report = runtime.tick(now=self.now)
        self.assertEqual(report["generation"]["reason"], "generation_disabled")
        self.assertIn("publishing", report)
        self.assertIn("commerce", report)
        self.assertIn("learning", report)

    def test_manual_review_is_preserved(self):
        self.config.auto_approve = False
        result = self.runtime().tick(now=self.now)
        self.assertEqual(result["release"]["held"], 2)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM candidates WHERE status='approved'").fetchone()[0], 0)

    def test_zero_reservation_and_unknown_config_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            SwarmConfig(generation_enabled=True, generation_reservation_cents=0).validate()
        with self.assertRaises(ValueError):
            SwarmConfig.from_dict({"hidden_provider_fallback": "paid"})

    def test_model_pass_flags_cannot_override_owner_thresholds(self):
        self.config.generation_enabled = False
        cid = self.generator.generate(self.people[0], "style", "instagram", "Style guide")["candidate_id"]
        self.store.record_event("identity_checked", {
            "candidate_id": cid, "scored": True, "passed": True, "score": 0.1,
        })
        runtime = self.runtime()
        self.store.db.execute("INSERT INTO swarm_content(candidate_id,campaign_id,run_id) VALUES(?,?,?)",
                              (cid, self.config.campaign_id, "run"))
        self.store.db.commit()
        result = runtime.tick(now=self.now)
        self.assertEqual(result["release"]["approved"], 0)
        self.assertEqual(self.store.candidate(cid)["status"], "proposed")

    def test_another_process_lock_prevents_calls(self):
        first = self.runtime()
        lock = first._lock()
        try:
            self.assertEqual(self.runtime().tick(now=self.now)["status"], "busy")
            self.assertEqual(self.generator.calls, 0)
        finally:
            lock.close()

    def test_full_tick_publishes_then_signed_sale_and_refund_close_learning(self):
        publisher = ReceiptPublisher(self.now)
        commerce = StripeCommerce(self.store, "whsec-test")
        runtime = self.runtime(publishers={"instagram": publisher}, commerce=commerce)
        first = runtime.tick(now=self.now)
        self.assertEqual(len(first["publishing"]), 2)
        self.assertEqual(publisher.calls, 2)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM candidates WHERE status='published'").fetchone()[0], 2)
        link = self.store.db.execute("SELECT * FROM candidate_offer LIMIT 1").fetchone()

        def ingest(kind, identifier, obj):
            event = {"id": identifier, "type": kind, "livemode": True,
                     "data": {"object": obj}}
            raw = json.dumps(event).encode()
            stamp = int(time.time())
            sig = hmac.new(b"whsec-test", str(stamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
            return commerce.ingest(raw, f"t={stamp},v1={sig}")

        ingest("checkout.session.completed", "evt_sale", {
            "id": "cs_sale", "payment_status": "paid", "amount_total": 1000,
            "currency": "usd", "payment_intent": "pi_sale",
            "client_reference_id": link["tracking_token"],
        })
        ingest("charge.refunded", "evt_refund", {
            "id": "ch_sale", "payment_intent": "pi_sale", "currency": "usd",
            "amount_refunded": 200,
        })
        self.config.generation_enabled = False
        second = runtime.tick(now=self.now + timedelta(hours=2))
        self.assertEqual(len(second["learning"]), 1)
        self.assertEqual(second["learning"][0]["reward_cents"], 780)
        self.assertEqual(publisher.calls, 2)
        self.assertEqual(sum(s["revenue_cents"] for s in self.store.stats(self.people)), 1000)
        self.assertEqual(sum(s["refund_cents"] for s in self.store.stats(self.people)), 200)
        self.assertEqual(sum(s["views"] for s in self.store.stats(self.people)), 300)
        self.assertEqual(sum(s["impressions"] for s in self.store.stats(self.people)), 0)
        again = self.runtime(publishers={"instagram": publisher}, commerce=commerce).tick(
            now=self.now + timedelta(hours=3))
        self.assertEqual(again["learning"], [])
        self.assertEqual(self.learning.policy.count(), 1)
        self.assertEqual(publisher.calls, 2)
        prior = self.learning._existing(second["learning"][0]["run_id"])
        ingest("charge.refunded", "evt_later_refund", {
            "id": "ch_sale", "payment_intent": "pi_sale", "currency": "usd",
            "amount_refunded": 500,
        })
        corrected = runtime.tick(now=self.now + timedelta(days=4))
        self.assertEqual(corrected["learning"][0]["status"], "corrected")
        self.assertEqual(corrected["learning"][0]["reward_cents"], 480)
        latest = self.learning._existing(prior["run_id"])
        self.assertEqual(latest["experience_id"], prior["experience_id"])
        self.assertEqual(self.learning.policy.count(), 1)
        old = self.store.db.execute("SELECT approved FROM knowledge WHERE id=?",
                                    (prior["knowledge_id"],)).fetchone()
        self.assertFalse(old[0])

    def test_pending_publication_reserves_daily_slot_before_receipt(self):
        class PendingPublisher(ReceiptPublisher):
            def publish(self, **kwargs):
                self.calls += 1
                return pending_publish_result("instagram", {
                    "phase": "published", "media_id": f"media-{self.calls}"})
        publisher = PendingPublisher(self.now)
        self.config.max_posts_per_day = 1
        runtime = self.runtime(publishers={"instagram": publisher})
        report = runtime.tick(now=self.now)
        self.assertEqual(publisher.calls, 1)
        self.assertEqual(len(report["publishing"]), 1)

    def test_invalid_account_path_rejected_before_generation(self):
        self.config.accounts[self.people[0]["id"]] = "123/media_publish?creation_id=123"
        with self.assertRaises(ValueError):
            self.runtime()
        self.assertEqual(self.generator.calls, 0)

    def test_cost_status_includes_nonconverting_content_and_failed_reservations(self):
        cid = self.generator.generate(self.people[0], "unsold", "instagram", "guide",
                                      cost_cents=500)["candidate_id"]
        other = self.generator.generate(self.people[1], "other-campaign", "instagram", "guide",
                                        cost_cents=999)["candidate_id"]
        self.store.record_event("distribution_cost", {"candidate_id": cid,
                               "persona_id": self.people[0]["id"], "amount_cents": 30})
        runtime = self.runtime(commerce=StripeCommerce(self.store, "whsec-test"))
        self.store.db.execute("INSERT INTO swarm_content(candidate_id,campaign_id,run_id) VALUES(?,?,?)",
                              (cid, self.config.campaign_id, "nonconverting-run"))
        self.store.db.execute("INSERT INTO swarm_attempt VALUES(?,?,?,?,?,?,?)",
                              ("failed", self.config.campaign_id, self.now.isoformat(), 80,
                               "failed", None, "RuntimeError"))
        self.store.db.commit()
        money = runtime.status(now=self.now)["campaign_contribution"]
        self.assertEqual(money["recorded_asset_cost_basis_cents"], 500)
        self.assertEqual(money["recorded_distribution_cost_cents"], 30)
        self.assertEqual(money["contribution_after_recorded_cost_basis_cents"], -530)
        self.assertEqual(money["contribution_after_generation_reservations_cents"], -610)
        self.assertFalse(money["complete"])

    def test_learning_requires_confirmed_publication_timestamps(self):
        self.runtime().tick(now=self.now)
        for row in self.store.db.execute("SELECT id FROM candidates").fetchall():
            self.store.publish(row["id"], "https://www.instagram.com/p/manual/")
            self.store.record_event("view", {"candidate_id": row["id"], "count": 150,
                                   "persona_id": self.store.candidate(row["id"])["persona_id"]})
        self.assertEqual(self.runtime()._learn(self.now + timedelta(days=1)), [])
        self.assertEqual(self.learning.policy.count(), 0)


if __name__ == "__main__":
    unittest.main()

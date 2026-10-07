"""Late monetary outcomes must correct settled learning without adding experiences."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spicecore.analytics.ingest import AnalyticsIngestor
from spicecore.analytics.normalize import NormalizedMetrics
from spicecore.autopilot import CoreAutopilot
from spicecore.core import Store, load_personas
from spicecore.deeprl import DeepRLPolicy
from spicecore.experiments import ExperimentPlanner
from spicecore.learning import LearningController, LearningNotReady
from spicecore.memory import KnowledgeBase
from test_learning import FakeGenerator, FakeMoA, FakePlanProvider


ROOT = Path(__file__).resolve().parents[1]


class ForbiddenEmbedder:
    def embed(self, text):
        raise AssertionError("unexpected external embedding call")


class LearningReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "learning.sqlite")
        self.people = load_personas(ROOT / "personas")
        self.planner = ExperimentPlanner(FakePlanProvider(), self.store)
        self.autopilot = CoreAutopilot(
            self.store, self.people, FakeMoA(), self.planner, FakeGenerator(self.store), min_experiences=4,
        )
        self.knowledge = KnowledgeBase(self.store)
        self.learning = LearningController(
            self.store, self.people, self.planner, self.knowledge, min_experiences=4,
        )
        self.run = self.autopilot.run_once(
            "Improve affiliate conversion", "TikTok", "affiliate", variant_count=2,
            seed=20, cost_cents_per_asset=10, max_pending_review=6, daily_budget_cents=500,
        )
        self.variants = self.planner.get(self.run["plan_id"])["variants"]
        for index, variant in enumerate(self.variants):
            cid = variant["candidate_id"]
            self.store.review(cid, "approved", "operator")
            self.store.publish(cid, f"https://example.org/{index}")
            self.store.record_event("impression", {
                "candidate_id": cid, "persona_id": self.run["persona_id"], "amount_cents": 0, "count": 500,
            }, external_id=f"original-exposure-{index}")
        self.cid = self.variants[0]["candidate_id"]
        self.store.record_outcome(self.cid, "purchase", 2000, "original-sale")
        self.original = self.learning.settle_autopilot_run(self.run["run_id"])
        self.assertEqual(self.original["reward_cents"], 1980)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def reconcile(self):
        return self.learning.reconcile_autopilot_run(self.run["run_id"])

    def ready_run(self):
        run = self.autopilot.run_once(
            "Additional measured experiment", "TikTok", "affiliate", variant_count=2,
            seed=21, cost_cents_per_asset=10, max_pending_review=6, daily_budget_cents=500,
        )
        variants = self.planner.get(run["plan_id"])["variants"]
        for index, variant in enumerate(variants):
            cid = variant["candidate_id"]
            self.store.review(cid, "approved", "operator")
            self.store.publish(cid, f"https://example.org/additional-{index}")
            self.store.record_event("impression", {
                "candidate_id": cid, "persona_id": run["persona_id"], "amount_cents": 0, "count": 100,
            }, external_id=f"additional-exposure-{run['run_id']}-{index}")
        cid = variants[0]["candidate_id"]
        sale = self.store.record_outcome(cid, "purchase", 1000, f"additional-sale-{run['run_id']}")
        return run, cid, sale

    def knowledge_rows(self):
        return [dict(row) for row in self.store.db.execute("SELECT * FROM knowledge ORDER BY ts,id")]

    def experience(self):
        return dict(self.store.db.execute(
            "SELECT * FROM rl_experience WHERE id=?", (self.original["experience_id"],),
        ).fetchone())

    def local_state(self):
        return {
            "events": self.store.events(),
            "knowledge": self.knowledge_rows(),
            "experience": self.experience(),
            "closure": dict(self.store.db.execute(
                "SELECT * FROM learning_closure WHERE run_id=?", (self.run["run_id"],),
            ).fetchone()),
        }

    def test_late_refund_corrects_same_experience_and_supersedes_knowledge(self):
        old_events = self.store.events()
        self.store.record_outcome(self.cid, "refund", 1000, "late-refund")
        result = self.reconcile()
        self.assertEqual(result["status"], "corrected")
        self.assertTrue(result["changed"])
        self.assertEqual(result["reward_cents"], 980)
        self.assertEqual(result["experience_id"], self.original["experience_id"])
        self.assertEqual(self.learning.policy.count(), 1)
        self.assertEqual(self.experience()["reward"], 9.8)
        self.assertEqual(json.loads(self.experience()["next_state_json"]), DeepRLPolicy.features(self.store.stats(self.people)))
        rows = {row["id"]: row for row in self.knowledge_rows()}
        self.assertEqual(rows[self.original["knowledge_id"]]["approved"], 0)
        self.assertEqual(rows[result["knowledge_id"]]["approved"], 1)
        self.assertEqual(json.loads(rows[result["knowledge_id"]]["body"])["reward_cents"], 980)
        self.assertEqual(self.store.events()[:len(old_events)], old_events)
        correction = [e for e in self.store.events() if e["kind"] == "autopilot_learning_corrected"][-1]
        self.assertEqual(correction["payload"]["previous_reward_cents"], 1980)
        self.assertEqual(correction["payload"]["reward_cents"], 980)
        self.assertEqual(correction["payload"]["superseded_knowledge_id"], self.original["knowledge_id"])
        hits = self.knowledge.search("observed experiment affiliate conversion")
        self.assertNotIn(self.original["knowledge_id"], {hit["id"] for hit in hits})
        self.assertIn(result["knowledge_id"], {hit["id"] for hit in hits})

    def test_replay_and_new_exposure_do_not_create_additional_corrections(self):
        self.store.record_outcome(self.cid, "refund", 1000, "late-refund")
        corrected = self.reconcile()
        before = self.local_state()
        for _ in range(3):
            result = self.reconcile()
            self.assertEqual(result["status"], "unchanged")
            self.assertFalse(result["changed"])
            self.assertEqual(result["knowledge_id"], corrected["knowledge_id"])
            self.assertEqual(result["reward_cents"], 980)
        self.assertEqual(self.local_state(), before)
        self.store.record_event("impression", {
            "candidate_id": self.cid, "persona_id": self.run["persona_id"], "amount_cents": 0, "count": 1000,
        }, external_id="late-exposure")
        self.store.record_outcome(self.cid, "click", external_id="late-click")
        before = self.local_state()
        for _ in range(3):
            result = self.reconcile()
            self.assertEqual(result["status"], "unchanged")
            self.assertEqual(result["summary"]["total_impressions"], 2000)
        self.assertEqual(self.local_state(), before)
        self.assertEqual(self.learning.policy.count(), 1)

    def test_chargebacks_fees_and_reversals_correct_monetary_evidence(self):
        self.store.record_outcome(self.cid, "chargeback", 1200, "late-chargeback")
        self.store.record_outcome(self.cid, "commerce_cost", 40, "late-fee")
        first = self.reconcile()
        self.assertEqual(first["reward_cents"], 740)
        self.store.record_outcome(self.cid, "chargeback_reversal", 1200, "chargeback-won")
        self.store.record_outcome(self.cid, "commerce_cost_reversal", 40, "fee-credit")
        second = self.reconcile()
        self.assertEqual(second["status"], "corrected")
        self.assertEqual(second["reward_cents"], 1980)
        outcome = second["summary"]["variants"][0]
        self.assertEqual(outcome["revenue_cents"], 2000)
        self.assertEqual(outcome["chargeback_cents"], 1200)
        self.assertEqual(outcome["chargeback_reversal_cents"], 1200)
        self.assertEqual(outcome["commerce_cost_cents"], 40)
        self.assertEqual(outcome["commerce_cost_reversal_cents"], 40)
        self.assertEqual(self.learning.policy.count(), 1)
        self.assertEqual(sum(row["approved"] for row in self.knowledge_rows()), 1)
        self.assertEqual(len(self.knowledge_rows()), 3)

    def test_net_neutral_adjustments_still_correct_the_monetary_breakdown(self):
        self.store.record_outcome(self.cid, "chargeback", 100, "late-chargeback")
        self.store.record_outcome(self.cid, "chargeback_reversal", 100, "chargeback-won")
        result = self.reconcile()
        self.assertEqual(result["status"], "corrected")
        self.assertEqual(result["reward_cents"], 1980)
        self.assertEqual(len(self.knowledge_rows()), 2)
        before = self.local_state()
        self.assertEqual(self.reconcile()["status"], "unchanged")
        self.assertEqual(self.local_state(), before)

    def test_correction_failure_rolls_back_all_learning_writes(self):
        self.store.record_outcome(self.cid, "refund", 1000, "late-refund")
        before = self.local_state()
        original_event = self.store._event

        def fail_correction(kind, payload, external_id=None):
            if kind == "autopilot_learning_corrected":
                raise RuntimeError("audit write failed")
            return original_event(kind, payload, external_id)

        with patch.object(self.store, "_event", side_effect=fail_correction):
            with self.assertRaisesRegex(RuntimeError, "audit write failed"):
                self.reconcile()
        self.assertEqual(self.local_state(), before)
        self.assertEqual(self.reconcile()["reward_cents"], 980)

    def test_enclosing_transaction_can_roll_back_correction(self):
        self.store.record_outcome(self.cid, "refund", 1000, "late-refund")
        before = self.local_state()
        with self.assertRaisesRegex(RuntimeError, "abort outer work"):
            with self.store.db:
                self.store.db.execute("UPDATE autopilot_run SET reason='temporary' WHERE id=?", (self.run["run_id"],))
                self.reconcile()
                raise RuntimeError("abort outer work")
        self.assertEqual(self.local_state(), before)
        self.assertEqual(self.reconcile()["reward_cents"], 980)

    def test_correction_never_calls_embedding_provider_or_nested_committing_add(self):
        self.store.record_outcome(self.cid, "refund", 1000, "late-refund")
        self.knowledge.embedder = ForbiddenEmbedder()
        with patch.object(self.knowledge, "add", side_effect=AssertionError("nested committing add")):
            result = self.reconcile()
        self.assertEqual(result["reward_cents"], 980)
        corrected = {row["id"]: row for row in self.knowledge_rows()}[result["knowledge_id"]]
        self.assertIsNone(corrected["embedding_json"])

    def test_unknown_and_unsettled_runs_do_not_modify_learning(self):
        pending = self.autopilot.run_once(
            "Next experiment", "TikTok", "affiliate", variant_count=2, seed=21,
            max_pending_review=6, daily_budget_cents=500,
        )
        before = self.local_state()
        with self.assertRaises(ValueError):
            self.learning.reconcile_autopilot_run("missing")
        with self.assertRaises(LearningNotReady):
            self.learning.reconcile_autopilot_run(pending["run_id"])
        self.assertEqual(self.local_state(), before)

    def test_views_without_impressions_require_explicit_views_exposure_gate(self):
        run = self.autopilot.run_once(
            "Learn from measured video exposure", "TikTok", "affiliate", variant_count=2,
            seed=21, cost_cents_per_asset=10, max_pending_review=6, daily_budget_cents=500,
        )
        variants = self.planner.get(run["plan_id"])["variants"]
        ingestor = AnalyticsIngestor(self.store)
        for index, variant in enumerate(variants):
            cid = variant["candidate_id"]
            self.store.review(cid, "approved", "operator")
            self.store.publish(cid, f"https://example.org/views-{index}")
            ingestor.ingest(NormalizedMetrics(
                platform="tiktok", post_id=f"views-only-{index}", candidate_id=cid,
                persona_id=run["persona_id"], views=100,
            ))
        with self.assertRaises(LearningNotReady):
            self.learning.settle_autopilot_run(run["run_id"])
        self.assertEqual(self.learning.policy.count(), 1)
        result = self.learning.settle_autopilot_run(run["run_id"], exposure_metric="views")
        self.assertEqual(result["status"], "settled")
        self.assertEqual(result["total_impressions"], 0)
        self.assertEqual(result["total_views"], 200)
        self.assertEqual(result["summary"]["exposure_metric"], "views")
        self.store.record_outcome(variants[0]["candidate_id"], "distribution_cost", 5, "views-delivery-fee")
        corrected = self.learning.reconcile_autopilot_run(run["run_id"])
        self.assertEqual(corrected["status"], "corrected")
        self.assertEqual(corrected["reward_cents"], -25)
        self.assertEqual(corrected["summary"]["exposure_metric"], "views")
        self.assertEqual(corrected["total_views"], 200)
        self.assertEqual(corrected["total_impressions"], 0)
        self.assertEqual(self.learning.policy.count(), 2)

    def test_unknown_exposure_metric_is_rejected(self):
        before = self.local_state()
        with self.assertRaisesRegex(ValueError, "exposure_metric"):
            self.learning.settle_autopilot_run(self.run["run_id"], exposure_metric="engagement")
        self.assertEqual(self.local_state(), before)

    def test_verified_reconciliation_ignores_manual_monetary_outcomes(self):
        verified = LearningController(
            self.store, self.people, self.planner, self.knowledge, min_experiences=4,
            verified_revenue_only=True,
        )
        corrected = verified.reconcile_autopilot_run(self.run["run_id"])
        self.assertEqual(corrected["status"], "corrected")
        self.assertEqual(corrected["reward_cents"], -20)
        self.assertEqual(corrected["summary"]["variants"][0]["revenue_cents"], 0)
        self.assertTrue(corrected["summary"]["verified_revenue_only"])
        self.assertEqual(json.loads(self.experience()["next_state_json"]),
                         DeepRLPolicy.features(self.store.stats(self.people, verified_revenue_only=True)))
        self.store.record_outcome(self.cid, "refund", 1000, "manual-refund")
        self.store.record_outcome(self.cid, "purchase", 1000, "manual-estimated-sale")
        before = self.local_state()
        result = verified.reconcile_autopilot_run(self.run["run_id"])
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["reward_cents"], -20)
        self.assertEqual(self.local_state(), before)
        self.assertEqual(self.learning.policy.count(), 1)

    def test_verified_settlement_ignores_manual_money_and_filters_next_state(self):
        run = self.autopilot.run_once(
            "Learn from verified sales", "TikTok", "affiliate", variant_count=2,
            seed=21, cost_cents_per_asset=10, max_pending_review=6, daily_budget_cents=500,
        )
        variants = self.planner.get(run["plan_id"])["variants"]
        for index, variant in enumerate(variants):
            cid = variant["candidate_id"]
            self.store.review(cid, "approved", "operator")
            self.store.publish(cid, f"https://example.org/verified-{index}")
            self.store.record_event("impression", {
                "candidate_id": cid, "persona_id": run["persona_id"], "amount_cents": 0, "count": 100,
            }, external_id=f"verified-exposure-{index}")
        self.store.record_outcome(variants[0]["candidate_id"], "purchase", 2000, "manual-sale-new-run")
        verified = LearningController(
            self.store, self.people, self.planner, self.knowledge, min_experiences=4,
            verified_revenue_only=True,
        )
        result = verified.settle_autopilot_run(run["run_id"])
        self.assertEqual(result["reward_cents"], -20)
        self.assertTrue(result["summary"]["verified_revenue_only"])
        experience = self.store.db.execute("SELECT * FROM rl_experience WHERE id=?", (result["experience_id"],)).fetchone()
        self.assertEqual(experience["reward"], -0.2)
        self.assertEqual(json.loads(experience["next_state_json"]),
                         DeepRLPolicy.features(self.store.stats(self.people, verified_revenue_only=True)))
        self.assertEqual(self.learning.policy.count(), 2)

    def test_verified_sale_and_late_refund_correct_the_same_experience(self):
        verified = LearningController(
            self.store, self.people, self.planner, self.knowledge, min_experiences=4,
            verified_revenue_only=True,
        )
        self.assertEqual(verified.reconcile_autopilot_run(self.run["run_id"])["reward_cents"], -20)
        sale_id = self.store.db.execute("SELECT id FROM events WHERE external_id='original-sale'").fetchone()["id"]
        with self.store.db:
            self.store.db.execute("INSERT INTO verified_money_event(event_id,provider) VALUES(?,?)", (sale_id, "stripe"))
        sale = verified.reconcile_autopilot_run(self.run["run_id"])
        self.assertEqual(sale["reward_cents"], 1980)
        refund = self.store.record_outcome(self.cid, "refund", 1000, "verified-late-refund")
        with self.store.db:
            self.store.db.execute("INSERT INTO verified_money_event(event_id,provider) VALUES(?,?)", (refund["id"], "stripe"))
        corrected = verified.reconcile_autopilot_run(self.run["run_id"])
        self.assertEqual(corrected["status"], "corrected")
        self.assertEqual(corrected["reward_cents"], 980)
        self.assertEqual(corrected["experience_id"], self.original["experience_id"])
        self.assertEqual(self.experience()["reward"], 9.8)
        self.assertEqual(self.learning.policy.count(), 1)
        before = self.local_state()
        self.assertEqual(verified.reconcile_autopilot_run(self.run["run_id"])["status"], "unchanged")
        self.assertEqual(self.local_state(), before)

    def test_initial_close_failure_rolls_back_replay_and_rag_then_refund_stays_consistent(self):
        run, cid, _ = self.ready_run()
        before = self.local_state()
        original_event = self.store._event

        def fail_close(kind, payload, external_id=None):
            if kind == "autopilot_learning_closed":
                raise RuntimeError("initial close audit failed")
            return original_event(kind, payload, external_id)

        with patch.object(self.store, "_event", side_effect=fail_close):
            with self.assertRaisesRegex(RuntimeError, "initial close audit failed"):
                self.learning.settle_autopilot_run(run["run_id"])
        self.assertEqual(self.learning.policy.count(), 1)
        self.assertEqual(self.local_state(), before)
        self.assertIsNone(self.store.db.execute("SELECT * FROM learning_closure WHERE run_id=?", (run["run_id"],)).fetchone())
        settled = self.learning.settle_autopilot_run(run["run_id"])
        self.assertEqual(settled["reward_cents"], 980)
        self.store.record_outcome(cid, "refund", 1000, "post-retry-refund")
        corrected = self.learning.reconcile_autopilot_run(run["run_id"])
        self.assertEqual(corrected["reward_cents"], -20)
        approved = self.store.db.execute("SELECT body FROM knowledge WHERE source=? AND approved=1", (f"experiment:{run['plan_id']}",)).fetchall()
        self.assertEqual([json.loads(row["body"])["reward_cents"] for row in approved], [-20])
        self.assertEqual(self.learning.policy.count(), 2)
        self.assertEqual(settled["experience_id"], corrected["experience_id"])

    def test_refund_revokes_all_legacy_approved_duplicate_knowledge(self):
        orphan = self.knowledge.add(
            source=f"experiment:{self.run['plan_id']}", title="Legacy orphan results",
            body=json.dumps(self.original["summary"]), tags=["observed", "experiment"], approved=True,
        )
        self.store.record_outcome(self.cid, "refund", 1000, "late-refund")
        corrected = self.reconcile()
        approved = self.store.db.execute("SELECT id FROM knowledge WHERE source=? AND approved=1", (f"experiment:{self.run['plan_id']}",)).fetchall()
        self.assertEqual([row["id"] for row in approved], [corrected["knowledge_id"]])
        event = [item for item in self.store.events() if item["kind"] == "autopilot_learning_corrected"][-1]
        self.assertEqual(set(event["payload"]["superseded_knowledge_ids"]), {self.original["knowledge_id"], orphan["id"]})

    def test_initial_settlement_avoids_embedding_and_nested_committing_helpers(self):
        run, _, _ = self.ready_run()
        self.knowledge.embedder = ForbiddenEmbedder()
        with patch.object(self.knowledge, "add", side_effect=AssertionError("nested committing knowledge add")), \
                patch.object(self.learning.policy, "record", side_effect=AssertionError("nested committing replay insert")):
            result = self.learning.settle_autopilot_run(run["run_id"])
        self.assertEqual(result["reward_cents"], 980)
        self.assertEqual(self.learning.policy.count(), 2)

    def test_production_promotes_rederived_legacy_episode_without_new_replay_row(self):
        sale_id = self.store.db.execute("SELECT id FROM events WHERE external_id='original-sale'").fetchone()["id"]
        with self.store.db:
            self.store.db.execute("INSERT INTO verified_money_event(event_id,provider) VALUES(?,?)", (sale_id, "stripe"))
        verified = LearningController(
            self.store, self.people, self.planner, self.knowledge, min_experiences=4,
            verified_revenue_only=True,
        )
        self.assertEqual(verified.policy.count(), 0)
        result = verified.reconcile_autopilot_run(self.run["run_id"])
        self.assertEqual(result["status"], "corrected")
        self.assertEqual(result["reward_cents"], 1980)
        self.assertEqual(result["experience_id"], self.original["experience_id"])
        self.assertEqual(verified.policy.count(), 1)
        self.assertEqual(self.learning.policy.count(), 1)
        marker = self.store.db.execute("SELECT experience_id FROM rl_verified_experience").fetchall()
        self.assertEqual([row["experience_id"] for row in marker], [result["experience_id"]])
        before = self.local_state()
        self.assertEqual(verified.reconcile_autopilot_run(self.run["run_id"])["status"], "unchanged")
        self.assertEqual(self.local_state(), before)

    def test_verified_episode_marker_commits_with_initial_settlement(self):
        run, _, sale = self.ready_run()
        with self.store.db:
            self.store.db.execute("INSERT INTO verified_money_event(event_id,provider) VALUES(?,?)", (sale["id"], "stripe"))
        verified = LearningController(
            self.store, self.people, self.planner, self.knowledge, min_experiences=4,
            verified_revenue_only=True,
        )
        self.assertEqual(verified.policy.count(), 0)
        original_event = self.store._event

        def fail_close(kind, payload, external_id=None):
            if kind == "autopilot_learning_closed":
                raise RuntimeError("verified close audit failed")
            return original_event(kind, payload, external_id)

        with patch.object(self.store, "_event", side_effect=fail_close):
            with self.assertRaisesRegex(RuntimeError, "verified close audit failed"):
                verified.settle_autopilot_run(run["run_id"])
        self.assertEqual(verified.policy.count(), 0)
        self.assertEqual(self.learning.policy.count(), 1)
        result = verified.settle_autopilot_run(run["run_id"])
        self.assertEqual(result["reward_cents"], 980)
        self.assertEqual(verified.policy.count(), 1)
        self.assertEqual(self.learning.policy.count(), 2)
        marker = self.store.db.execute("SELECT experience_id FROM rl_verified_experience").fetchall()
        self.assertEqual([row["experience_id"] for row in marker], [result["experience_id"]])

    def test_legacy_partial_episode_retry_reuses_replay_and_replaces_orphan_rag(self):
        run, cid, _ = self.ready_run()
        state = run["policy"]["state"]
        legacy_experience_id = self.learning.policy.record(
            state, run["persona_id"], 980, DeepRLPolicy.features(self.store.stats(self.people)),
            done=True, external_id=f"autopilot-learning:{run['run_id']}",
        )
        orphan = self.knowledge.add(
            source=f"experiment:{run['plan_id']}", title="Legacy partial results",
            body=json.dumps({"reward_cents": 980}), approved=True,
        )
        self.store.record_outcome(cid, "refund", 1000, "legacy-partial-late-refund")
        result = self.learning.settle_autopilot_run(run["run_id"])
        self.assertEqual(result["reward_cents"], -20)
        self.assertEqual(result["experience_id"], legacy_experience_id)
        self.assertEqual(self.learning.policy.count(), 2)
        replay = self.store.db.execute("SELECT reward FROM rl_experience WHERE id=?", (legacy_experience_id,)).fetchone()
        self.assertEqual(replay["reward"], -0.2)
        approved = self.store.db.execute("SELECT body FROM knowledge WHERE source=? AND approved=1", (f"experiment:{run['plan_id']}",)).fetchall()
        self.assertEqual([json.loads(row["body"])["reward_cents"] for row in approved], [-20])
        old = self.store.db.execute("SELECT approved FROM knowledge WHERE id=?", (orphan["id"],)).fetchone()
        self.assertEqual(old["approved"], 0)

    def test_unverified_rewrite_removes_episode_from_production_training_scope(self):
        verified = LearningController(
            self.store, self.people, self.planner, self.knowledge, min_experiences=4,
            verified_revenue_only=True,
        )
        self.assertEqual(verified.reconcile_autopilot_run(self.run["run_id"])["reward_cents"], -20)
        self.assertEqual(verified.policy.count(), 1)
        manual = self.learning.reconcile_autopilot_run(self.run["run_id"])
        self.assertEqual(manual["status"], "corrected")
        self.assertEqual(manual["reward_cents"], 1980)
        self.assertEqual(verified.policy.count(), 0)
        self.assertEqual(self.learning.policy.count(), 1)

    def test_atomic_settlement_preserves_unknown_action_validation(self):
        run, _, _ = self.ready_run()
        with self.store.db:
            self.store.db.execute("UPDATE autopilot_run SET persona_id=? WHERE id=?", ("unknown_persona", run["run_id"]))
        before = self.local_state()
        with self.assertRaisesRegex(ValueError, "Unknown action"):
            self.learning.settle_autopilot_run(run["run_id"])
        self.assertEqual(self.local_state(), before)
        self.assertEqual(self.learning.policy.count(), 1)


if __name__ == "__main__":
    unittest.main()

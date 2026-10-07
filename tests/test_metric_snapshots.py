"""Regression tests for cumulative social observations and aggregate ledger counts."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spicecore.analytics.ingest import AnalyticsIngestor
from spicecore.analytics.normalize import MetricsNormalizer, NormalizedMetrics
from spicecore.core import Store
from spicecore.distribution.base import PlatformMetrics
from spicecore.experiments import ExperimentPlanner


class CumulativeMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "metrics.sqlite"
        self.store = Store(self.path)
        self.persona = {"id": "ruby_wren", "name": "Ruby Wren", "version": "v1"}
        self.cid = self.store.propose(
            self.persona, "astronomy", "video", "instagram", "zine", cost_cents=25,
        )
        self.store.review(self.cid, "approved", "operator")
        self.store.publish(self.cid, "https://instagram.com/p/post-1")
        self.ingestor = AnalyticsIngestor(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def snapshot(self, impressions=100, clicks=10, timestamp="2026-10-06T10:01:00+00:00", **kwargs):
        return MetricsNormalizer.normalize_generic(
            "instagram", {"fetched_at": timestamp, "impressions": impressions, "link_clicks": clicks},
            self.cid, self.persona["id"], "post-1", **kwargs,
        )

    def stats(self):
        return self.store.stats([self.persona])[0]

    def test_real_normalizer_adds_only_growth_in_same_hour(self):
        first = self.snapshot()
        second = self.snapshot(160, 15, "2026-10-06T10:02:00+00:00")
        self.assertNotEqual(first.external_id, second.external_id)
        self.ingestor.ingest(first)
        self.ingestor.ingest(second)
        self.ingestor.ingest(second)
        self.assertEqual(self.stats()["impressions"], 160)
        self.assertEqual(self.stats()["clicks"], 15)
        outcomes = [e for e in self.store.events() if e["kind"] == "impression"]
        self.assertEqual([e["payload"]["count"] for e in outcomes], [100, 60])

    def test_unique_observation_ids_do_not_double_lifetime_counters(self):
        self.ingestor.ingest(replace(self.snapshot(), external_id="poll-one"))
        self.ingestor.ingest(replace(self.snapshot(), external_id="poll-two"))
        self.ingestor.ingest(replace(self.snapshot(140, 13), external_id="poll-three"))
        self.assertEqual(self.stats()["impressions"], 140)
        self.assertEqual(self.stats()["clicks"], 13)

    def test_watermark_survives_reopen_and_decreases_remain_auditable(self):
        self.ingestor.ingest(self.snapshot())
        self.store.close()
        self.store = Store(self.path)
        self.ingestor = AnalyticsIngestor(self.store)
        self.ingestor.ingest(self.snapshot(80, 6, "2026-10-06T09:59:00+00:00"))
        self.ingestor.ingest(self.snapshot(90, 8, "2026-10-06T10:03:00+00:00"))
        self.assertEqual(self.stats()["impressions"], 100)
        self.assertEqual(self.stats()["clicks"], 10)
        self.ingestor.ingest(self.snapshot(120, 11, "2026-10-06T10:04:00+00:00"))
        self.assertEqual(self.stats()["impressions"], 120)
        observations = [e for e in self.store.events() if e["kind"] == "metrics_ingested"]
        self.assertTrue(observations[1]["payload"]["accounting"]["stale"])
        self.assertIn("impressions", observations[2]["payload"]["accounting"]["decreased_fields"])

    def test_conflicting_observation_id_raises_without_writes(self):
        self.ingestor.ingest(replace(self.snapshot(), external_id="same-observation"))
        before = self.store.events()
        with self.assertRaisesRegex(ValueError, "External ID"):
            self.ingestor.ingest(replace(self.snapshot(200, 20), external_id="same-observation"))
        self.assertEqual(self.store.events(), before)
        self.assertEqual(self.stats()["impressions"], 100)

    def test_invalid_candidate_persona_and_negative_counters_rejected(self):
        for invalid in (
            replace(self.snapshot(), candidate_id="missing"),
            replace(self.snapshot(), persona_id="someone_else"),
            replace(self.snapshot(), impressions=-1),
            replace(self.snapshot(), link_clicks=-1),
            replace(self.snapshot(), revenue_cents=-1),
        ):
            with self.subTest(metrics=invalid):
                before = self.store.events()
                with self.assertRaises(ValueError):
                    self.ingestor.ingest(invalid)
                self.assertEqual(self.store.events(), before)

    def test_outcome_failure_rolls_back_snapshot_and_watermark(self):
        first = self.snapshot()
        before = self.store.events()
        original = self.store._event

        def fail_click(kind, payload, external_id=None):
            if kind == "click":
                raise RuntimeError("ledger write failed")
            return original(kind, payload, external_id)

        with patch.object(self.store, "_event", side_effect=fail_click):
            with self.assertRaisesRegex(RuntimeError, "ledger write failed"):
                self.ingestor.ingest(first)
        self.assertEqual(self.store.events(), before)
        self.ingestor.ingest(first)
        self.assertEqual(self.stats()["impressions"], 100)
        self.assertEqual(self.stats()["clicks"], 10)

    def test_conflicting_outcome_id_rolls_back_new_observation(self):
        metrics = self.snapshot()
        self.store.record_event("click", {
            "candidate_id": self.cid, "persona_id": self.persona["id"], "amount_cents": 0, "count": 999,
        }, external_id=f"{metrics.external_id}_clk")
        before = self.store.events()
        with self.assertRaisesRegex(ValueError, "External ID"):
            self.ingestor.ingest(metrics)
        self.assertEqual(self.store.events(), before)
        self.assertEqual(self.stats()["impressions"], 0)

    def test_upgrade_seeds_high_water_from_actual_legacy_outcomes(self):
        legacy = replace(self.snapshot(), external_id="met_instagram_post-1")
        payload = legacy.to_dict()
        payload.pop("cumulative")
        self.store.record_event("metrics_ingested", payload, external_id=f"{legacy.external_id}_snapshot")
        # The old implementation swallowed failures, so this snapshot has no click outcome.
        self.store.record_event("impression", {
            "candidate_id": self.cid, "persona_id": self.persona["id"], "amount_cents": 0, "count": 100,
        }, external_id=f"{legacy.external_id}_imp")
        self.ingestor.ingest(self.snapshot(140, 14, "2026-10-06T10:02:00+00:00"))
        self.assertEqual(self.stats()["impressions"], 140)
        self.assertEqual(self.stats()["clicks"], 14)

    def test_manual_increment_mode_is_explicit_and_cannot_change_midstream(self):
        first = replace(self.snapshot(), cumulative=False, external_id="manual-one")
        second = replace(self.snapshot(20, 3), cumulative=False, external_id="manual-two")
        self.ingestor.ingest(first)
        self.ingestor.ingest(second)
        self.ingestor.ingest(second)
        self.assertEqual(self.stats()["impressions"], 120)
        self.assertEqual(self.stats()["clicks"], 13)
        before = self.store.events()
        with self.assertRaisesRegex(ValueError, "accounting mode"):
            self.ingestor.ingest(self.snapshot(140, 14))
        self.assertEqual(self.store.events(), before)

    def test_enclosing_transaction_can_roll_back_metrics(self):
        before = self.store.events()
        with self.assertRaisesRegex(RuntimeError, "abort outer work"):
            with self.store.db:
                self.store.db.execute("UPDATE candidates SET theme=? WHERE id=?", ("temporary", self.cid))
                self.ingestor.ingest(self.snapshot())
                raise RuntimeError("abort outer work")
        self.assertEqual(self.store.events(), before)
        self.ingestor.ingest(self.snapshot())
        self.assertEqual(self.stats()["impressions"], 100)

    def test_explicit_manual_money_uses_cumulative_deltas(self):
        self.ingestor.ingest(self.snapshot(revenue_cents=1000, cost_cents=20))
        self.ingestor.ingest(self.snapshot(110, 11, "2026-10-06T10:02:00+00:00", revenue_cents=1300, cost_cents=30))
        self.assertEqual(self.stats()["revenue_cents"], 1300)
        self.assertEqual(self.stats()["cost_cents"], 55)

    def planner_for_candidate(self):
        planner = ExperimentPlanner(None, self.store)
        plan_id = "test-plan"
        plan = {"plan_id": plan_id, "persona_id": self.persona["id"], "primary_metric": "link_clicks",
                "reversal_condition": "No improvement", "variants": [{"id": "v1"}]}
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO experiment_plan
                   (id,ts,objective,persona_id,persona_version,channel,offer,hypothesis,
                    primary_metric,reversal_condition,variant_count,plan_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (plan_id, "2026-10-06", "conversion", self.persona["id"], "v1", "instagram", "zine",
                 "framing helps", "link_clicks", "No improvement", 1, json.dumps(plan)),
            )
            self.store.db.execute("INSERT INTO experiment_variant VALUES(?,?,?)", (plan_id, "v1", self.cid))
        return planner, plan_id

    def test_planner_uses_aggregate_counts_and_legacy_single_events(self):
        planner, plan_id = self.planner_for_candidate()
        self.ingestor.ingest(self.snapshot())
        self.store.record_outcome(self.cid, "impression", external_id="legacy-impression")
        self.store.record_outcome(self.cid, "click", external_id="legacy-click")
        result = planner.results(plan_id)["variants"][0]
        self.assertEqual(result["impressions"], 101)
        self.assertEqual(result["clicks"], 11)
        self.assertEqual(result["click_rate"], round(11 / 101, 6))

    def test_planner_nets_chargebacks_and_reversals_without_inflating_purchases(self):
        planner, plan_id = self.planner_for_candidate()
        self.ingestor.ingest(self.snapshot())
        for kind, amount in (
            ("purchase", 1000), ("refund", 100), ("distribution_cost", 20),
            ("commerce_cost", 40), ("chargeback", 200),
            ("chargeback_reversal", 50), ("commerce_cost_reversal", 10),
        ):
            self.store.record_event(kind, {
                "candidate_id": self.cid, "persona_id": self.persona["id"], "amount_cents": amount,
            }, external_id=f"money-{kind}")
        result = planner.results(plan_id)["variants"][0]
        self.assertEqual(result["chargeback_cents"], 200)
        self.assertEqual(result["chargeback_reversal_cents"], 50)
        self.assertEqual(result["commerce_cost_reversal_cents"], 10)
        self.assertEqual(result["revenue_cents"], 1000)
        self.assertEqual(result["refund_cents"], 100)
        self.assertEqual(result["commerce_cost_cents"], 40)
        self.assertEqual(result["net_cents"], 675)


class SnapshotNormalizationTests(unittest.TestCase):
    def test_generic_preserves_fetch_time_and_deterministic_snapshot_id(self):
        source = PlatformMetrics("instagram", "p", fetched_at="2026-10-06T10:01:02.123456+00:00", views=50)
        first = MetricsNormalizer.normalize_generic("instagram", source, "candidate", "persona", "p")
        second = MetricsNormalizer.normalize_generic("instagram", source, "candidate", "persona", "p")
        self.assertEqual(first.timestamp, source.fetched_at)
        self.assertEqual(first.external_id, second.external_id)
        self.assertEqual(first.impressions, 0)

    def test_same_timestamp_changed_values_receive_distinct_snapshot_ids(self):
        raw = {"fetched_at": "2026-10-06T10:01:02+00:00", "impressions": 20}
        first = MetricsNormalizer.normalize_generic("instagram", raw, "candidate", "persona", "p")
        second = MetricsNormalizer.normalize_generic("instagram", {**raw, "impressions": 30}, "candidate", "persona", "p")
        self.assertNotEqual(first.external_id, second.external_id)

    def test_instagram_does_not_invent_watch_or_completion_or_revenue(self):
        raw = {"fetched_at": "2026-10-06T10:01:02+00:00", "data": [{"name": "plays", "values": [{"value": 100}]}],
               "revenue_cents": 99999, "cost_cents": 99999}
        result = MetricsNormalizer.normalize_instagram(raw, "candidate", "persona", "p")
        self.assertEqual(result.timestamp, raw["fetched_at"])
        self.assertEqual(result.views, 100)
        self.assertEqual(result.impressions, 0)
        self.assertEqual(result.watch_time_ms, 0)
        self.assertEqual(result.completion_rate, 0.0)
        self.assertEqual(result.revenue_cents, 0)
        self.assertEqual(result.cost_cents, 0)

    def test_normalization_rejects_fractional_negative_and_boolean_counters(self):
        for invalid in (-0.1, -1, 1.5, True, "-1"):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    MetricsNormalizer.normalize_generic("instagram", {"impressions": invalid}, "candidate", "persona", "p")


if __name__ == "__main__":
    unittest.main()

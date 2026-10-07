import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spicecore.analytics.ingest import AnalyticsIngestor, COUNTERS
from spicecore.analytics.normalize import MetricsNormalizer, NormalizedMetrics
from spicecore.core import Store
from spicecore.distribution.instagram import InstagramGraphPublisher
from spicecore.experiments import ExperimentPlanner


class HTTPResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(json.dumps(data).encode())
        self.status = 200


class MetricViewsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledger.sqlite"
        self.store = Store(self.path)
        self.persona = {"id": "lila_hart", "version": "v1", "name": "Lila"}
        self.cid = self.store.propose(self.persona, "ceramics", "still", "instagram", "guide")
        self.store.review(self.cid, "approved", "operator")
        self.store.publish(self.cid, "https://www.instagram.com/p/actual/")
        self.ingestor = AnalyticsIngestor(self.store)
        self.planner = ExperimentPlanner(None, self.store)
        self.plan_id = "views-plan"
        plan = {"plan_id": self.plan_id, "persona_id": self.persona["id"], "primary_metric": "views",
                "reversal_condition": "no growth", "variants": [{"id": "v1"}]}
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO experiment_plan
                   (id,ts,objective,persona_id,persona_version,channel,offer,hypothesis,
                    primary_metric,reversal_condition,variant_count,plan_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.plan_id, "2026-10-06", "income", self.persona["id"], "v1", "instagram", "guide",
                 "test views", "views", "no growth", 1, json.dumps(plan)),
            )
            self.store.db.execute("INSERT INTO experiment_variant VALUES(?,?,?)", (self.plan_id, "v1", self.cid))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def observation(self, views=1000, timestamp="2026-10-06T10:00:00+00:00", post_id="media-1"):
        return NormalizedMetrics("instagram", post_id, self.cid, self.persona["id"],
                                 timestamp=timestamp, views=views)

    def view_events(self):
        return [event for event in self.store.events() if event["kind"] == "view"]

    def view_count(self):
        return sum(event["payload"].get("count", 1) for event in self.view_events())

    def legacy_snapshot(self, views=1000):
        observation = self.observation(views)
        after = {name: getattr(observation, name) for name in COUNTERS}
        accounting = {"high_water_before": dict.fromkeys(COUNTERS, 0), "high_water_after": after,
                      "deltas": after, "decreased_fields": [], "stale": False}
        self.store.record_event("metrics_ingested", {**observation.to_dict(), "accounting": accounting},
                                external_id=f"{observation.external_id}_snapshot")
        with self.store.db:
            self.store.db.execute("INSERT INTO analytics_metric_watermarks VALUES(?,?,?,?,?,?,?)", (
                "instagram", "media-1", self.cid, self.persona["id"], 1,
                observation.timestamp, json.dumps(after),
            ))
        return observation

    def test_actual_instagram_metric_adapter_records_views_without_impressions(self):
        response = {"data": [{"name": "views", "values": [{"value": 1000}]}]}
        publisher = InstagramGraphPublisher(access_token="test-only")
        with patch("urllib.request.urlopen", return_value=HTTPResponse(response)) as http:
            fetched = publisher.fetch_metrics("media-1", "account-1")
        self.assertEqual(http.call_args.args[0].get_method(), "GET")
        self.assertEqual(fetched.views, 1000)
        self.assertEqual(fetched.impressions, 0)
        normalized = MetricsNormalizer.normalize_generic("instagram", fetched, self.cid, self.persona["id"], "media-1")
        self.ingestor.ingest(normalized)
        variant = self.planner.results(self.plan_id)["variants"][0]
        self.assertEqual(self.view_count(), 1000)
        self.assertEqual(variant["views"], 1000)
        self.assertEqual(variant["impressions"], 0)
        self.assertIsNone(variant["click_rate"])

    def test_replay_growth_decrease_and_restart_count_only_actual_growth(self):
        first = self.observation()
        self.ingestor.ingest(first)
        self.ingestor.ingest(first)
        self.ingestor.ingest(self.observation(1250, "2026-10-06T10:01:00+00:00"))
        self.ingestor.ingest(self.observation(800, "2026-10-06T10:02:00+00:00"))
        self.store.close()
        self.store = Store(self.path)
        self.ingestor = AnalyticsIngestor(self.store)
        self.planner = ExperimentPlanner(None, self.store)
        self.ingestor.ingest(self.observation(1300, "2026-10-06T10:03:00+00:00"))
        self.assertEqual([event["payload"]["count"] for event in self.view_events()], [1000, 250, 50])
        self.assertEqual(self.planner.results(self.plan_id)["variants"][0]["views"], 1300)

    def test_upgrade_recovers_snapshotted_views_without_skipping_high_water(self):
        self.legacy_snapshot()
        self.ingestor.ingest(self.observation(1100, "2026-10-06T10:01:00+00:00"))
        self.assertEqual(self.view_count(), 1100)
        self.ingestor.ingest(self.observation(1150, "2026-10-06T10:02:00+00:00"))
        self.assertEqual(self.view_count(), 1150)

    def test_replaying_old_snapshot_recovers_missing_view_outcome_once(self):
        old = self.legacy_snapshot()
        self.ingestor.ingest(old)
        self.ingestor.ingest(old)
        self.assertEqual(self.view_count(), 1000)

    def test_upgrade_bootstraps_from_partial_actual_view_outcomes(self):
        old = self.legacy_snapshot()
        self.store.record_event("view", {
            "candidate_id": self.cid, "persona_id": self.persona["id"], "amount_cents": 0, "count": 200,
        }, external_id=f"{old.external_id}_view")
        self.ingestor.ingest(old)
        self.assertEqual(self.view_count(), 1000)
        self.ingestor.ingest(self.observation(1250, "2026-10-06T10:01:00+00:00"))
        self.assertEqual(self.view_count(), 1250)

    def test_post_watermarks_do_not_share_view_accounting(self):
        self.legacy_snapshot()
        self.ingestor.ingest(self.observation(700, "2026-10-06T10:01:00+00:00", "media-2"))
        self.ingestor.ingest(self.observation(1100, "2026-10-06T10:01:00+00:00"))
        self.assertEqual(self.view_count(), 1800)
        self.assertEqual(self.planner.results(self.plan_id)["variants"][0]["views"], 1800)

    def test_one_off_view_event_remains_distinct_from_snapshot_counts(self):
        self.ingestor.ingest(self.observation())
        self.store.record_event("view", {"candidate_id": self.cid, "persona_id": self.persona["id"], "amount_cents": 0})
        self.assertEqual(self.planner.results(self.plan_id)["variants"][0]["views"], 1001)

    def test_instagram_normalization_recognizes_real_views_metric(self):
        result = MetricsNormalizer.normalize_instagram(
            {"data": [{"name": "views", "total_value": {"value": 1000}}]}, self.cid, self.persona["id"], "media-1",
        )
        self.assertEqual(result.views, 1000)
        self.assertEqual(result.impressions, 0)

    def test_invalid_view_counts_fail_before_any_ledger_writes(self):
        before = self.store.events()
        for count in (-1, True, 1.5):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    self.ingestor.ingest(replace(self.observation(), views=count))
        self.assertEqual(self.store.events(), before)

    def test_verified_revenue_mode_uses_event_whitelist_and_preserves_typed_views(self):
        self.ingestor.ingest(self.observation())
        verified = set()
        for kind, amount, observed in (
            ("purchase", 900, True), ("refund", 100, True),
            ("purchase", 99999, False), ("commerce_cost", 999, False),
            ("distribution_cost", 10, False),
        ):
            event = self.store.record_event(kind, {
                "candidate_id": self.cid, "persona_id": self.persona["id"], "amount_cents": amount,
            })
            if observed:
                verified.add(event["id"])
        with patch.object(self.store, "monetary_event_is_observed",
                          side_effect=lambda event_id, kind: kind == "distribution_cost" or event_id in verified,
                          create=True):
            filtered = self.planner.results(self.plan_id, verified_revenue_only=True)["variants"][0]
        legacy = self.planner.results(self.plan_id)["variants"][0]
        self.assertEqual(filtered["revenue_cents"], 900)
        self.assertEqual(filtered["refund_cents"], 100)
        self.assertEqual(filtered["distribution_cost_cents"], 10)
        self.assertEqual(filtered["commerce_cost_cents"], 0)
        self.assertEqual(filtered["net_cents"], 790)
        self.assertEqual(filtered["views"], 1000)
        self.assertEqual(filtered["impressions"], 0)
        self.assertEqual(legacy["revenue_cents"], 100899)


if __name__ == "__main__":
    unittest.main()

import os
import shutil
import tempfile
import unittest

from spicecore.analytics.ingest import AnalyticsIngestor
from spicecore.analytics.normalize import MetricsNormalizer, NormalizedMetrics
from spicecore.core import Store


class TestMetricIngest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_analytics.sqlite")
        self.store = Store(self.db_path)
        self.ingestor = AnalyticsIngestor(self.store)

        # Create published candidate
        self.persona = {"id": "ruby_wren", "name": "Ruby Wren", "version": "2e19ba670498"}
        self.cid = self.store.propose(
            persona=self.persona,
            theme="mini essays on astronomy",
            format="video",
            channel="instagram",
            offer="Printed zine subscription",
            cost_cents=25,
        )
        self.store.review(self.cid, "approved", reviewer="lead_operator")
        self.store.publish(self.cid, "https://instagram.com/p/ruby_astronomy_1")

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalization_and_idempotent_ingestion(self):
        # 1. Normalization from raw Instagram Insights format
        raw_ig_payload = {
            "data": [
                {"name": "impressions", "values": [{"value": 1500}]},
                {"name": "plays", "values": [{"value": 1200}]},
                {"name": "likes", "values": [{"value": 180}]},
                {"name": "comments", "values": [{"value": 24}]},
                {"name": "shares", "values": [{"value": 15}]},
                {"name": "saved", "values": [{"value": 42}]},
                {"name": "website_clicks", "values": [{"value": 35}]},
            ],
            "watch_time_ms": 7800000,
            "completion_rate": 0.72,
        }

        normalized = MetricsNormalizer.normalize_instagram(
            raw_payload=raw_ig_payload,
            candidate_id=self.cid,
            persona_id="ruby_wren",
            post_id="post_ig_999",
            cost_cents=10,
            revenue_cents=4500,  # $45.00
        )

        self.assertEqual(normalized.platform, "instagram")
        self.assertEqual(normalized.impressions, 1500)
        self.assertEqual(normalized.views, 1200)
        self.assertEqual(normalized.likes, 180)
        self.assertEqual(normalized.link_clicks, 35)
        self.assertEqual(normalized.revenue_cents, 4500)

        # 2. Ingest into Store
        res1 = self.ingestor.ingest(normalized)
        self.assertEqual(res1["candidate_id"], self.cid)

        # Check persona stats in store
        stats1 = self.store.stats([self.persona])[0]
        self.assertEqual(stats1["revenue_cents"], 4500)
        self.assertEqual(stats1["impressions"], 1500)
        self.assertEqual(stats1["clicks"], 35)

        # 3. IDEMPOTENT INGESTION: Ingesting identical metrics again must NOT double revenue or impressions
        res2 = self.ingestor.ingest(normalized)

        stats2 = self.store.stats([self.persona])[0]
        self.assertEqual(stats2["revenue_cents"], 4500)  # Still exactly 4500, not 9000!
        self.assertEqual(stats2["impressions"], 1500)
        self.assertEqual(stats2["clicks"], 35)


if __name__ == "__main__":
    unittest.main()

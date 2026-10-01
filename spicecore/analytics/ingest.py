"""Idempotent ingestion of normalized metrics into the auditable experiment ledger."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .normalize import NormalizedMetrics


class AnalyticsIngestor:
    """Ingests normalized metrics into the Store experiment ledger idempotently."""

    def __init__(self, store: Any):
        self.store = store

    def ingest(self, metrics: NormalizedMetrics) -> Dict[str, Any]:
        """Records normalized observation events in the store.

        Uses external_id to guarantee that retried or repeated ingestions
        do not duplicate impressions, clicks, or revenue.
        """
        results: Dict[str, Any] = {
            "post_id": metrics.post_id,
            "candidate_id": metrics.candidate_id,
            "events_recorded": [],
        }

        # 1. Record aggregate metrics snapshot event
        snapshot_ext_id = f"{metrics.external_id}_snapshot"
        try:
            ev = self.store.record_event(
                kind="metrics_ingested",
                payload=metrics.to_dict(),
                external_id=snapshot_ext_id,
            )
            results["events_recorded"].append(ev)
        except Exception as e:
            logging.warning("Metrics snapshot event already recorded or failed: %s", e)

        # 2. Record standard ledger outcomes (impressions, clicks, revenue)
        # Check if candidate is published in store
        try:
            cand = self.store.candidate(metrics.candidate_id)
            if cand and cand.get("status") == "published":
                # Record impressions if > 0
                if metrics.impressions > 0:
                    try:
                        self.store.record_event(
                            "impression",
                            {
                                "candidate_id": metrics.candidate_id,
                                "persona_id": metrics.persona_id,
                                "amount_cents": 0,
                                "count": int(metrics.impressions),
                            },
                            external_id=f"{metrics.external_id}_imp",
                        )
                    except Exception as err:
                        logging.debug("Impression outcome skipped/deduped: %s", err)

                # Record clicks if > 0
                if metrics.link_clicks > 0:
                    try:
                        self.store.record_event(
                            "click",
                            {
                                "candidate_id": metrics.candidate_id,
                                "persona_id": metrics.persona_id,
                                "amount_cents": 0,
                                "count": int(metrics.link_clicks),
                            },
                            external_id=f"{metrics.external_id}_clk",
                        )
                    except Exception as err:
                        logging.debug("Click outcome skipped/deduped: %s", err)

                # Record revenue if > 0
                if metrics.revenue_cents > 0:
                    try:
                        self.store.record_outcome(
                            cid=metrics.candidate_id,
                            kind="purchase",
                            amount_cents=metrics.revenue_cents,
                            external_id=f"{metrics.external_id}_rev",
                        )
                    except Exception as err:
                        logging.debug("Revenue outcome skipped/deduped: %s", err)

                # Record distribution / provider cost if > 0
                if metrics.cost_cents > 0:
                    try:
                        self.store.record_outcome(
                            cid=metrics.candidate_id,
                            kind="distribution_cost",
                            amount_cents=metrics.cost_cents,
                            external_id=f"{metrics.external_id}_cost",
                        )
                    except Exception as err:
                        logging.debug("Cost outcome skipped/deduped: %s", err)

        except Exception as ex:
            logging.warning("Candidate lookup or outcome recording error: %s", ex)

        return results

    def ingest_batch(self, batch: List[NormalizedMetrics]) -> List[Dict[str, Any]]:
        return [self.ingest(m) for m in batch]

"""Atomic, idempotent accounting of cumulative social metrics observations."""

from __future__ import annotations

import json
import math
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List

from .normalize import NormalizedMetrics


COUNTERS = (
    "impressions", "views", "watch_time_ms", "likes", "comments", "shares",
    "saves", "profile_visits", "link_clicks", "revenue_cents", "cost_cents",
)
OUTCOMES = (
    ("impressions", "impression", "imp"),
    ("views", "view", "view"),
    ("link_clicks", "click", "clk"),
    ("revenue_cents", "purchase", "rev"),
    ("cost_cents", "distribution_cost", "cost"),
)


def _observed_at(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Metrics timestamp must be an ISO timestamp")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Metrics timestamp must be an ISO timestamp") from exc
    return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp


class AnalyticsIngestor:
    """Keep a persistent high water for each platform/post/candidate stream.

    Cumulative counters only add growth beyond that high water. Explicit manual
    increments may use cumulative=False, but a stream cannot change accounting
    modes. Financial fields remain manual compatibility inputs; social analytics
    alone are not evidence of authenticated sales.
    """

    def __init__(self, store: Any):
        self.store = store
        self.store.db.execute(
            """CREATE TABLE IF NOT EXISTS analytics_metric_watermarks (
                platform TEXT NOT NULL,
                post_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL REFERENCES candidates(id),
                persona_id TEXT NOT NULL,
                cumulative INTEGER NOT NULL,
                latest_timestamp TEXT NOT NULL,
                counters TEXT NOT NULL,
                PRIMARY KEY(platform, post_id, candidate_id)
            )"""
        )
        # Earlier metric watermarks tracked views without recording typed outcomes.
        # Keep observed high water separate from the total actually in the ledger.
        self.store.db.execute(
            """CREATE TABLE IF NOT EXISTS analytics_view_watermarks (
                platform TEXT NOT NULL,
                post_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL REFERENCES candidates(id),
                accounted_views INTEGER NOT NULL,
                PRIMARY KEY(platform,post_id,candidate_id)
            )"""
        )

    @contextmanager
    def _transaction(self):
        """Serialize writers before reading high waters; preserve caller transactions."""
        db = self.store.db
        savepoint = "metrics_" + uuid.uuid4().hex if db.in_transaction else None
        if savepoint:
            db.execute(f"SAVEPOINT {savepoint}")
        else:
            db.execute("BEGIN IMMEDIATE")
        try:
            if savepoint:
                # Acquire the SQLite writer lock before reading existing observations.
                db.execute("UPDATE analytics_metric_watermarks SET persona_id=persona_id WHERE 0")
            yield
            if savepoint:
                db.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                db.commit()
        except Exception:
            if savepoint:
                db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                db.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                db.rollback()
            raise

    def _existing_event(self, external_id: str) -> dict | None:
        row = self.store.db.execute(
            "SELECT * FROM events WHERE external_id=?", (external_id,),
        ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "ts": row["ts"], "kind": row["kind"],
                "external_id": row["external_id"], "payload": json.loads(row["payload"])}

    def _event(self, kind: str, payload: dict, external_id: str) -> dict:
        existing = self._existing_event(external_id)
        if existing:
            if existing["kind"] != kind or existing["payload"] != payload:
                raise ValueError("External ID already used for a different event")
            return existing
        # Store.record_event commits its own context. Use the same ledger primitive
        # here so snapshot, outcomes, and high water commit or roll back together.
        return self.store._event(kind, payload, external_id)

    @staticmethod
    def _validate(metrics: NormalizedMetrics) -> datetime:
        for name in ("platform", "post_id", "candidate_id", "persona_id", "external_id"):
            value = getattr(metrics, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Metrics {name} is required")
        for name in COUNTERS:
            value = getattr(metrics, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"Metrics {name} must be a nonnegative integer")
        rate = metrics.completion_rate
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate <= 1:
            raise ValueError("Metrics completion_rate must be between zero and one")
        if not isinstance(metrics.cumulative, bool):
            raise ValueError("Metrics cumulative must be a boolean")
        return _observed_at(metrics.timestamp)

    def _legacy_watermark(self, metrics: NormalizedMetrics) -> tuple[dict, str | None]:
        """Seed upgrades from previously recorded observations and actual outcomes.

        The original ingestor could leave partial observations. Derive financial,
        impression, and click baselines from the corresponding ledger events so
        an unrecorded outcome can still be accounted for on the next fetch.
        """
        counters = dict.fromkeys(COUNTERS, 0)
        latest = None
        outcome_names = {item[0] for item in OUTCOMES}
        for row in self.store.db.execute("SELECT payload FROM events WHERE kind='metrics_ingested' ORDER BY seq"):
            payload = json.loads(row["payload"])
            if any(payload.get(name) != getattr(metrics, name) for name in ("platform", "post_id", "candidate_id")):
                continue
            if payload.get("persona_id") != metrics.persona_id:
                raise ValueError("Metrics persona_id does not match prior observation")
            if payload.get("cumulative", True) != metrics.cumulative:
                raise ValueError("Metrics stream cannot change cumulative accounting mode")
            stamp = payload["timestamp"]
            if latest is None or _observed_at(stamp) > _observed_at(latest):
                latest = stamp
            accounting = payload.get("accounting")
            if accounting:
                for name in COUNTERS:
                    counters[name] = max(counters[name], accounting["high_water_after"][name])
                continue
            for name in COUNTERS:
                if name not in outcome_names or name == "views":
                    counters[name] = max(counters[name], int(payload.get(name, 0)))
            for name, kind, suffix in OUTCOMES:
                if kind == "view":
                    # Actual view outcome accounting has its own migration baseline.
                    continue
                outcome = self._existing_event(f"{payload['external_id']}_{suffix}")
                if outcome:
                    data = outcome["payload"]
                    if (outcome["kind"] != kind or data.get("candidate_id") != metrics.candidate_id
                            or data.get("persona_id") != metrics.persona_id):
                        raise ValueError("External ID already used for a different event")
                    counters[name] += int(data.get("count", 1) if kind in ("impression", "click") else data["amount_cents"])
        return counters, latest

    def _recorded_views(self, metrics: NormalizedMetrics) -> int:
        """Bootstrap a post's new outcome watermark from its actual ledger events."""
        row = self.store.db.execute(
            "SELECT accounted_views FROM analytics_view_watermarks WHERE platform=? AND post_id=? AND candidate_id=?",
            (metrics.platform, metrics.post_id, metrics.candidate_id),
        ).fetchone()
        if row:
            return int(row[0])
        legacy_ids = set()
        for snapshot in self.store.db.execute("SELECT payload FROM events WHERE kind='metrics_ingested'"):
            data = json.loads(snapshot[0])
            if all(data.get(name) == getattr(metrics, name) for name in ("platform", "post_id", "candidate_id", "persona_id")):
                if data.get("external_id"):
                    legacy_ids.add(f"{data['external_id']}_view")
        total = 0
        for event in self.store.db.execute("SELECT external_id,payload FROM events WHERE kind='view'"):
            data = json.loads(event["payload"])
            if data.get("candidate_id") != metrics.candidate_id:
                continue
            belongs = (data.get("platform") == metrics.platform and data.get("post_id") == metrics.post_id)
            if not belongs and event["external_id"] not in legacy_ids:
                continue
            if data.get("persona_id") != metrics.persona_id:
                raise ValueError("View outcome persona_id does not match observation")
            total += int(data.get("count", 1))
        return total

    def _record_view_outcome(self, metrics: NormalizedMetrics, observed_high_water: int,
                             result: Dict[str, Any]) -> int:
        baseline = self._recorded_views(metrics)
        target = max(baseline, observed_high_water)
        delta = target - baseline
        if delta:
            external_id = f"{metrics.external_id}_view"
            if self._existing_event(external_id):
                # Recover an old partial outcome without overwriting its receipt.
                external_id += "_recovery"
            result["events_recorded"].append(self._event("view", {
                "candidate_id": metrics.candidate_id, "persona_id": metrics.persona_id,
                "amount_cents": 0, "count": delta,
                "platform": metrics.platform, "post_id": metrics.post_id,
            }, external_id))
        self.store.db.execute(
            """INSERT INTO analytics_view_watermarks VALUES(?,?,?,?)
               ON CONFLICT(platform,post_id,candidate_id) DO UPDATE SET accounted_views=excluded.accounted_views""",
            (metrics.platform, metrics.post_id, metrics.candidate_id, target),
        )
        return delta

    def ingest(self, metrics: NormalizedMetrics) -> Dict[str, Any]:
        """Audit an observation and account for its new counters without hiding errors."""
        observed_at = self._validate(metrics)
        observation = metrics.to_dict()
        result: Dict[str, Any] = {
            "post_id": metrics.post_id,
            "candidate_id": metrics.candidate_id,
            "events_recorded": [],
            "duplicate": False,
        }
        with self._transaction():
            candidate = self.store.candidate(metrics.candidate_id)
            if candidate["persona_id"] != metrics.persona_id:
                raise ValueError("Metrics persona_id does not match candidate")
            if candidate["status"] != "published":
                raise ValueError("Analytics require a published candidate")

            snapshot_id = f"{metrics.external_id}_snapshot"
            existing = self._existing_event(snapshot_id)
            if existing:
                old = dict(existing["payload"])
                old.pop("accounting", None)
                old.setdefault("cumulative", True)
                if existing["kind"] != "metrics_ingested" or old != observation:
                    raise ValueError("External ID already used for a different observation")
                result.update(duplicate=True, deltas=dict.fromkeys(COUNTERS, 0),
                              accounting=existing["payload"].get("accounting", {}))
                result["events_recorded"].append(existing)
                watermark = self.store.db.execute(
                    "SELECT counters FROM analytics_metric_watermarks WHERE platform=? AND post_id=? AND candidate_id=?",
                    (metrics.platform, metrics.post_id, metrics.candidate_id),
                ).fetchone()
                tracked = json.loads(watermark[0]) if watermark else self._legacy_watermark(metrics)[0]
                recorded = dict.fromkeys(COUNTERS, 0)
                recorded["views"] = self._record_view_outcome(metrics, max(metrics.views, tracked.get("views", 0)), result)
                result["recorded_deltas"] = recorded
                return result

            key = (metrics.platform, metrics.post_id, metrics.candidate_id)
            watermark = self.store.db.execute(
                """SELECT * FROM analytics_metric_watermarks
                   WHERE platform=? AND post_id=? AND candidate_id=?""", key,
            ).fetchone()
            if watermark:
                if watermark["persona_id"] != metrics.persona_id:
                    raise ValueError("Metrics persona_id does not match watermark")
                if bool(watermark["cumulative"]) != metrics.cumulative:
                    raise ValueError("Metrics stream cannot change cumulative accounting mode")
                before = {**dict.fromkeys(COUNTERS, 0), **json.loads(watermark["counters"])}
                latest = watermark["latest_timestamp"]
            else:
                before, latest = self._legacy_watermark(metrics)

            values = {name: getattr(metrics, name) for name in COUNTERS}
            after = {name: max(before[name], values[name]) if metrics.cumulative else before[name] + values[name]
                     for name in COUNTERS}
            deltas = {name: after[name] - before[name] for name in COUNTERS}
            stale = latest is not None and observed_at < _observed_at(latest)
            accounting = {
                "high_water_before": before,
                "high_water_after": after,
                "deltas": deltas,
                "decreased_fields": [name for name in COUNTERS if metrics.cumulative and values[name] < before[name]],
                "stale": stale,
            }
            result["events_recorded"].append(self._event(
                "metrics_ingested", {**observation, "accounting": accounting}, snapshot_id,
            ))
            recorded_deltas = dict(deltas)
            for name, kind, suffix in OUTCOMES:
                if kind == "view":
                    recorded_deltas[name] = self._record_view_outcome(metrics, after[name], result)
                    continue
                if not deltas[name]:
                    continue
                payload = {"candidate_id": metrics.candidate_id, "persona_id": metrics.persona_id,
                           "amount_cents": deltas[name] if kind in ("purchase", "distribution_cost") else 0}
                if kind in ("impression", "click"):
                    payload["count"] = deltas[name]
                result["events_recorded"].append(self._event(kind, payload, f"{metrics.external_id}_{suffix}"))

            latest = metrics.timestamp if latest is None or observed_at > _observed_at(latest) else latest
            self.store.db.execute(
                """INSERT INTO analytics_metric_watermarks
                   (platform,post_id,candidate_id,persona_id,cumulative,latest_timestamp,counters)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(platform,post_id,candidate_id) DO UPDATE SET
                   latest_timestamp=excluded.latest_timestamp,counters=excluded.counters""",
                (*key, metrics.persona_id, int(metrics.cumulative), latest, json.dumps(after, sort_keys=True)),
            )
            result.update(deltas=deltas, recorded_deltas=recorded_deltas, accounting=accounting)
        return result

    def ingest_batch(self, batch: List[NormalizedMetrics]) -> List[Dict[str, Any]]:
        return [self.ingest(metrics) for metrics in batch]

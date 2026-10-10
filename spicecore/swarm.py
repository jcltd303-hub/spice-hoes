"""Persistent orchestration of production, delivery, observed earnings, and learning."""

from __future__ import annotations

import fcntl
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .analytics.ingest import AnalyticsIngestor
from .analytics.normalize import MetricsNormalizer
from .autoresponder import validate_reply
from .distribution.scheduler import Scheduler, ScheduleStatus
from .distribution.worker import OutboxWorker
from .learning import LearningNotReady
from .offers import OfferRegistry
from .policy import recommend
from .runtime_policy import RuntimePolicy


@dataclass
class SwarmConfig:
    campaign_id: str = "launch-v1"
    objective: str = "Improve verified contribution margin from disclosed AI lifestyle content"
    channel: str = "instagram"
    offer_id: str = ""
    destination_url: str = ""
    accounts: dict[str, str] = field(default_factory=dict)
    generation_enabled: bool = False
    auto_approve: bool = False
    variants: int = 2
    asset_cost_cents: int = 0
    generation_reservation_cents: int = 100
    monthly_budget_cents: int = 20000
    generation_interval_seconds: int = 3600
    observation_window_seconds: int = 86400
    metrics_interval_seconds: int = 3600
    learning_exposure_metric: str = "views"
    max_unsettled_batches: int = 3
    max_posts_per_day: int = 3
    caption_template: str = "{name}'s {theme} inspiration. Explore {offer}: {url}"

    @classmethod
    def from_dict(cls, value: dict) -> "SwarmConfig":
        if not isinstance(value, dict):
            raise ValueError("swarm configuration must be an object")
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError("unknown swarm settings: " + ", ".join(sorted(unknown)))
        config = cls(**value)
        config.validate()
        return config

    @classmethod
    def load(cls, path: str | Path) -> "SwarmConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def validate(self):
        if not isinstance(self.campaign_id, str) or not self.campaign_id.strip():
            raise ValueError("campaign_id is required")
        if self.channel not in ("instagram", "tiktok", "youtube_shorts"):
            raise ValueError("unsupported swarm channel")
        if self.learning_exposure_metric not in ("views", "impressions"):
            raise ValueError("learning_exposure_metric must be views or impressions")
        if not isinstance(self.accounts, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) or not v.strip()
            for k, v in self.accounts.items()
        ):
            raise ValueError("accounts must map persona IDs to nonempty account IDs")
        account_pattern = {"instagram": r"[0-9]+", "youtube_shorts": r"UC[A-Za-z0-9_-]{22}",
                           "tiktok": r"@?[A-Za-z0-9_.]{1,24}"}[self.channel]
        if any(re.fullmatch(account_pattern, account) is None for account in self.accounts.values()):
            raise ValueError("accounts must contain valid platform account IDs")
        for key in ("generation_enabled", "auto_approve"):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"{key} must be a boolean")
        for key in ("variants", "asset_cost_cents", "generation_reservation_cents",
                    "monthly_budget_cents", "generation_interval_seconds",
                    "observation_window_seconds", "metrics_interval_seconds",
                    "max_unsettled_batches", "max_posts_per_day"):
            value = getattr(self, key)
            if type(value) is not int or value < 0:
                raise ValueError(f"{key} must be a non-negative integer")
        if not 2 <= self.variants <= 6:
            raise ValueError("variants must be 2..6")
        if min(self.generation_interval_seconds, self.metrics_interval_seconds,
               self.max_unsettled_batches, self.max_posts_per_day) < 1:
            raise ValueError("intervals and backlog limits must be positive")
        if self.generation_enabled and self.generation_reservation_cents < 1:
            raise ValueError("generation needs a conservative nonzero cost reservation")
        if self.generation_reservation_cents < self.variants * self.asset_cost_cents:
            raise ValueError("reservation must cover all asset costs plus model calls")
        if self.destination_url:
            p = urlsplit(self.destination_url)
            if p.scheme != "https" or not p.netloc or p.username or p.password:
                raise ValueError("destination_url must be an HTTPS commerce URL")
        if not self.objective.strip() or not self.caption_template.strip():
            raise ValueError("objective and caption_template are required")


class SwarmRuntime:
    def __init__(self, store, personas, config: SwarmConfig, *, autopilot=None,
                 learning=None, publishers=None, media_delivery=None, commerce=None,
                 production_blockers=None):
        config.validate()
        self.store, self.personas, self.config = store, list(personas), config
        self.by_id = {p["id"]: p for p in self.personas}
        self.autopilot, self.learning = autopilot, learning
        self.publishers = publishers or {}
        self.media_delivery, self.commerce = media_delivery, commerce
        self.production_blockers = production_blockers or (lambda: [])
        self.offers = OfferRegistry(store)
        self.policy = RuntimePolicy(store)
        self.scheduler = Scheduler(store)
        self.worker = OutboxWorker(self.scheduler, self.publishers, store)
        self.ingestor = AnalyticsIngestor(store)
        self.store.db.executescript("""
            CREATE TABLE IF NOT EXISTS swarm_attempt (
                id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, ts TEXT NOT NULL,
                reserved_cents INTEGER NOT NULL, state TEXT NOT NULL,
                run_id TEXT, reason TEXT
            );
            CREATE TABLE IF NOT EXISTS swarm_content (
                candidate_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL,
                run_id TEXT NOT NULL, tracked_url TEXT NOT NULL DEFAULT '',
                caption TEXT NOT NULL DEFAULT '', media_uri TEXT,
                hold_reasons TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS swarm_poll (
                schedule_id TEXT PRIMARY KEY, last_polled_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS swarm_publication_slot (
                schedule_id TEXT PRIMARY KEY, allocated_at TEXT NOT NULL
            );
        """)
        self.store.db.commit()

    @staticmethod
    def _now(now=None):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("runtime clock needs an explicit timezone")
        return now.astimezone(timezone.utc)

    def _budget(self, now):
        def reserved(prefix):
            return int(self.store.db.execute(
                "SELECT COALESCE(SUM(reserved_cents),0) FROM swarm_attempt WHERE ts LIKE ?",
                (prefix + "%",)).fetchone()[0])
        return {"reserved_today_cents": reserved(now.date().isoformat()),
                "reserved_month_cents": reserved(now.strftime("%Y-%m")),
                "daily_limit_cents": self.policy.current()["values"]["daily_budget_cents"],
                "monthly_limit_cents": self.config.monthly_budget_cents,
                "basis": "Conservative operating reservations; actual fees and cash require provider receipts"}

    def _blockers(self):
        blockers = []
        if not self.config.offer_id:
            blockers.append("offer_id")
        else:
            try:
                if not self.offers.get(self.config.offer_id)["active"]:
                    blockers.append("active_offer")
            except ValueError:
                blockers.append("known_offer")
        if not self.config.destination_url:
            blockers.append("destination_url")
        if not self.config.accounts or set(self.by_id) - set(self.config.accounts):
            blockers.append("accounts")
        blockers.extend(self.production_blockers())
        return list(dict.fromkeys(blockers))

    def status(self, now=None):
        now = self._now(now)
        unresolved = self.store.db.execute(
            "SELECT COUNT(*) FROM swarm_attempt WHERE campaign_id=? AND state='running'",
            (self.config.campaign_id,)).fetchone()[0]
        return {"campaign_id": self.config.campaign_id, "channel": self.config.channel,
                "generation_enabled": self.config.generation_enabled,
                "auto_approve": self.config.auto_approve, "blockers": self._blockers(),
                "budget": self._budget(now), "interrupted_attempts": unresolved,
                "campaign_contribution": self._campaign_contribution(),
                "queue": {state.value: sum(p.status == state for p in self.scheduler.list_posts())
                          for state in ScheduleStatus},
                "verified_commerce": self.commerce.status() if self.commerce else {"configured": False}}

    def _campaign_contribution(self):
        candidates = {r["candidate_id"]: r["run_id"] for r in self.store.db.execute(
            "SELECT candidate_id,run_id FROM swarm_content WHERE campaign_id=?", (self.config.campaign_id,))}
        asset_costs = {cid: int(self.store.candidate(cid)["cost_cents"]) for cid in candidates}
        money = self.commerce.verified_totals(candidates) if self.commerce else {
            "verified_contribution_before_cost_basis_cents": 0, "configured_unit_cost_basis_cents": 0}
        distribution = sum(int(payload.get("amount_cents", 0))
                           for payload in (json.loads(r[0]) for r in self.store.db.execute(
                               "SELECT payload FROM events WHERE kind='distribution_cost'"))
                           if payload.get("candidate_id") in candidates)
        attempts = self.store.db.execute("SELECT reserved_cents,run_id FROM swarm_attempt WHERE campaign_id=?",
                                         (self.config.campaign_id,)).fetchall()
        additional_estimate = sum(max(0, r["reserved_cents"] - sum(
            asset_costs[cid] for cid, run_id in candidates.items() if r["run_id"] and run_id == r["run_id"]))
                                  for r in attempts)
        recorded_basis = sum(asset_costs.values()) + distribution + money["configured_unit_cost_basis_cents"]
        contribution = money["verified_contribution_before_cost_basis_cents"] - recorded_basis
        return {**money, "scope": "campaign_content_and_generation_attempts",
                "recorded_asset_cost_basis_cents": sum(asset_costs.values()),
                "recorded_distribution_cost_cents": distribution,
                "generation_reservations_cents": sum(r["reserved_cents"] for r in attempts),
                "additional_generation_estimate_cents": additional_estimate,
                "contribution_after_recorded_cost_basis_cents": contribution,
                "contribution_after_generation_reservations_cents": contribution - additional_estimate,
                "complete": False, "commerce_configured": self.commerce is not None,
                "basis": "Signed live money minus all recorded campaign costs; reservations are conservative estimates. Unrecorded costs remain unknown."}

    def _lock(self):
        path = self.store.db.execute("PRAGMA database_list").fetchone()[2]
        handle = open((path or "/tmp/spice-swarm-memory") + ".swarm.lock", "a")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle

    def _reserve(self, now):
        values = self.policy.current()["values"]
        budget = self._budget(now)
        required = self.config.generation_reservation_cents
        if budget["reserved_today_cents"] + required > values["daily_budget_cents"]:
            return None, "daily_budget_limit"
        if budget["reserved_month_cents"] + required > self.config.monthly_budget_cents:
            return None, "monthly_budget_limit"
        latest = self.store.db.execute(
            "SELECT * FROM swarm_attempt WHERE campaign_id=? ORDER BY ts DESC LIMIT 1",
            (self.config.campaign_id,)).fetchone()
        if latest and (now - datetime.fromisoformat(latest["ts"])).total_seconds() < self.config.generation_interval_seconds:
            return None, "generation_interval"
        if latest and latest["state"] == "running":
            return None, "interrupted_generation_needs_reconciliation"
        count = self.store.db.execute(
            """SELECT COUNT(*) FROM swarm_attempt s JOIN autopilot_run a ON s.run_id=a.id
               WHERE s.campaign_id=? AND a.status='created'""",
            (self.config.campaign_id,)).fetchone()[0] if self.autopilot else 0
        if count >= self.config.max_unsettled_batches:
            return None, "unsettled_batch_limit"
        attempt_id = str(uuid.uuid4())
        with self.store.db:
            self.store.db.execute("INSERT INTO swarm_attempt VALUES(?,?,?,?,?,?,?)",
                                  (attempt_id, self.config.campaign_id, now.isoformat(),
                                   required, "running", None, None))
            self.store._event("swarm_budget_reserved", {
                "attempt_id": attempt_id, "campaign_id": self.config.campaign_id,
                "reserved_cents": required,
            })
        return attempt_id, None

    def _generate(self, now):
        if not self.config.generation_enabled:
            return {"status": "blocked", "reason": "generation_disabled"}
        blockers = self._blockers()
        if blockers:
            return {"status": "blocked", "reason": "configuration", "blockers": blockers}
        if self.config.channel != "instagram":
            return {"status": "blocked", "reason": "automatic_generation_requires_still_image_channel"}
        if self.autopilot is None:
            return {"status": "blocked", "reason": "production_workers_unavailable"}
        values = self.policy.current()["values"]
        gate = self.autopilot.preflight(
            self.config.objective, self.config.channel, self.offers.get(self.config.offer_id)["name"],
            variant_count=self.config.variants, cost_cents_per_asset=self.config.asset_cost_cents,
            max_pending_review=values["max_pending_review"], daily_budget_cents=values["daily_budget_cents"])
        if not gate["allowed"]:
            return {"status": "blocked", "reason": gate["reason"]}
        attempt, reason = self._reserve(now)
        if not attempt:
            return {"status": "blocked", "reason": reason}
        try:
            run = self.autopilot.run_once(
                self.config.objective, self.config.channel, self.offers.get(self.config.offer_id)["name"],
                variant_count=self.config.variants, cost_cents_per_asset=self.config.asset_cost_cents,
                max_pending_review=values["max_pending_review"], daily_budget_cents=values["daily_budget_cents"])
            with self.store.db:
                self.store.db.execute("UPDATE swarm_attempt SET state=?,run_id=? WHERE id=?",
                                      (run["status"], run["run_id"], attempt))
                for output in run.get("outputs", []):
                    self.store.db.execute(
                        "INSERT OR IGNORE INTO swarm_content(candidate_id,campaign_id,run_id) VALUES(?,?,?)",
                        (output["candidate_id"], self.config.campaign_id, run["run_id"]))
            return {"status": run["status"], "run_id": run["run_id"],
                    "created_candidates": run["created_candidates"], "policy": run.get("policy")}
        except Exception as exc:
            # Retain the reservation even if the upstream call produced no candidate.
            with self.store.db:
                self.store.db.execute("UPDATE swarm_attempt SET state='failed',reason=? WHERE id=?",
                                      (type(exc).__name__, attempt))
                self.store._event("swarm_generation_failed", {
                    "attempt_id": attempt, "error_type": type(exc).__name__,
                })
            return {"status": "failed", "reason": type(exc).__name__}

    def _release(self, now):
        report = {"approved": 0, "held": 0, "scheduled": 0, "errors": []}
        rows = self.store.db.execute(
            "SELECT * FROM swarm_content WHERE campaign_id=?", (self.config.campaign_id,)).fetchall()
        for row in rows:
            cid = row["candidate_id"]
            candidate = self.store.candidate(cid)
            if candidate["status"] in ("rejected", "revise", "published"):
                continue
            persona = self.by_id[candidate["persona_id"]]
            try:
                if not row["caption"]:
                    offer = self.offers.get(self.config.offer_id)
                    link = self.offers.register_candidate(cid, offer["id"], self.config.destination_url)
                    tracked = link["tracked_url"]
                    if urlsplit(tracked).hostname == "buy.stripe.com":
                        p = urlsplit(tracked)
                        query = dict(parse_qsl(p.query))
                        query["client_reference_id"] = link["tracking_token"]
                        tracked = urlunsplit((p.scheme, p.netloc, p.path, urlencode(query), p.fragment))
                    caption = self.config.caption_template.format(
                        name=persona["name"], theme=candidate["theme"], offer=offer["name"], url=tracked)
                    with self.store.db:
                        self.store.db.execute(
                            "UPDATE swarm_content SET tracked_url=?,caption=? WHERE candidate_id=?",
                            (tracked, caption, cid))
                else:
                    caption = row["caption"]
                reasons = validate_reply(caption, "")
                if len(caption) > 1800:
                    reasons.append("caption_too_long")
                if candidate["status"] == "proposed":
                    evidence = {}
                    for event in self.store.events():
                        if event["payload"].get("candidate_id") == cid:
                            evidence[event["kind"]] = event["payload"]
                    identity = evidence.get("identity_checked", {})
                    quality = evidence.get("quality_checked", {})
                    thresholds = self.policy.current()["values"]
                    if not (identity.get("scored") and identity.get("passed")
                            and isinstance(identity.get("score"), (int, float))
                            and identity["score"] >= thresholds["identity_threshold"]):
                        reasons.append("scored_identity_required")
                    if not (quality.get("passed") and isinstance(quality.get("score"), (int, float))
                            and quality["score"] >= thresholds["quality_threshold"]):
                        reasons.append("passed_quality_required")
                    if not self.config.auto_approve:
                        reasons.append("manual_review")
                    if not reasons:
                        self.store.review(cid, "approved", "owner-authorized-swarm",
                                          note=f"scored release; campaign={self.config.campaign_id}")
                        report["approved"] += 1
                        candidate = self.store.candidate(cid)
                with self.store.db:
                    self.store.db.execute("UPDATE swarm_content SET hold_reasons=? WHERE candidate_id=?",
                                          (json.dumps(reasons), cid))
                if reasons:
                    report["held"] += 1
                    continue
                if not self.publishers:
                    continue
                if any(p.candidate_id == cid for p in self.scheduler.list_posts()):
                    continue
                if not self.offers.get(self.config.offer_id)["active"]:
                    raise ValueError("inactive_offer")
                media_uri = row["media_uri"]
                if not media_uri:
                    media_uri = self.media_delivery.prepare(candidate) if self.media_delivery else candidate["asset_uri"]
                    if post_requires_url(self.config.channel) and urlsplit(media_uri or "").scheme != "https":
                        raise ValueError("public_media_delivery_required")
                    with self.store.db:
                        self.store.db.execute("UPDATE swarm_content SET media_uri=? WHERE candidate_id=?",
                                              (media_uri, cid))
                self.scheduler.schedule_candidate(
                    cid, self.config.channel, self.config.accounts[persona["id"]],
                    now.isoformat(), media_uri=media_uri, caption=caption,
                    disclosure=persona["disclosure"], hashtags=["AIInfluencer", "fictional"])
                report["scheduled"] += 1
            except Exception as exc:
                report["errors"].append({"candidate_id": cid, "error_type": type(exc).__name__})
        return report

    def _publish(self, now):
        scoped = {row[0] for row in self.store.db.execute(
            "SELECT candidate_id FROM swarm_content WHERE campaign_id=?", (self.config.campaign_id,))}
        posts = {p.schedule_id: p for p in self.scheduler.list_posts()}
        slots = {r["schedule_id"]: r["allocated_at"] for r in self.store.db.execute(
            "SELECT * FROM swarm_publication_slot")}
        today = now.date().isoformat()
        inflight = {"pending", "publishing", "needs_reconciliation"}
        used = {sid for sid, post in posts.items() if post.candidate_id in scoped and (
            slots.get(sid, "")[:10] == today
            or post.status.value in inflight
            or (post.published_at and post.published_at[:10] == today))}
        results = []
        for post in self.scheduler.get_due_posts(now.isoformat()):
            if post.candidate_id not in scoped:
                continue
            if post.schedule_id not in used:
                if len(used) >= self.config.max_posts_per_day:
                    continue
                # Reserve before a provider operation that could make content public.
                with self.store.db:
                    self.store.db.execute("INSERT OR REPLACE INTO swarm_publication_slot VALUES(?,?)",
                                          (post.schedule_id, now.isoformat()))
                used.add(post.schedule_id)
            result = self.worker.process_post(post, as_of_iso=now.isoformat())
            # Do not expose provider state (which can contain signed media URLs).
            results.append({"schedule_id": post.schedule_id, "success": result.success,
                            "platform": result.platform, "retryable": result.retryable})
        return results

    def _metrics(self, now):
        results = []
        scoped = {r[0] for r in self.store.db.execute(
            "SELECT candidate_id FROM swarm_content WHERE campaign_id=?", (self.config.campaign_id,))}
        for post in self.scheduler.list_posts():
            if post.status != ScheduleStatus.PUBLISHED or post.candidate_id not in scoped:
                continue
            row = self.store.db.execute("SELECT last_polled_at FROM swarm_poll WHERE schedule_id=?",
                                        (post.schedule_id,)).fetchone()
            if row and (now - datetime.fromisoformat(row[0])).total_seconds() < self.config.metrics_interval_seconds:
                continue
            try:
                publisher = self.publishers[post.platform]
                raw = publisher.fetch_metrics(post.external_post_id, post.account_id)
                candidate = self.store.candidate(post.candidate_id)
                metrics = MetricsNormalizer.normalize_generic(
                    post.platform, raw, post.candidate_id, candidate["persona_id"], post.external_post_id)
                result = self.ingestor.ingest(metrics)
                results.append({"schedule_id": post.schedule_id, "status": "ingested"})
            except Exception as exc:
                results.append({"schedule_id": post.schedule_id, "error_type": type(exc).__name__})
            # Back off repeated failures too; no request storm on a bad credential.
            with self.store.db:
                self.store.db.execute("INSERT OR REPLACE INTO swarm_poll VALUES(?,?)",
                                      (post.schedule_id, now.isoformat()))
        return results

    def _learn(self, now):
        if self.learning is None:
            return []
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='autopilot_run'").fetchone() is None:
            return []
        results = []
        for row in self.store.db.execute(
            """SELECT a.* FROM autopilot_run a JOIN swarm_attempt s ON s.run_id=a.id
               WHERE s.campaign_id=? AND a.status IN ('created','settled')""", (self.config.campaign_id,)).fetchall():
            if row["status"] == "settled":
                outcome = self.learning.reconcile_autopilot_run(row["id"])
                if outcome["changed"]:
                    results.append({"run_id": row["id"], "status": outcome["status"],
                                    "reward_cents": outcome["reward_cents"]})
                continue
            plan = self.learning.planner.get(row["plan_id"])
            cids = {v.get("candidate_id") for v in plan["variants"]}
            published = {cid for cid in cids if cid and self.store.candidate(cid)["status"] == "published"}
            posts = [p for p in self.scheduler.list_posts() if p.candidate_id in published
                     and p.status == ScheduleStatus.PUBLISHED and p.published_at]
            if published - {p.candidate_id for p in posts}:
                continue
            if any((now - datetime.fromisoformat(p.published_at)).total_seconds()
                   < self.config.observation_window_seconds for p in posts):
                continue
            try:
                outcome = self.learning.settle_autopilot_run(
                    row["id"], self.policy.current()["values"]["min_impressions_to_learn"],
                    exposure_metric=self.config.learning_exposure_metric)
                results.append({"run_id": row["id"], "status": outcome["status"],
                                "reward_cents": outcome["reward_cents"]})
            except LearningNotReady:
                continue
        if results and self.learning.policy.count() >= self.learning.policy.min_experiences:
            training = self.learning.policy.train()
            if self.autopilot:
                self.autopilot.policy.load_latest()
            self.store.record_event("swarm_learning_trained", {
                "campaign_id": self.config.campaign_id,
                "experience_count": training["experiences"],
                "corrected_runs": sum(r["status"] == "corrected" for r in results),
            })
        return results

    def tick(self, now=None):
        now = self._now(now)
        handle = self._lock()
        if handle is None:
            return {"status": "busy", "reason": "another_runtime_is_active"}
        try:
            release = self._release(now)
            publishing = self._publish(now)
            metrics = self._metrics(now)
            commerce = self.commerce.retry_pending() if self.commerce else {"configured": False}
            learning = self._learn(now)
            generation = self._generate(now)
            new_release = self._release(now)
            for key in ("approved", "held", "scheduled"):
                release[key] = max(release[key], new_release[key]) if key == "held" else release[key] + new_release[key]
            release["errors"].extend(new_release["errors"])
            publishing.extend(self._publish(now))
            recommendation = recommend(self.store.stats(self.personas, verified_revenue_only=True))
            report = {"timestamp": now.isoformat(), "generation": generation, "release": release,
                      "publishing": publishing, "metrics": metrics, "commerce": commerce,
                      "learning": learning, "recommendation": recommendation, **self.status(now)}
            self.store.record_event("swarm_tick", report)
            return report
        finally:
            handle.close()


def post_requires_url(channel):
    return channel in ("instagram", "tiktok")

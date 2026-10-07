"""Durable publication outbox with approval checks and atomic worker claims."""

from __future__ import annotations

import enum
import json
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit


def _instant(value: Optional[str] = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("publication time must be an ISO timestamp") from exc
    if result.tzinfo is None:
        raise ValueError("publication time must include a timezone")
    return result.astimezone(timezone.utc)


def _timestamp(value: Optional[str] = None) -> str:
    return _instant(value).isoformat()


class ScheduleStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PENDING = "pending"
    PUBLISHED = "published"
    NEEDS_RECONCILIATION = "needs_reconciliation"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConcurrentPostUpdate(RuntimeError):
    """A stale worker tried to overwrite a newer publication state."""


@dataclass
class ScheduledPost:
    candidate_id: str
    media_job_id: str
    platform: str
    account_id: str
    scheduled_at: str
    media_uri: str
    caption: str
    disclosure: str
    schedule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ScheduleStatus = ScheduleStatus.SCHEDULED
    external_post_id: Optional[str] = None
    canonical_url: Optional[str] = None
    published_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    hashtags: List[str] = field(default_factory=list)
    provider_state: Dict[str, Any] = field(default_factory=dict)
    next_attempt_at: Optional[str] = None
    claimed_at: Optional[str] = None
    poll_count: int = 0
    revision: int = 0
    created_at: str = field(default_factory=_timestamp)
    updated_at: str = field(default_factory=_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = ScheduleStatus(self.status).value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledPost":
        values = {item.name: data[item.name] for item in fields(cls) if item.name in data}
        values["status"] = ScheduleStatus(data.get("status", ScheduleStatus.SCHEDULED))
        return cls(**values)


class Scheduler:
    """Persists queues in the Store database, or keeps a lightweight memory queue."""

    def __init__(self, store: Any = None, claim_lease_seconds: int = 300):
        if claim_lease_seconds < 1:
            raise ValueError("claim lease must be positive")
        self.store = store
        self.db = getattr(store, "db", None)
        self.claim_lease_seconds = claim_lease_seconds
        self.posts: Dict[str, ScheduledPost] = {}
        if self.db is not None:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS scheduled_post (
                    schedule_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    media_job_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    next_attempt_at TEXT,
                    claimed_at TEXT,
                    revision INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    post_json TEXT NOT NULL,
                    UNIQUE(candidate_id, platform, account_id)
                );
                CREATE INDEX IF NOT EXISTS scheduled_post_due
                    ON scheduled_post(status, scheduled_at, next_attempt_at);
            """)
            self.db.commit()
            self.list_posts()

    def _cache(self, post: ScheduledPost) -> ScheduledPost:
        cached = self.posts.get(post.schedule_id)
        if cached is None:
            self.posts[post.schedule_id] = post
            return post
        if cached is not post:
            for item in fields(ScheduledPost):
                setattr(cached, item.name, getattr(post, item.name))
        return cached

    def _existing(self, candidate_id: str, platform: str, account_id: str) -> Optional[ScheduledPost]:
        if self.db is not None:
            row = self.db.execute(
                "SELECT post_json FROM scheduled_post WHERE candidate_id=? AND platform=? AND account_id=?",
                (candidate_id, platform, account_id),
            ).fetchone()
            return self._cache(ScheduledPost.from_dict(json.loads(row[0]))) if row else None
        return next((post for post in self.posts.values() if (
            post.candidate_id, post.platform, post.account_id
        ) == (candidate_id, platform, account_id)), None)

    @staticmethod
    def _validate_media_uri(media_uri: str) -> str:
        value = str(media_uri or "").strip()
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return value
        if parsed.scheme:
            raise ValueError("publication asset must be a local file or absolute HTTP(S) URI")
        path = Path(value)
        if not value or not path.is_file() or path.stat().st_size == 0:
            raise ValueError("publication requires an existing, nonempty asset")
        return str(path)

    def _create_post(self, post: ScheduledPost) -> ScheduledPost:
        if not post.platform.strip() or not post.account_id.strip():
            raise ValueError("publication platform and account are required")
        post.scheduled_at = _timestamp(post.scheduled_at)
        if self.db is None:
            existing = self._existing(post.candidate_id, post.platform, post.account_id)
            return existing or self._cache(post)
        with self.db:
            self.db.execute(
                """INSERT INTO scheduled_post
                   (schedule_id,candidate_id,media_job_id,platform,account_id,status,
                    scheduled_at,next_attempt_at,claimed_at,revision,updated_at,post_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(candidate_id,platform,account_id) DO NOTHING""",
                (post.schedule_id, post.candidate_id, post.media_job_id, post.platform,
                 post.account_id, post.status.value, post.scheduled_at, post.next_attempt_at,
                 post.claimed_at, post.revision, post.updated_at, json.dumps(post.to_dict(), sort_keys=True)),
            )
        return self._existing(post.candidate_id, post.platform, post.account_id)

    def _scheduled_event(self, post: ScheduledPost) -> None:
        if self.store and hasattr(self.store, "record_event"):
            self.store.record_event("media_scheduled", {
                "schedule_id": post.schedule_id,
                "candidate_id": post.candidate_id,
                "media_job_id": post.media_job_id,
                "platform": post.platform,
                "account_id": post.account_id,
                "scheduled_at": post.scheduled_at,
            }, external_id=f"media-scheduled:{post.schedule_id}")

    def schedule_candidate(self, candidate_id: str, platform: str, account_id: str,
                           scheduled_at_iso: str, media_uri: Optional[str] = None,
                           caption: str = "", disclosure: str = "",
                           hashtags: Optional[List[str]] = None) -> ScheduledPost:
        """Queue an approved generated asset once per candidate/platform/account."""
        if not self.store or not hasattr(self.store, "candidate"):
            raise ValueError("candidate scheduling requires a Store")
        existing = self._existing(candidate_id, platform, account_id)
        if existing:
            return existing
        candidate = self.store.candidate(candidate_id)
        if candidate["status"] not in ("approved", "published"):
            raise PermissionError("publication requires an approved candidate")
        uri = self._validate_media_uri(media_uri or candidate.get("asset_uri"))
        post = self._create_post(ScheduledPost(
            candidate_id=candidate_id,
            media_job_id=f"candidate:{candidate_id}",
            platform=platform,
            account_id=account_id,
            scheduled_at=scheduled_at_iso,
            media_uri=uri,
            caption=caption or candidate["theme"],
            disclosure=disclosure or "Fictional AI-generated adult character",
            hashtags=list(hashtags or []),
        ))
        self._scheduled_event(post)
        return post

    def schedule(self, media_job: Any, platform: str, account_id: str,
                 scheduled_at_iso: str, caption: Optional[str] = None,
                 hashtags: Optional[List[str]] = None) -> ScheduledPost:
        """Preserve the rendered-media approval gate and existing scheduling API."""
        from ..media.models import RenderState
        existing = self._existing(media_job.candidate_id, platform, account_id)
        if existing and existing.media_job_id == media_job.id:
            return existing
        if media_job.status != RenderState.APPROVED:
            raise PermissionError(
                f"Cannot schedule media job {media_job.id}: status is '{media_job.status.value}'. "
                "Only approved media can be scheduled for publication."
            )
        if not media_job.output_uri:
            raise ValueError(f"Media job {media_job.id} has no rendered output_uri")
        post = self._create_post(ScheduledPost(
            candidate_id=media_job.candidate_id,
            media_job_id=media_job.id,
            platform=platform,
            account_id=account_id,
            scheduled_at=scheduled_at_iso,
            media_uri=media_job.output_uri,
            caption=caption or media_job.script,
            disclosure=media_job.voice_profile.get("disclosure", "Fictional AI-generated adult character"),
            hashtags=list(hashtags or ["spicehoes", "fictional", "adultcreator"]),
        ))
        media_job.update_status(RenderState.SCHEDULED)
        self._scheduled_event(post)
        return post

    def save_post(self, post: ScheduledPost) -> ScheduledPost:
        """Save a state transition without letting a stale worker overwrite a receipt."""
        post.status = ScheduleStatus(post.status)
        if post.retry_count < 0 or post.max_retries < 1 or post.poll_count < 0:
            raise ValueError("publication retry and poll counts must be valid")
        post.scheduled_at = _timestamp(post.scheduled_at)
        if post.next_attempt_at:
            post.next_attempt_at = _timestamp(post.next_attempt_at)
        if post.claimed_at:
            post.claimed_at = _timestamp(post.claimed_at)
        if not isinstance(post.provider_state, dict):
            raise ValueError("publication provider state must be an object")
        if self.db is None:
            return self._cache(post)
        old_revision = post.revision
        post.revision += 1
        try:
            with self.db:
                changed = self.db.execute(
                    """UPDATE scheduled_post SET candidate_id=?,media_job_id=?,platform=?,account_id=?,
                       scheduled_at=?,status=?,next_attempt_at=?,claimed_at=?,revision=?,updated_at=?,post_json=?
                       WHERE schedule_id=? AND revision=?""",
                    (post.candidate_id, post.media_job_id, post.platform, post.account_id,
                     post.scheduled_at, post.status.value, post.next_attempt_at, post.claimed_at, post.revision,
                     post.updated_at, json.dumps(post.to_dict(), sort_keys=True), post.schedule_id, old_revision),
                ).rowcount
                if changed != 1:
                    raise ConcurrentPostUpdate(f"Publication {post.schedule_id} changed in another worker")
        except Exception:
            post.revision = old_revision
            raise
        return self._cache(post)

    def get_post(self, schedule_id: str) -> ScheduledPost:
        if self.db is not None:
            row = self.db.execute(
                "SELECT post_json FROM scheduled_post WHERE schedule_id=?", (schedule_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Scheduled post not found: {schedule_id}")
            return self._cache(ScheduledPost.from_dict(json.loads(row[0])))
        if schedule_id not in self.posts:
            raise KeyError(f"Scheduled post not found: {schedule_id}")
        return self.posts[schedule_id]

    def list_posts(self, status: Optional[str] = None) -> List[ScheduledPost]:
        wanted = ScheduleStatus(status) if status is not None else None
        if self.db is not None:
            query = "SELECT post_json FROM scheduled_post"
            params = ()
            if wanted:
                query += " WHERE status=?"
                params = (wanted.value,)
            query += " ORDER BY scheduled_at,schedule_id"
            return [self._cache(ScheduledPost.from_dict(json.loads(row[0])))
                    for row in self.db.execute(query, params).fetchall()]
        return sorted(
            (post for post in self.posts.values() if wanted is None or post.status == wanted),
            key=lambda post: (_instant(post.scheduled_at), post.schedule_id),
        )

    @staticmethod
    def _eligible(post: ScheduledPost, as_of: datetime) -> bool:
        if post.status not in (ScheduleStatus.SCHEDULED, ScheduleStatus.PENDING, ScheduleStatus.NEEDS_RECONCILIATION):
            return False
        if post.status == ScheduleStatus.NEEDS_RECONCILIATION and not (post.external_post_id and post.canonical_url):
            return False
        return (_instant(post.scheduled_at) <= as_of and
                (not post.next_attempt_at or _instant(post.next_attempt_at) <= as_of))

    def _recover_expired_claims(self, as_of: datetime) -> None:
        expiry = as_of - timedelta(seconds=self.claim_lease_seconds)
        for post in self.list_posts(ScheduleStatus.PUBLISHING):
            if post.claimed_at and _instant(post.claimed_at) > expiry:
                continue
            if post.external_post_id and post.canonical_url:
                post.status = ScheduleStatus.NEEDS_RECONCILIATION
                post.last_error = "Worker stopped after receiving a confirmed publication receipt"
            elif post.provider_state:
                # Retained operation IDs permit status/resume calls, never a new initialization.
                if (post.platform == "youtube_shorts" and post.provider_state.get("upload_url")
                        and not post.provider_state.get("video_id")):
                    # A crash may follow accepted bytes but precede saving their offset.
                    # Ask the retained session what arrived before transferring more.
                    post.provider_state["must_probe"] = True
                post.status = ScheduleStatus.PENDING
                post.last_error = "Worker stopped while resuming a retained provider operation"
            else:
                post.status = ScheduleStatus.NEEDS_RECONCILIATION
                post.last_error = "Worker stopped during submission; reconcile the provider before retrying"
            post.claimed_at = None
            post.updated_at = as_of.isoformat()
            post.next_attempt_at = as_of.isoformat()
            try:
                self.save_post(post)
            except ConcurrentPostUpdate:
                self.get_post(post.schedule_id)

    def get_due_posts(self, as_of_iso: Optional[str] = None) -> List[ScheduledPost]:
        as_of = _instant(as_of_iso)
        self._recover_expired_claims(as_of)
        return [post for post in self.list_posts() if self._eligible(post, as_of)]

    def claim_post(self, schedule_id: str, as_of_iso: Optional[str] = None) -> Optional[ScheduledPost]:
        """Atomically claim a due row; another worker or a stale caller receives None."""
        as_of = _instant(as_of_iso)
        post = self.get_post(schedule_id)
        if not self._eligible(post, as_of):
            return None
        previous_status = post.status
        old_revision = post.revision
        post.status = ScheduleStatus.PUBLISHING
        post.claimed_at = as_of.isoformat()
        post.updated_at = as_of.isoformat()
        if self.db is None:
            return post
        post.revision += 1
        with self.db:
            changed = self.db.execute(
                """UPDATE scheduled_post SET status=?,claimed_at=?,revision=?,updated_at=?,post_json=?
                   WHERE schedule_id=? AND status=? AND revision=?""",
                (post.status.value, post.claimed_at, post.revision, post.updated_at,
                 json.dumps(post.to_dict(), sort_keys=True), schedule_id, previous_status.value, old_revision),
            ).rowcount
        if changed != 1:
            self.get_post(schedule_id)
            return None
        return self._cache(post)

    def cancel(self, schedule_id: str) -> ScheduledPost:
        post = self.get_post(schedule_id)
        if post.status in (ScheduleStatus.PUBLISHED, ScheduleStatus.PUBLISHING,
                           ScheduleStatus.PENDING, ScheduleStatus.NEEDS_RECONCILIATION):
            raise ValueError("Cannot cancel a submitted or already published post in the local queue")
        post.status = ScheduleStatus.CANCELLED
        post.updated_at = _timestamp()
        post.next_attempt_at = None
        return self.save_post(post)

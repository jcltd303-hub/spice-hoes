"""Scheduling queue and review gate enforcement for media publishing."""

from __future__ import annotations

import enum
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ScheduleStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledPost:
    candidate_id: str
    media_job_id: str
    platform: str
    account_id: str
    scheduled_at: str  # ISO timestamp
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
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, ScheduleStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledPost":
        status_val = data.get("status", ScheduleStatus.SCHEDULED)
        if isinstance(status_val, str):
            status = ScheduleStatus(status_val)
        else:
            status = status_val

        return cls(
            schedule_id=data.get("schedule_id", str(uuid.uuid4())),
            candidate_id=data["candidate_id"],
            media_job_id=data["media_job_id"],
            platform=data["platform"],
            account_id=data["account_id"],
            scheduled_at=data["scheduled_at"],
            media_uri=data["media_uri"],
            caption=data["caption"],
            disclosure=data["disclosure"],
            status=status,
            external_post_id=data.get("external_post_id"),
            canonical_url=data.get("canonical_url"),
            published_at=data.get("published_at"),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            last_error=data.get("last_error"),
            hashtags=data.get("hashtags", []),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )


class Scheduler:
    """Manages scheduled social posts with strict human approval review gating."""

    def __init__(self, store: Any = None):
        self.store = store
        self.posts: Dict[str, ScheduledPost] = {}

    def schedule(
        self,
        media_job: Any,  # MediaJob
        platform: str,
        account_id: str,
        scheduled_at_iso: str,
        caption: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
    ) -> ScheduledPost:
        """Schedules a media job for publishing, strictly checking review approval."""
        # REVIEW GATE: Verify media job is in APPROVED state
        from ..media.models import RenderState
        if media_job.status != RenderState.APPROVED:
            raise PermissionError(
                f"Cannot schedule media job {media_job.id}: status is '{media_job.status.value}'. "
                "Only human-approved media can be scheduled for publication."
            )

        if not media_job.output_uri:
            raise ValueError(f"Media job {media_job.id} has no rendered output_uri")

        post = ScheduledPost(
            candidate_id=media_job.candidate_id,
            media_job_id=media_job.id,
            platform=platform,
            account_id=account_id,
            scheduled_at=scheduled_at_iso,
            media_uri=media_job.output_uri,
            caption=caption or media_job.script,
            disclosure=media_job.voice_profile.get("disclosure", "Fictional AI-generated adult character"),
            hashtags=hashtags or ["spicehoes", "fictional", "adultcreator"],
        )
        self.posts[post.schedule_id] = post

        # Update media job status to SCHEDULED
        media_job.update_status(RenderState.SCHEDULED)

        if self.store and hasattr(self.store, "record_event"):
            self.store.record_event("media_scheduled", {
                "schedule_id": post.schedule_id,
                "media_job_id": media_job.id,
                "platform": platform,
                "scheduled_at": scheduled_at_iso,
            })

        return post

    def get_due_posts(self, as_of_iso: Optional[str] = None) -> List[ScheduledPost]:
        """Finds scheduled posts that are due for publication."""
        target_ts = as_of_iso or datetime.now(timezone.utc).isoformat()
        due = []
        for post in self.posts.values():
            if post.status == ScheduleStatus.SCHEDULED and post.scheduled_at <= target_ts:
                due.append(post)
        return due

    def get_post(self, schedule_id: str) -> ScheduledPost:
        if schedule_id not in self.posts:
            raise KeyError(f"Scheduled post not found: {schedule_id}")
        return self.posts[schedule_id]

    def cancel(self, schedule_id: str) -> ScheduledPost:
        post = self.get_post(schedule_id)
        if post.status == ScheduleStatus.PUBLISHED:
            raise ValueError("Cannot cancel an already published post")
        post.status = ScheduleStatus.CANCELLED
        post.updated_at = datetime.now(timezone.utc).isoformat()
        return post

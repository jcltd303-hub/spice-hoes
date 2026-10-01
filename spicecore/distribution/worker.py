"""Outbox worker processing scheduled social publications with idempotency and retry logic."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import Publisher, PublishResult
from .scheduler import ScheduledPost, ScheduleStatus, Scheduler


class OutboxWorker:
    """Processes due scheduled publications through the outbox queue."""

    def __init__(
        self,
        scheduler: Scheduler,
        publishers: Dict[str, Publisher],
        store: Any = None,
    ):
        self.scheduler = scheduler
        self.publishers = publishers
        self.store = store

    def _record_audit_event(self, kind: str, payload: Dict[str, Any], external_id: Optional[str] = None) -> None:
        if self.store and hasattr(self.store, "record_event"):
            try:
                self.store.record_event(kind, payload, external_id=external_id)
            except Exception as e:
                logging.warning("Outbox worker audit log failed: %s", e)

    def process_due(self, as_of_iso: Optional[str] = None) -> List[PublishResult]:
        """Polls outbox queue for due posts and publishes them safely."""
        due_posts = self.scheduler.get_due_posts(as_of_iso)
        results: List[PublishResult] = []

        for post in due_posts:
            res = self.process_post(post)
            results.append(res)

        return results

    def process_post(self, post: ScheduledPost) -> PublishResult:
        """Executes publishing for a single scheduled post with idempotency and retry safeguards."""
        if post.status == ScheduleStatus.PUBLISHED:
            # Already published - do not publish again!
            return PublishResult(
                success=True,
                platform=post.platform,
                external_post_id=post.external_post_id,
                canonical_url=post.canonical_url,
                published_at=post.published_at,
                response_metadata={"idempotent_skip": True},
            )

        publisher = self.publishers.get(post.platform)
        if not publisher:
            err = f"No publisher registered for platform '{post.platform}'"
            post.status = ScheduleStatus.FAILED
            post.last_error = err
            post.updated_at = datetime.now(timezone.utc).isoformat()
            return PublishResult(success=False, platform=post.platform, error_message=err)

        post.status = ScheduleStatus.PUBLISHING
        post.updated_at = datetime.now(timezone.utc).isoformat()

        self._record_audit_event("publish_started", {
            "schedule_id": post.schedule_id,
            "media_job_id": post.media_job_id,
            "platform": post.platform,
            "account_id": post.account_id,
        })

        # Idempotency key binds candidate_id + media_job_id + platform
        idempotency_key = f"{post.candidate_id}:{post.media_job_id}:{post.platform}"

        try:
            res = publisher.publish(
                media_uri=post.media_uri,
                caption=post.caption,
                disclosure=post.disclosure,
                account_id=post.account_id,
                idempotency_key=idempotency_key,
                hashtags=post.hashtags,
            )

            if res.success:
                post.status = ScheduleStatus.PUBLISHED
                post.external_post_id = res.external_post_id
                post.canonical_url = res.canonical_url
                post.published_at = res.published_at or datetime.now(timezone.utc).isoformat()
                post.updated_at = datetime.now(timezone.utc).isoformat()

                # Record in store experiment ledger if available
                if self.store and hasattr(self.store, "publish"):
                    try:
                        self.store.publish(
                            cid=post.candidate_id,
                            url=post.canonical_url or f"https://social/{post.external_post_id}",
                            external_id=f"pub_{post.schedule_id}",
                        )
                    except Exception as err:
                        logging.warning("Store publish update skipped: %s", err)

                self._record_audit_event(
                    "publish_completed",
                    {
                        "schedule_id": post.schedule_id,
                        "candidate_id": post.candidate_id,
                        "external_post_id": post.external_post_id,
                        "canonical_url": post.canonical_url,
                        "platform": post.platform,
                    },
                    external_id=f"pub_ev_{post.schedule_id}",
                )
                return res

            else:
                # Failed attempt
                post.retry_count += 1
                post.last_error = res.error_message
                post.updated_at = datetime.now(timezone.utc).isoformat()

                if post.retry_count >= post.max_retries or not res.retryable:
                    post.status = ScheduleStatus.FAILED
                else:
                    post.status = ScheduleStatus.SCHEDULED  # Ready for retry

                self._record_audit_event("publish_failed", {
                    "schedule_id": post.schedule_id,
                    "error": res.error_message,
                    "retry_count": post.retry_count,
                    "retryable": res.retryable,
                })
                return res

        except Exception as ex:
            logging.exception("Unhandled error during outbox publishing: %s", ex)
            post.retry_count += 1
            post.last_error = str(ex)
            post.status = ScheduleStatus.FAILED if post.retry_count >= post.max_retries else ScheduleStatus.SCHEDULED
            post.updated_at = datetime.now(timezone.utc).isoformat()

            self._record_audit_event("publish_failed", {
                "schedule_id": post.schedule_id,
                "error": str(ex),
                "retry_count": post.retry_count,
            })
            return PublishResult(success=False, platform=post.platform, error_message=str(ex), retryable=True)

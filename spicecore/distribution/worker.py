"""Publish durable outbox rows, resume provider operations, and reconcile receipts."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from .base import Publisher, PublishResult, safe_provider_error
from .scheduler import ScheduledPost, ScheduleStatus, Scheduler, _instant


class OutboxWorker:
    """A bounded publication tick; remote submissions are never replayed blindly."""

    def __init__(self, scheduler: Scheduler, publishers: Dict[str, Publisher], store: Any = None,
                 retry_base_seconds: int = 30, retry_max_seconds: int = 3600,
                 max_pending_polls: int = 48):
        if retry_base_seconds < 1 or retry_max_seconds < retry_base_seconds or max_pending_polls < 1:
            raise ValueError("publication backoff and pending limits must be positive")
        self.scheduler = scheduler
        self.publishers = publishers
        self.store = store if store is not None else scheduler.store
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        self.max_pending_polls = max_pending_polls

    def _record_audit_event(self, kind: str, payload: Dict[str, Any], external_id: Optional[str] = None) -> None:
        if self.store and hasattr(self.store, "record_event"):
            try:
                self.store.record_event(kind, payload, external_id=external_id)
            except Exception as exc:
                logging.warning("Outbox worker audit log failed: %s", type(exc).__name__)

    @staticmethod
    def _public_result(result: PublishResult) -> PublishResult:
        if result.error_message:
            result.error_message = safe_provider_error(result.platform, result.error_message)
        result.response_metadata = {k: bool(v) for k, v in (result.response_metadata or {}).items()
                                    if k in ("pending", "needs_reconciliation", "ambiguous",
                                             "receipt_saved", "idempotent_skip")}
        return result

    def _backoff_at(self, as_of_iso: str, attempt: int) -> str:
        seconds = min(self.retry_max_seconds, self.retry_base_seconds * (2 ** min(max(0, attempt - 1), 16)))
        return (_instant(as_of_iso) + timedelta(seconds=seconds)).isoformat()

    @staticmethod
    def _has_receipt(post: ScheduledPost) -> bool:
        if not isinstance(post.external_post_id, str) or not post.external_post_id.strip():
            return False
        parsed = urlsplit(post.canonical_url or "")
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    @staticmethod
    def _receipt_result(post: ScheduledPost, replay: bool = False) -> PublishResult:
        return PublishResult(
            success=True, platform=post.platform, external_post_id=post.external_post_id,
            canonical_url=post.canonical_url, published_at=post.published_at,
            response_metadata={"idempotent_skip": replay},
        )

    def process_due(self, as_of_iso: Optional[str] = None) -> List[PublishResult]:
        as_of = _instant(as_of_iso).isoformat()
        results = []
        for post in self.scheduler.get_due_posts(as_of):
            try:
                results.append(self.process_post(post, as_of))
            except Exception as exc:
                # A durable PUBLISHING claim survives a failed persistence write. Its
                # expired lease will require reconciliation rather than a new submit.
                logging.warning("Publication queue state update failed for %s: %s", post.schedule_id, type(exc).__name__)
                results.append(PublishResult(
                    success=False, platform=post.platform, error_message=safe_provider_error(post.platform, exc),
                    response_metadata={"needs_reconciliation": True},
                ))
        return results

    def _validate_candidate(self, post: ScheduledPost) -> None:
        if self.store and hasattr(self.store, "candidate"):
            candidate = self.store.candidate(post.candidate_id)
            if candidate["status"] not in ("approved", "published"):
                raise PermissionError("candidate approval was revoked or is missing")
            if post.media_job_id == f"candidate:{post.candidate_id}" and not post.provider_state:
                self.scheduler._validate_media_uri(post.media_uri)

    def _write_receipt(self, post: ScheduledPost) -> None:
        if not self.store or not hasattr(self.store, "publish"):
            return
        external_id = f"pub_{post.schedule_id}"
        candidate = self.store.candidate(post.candidate_id)
        payload = {
            "candidate_id": post.candidate_id,
            "persona_id": candidate["persona_id"],
            "url": post.canonical_url,
        }
        if candidate["status"] == "approved":
            self.store.publish(cid=post.candidate_id, url=post.canonical_url, external_id=external_id)
        elif candidate["status"] == "published":
            # One approved candidate can have distinct account/platform receipts.
            # record_event also verifies the content of any existing receipt ID.
            self.store.record_event("content_published", payload, external_id=external_id)
        else:
            raise PermissionError("confirmed publication receipt cannot update an unapproved candidate")

    def _finish_receipt(self, post: ScheduledPost, as_of_iso: str,
                        result: Optional[PublishResult] = None) -> PublishResult:
        try:
            self._write_receipt(post)
        except Exception as exc:
            post.status = ScheduleStatus.NEEDS_RECONCILIATION
            post.last_error = safe_provider_error(post.platform, exc)
            post.claimed_at = None
            post.updated_at = as_of_iso
            post.retry_count += 1
            post.next_attempt_at = self._backoff_at(as_of_iso, post.retry_count)
            self.scheduler.save_post(post)
            return PublishResult(
                success=False, platform=post.platform, external_post_id=post.external_post_id,
                canonical_url=post.canonical_url, published_at=post.published_at,
                error_message=post.last_error,
                response_metadata={"receipt_saved": True, "needs_reconciliation": True},
            )
        post.status = ScheduleStatus.PUBLISHED
        post.last_error = None
        post.claimed_at = None
        post.next_attempt_at = None
        post.updated_at = as_of_iso
        self.scheduler.save_post(post)
        self._record_audit_event("publish_completed", {
            "schedule_id": post.schedule_id,
            "candidate_id": post.candidate_id,
            "external_post_id": post.external_post_id,
            "canonical_url": post.canonical_url,
            "platform": post.platform,
            "account_id": post.account_id,
        }, external_id=f"pub_ev_{post.schedule_id}")
        return self._public_result(result or self._receipt_result(post))

    def _fail(self, post: ScheduledPost, result: PublishResult, as_of_iso: str,
              ambiguous: bool = False) -> PublishResult:
        post.retry_count += 1
        result = self._public_result(result)
        post.last_error = result.error_message or "publication attempt failed"
        post.updated_at = as_of_iso
        post.claimed_at = None
        post.next_attempt_at = None
        if ambiguous:
            post.status = ScheduleStatus.NEEDS_RECONCILIATION
        elif not result.retryable or post.retry_count >= post.max_retries:
            # A retained remote operation may still finish after polling fails.
            post.status = ScheduleStatus.NEEDS_RECONCILIATION if post.provider_state else ScheduleStatus.FAILED
        else:
            post.status = ScheduleStatus.PENDING if post.provider_state else ScheduleStatus.SCHEDULED
            post.next_attempt_at = self._backoff_at(as_of_iso, post.retry_count)
        self.scheduler.save_post(post)
        self._record_audit_event("publish_failed", {
            "schedule_id": post.schedule_id,
            "error": post.last_error,
            "retry_count": post.retry_count,
            "retryable": result.retryable,
            "status": post.status.value,
        })
        return result

    def process_post(self, post: ScheduledPost, as_of_iso: Optional[str] = None) -> PublishResult:
        as_of = _instant(as_of_iso).isoformat()
        # The supplied dataclass may belong to a stale process or older queue view.
        current = self.scheduler.get_post(post.schedule_id)
        if current.status == ScheduleStatus.PUBLISHED:
            return self._receipt_result(current, replay=True)
        claimed = self.scheduler.claim_post(current.schedule_id, as_of)
        if claimed is None:
            return PublishResult(
                success=False, platform=current.platform,
                error_message="publication is not due, is already claimed, or is terminal",
            )
        post = claimed
        if self._has_receipt(post):
            return self._finish_receipt(post, as_of)

        try:
            self._validate_candidate(post)
        except (ValueError, PermissionError, OSError) as exc:
            return self._fail(post, PublishResult(
                success=False, platform=post.platform, error_message=str(exc),
            ), as_of)

        publisher = self.publishers.get(post.platform)
        if publisher is None:
            return self._fail(post, PublishResult(
                success=False, platform=post.platform,
                error_message=f"No publisher registered for platform '{post.platform}'",
            ), as_of)

        self._record_audit_event("publish_started", {
            "schedule_id": post.schedule_id,
            "media_job_id": post.media_job_id,
            "platform": post.platform,
            "account_id": post.account_id,
            "resuming": bool(post.provider_state),
        })
        try:
            result = publisher.publish(
                media_uri=post.media_uri,
                caption=post.caption,
                disclosure=post.disclosure,
                account_id=post.account_id,
                idempotency_key=f"{post.candidate_id}:{post.media_job_id}:{post.platform}:{post.account_id}",
                hashtags=post.hashtags,
                resume_metadata=dict(post.provider_state),
            )
        except Exception as exc:
            logging.warning("Publication provider call failed for %s: %s", post.schedule_id, type(exc).__name__)
            return self._fail(post, PublishResult(
                success=False, platform=post.platform, error_message=safe_provider_error(post.platform, exc), retryable=True,
                response_metadata={"needs_reconciliation": not bool(post.provider_state)},
            ), as_of, ambiguous=not bool(post.provider_state))

        metadata = result.response_metadata or {}
        state = metadata.get("provider_state")
        if isinstance(state, dict) and state:
            post.provider_state = dict(state)
        if getattr(result, "pending", False) or metadata.get("pending"):
            if not post.provider_state:
                return self._fail(post, PublishResult(
                    success=False, platform=post.platform,
                    error_message="provider accepted an operation without resumable state",
                ), as_of, ambiguous=True)
            post.poll_count += 1
            result = self._public_result(result)
            post.status = (ScheduleStatus.PENDING if post.poll_count < self.max_pending_polls
                           else ScheduleStatus.NEEDS_RECONCILIATION)
            post.last_error = (result.error_message if post.status == ScheduleStatus.PENDING
                               else "provider operation exceeded the bounded polling limit")
            post.claimed_at = None
            post.updated_at = as_of
            post.next_attempt_at = self._backoff_at(as_of, post.poll_count)
            self.scheduler.save_post(post)
            return result
        if metadata.get("needs_reconciliation") or metadata.get("ambiguous"):
            return self._fail(post, result, as_of, ambiguous=True)
        if not result.success:
            return self._fail(post, result, as_of)

        post.external_post_id = result.external_post_id
        post.canonical_url = result.canonical_url
        post.published_at = result.published_at or as_of
        if not self._has_receipt(post):
            return self._fail(post, PublishResult(
                success=False, platform=post.platform,
                error_message="provider success requires a confirmed post ID and canonical URL",
                response_metadata={"needs_reconciliation": True},
            ), as_of, ambiguous=True)
        # Commit the actual receipt before touching the experiment ledger. A crash
        # after this write can finish bookkeeping without submitting remote media.
        post.updated_at = as_of
        self.scheduler.save_post(post)
        return self._finish_receipt(post, as_of, result)

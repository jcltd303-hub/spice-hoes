"""Base interfaces for social platform publishers and scheduling adapters."""

from __future__ import annotations

import abc
import ipaddress
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class PublishResult:
    success: bool
    platform: str
    external_post_id: Optional[str] = None
    canonical_url: Optional[str] = None
    published_at: Optional[str] = None
    response_metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    retryable: bool = False
    # Acceptance/upload is not publication. Persist provider_state before polling.
    pending: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PublisherAPIError(RuntimeError):
    """A provider rejected a request, with explicit retry/uncertainty information."""

    def __init__(self, message: str, *, retryable: bool = False, ambiguous: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.ambiguous = ambiguous


class PublisherValidationError(ValueError):
    """Static application validation text, without provider/customer values."""


class SafePublisherMessage(str):
    """A diagnostic assembled only from static text and known provider codes."""


def safe_provider_error(platform: str, error=None, *, code=None) -> SafePublisherMessage:
    known_codes = {"url_ownership_unverified", "duration_check_failed", "rate_limit_exceeded",
                   "internal_error", "access_token_invalid", "invalid_params", "scope_not_authorized",
                   "spam_risk_too_many_posts", "spam_risk_user_banned_from_posting", "auth_removed",
                   "file_format_check_failed", "picture_size_check_failed"}
    provider_code = str(code) if type(code) is int and 0 <= code <= 999999 else (
        code if isinstance(code, str) and code in known_codes else "unclassified")
    if isinstance(error, (PublisherAPIError, PublisherValidationError)):
        return SafePublisherMessage(str(error))
    if isinstance(error, SafePublisherMessage):
        return error
    kind = type(error).__name__ if isinstance(error, BaseException) else "PublisherError"
    return SafePublisherMessage(f"{platform} {kind} ({provider_code})")


def resume_provider_state(metadata: Optional[Dict[str, Any]], platform: str, account_id: str) -> Dict[str, Any]:
    """Accept persisted state, refusing to resume a different platform/account."""
    if metadata is None or metadata == {}:
        return {}
    if not isinstance(metadata, dict):
        raise PublisherValidationError("resume_metadata must be a provider state dictionary")
    state = metadata.get("provider_state", metadata)
    if not isinstance(state, dict) or not state:
        raise PublisherValidationError("resume_metadata does not contain provider state")
    state = dict(state)
    if state.get("platform", platform) != platform or state.get("account_id", account_id) != account_id:
        raise PublisherValidationError("Provider state belongs to a different platform or account")
    state.setdefault("platform", platform)
    state.setdefault("account_id", account_id)
    return state


def require_public_media_url(media_uri: str) -> str:
    """URL-pull providers cannot fetch a local path or private-host URL."""
    parsed = urllib.parse.urlsplit(media_uri)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise PublisherValidationError("Media must have a publicly accessible HTTPS URL")
    if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local")):
        raise PublisherValidationError("Media URL must use a public host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise PublisherValidationError("Media URL must use a public host")
    return media_uri


def pending_publish_result(platform: str, state: Dict[str, Any], response: Optional[Dict[str, Any]] = None, error_message: Optional[str] = None) -> PublishResult:
    return PublishResult(
        success=False, pending=True, platform=platform,
        error_message=SafePublisherMessage(error_message) if error_message else None,
        response_metadata={"pending": True, "provider_state": dict(state), "response": response or {}},
    )


def failed_publish_result(platform: str, error_message: str, state: Optional[Dict[str, Any]] = None, *, retryable: bool = False, needs_reconciliation: bool = False) -> PublishResult:
    metadata: Dict[str, Any] = {"provider_state": dict(state)} if state else {}
    if needs_reconciliation:
        metadata["needs_reconciliation"] = True
    return PublishResult(success=False, platform=platform, error_message=SafePublisherMessage(error_message), retryable=retryable, response_metadata=metadata)


@dataclass
class PlatformMetrics:
    platform: str
    post_id: str
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    impressions: int = 0
    views: int = 0
    watch_time_ms: int = 0
    completion_rate: float = 0.0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    profile_visits: int = 0
    link_clicks: int = 0
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Publisher(abc.ABC):
    """Abstract interface for social publishing networks."""

    @property
    @abc.abstractmethod
    def platform_name(self) -> str:
        pass

    @abc.abstractmethod
    def publish(
        self,
        media_uri: str,
        caption: str,
        disclosure: str,
        account_id: str,
        idempotency_key: Optional[str] = None,
        hashtags: Optional[list] = None,
        resume_metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> PublishResult:
        """Submit once or resume with persisted ``resume_metadata`` provider state.

        ``success`` means confirmed publication. Asynchronous acceptance returns
        ``pending`` and ``response_metadata['provider_state']`` for a later call.
        An idempotency key alone does not make external provider POSTs idempotent.
        """
        pass

    @abc.abstractmethod
    def schedule(
        self,
        media_uri: str,
        caption: str,
        disclosure: str,
        account_id: str,
        scheduled_at_iso: str,
        idempotency_key: Optional[str] = None,
        **kwargs,
    ) -> PublishResult:
        """Schedules media using native platform scheduling API if supported."""
        pass

    @abc.abstractmethod
    def delete(self, external_post_id: str, account_id: str) -> bool:
        """Deletes a previously published post."""
        pass

    @abc.abstractmethod
    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        """Retrieves raw performance metrics for a published post."""
        pass

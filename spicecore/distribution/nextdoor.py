"""Nextdoor distribution adapter and campaign generator.

Nextdoor exposes no public posting API for ordinary accounts, so this adapter is
honest about that: it does NOT auto-publish. ``publish()``/``schedule()`` fail
closed with a manual-handoff package (staged copy + posting checklist) that the
operator pastes into the Nextdoor app/website from a verified account, then
records with the normal ``publish`` CLI command.

Campaign copy is generated deterministically from a seed, always carries the
persona disclosure, and is validated against the project's engagement policy:
no claiming to be a real human/neighbor, no guaranteed-earnings claims, no
pressure tactics, and no payment-card/banking requests. Generated variants are
proposed as candidates and stay ``proposed`` until a human approves them.
"""

from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import PlatformMetrics, Publisher, PublishResult

PLATFORM = "nextdoor"

# ---------------------------------------------------------------------------
# Copy policy
# ---------------------------------------------------------------------------

# (pattern, human-readable violation)
_BANNED_PATTERNS = [
    (
        re.compile(
            r"\bi['\u2019]?m (a real|your|a local) (person|human|neighbor)\b"
            r"|\bas a (real|fellow) (human|neighbor)\b"
            r"|\bi live at \d+",
            re.IGNORECASE,
        ),
        "claims to be a real human/neighbor",
    ),
    (
        re.compile(r"\b(act now|don['\u2019]?t miss out|last chance|you must|if you cared)\b", re.IGNORECASE),
        "pressure/manipulation language",
    ),
    (
        re.compile(
            r"\b(card number|bank account|routing number|sort code|send me money|"
            r"venmo me|cash.?app me|wire (the|me)|zelle me)\b",
            re.IGNORECASE,
        ),
        "requests payment-card or banking details",
    ),
    (re.compile(r"[A-Z][A-Z\s]{14,}[A-Z]"), "shouting (long all-caps run)"),
    (re.compile(r"!{3,}"), "excessive exclamation marks"),
]


def _money_guarantee(text: str) -> bool:
    """Flags 'guaranteed earnings' style claims without banning the word alone."""
    has_guarantee = re.search(r"\bguarantee\w*\b", text, re.IGNORECASE)
    has_money = re.search(r"\b(money|earn\w*|income|profit|returns?|payout|cash)\b", text, re.IGNORECASE)
    return bool(has_guarantee and has_money)


def _link_count(text: str) -> int:
    return len(re.findall(r"https?://", text))


def validate_copy(text: str, require_disclosure: str = "") -> List[str]:
    """Return a list of policy violations found in the copy (empty = clean)."""
    violations: List[str] = []
    for pattern, label in _BANNED_PATTERNS:
        if pattern.search(text):
            violations.append(label)
    if _money_guarantee(text):
        violations.append("guaranteed-earnings claim")
    if _link_count(text) > 2:
        violations.append("too many links (spam pattern)")
    if require_disclosure and require_disclosure.strip() not in text:
        violations.append("missing persona disclosure")
    return violations


# ---------------------------------------------------------------------------
# Campaign generation
# ---------------------------------------------------------------------------

_CAMPAIGN_KINDS = ("story", "offer", "event")

_HOOKS = [
    "Neighbors \u2014 a quick story from {neighborhood}.",
    "Hey {neighborhood}, wanted to share something local.",
    "{neighborhood} neighbors, this one is close to home.",
]

_STORY_BODIES = [
    "I have been following {cause} for a while, and the work happening right here in our area is the real deal \u2014 {detail}",
    "You may have heard about {cause} around {neighborhood}. I looked into what they actually do, and {detail}",
]

_STORY_DETAILS = [
    "volunteers from our own streets run the whole thing, and every dollar stays local.",
    "they quietly helped dozens of local families this year without much fanfare.",
    "it is one of those rare efforts where you can see exactly where the money goes.",
]

_STORY_ASKS = [
    "They are raising funds to keep it going, and I figured our neighborhood would want to know.",
    "There is a fundraiser running to keep the lights on \u2014 passing it along in case it speaks to you.",
]

_OFFER_LEADS = [
    "Local find worth sharing: {cause}.",
    "Something I have actually been using: {cause}.",
]

_OFFER_BODIES = [
    "Full disclosure, this is an affiliate link, so I may earn a small commission if you buy \u2014 at no extra cost to you. {detail}",
    "Posting this as an affiliate: if you grab one through my link I earn a small commission. {detail}",
]

_OFFER_DETAILS = [
    "I only share things I would recommend to a friend, and this one earned it.",
    "Quality has held up well for me so far, which is why I am comfortable posting it here.",
]

_EVENT_LEADS = [
    "Mark your calendars, {neighborhood} \u2014 {cause} is happening soon.",
    "{neighborhood}: heads up about {cause}, coming up locally.",
]

_EVENT_BODIES = [
    "Details: {detail} Would be great to see some familiar faces there.",
    "The plan: {detail} Come say hi if you make it.",
]

_EVENT_DETAILS = [
    "a casual neighborhood get-together with a short fundraiser for {goal}.",
    "an open-house style afternoon supporting {goal}, all are welcome.",
]

_CTAS_WITH_OFFER = [
    "Official page with details: {offer}. Happy to answer what I can in the comments.",
    "If you would like to help, the official page is here: {offer}. No pressure either way.",
]

_CTAS_NO_OFFER = [
    "Drop questions in the comments \u2014 happy to share what I know.",
    "Curious what neighbors think \u2014 chime in below.",
]

_DISCLOSURE_TAIL = "\n\n\u2014 {persona_name} \u00b7 {disclosure} \u00b7 Drafted with AI assistance; a human reviewed this before posting."


@dataclass
class NextdoorCampaignVariant:
    variant_id: str
    kind: str
    title: str
    body: str
    cta: str
    tags: List[str] = field(default_factory=list)
    seed: Optional[int] = None
    violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_campaign(
    persona: Dict[str, Any],
    goal: str,
    cause: str,
    neighborhood: str,
    offer: str = "none",
    seed: Optional[int] = None,
    count: int = 3,
) -> List[NextdoorCampaignVariant]:
    """Generate deterministic Nextdoor campaign copy variants.

    Every variant carries the persona disclosure and is validated before
    return; ``violations`` should always be empty by construction, and any
    non-empty result means the generator itself needs fixing.
    """
    if not goal.strip() or not cause.strip() or not neighborhood.strip():
        raise ValueError("goal, cause, and neighborhood are required")
    if not persona.get("id") or not persona.get("disclosure"):
        raise ValueError("persona with id and disclosure is required")

    rng = random.Random(seed)
    disclosure = str(persona["disclosure"]).strip()
    tail = _DISCLOSURE_TAIL.format(persona_name=persona.get("name", persona["id"]), disclosure=disclosure)
    has_offer = bool(offer and offer.strip().lower() != "none")
    ctas = [c.format(offer=offer) for c in _CTAS_WITH_OFFER] if has_offer else list(_CTAS_NO_OFFER)

    kinds = list(_CAMPAIGN_KINDS)[: max(1, count)]
    variants: List[NextdoorCampaignVariant] = []
    for i, kind in enumerate(kinds):
        if kind == "story":
            title = f"{cause} \u2014 a {neighborhood} story"
            body = (
                f"{rng.choice(_HOOKS).format(neighborhood=neighborhood)}\n\n"
                f"{rng.choice(_STORY_BODIES).format(cause=cause, neighborhood=neighborhood, detail=rng.choice(_STORY_DETAILS))}\n\n"
                f"{rng.choice(_STORY_ASKS)}"
            )
        elif kind == "offer":
            title = rng.choice(_OFFER_LEADS).format(cause=cause)
            body = rng.choice(_OFFER_BODIES).format(detail=rng.choice(_OFFER_DETAILS))
            if has_offer:
                body += f" Link: {offer}"
        else:  # event
            title = rng.choice(_EVENT_LEADS).format(neighborhood=neighborhood, cause=cause)
            body = rng.choice(_EVENT_BODIES).format(
                detail=rng.choice(_EVENT_DETAILS).format(goal=goal)
            )

        cta = rng.choice(ctas)
        full_body = f"{body}\n\n{cta}{tail}"
        variants.append(
            NextdoorCampaignVariant(
                variant_id=f"nd_{kind}_{seed if seed is not None else 'x'}_{i}",
                kind=kind,
                title=title,
                body=full_body,
                cta=cta,
                tags=[neighborhood.lower().replace(" ", "-"), "local", kind],
                seed=seed,
                violations=validate_copy(full_body, require_disclosure=disclosure),
            )
        )
    return variants


# ---------------------------------------------------------------------------
# Publisher (manual-handoff: Nextdoor has no public posting API)
# ---------------------------------------------------------------------------

_MANUAL_STEPS = [
    "Review and approve the candidate in the review desk (`serve`).",
    "Copy the staged text from the handoff package.",
    "Post manually from the Nextdoor app/website using the verified neighborhood account.",
    "Record the live URL: python3 -m spicecore.cli publish <candidate_id> --url <url>.",
    "Log observed outcomes with the `outcome` command for attribution.",
]


class NextdoorPublisher(Publisher):
    """Manual-handoff publisher for Nextdoor.

    Nextdoor offers no public API for posting as a neighborhood account, so
    this adapter never auto-publishes. ``publish()`` validates the copy and
    returns a staged handoff the operator posts by hand. Fails closed, exactly
    like the credential-less API adapters.
    """

    def __init__(self):
        self._idempotency_map: Dict[str, Dict[str, Any]] = {}

    @property
    def platform_name(self) -> str:
        return PLATFORM

    def _stage(
        self,
        media_uri: str,
        caption: str,
        disclosure: str,
        account_id: str,
        idempotency_key: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
    ) -> PublishResult:
        full_text = f"{caption}\n\n{disclosure}".strip()
        violations = validate_copy(full_text, require_disclosure=disclosure)
        staged = {
            "media_uri": media_uri,
            "text": full_text,
            "hashtags": hashtags or [],
            "account_id": account_id,
            "manual_steps": _MANUAL_STEPS,
        }
        if idempotency_key:
            self._idempotency_map[idempotency_key] = staged
        if violations:
            return PublishResult(
                success=False,
                platform=PLATFORM,
                error_message="Copy failed Nextdoor policy check: " + "; ".join(violations),
                retryable=False,
                response_metadata={"staged": staged, "violations": violations},
            )
        return PublishResult(
            success=False,
            platform=PLATFORM,
            error_message=(
                "Nextdoor has no public posting API; copy staged for manual posting. "
                "Approve the candidate, post by hand from the verified account, then record the URL."
            ),
            retryable=False,
            response_metadata={
                "staged": staged,
                "manual_handoff": True,
                "idempotent_replay": bool(idempotency_key and idempotency_key in self._idempotency_map),
            },
        )

    def publish(
        self,
        media_uri: str,
        caption: str,
        disclosure: str,
        account_id: str,
        idempotency_key: Optional[str] = None,
        hashtags: Optional[list] = None,
        **kwargs,
    ) -> PublishResult:
        if idempotency_key and idempotency_key in self._idempotency_map:
            staged = self._idempotency_map[idempotency_key]
            return PublishResult(
                success=False,
                platform=PLATFORM,
                error_message="Manual handoff already staged for this idempotency key.",
                retryable=False,
                response_metadata={"staged": staged, "manual_handoff": True, "idempotent_replay": True},
            )
        return self._stage(media_uri, caption, disclosure, account_id, idempotency_key, hashtags)

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
        # No native scheduling without an API; hand off for manual posting at the chosen time.
        result = self.publish(media_uri, caption, disclosure, account_id, idempotency_key=idempotency_key, **kwargs)
        result.response_metadata["requested_schedule_at"] = scheduled_at_iso
        return result

    def delete(self, external_post_id: str, account_id: str) -> bool:
        return False

    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        raise RuntimeError(
            "Nextdoor exposes no metrics API; record impressions/clicks manually via the `outcome` command."
        )


def staged_at_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

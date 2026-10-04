"""Guarded DM auto-responder.

Wires the engagement pipeline end to end: ingest -> draft -> programmatic
policy validation -> approve -> outbox.

Guards (enforced in code, not just in prompts):
- Disclosure is mandatory. If the draft lacks the persona disclosure, it is
  appended automatically — never skipped.
- Policy validation. Every draft is checked for identity deception ("I'm a real
  human/neighbor"), pressure/manipulation tactics, payment-card or banking
  requests, guaranteed-earnings claims, shouting, and link spam. Any violation
  holds the draft for human review; it is never auto-approved.
- Model handoff. If the drafting model itself flags a `handoff_reason`, the
  draft is held for human review.
- Rate limit. At most `max_auto_per_day` auto-approvals per conversation per
  24 hours (default 10). Beyond that, drafts are held for human review.
- Text only. The auto path never generates or attaches images/media. Generated
  media stays on the human-reviewed generate -> review -> approve path.
- Audit. Every auto-approval and every hold is recorded as a ledger event.

Drafts that fail any guard stay `proposed` and appear in the normal review
queue; nothing failing validation is ever sent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .distribution.nextdoor import validate_copy
from .engagement import EngagementAgent

AUTO_REVIEWER = "auto-responder"
DEFAULT_MAX_AUTO_PER_DAY = 10


def validate_reply(body: str, disclosure: str) -> List[str]:
    """Policy violations in a DM reply draft (empty = clean)."""
    return validate_copy(body, require_disclosure=disclosure)


class AutoResponder:
    def __init__(
        self,
        agent: EngagementAgent,
        max_auto_per_day: int = DEFAULT_MAX_AUTO_PER_DAY,
    ):
        self.agent = agent
        self.store = agent.store
        self.max_auto_per_day = max(1, max_auto_per_day)

    # -- internals ------------------------------------------------------

    def _auto_approved_today(self, conversation_id: str) -> int:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        row = self.store.db.execute(
            """SELECT COUNT(*) FROM engagement_draft
               WHERE conversation_id=? AND reviewer=? AND status='approved' AND ts >= ?""",
            (conversation_id, AUTO_REVIEWER, since),
        ).fetchone()
        return int(row[0])

    def _existing_draft(self, inbound_message_id: str) -> Optional[Dict[str, Any]]:
        row = self.store.db.execute(
            "SELECT * FROM engagement_draft WHERE inbound_message_id=? ORDER BY ts DESC LIMIT 1",
            (inbound_message_id,),
        ).fetchone()
        return dict(row) if row else None

    def _hold_reasons(self, draft: Dict[str, Any], disclosure: str) -> List[str]:
        reasons: List[str] = []
        if draft.get("handoff_reason"):
            reasons.append(f"model handoff: {draft['handoff_reason']}")
        # Disclosure is enforced by the append step below, not the validator:
        # a merely disclosure-less draft must not be held for that alone.
        violations = validate_reply(draft["reply"], "")
        reasons.extend(f"policy: {v}" for v in violations)
        return reasons

    # -- public API -----------------------------------------------------

    def process_inbound(
        self,
        persona: Dict[str, Any],
        channel: str,
        external_conversation_id: str,
        external_message_id: str,
        body: str,
    ) -> Dict[str, Any]:
        """Process one inbound DM end to end. Idempotent per external message id."""
        disclosure = str(persona.get("disclosure", "")).strip()
        if not persona.get("id") or not disclosure:
            raise ValueError("persona with id and disclosure is required")

        inbound = self.agent.ingest_inbound(
            persona, channel, external_conversation_id, external_message_id, body
        )
        existing = self._existing_draft(inbound["id"])
        if existing:
            return {
                "action": "already_processed",
                "draft_id": existing["id"],
                "status": existing["status"],
                "inbound_message_id": inbound["id"],
            }

        conversation_id = inbound["conversation_id"]
        if self._auto_approved_today(conversation_id) >= self.max_auto_per_day:
            # Draft first so the human sees it, then hold it.
            draft = self.agent.draft_reply(persona, inbound["id"])
            self.store.record_event("auto_reply_held", {
                "draft_id": draft["draft_id"],
                "conversation_id": conversation_id,
                "inbound_message_id": inbound["id"],
                "persona_id": persona["id"],
                "channel": channel,
                "reasons": ["rate_limit: max auto-replies per conversation per day reached"],
            })
            return {
                "action": "held",
                "draft_id": draft["draft_id"],
                "status": "proposed",
                "reasons": ["rate_limit"],
                "inbound_message_id": inbound["id"],
            }

        draft = self.agent.draft_reply(persona, inbound["id"])
        reasons = self._hold_reasons(draft, disclosure)
        if reasons:
            self.store.record_event("auto_reply_held", {
                "draft_id": draft["draft_id"],
                "conversation_id": conversation_id,
                "inbound_message_id": inbound["id"],
                "persona_id": persona["id"],
                "channel": channel,
                "reasons": reasons,
            })
            return {
                "action": "held",
                "draft_id": draft["draft_id"],
                "status": "proposed",
                "reasons": reasons,
                "inbound_message_id": inbound["id"],
            }

        reply = draft["reply"]
        if disclosure not in reply:
            reply = f"{reply}\n\n{disclosure}"
            # Re-validate after appending (append can only add the disclosure).
            extra = validate_reply(reply, disclosure)
            if extra:
                self.store.record_event("auto_reply_held", {
                    "draft_id": draft["draft_id"],
                    "conversation_id": conversation_id,
                    "inbound_message_id": inbound["id"],
                    "persona_id": persona["id"],
                    "channel": channel,
                    "reasons": [f"policy: {v}" for v in extra],
                })
                return {
                    "action": "held",
                    "draft_id": draft["draft_id"],
                    "status": "proposed",
                    "reasons": [f"policy: {v}" for v in extra],
                    "inbound_message_id": inbound["id"],
                }
            with self.store.db:
                self.store.db.execute(
                    "UPDATE engagement_draft SET body=? WHERE id=?",
                    (reply, draft["draft_id"]),
                )

        self.agent.review_draft(
            draft["draft_id"], "approved", AUTO_REVIEWER,
            note="auto-approved: policy-validated, disclosure present",
        )
        self.store.record_event("auto_reply_approved", {
            "draft_id": draft["draft_id"],
            "conversation_id": conversation_id,
            "inbound_message_id": inbound["id"],
            "persona_id": persona["id"],
            "channel": channel,
            "commerce_relevant": draft.get("commerce_relevant", False),
            "intent": draft.get("intent"),
        })
        return {
            "action": "auto_approved",
            "draft_id": draft["draft_id"],
            "status": "approved",
            "reply": reply,
            "inbound_message_id": inbound["id"],
        }

    def poll(
        self,
        persona: Dict[str, Any],
        channel: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Process every inbound message that has no draft yet (oldest first)."""
        query = """
            SELECT m.*, c.external_conversation_id, c.channel AS conv_channel
            FROM engagement_message m
            JOIN engagement_conversation c ON c.id = m.conversation_id
            LEFT JOIN engagement_draft d ON d.inbound_message_id = m.id
            WHERE m.direction='inbound' AND d.id IS NULL
              AND c.persona_id = ?
        """
        params: List[Any] = [persona["id"]]
        if channel:
            query += " AND c.channel = ?"
            params.append(channel)
        query += " ORDER BY m.ts ASC LIMIT ?"
        params.append(max(1, limit))
        rows = self.store.db.execute(query, params).fetchall()

        results = []
        for row in rows:
            results.append(self.process_inbound(
                persona,
                row["conv_channel"],
                row["external_conversation_id"],
                row["external_message_id"],
                row["body"],
            ))
        return results

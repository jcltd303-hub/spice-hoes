"""Auditable engagement draft agent with mandatory human review."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone


_CARDISH = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)


def redact_sensitive(text: str) -> str:
    text = _CARDISH.sub("[REDACTED_PAYMENT_NUMBER]", text)
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    return text


class EngagementAgent:
    def __init__(self, provider, store, knowledge):
        self.provider = provider
        self.store = store
        self.knowledge = knowledge
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS engagement_conversation (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                external_conversation_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS engagement_message (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                direction TEXT NOT NULL,
                external_message_id TEXT UNIQUE,
                body TEXT NOT NULL,
                intent TEXT,
                FOREIGN KEY(conversation_id) REFERENCES engagement_conversation(id)
            );
            CREATE TABLE IF NOT EXISTS engagement_draft (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                inbound_message_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                body TEXT NOT NULL,
                intent TEXT NOT NULL,
                commerce_relevant INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'proposed',
                reviewer TEXT,
                note TEXT,
                model TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES engagement_conversation(id)
            );
            """
        )
        self.store.db.commit()

    def _conversation(self, persona: dict, channel: str,
                      external_conversation_id: str) -> dict:
        row = self.store.db.execute(
            "SELECT * FROM engagement_conversation WHERE external_conversation_id=?",
            (external_conversation_id,),
        ).fetchone()
        if row:
            if row["persona_id"] != persona["id"] or row["channel"] != channel:
                raise ValueError("conversation identity mismatch")
            return dict(row)

        cid = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO engagement_conversation
                   (id,ts,persona_id,channel,external_conversation_id)
                   VALUES(?,?,?,?,?)""",
                (cid, ts, persona["id"], channel, external_conversation_id),
            )
            self.store._event("engagement_conversation_created", {
                "conversation_id": cid,
                "persona_id": persona["id"],
                "channel": channel,
            })
        return {
            "id": cid,
            "ts": ts,
            "persona_id": persona["id"],
            "channel": channel,
            "external_conversation_id": external_conversation_id,
        }

    def ingest_inbound(self, persona: dict, channel: str,
                       external_conversation_id: str,
                       external_message_id: str,
                       body: str) -> dict:
        if not all(str(x).strip() for x in (
            channel, external_conversation_id, external_message_id, body
        )):
            raise ValueError("channel, conversation id, message id and body are required")
        existing = self.store.db.execute(
            "SELECT * FROM engagement_message WHERE external_message_id=?",
            (external_message_id,),
        ).fetchone()
        if existing:
            return dict(existing)

        conversation = self._conversation(
            persona, channel, external_conversation_id
        )
        mid = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        clean = redact_sensitive(body.strip())
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO engagement_message
                   (id,conversation_id,ts,direction,external_message_id,body)
                   VALUES(?,?,?,?,?,?)""",
                (
                    mid, conversation["id"], ts, "inbound",
                    external_message_id, clean,
                ),
            )
            self.store._event("engagement_inbound_received", {
                "message_id": mid,
                "conversation_id": conversation["id"],
                "persona_id": persona["id"],
                "channel": channel,
            }, external_id=f"engagement-inbound:{external_message_id}")
        return {
            "id": mid,
            "conversation_id": conversation["id"],
            "ts": ts,
            "direction": "inbound",
            "external_message_id": external_message_id,
            "body": clean,
        }

    def _history(self, conversation_id: str, limit: int = 12) -> list[dict]:
        rows = self.store.db.execute(
            """SELECT direction,body,ts FROM engagement_message
               WHERE conversation_id=? ORDER BY ts DESC LIMIT ?""",
            (conversation_id, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def draft_reply(self, persona: dict, inbound_message_id: str) -> dict:
        inbound = self.store.db.execute(
            """SELECT m.*, c.channel, c.persona_id
               FROM engagement_message m
               JOIN engagement_conversation c ON c.id=m.conversation_id
               WHERE m.id=?""",
            (inbound_message_id,),
        ).fetchone()
        if inbound is None or inbound["direction"] != "inbound":
            raise ValueError("unknown inbound message")
        if inbound["persona_id"] != persona["id"]:
            raise ValueError("message/persona mismatch")

        history = self._history(inbound["conversation_id"])
        query = inbound["body"] + " " + persona.get("voice", "")
        context, citations = self.knowledge.context(query, limit=4, max_chars=4000)
        request = {
            "persona": {
                "id": persona["id"],
                "name": persona["name"],
                "age": persona["age"],
                "voice": persona.get("voice", ""),
                "hobbies": persona.get("hobbies", []),
                "disclosure": persona.get("disclosure", ""),
            },
            "channel": inbound["channel"],
            "history": history,
            "latest_inbound": inbound["body"],
            "retrieved_context": context,
            "schema": {
                "reply": "concise draft reply",
                "intent": "conversation intent label",
                "commerce_relevant": "boolean",
                "handoff_reason": "optional reason a human should inspect carefully",
            },
        }
        raw = self.provider.chat(
            "Draft a reply for a disclosed fictional adult AI persona. "
            "Never claim to be a real human, never imply that spending proves affection, "
            "never pressure the user to pay, and never request payment-card or banking details. "
            "You may answer product/offer questions factually and warmly. "
            "If asked whether the persona is AI, answer clearly. Return JSON only.",
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            temperature=0.4,
        )
        try:
            parsed = json.loads(raw)
            reply = str(parsed["reply"]).strip()
            intent = str(parsed.get("intent", "unknown")).strip() or "unknown"
            commerce = bool(parsed.get("commerce_relevant", False))
            handoff_reason = str(parsed.get("handoff_reason", "")).strip()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("engagement provider returned invalid JSON") from exc
        if not reply:
            raise ValueError("engagement provider returned empty reply")

        did = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        model = getattr(self.provider, "model_name", type(self.provider).__name__)
        clean_reply = redact_sensitive(reply)
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO engagement_draft
                   (id,conversation_id,inbound_message_id,ts,body,intent,
                    commerce_relevant,status,model)
                   VALUES(?,?,?,?,?,?,?,'proposed',?)""",
                (
                    did, inbound["conversation_id"], inbound_message_id, ts,
                    clean_reply, intent, 1 if commerce else 0, model,
                ),
            )
            self.store._event("engagement_reply_drafted", {
                "draft_id": did,
                "conversation_id": inbound["conversation_id"],
                "inbound_message_id": inbound_message_id,
                "persona_id": persona["id"],
                "intent": intent,
                "commerce_relevant": commerce,
                "handoff_reason": handoff_reason or None,
                "retrieval": citations,
                "model": model,
            })
        return {
            "draft_id": did,
            "conversation_id": inbound["conversation_id"],
            "inbound_message_id": inbound_message_id,
            "reply": clean_reply,
            "intent": intent,
            "commerce_relevant": commerce,
            "handoff_reason": handoff_reason or None,
            "status": "proposed",
            "requires_human_review": True,
            "retrieval": citations,
            "model": model,
        }

    def review_draft(self, draft_id: str, decision: str,
                     reviewer: str, note: str = "") -> dict:
        if decision not in ("approved", "rejected", "revise"):
            raise ValueError("invalid engagement review decision")
        if not reviewer.strip():
            raise ValueError("reviewer is required")
        row = self.store.db.execute(
            "SELECT * FROM engagement_draft WHERE id=?",
            (draft_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown engagement draft")
        if row["status"] != "proposed":
            raise ValueError("engagement draft already reviewed")
        with self.store.db:
            self.store.db.execute(
                """UPDATE engagement_draft
                   SET status=?,reviewer=?,note=? WHERE id=?""",
                (decision, reviewer.strip(), note.strip(), draft_id),
            )
            self.store._event("engagement_draft_reviewed", {
                "draft_id": draft_id,
                "decision": decision,
                "reviewer": reviewer.strip(),
                "note": note.strip(),
            })
        updated = self.store.db.execute(
            "SELECT * FROM engagement_draft WHERE id=?",
            (draft_id,),
        ).fetchone()
        return dict(updated)

    def approved_outbox(self, limit: int = 50) -> list[dict]:
        rows = self.store.db.execute(
            """SELECT d.*, c.channel, c.external_conversation_id
               FROM engagement_draft d
               JOIN engagement_conversation c ON c.id=d.conversation_id
               WHERE d.status='approved'
               ORDER BY d.ts LIMIT ?""",
            (max(1, limit),),
        ).fetchall()
        return [dict(row) for row in rows]

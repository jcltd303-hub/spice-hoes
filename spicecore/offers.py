"""Structured offers, tracked candidate links, and commerce attribution."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


OFFER_KINDS = {"affiliate", "digital_product", "brand_deal", "subscription", "other"}


class OfferRegistry:
    def __init__(self, store):
        self.store = store
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS offer (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                currency TEXT NOT NULL,
                expected_payout_cents INTEGER NOT NULL DEFAULT 0,
                variable_cost_cents INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidate_offer (
                candidate_id TEXT PRIMARY KEY,
                offer_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                tracking_token TEXT NOT NULL UNIQUE,
                destination_url TEXT NOT NULL,
                tracked_url TEXT NOT NULL,
                FOREIGN KEY(offer_id) REFERENCES offer(id)
            );
            """
        )
        self.store.db.commit()

    def create(self, name: str, kind: str, expected_payout_cents: int = 0,
               variable_cost_cents: int = 0, currency: str = "USD",
               metadata: dict | None = None) -> dict:
        if not name.strip() or kind not in OFFER_KINDS:
            raise ValueError("valid offer name and kind are required")
        if expected_payout_cents < 0 or variable_cost_cents < 0:
            raise ValueError("offer economics cannot be negative")
        if currency.upper() != "USD":
            raise ValueError("current ledger supports USD only")
        oid = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        item = {
            "id": oid,
            "ts": ts,
            "name": name.strip(),
            "kind": kind,
            "currency": "USD",
            "expected_payout_cents": int(expected_payout_cents),
            "variable_cost_cents": int(variable_cost_cents),
            "active": True,
            "metadata": metadata or {},
        }
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO offer
                   (id,ts,name,kind,currency,expected_payout_cents,
                    variable_cost_cents,active,metadata_json)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    oid, ts, item["name"], kind, "USD",
                    item["expected_payout_cents"], item["variable_cost_cents"],
                    1, json.dumps(item["metadata"], sort_keys=True),
                ),
            )
            self.store._event("offer_created", {
                "offer_id": oid,
                "name": item["name"],
                "kind": kind,
                "expected_payout_cents": item["expected_payout_cents"],
                "variable_cost_cents": item["variable_cost_cents"],
            })
        return item

    def get(self, offer_id: str) -> dict:
        row = self.store.db.execute(
            "SELECT * FROM offer WHERE id=?", (offer_id,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown offer")
        return {
            **dict(row),
            "active": bool(row["active"]),
            "metadata": json.loads(row["metadata_json"]),
        }

    def set_active(self, offer_id: str, active: bool) -> dict:
        self.get(offer_id)
        with self.store.db:
            self.store.db.execute(
                "UPDATE offer SET active=? WHERE id=?",
                (1 if active else 0, offer_id),
            )
            self.store._event("offer_status_changed", {
                "offer_id": offer_id,
                "active": bool(active),
            })
        return self.get(offer_id)

    @staticmethod
    def _tracking_url(destination_url: str, token: str) -> str:
        parsed = urlsplit(destination_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("destination_url must be an absolute http(s) URL")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["spice_ref"] = token
        return urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        ))

    def register_candidate(self, candidate_id: str, offer_id: str,
                           destination_url: str) -> dict:
        candidate = self.store.candidate(candidate_id)
        offer = self.get(offer_id)
        if not offer["active"]:
            raise ValueError("cannot register an inactive offer")

        existing = self.store.db.execute(
            "SELECT * FROM candidate_offer WHERE candidate_id=?",
            (candidate_id,),
        ).fetchone()
        if existing:
            if existing["offer_id"] != offer_id:
                raise ValueError("candidate already linked to another offer")
            return dict(existing)

        token = secrets.token_urlsafe(18)
        tracked_url = self._tracking_url(destination_url, token)
        ts = datetime.now(timezone.utc).isoformat()
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO candidate_offer
                   (candidate_id,offer_id,ts,tracking_token,destination_url,tracked_url)
                   VALUES(?,?,?,?,?,?)""",
                (
                    candidate_id, offer_id, ts, token,
                    destination_url, tracked_url,
                ),
            )
            self.store._event("candidate_offer_registered", {
                "candidate_id": candidate_id,
                "persona_id": candidate["persona_id"],
                "offer_id": offer_id,
                "tracking_token": token,
            })
        return {
            "candidate_id": candidate_id,
            "offer_id": offer_id,
            "ts": ts,
            "tracking_token": token,
            "destination_url": destination_url,
            "tracked_url": tracked_url,
        }

    def resolve(self, tracking_token: str) -> dict:
        row = self.store.db.execute(
            """SELECT co.*, o.name AS offer_name, o.kind AS offer_kind,
                      o.expected_payout_cents, o.variable_cost_cents, o.active
               FROM candidate_offer co
               JOIN offer o ON o.id=co.offer_id
               WHERE co.tracking_token=?""",
            (tracking_token,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown tracking token")
        return dict(row)

    def ingest(self, tracking_token: str, kind: str, external_id: str,
               amount_cents: int | None = None) -> dict:
        if kind not in ("click", "purchase", "refund"):
            raise ValueError("unsupported commerce event")
        if not external_id.strip():
            raise ValueError("external_id is required")

        link = self.resolve(tracking_token)
        candidate_id = link["candidate_id"]
        if kind == "click":
            amount = 0
        else:
            if amount_cents is None:
                amount = int(link["expected_payout_cents"])
            else:
                amount = int(amount_cents)
            if amount <= 0:
                raise ValueError("purchase/refund amount must be positive")

        event = self.store.record_outcome(
            candidate_id,
            kind,
            amount,
            external_id=f"commerce:{external_id}",
        )

        commerce_cost_event = None
        if kind == "purchase" and int(link["variable_cost_cents"]) > 0:
            commerce_cost_event = self.store.record_outcome(
                candidate_id,
                "commerce_cost",
                int(link["variable_cost_cents"]),
                external_id=f"commerce-cost:{external_id}",
            )

        payload = {
            "candidate_id": candidate_id,
            "offer_id": link["offer_id"],
            "tracking_token": tracking_token,
            "kind": kind,
            "amount_cents": amount,
            "outcome_event_id": event["id"],
            "commerce_cost_event_id": (
                commerce_cost_event["id"] if commerce_cost_event else None
            ),
        }
        audit = self.store.record_event(
            "commerce_attributed",
            payload,
            external_id=f"commerce-attribution:{external_id}",
        )
        return {**payload, "audit_event_id": audit["id"]}

    def performance(self, offer_id: str) -> dict:
        offer = self.get(offer_id)
        links = self.store.db.execute(
            "SELECT candidate_id FROM candidate_offer WHERE offer_id=?",
            (offer_id,),
        ).fetchall()
        candidate_ids = {row["candidate_id"] for row in links}
        metrics = {
            "candidates": len(candidate_ids),
            "impressions": 0,
            "clicks": 0,
            "purchases": 0,
            "revenue_cents": 0,
            "refund_cents": 0,
            "distribution_cost_cents": 0,
            "commerce_cost_cents": 0,
            "generation_cost_cents": 0,
        }
        for cid in candidate_ids:
            metrics["generation_cost_cents"] += int(
                self.store.candidate(cid)["cost_cents"]
            )

        rows = self.store.db.execute(
            """SELECT kind,payload FROM events
               WHERE kind IN ('impression','click','purchase','refund',
                              'distribution_cost','commerce_cost')"""
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            if payload.get("candidate_id") not in candidate_ids:
                continue
            kind = row["kind"]
            amount = int(payload.get("amount_cents", 0))
            if kind == "impression":
                metrics["impressions"] += 1
            elif kind == "click":
                metrics["clicks"] += 1
            elif kind == "purchase":
                metrics["purchases"] += 1
                metrics["revenue_cents"] += amount
            elif kind == "refund":
                metrics["refund_cents"] += amount
            elif kind == "distribution_cost":
                metrics["distribution_cost_cents"] += amount
            elif kind == "commerce_cost":
                metrics["commerce_cost_cents"] += amount

        metrics["net_cents"] = (
            metrics["revenue_cents"]
            - metrics["refund_cents"]
            - metrics["distribution_cost_cents"]
            - metrics["commerce_cost_cents"]
            - metrics["generation_cost_cents"]
        )
        metrics["click_rate"] = (
            round(metrics["clicks"] / metrics["impressions"], 6)
            if metrics["impressions"] else None
        )
        metrics["purchase_rate_per_click"] = (
            round(metrics["purchases"] / metrics["clicks"], 6)
            if metrics["clicks"] else None
        )
        return {
            "offer_id": offer_id,
            "name": offer["name"],
            "kind": offer["kind"],
            "currency": offer["currency"],
            "expected_unit_margin_cents": (
                int(offer["expected_payout_cents"])
                - int(offer["variable_cost_cents"])
            ),
            **metrics,
        }

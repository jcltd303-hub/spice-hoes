"""Verified Stripe receipts and a durable, customer-free USD commerce ledger.

Signature and event semantics follow https://docs.stripe.com/webhooks and
https://docs.stripe.com/api/refunds/object. No provider API calls are made.
Only signed, live, paid Checkout receipts can create purchase outcomes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .offers import OfferRegistry


CHECKOUT_EVENTS = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
REFUND_EVENTS = {"refund.created", "refund.updated", "charge.refund.updated", "refund.failed"}
CHARGE_EVENTS = {"charge.succeeded", "charge.updated", "charge.refunded"}
DISPUTE_EVENTS = {"charge.dispute.created", "charge.dispute.updated", "charge.dispute.closed",
                  "charge.dispute.funds_withdrawn", "charge.dispute.funds_reinstated"}
PAYOUT_EVENTS = {"payout.paid", "payout.failed", "payout.canceled"}
_MAX_CENTS = 10 ** 12


def _now():
    return datetime.now(timezone.utc).isoformat()


def _amount(value, field, *, signed=False):
    if type(value) is not int or abs(value) > _MAX_CENTS or (not signed and value < 0):
        raise ValueError(f"{field} must be an integer USD amount")
    return value


def _id(value, prefix, *, required=False):
    if isinstance(value, dict):
        value = value.get("id")
    if value is None and not required:
        return None
    if not isinstance(value, str) or not re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_]{1,200}", value):
        raise ValueError("invalid Stripe object identifier")
    return value


def _usd(obj):
    if not isinstance(obj.get("currency"), str) or obj["currency"].lower() != "usd":
        raise ValueError("commerce ledger supports USD only")
    return "USD"


def _references(obj):
    """Unknown references might be customer IDs or emails: retain only hashes."""
    metadata = obj.get("metadata") or {}
    refs = [obj.get("client_reference_id")]
    if isinstance(metadata, dict):
        refs.append(metadata.get("spice_ref"))
    return sorted({hashlib.sha256(ref.encode()).hexdigest() for ref in refs
                   if isinstance(ref, str) and ref and len(ref) <= 1024})


def _fees(obj):
    found = []
    values = [obj.get("balance_transaction")]
    if isinstance(obj.get("balance_transactions"), list):
        values.extend(obj["balance_transactions"])
    for value in values:
        if not isinstance(value, dict):
            continue  # A transaction ID alone says nothing about the actual fee.
        found.append({"id": _id(value.get("id"), "txn_", required=True),
                      "currency": _usd(value),
                      "fee_cents": _amount(value.get("fee"), "fee", signed=True)})
    return found


class StripeCommerce:
    def __init__(self, store, signing_secret: str, live_mode: bool = True,
                 *, tolerance_seconds: int = 300):
        if not isinstance(signing_secret, str) or not signing_secret.strip():
            raise ValueError("Stripe webhook signing secret is required")
        if type(live_mode) is not bool:
            raise ValueError("live_mode must be boolean")
        if type(tolerance_seconds) is not int or not 1 <= tolerance_seconds <= 300:
            raise ValueError("signature tolerance must be between 1 and 300 seconds")
        self.store = store
        self.signing_secret = signing_secret.encode()
        self.live_mode = live_mode
        self.tolerance_seconds = tolerance_seconds
        if self.store.db.in_transaction:
            raise RuntimeError("commerce initialization requires a committed Store")
        OfferRegistry(store)
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.executescript("""
            CREATE TABLE IF NOT EXISTS stripe_webhook (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                event_id TEXT NOT NULL,
                raw_sha256 TEXT NOT NULL,
                event_type TEXT NOT NULL,
                livemode INTEGER NOT NULL,
                received_at TEXT NOT NULL,
                normalized_json TEXT NOT NULL,
                state TEXT NOT NULL,
                reason TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                result_json TEXT NOT NULL,
                UNIQUE(provider,event_id)
            );
            CREATE TABLE IF NOT EXISTS stripe_transaction (
                provider TEXT NOT NULL,
                session_id TEXT NOT NULL,
                payment_intent TEXT,
                currency TEXT NOT NULL,
                gross_cents INTEGER NOT NULL,
                refund_cents INTEGER NOT NULL DEFAULT 0,
                recorded_refund_cents INTEGER NOT NULL DEFAULT 0,
                candidate_id TEXT,
                persona_id TEXT,
                offer_id TEXT,
                unit_cost_basis_cents INTEGER NOT NULL DEFAULT 0,
                purchase_event_id TEXT,
                source_event_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(provider,session_id),
                UNIQUE(provider,payment_intent)
            );
            CREATE TABLE IF NOT EXISTS stripe_charge (
                provider TEXT NOT NULL,
                charge_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                cumulative_refund_cents INTEGER NOT NULL DEFAULT 0,
                refund_snapshot_complete INTEGER NOT NULL DEFAULT 0,
                refund_snapshot_ids_json TEXT NOT NULL DEFAULT '[]',
                fee_known INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(provider,charge_id)
            );
            CREATE TABLE IF NOT EXISTS stripe_refund (
                provider TEXT NOT NULL,
                refund_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                charge_id TEXT,
                amount_cents INTEGER NOT NULL,
                status TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                PRIMARY KEY(provider,refund_id)
            );
            CREATE TABLE IF NOT EXISTS stripe_fee (
                provider TEXT NOT NULL,
                balance_transaction_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                PRIMARY KEY(provider,balance_transaction_id)
            );
            CREATE TABLE IF NOT EXISTS stripe_dispute (
                provider TEXT NOT NULL,
                dispute_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                withdrawn INTEGER NOT NULL DEFAULT 0,
                reinstated INTEGER NOT NULL DEFAULT 0,
                loss_event_id TEXT,
                reversal_event_id TEXT,
                PRIMARY KEY(provider,dispute_id)
            );
            CREATE TABLE IF NOT EXISTS stripe_payout (
                provider TEXT NOT NULL,
                payout_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                source_event_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'paid',
                PRIMARY KEY(provider,payout_id)
            );
            CREATE INDEX IF NOT EXISTS stripe_pending ON stripe_webhook(state,attempts,seq);
            CREATE TABLE IF NOT EXISTS verified_money_event (
                event_id TEXT PRIMARY KEY REFERENCES events(id),
                provider TEXT NOT NULL
            );
        """)
        # Receivers and unattended cycles may start at different versions.
        additions = {
            "stripe_transaction": {"recorded_refund_cents": "INTEGER NOT NULL DEFAULT 0"},
            "stripe_dispute": {"loss_event_id": "TEXT", "reversal_event_id": "TEXT"},
            "stripe_payout": {"status": "TEXT NOT NULL DEFAULT 'paid'"},
            "stripe_charge": {"refund_snapshot_complete": "INTEGER NOT NULL DEFAULT 0",
                              "refund_snapshot_ids_json": "TEXT NOT NULL DEFAULT '[]'"},
        }
        for table, fields in additions.items():
            existing = {row["name"] for row in self.store.db.execute(f"PRAGMA table_info({table})")}
            for column, definition in fields.items():
                if column not in existing:
                    self.store.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    if column == "recorded_refund_cents":
                        self.store.db.execute("UPDATE stripe_transaction SET recorded_refund_cents=refund_cents")
        self.store.db.commit()

    @contextmanager
    def _atomic(self):
        # Store.record_event's connection context commits nested transactions.
        # Use Store._event below so a receipt, payment, and all outcomes commit together.
        db = self.store.db
        if db.in_transaction:
            raise RuntimeError("commerce ingestion requires a committed Store")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield
            db.commit()
        except BaseException:
            db.rollback()
            raise

    def _verify(self, raw_body, signature_header):
        if not isinstance(raw_body, bytes) or not isinstance(signature_header, str):
            raise PermissionError("invalid Stripe signature")
        if len(signature_header) > 8192:
            raise PermissionError("invalid Stripe signature")
        parts = [item.strip().partition("=") for item in signature_header.split(",")]
        timestamps = [value for key, sep, value in parts if key == "t" and sep]
        signatures = [value for key, sep, value in parts if key == "v1" and sep
                      and re.fullmatch(r"[a-fA-F0-9]{64}", value)]
        if len(timestamps) != 1 or not re.fullmatch(r"[0-9]{1,12}", timestamps[0]) or not signatures:
            raise PermissionError("invalid Stripe signature")
        timestamp = timestamps[0]
        expected = hmac.new(self.signing_secret, timestamp.encode("ascii") + b"." + raw_body,
                            hashlib.sha256).hexdigest()
        matches = [hmac.compare_digest(expected, sig.lower()) for sig in signatures]
        if not any(matches) or abs(time.time() - int(timestamp)) > self.tolerance_seconds:
            raise PermissionError("invalid or expired Stripe signature")

    def _normalize(self, item):
        if not isinstance(item, dict):
            raise ValueError("invalid Stripe event")
        eid = _id(item.get("id"), "evt_", required=True)
        kind = item.get("type")
        if not isinstance(kind, str) or not re.fullmatch(r"[a-z0-9_.]{1,150}", kind):
            raise ValueError("invalid Stripe event type")
        live = item.get("livemode")
        if type(live) is not bool:
            raise ValueError("Stripe event livemode is required")
        data = item.get("data")
        obj = data.get("object") if isinstance(data, dict) else None
        if not isinstance(obj, dict):
            raise ValueError("invalid Stripe event object")
        if "livemode" in obj and (type(obj["livemode"]) is not bool or obj["livemode"] != live):
            raise ValueError("inconsistent Stripe livemode")
        account = _id(item.get("account"), "acct_")
        normalized = {"event_id": eid, "event_type": kind, "livemode": live,
                      "provider": "stripe" + (":" + account if account else "")}
        if not live or not self.live_mode:
            return normalized
        if kind in CHECKOUT_EVENTS:
            normalized["session_id"] = _id(obj.get("id"), "cs_", required=True)
            normalized["paid"] = obj.get("payment_status") == "paid"
            if not normalized["paid"]:
                return normalized
            if obj.get("status") not in (None, "complete"):
                raise ValueError("paid Checkout Session must be complete")
            normalized.update(currency=_usd(obj), amount_cents=_amount(obj.get("amount_total"), "amount_total"),
                              references=_references(obj), payment_intent=_id(obj.get("payment_intent"), "pi_"))
            intent = obj.get("payment_intent")
            charge = intent.get("latest_charge") if isinstance(intent, dict) else None
            normalized["charge_id"] = _id(charge, "ch_")
            normalized["fees"] = _fees(charge) if isinstance(charge, dict) else []
        elif kind in CHARGE_EVENTS:
            normalized.update(charge_id=_id(obj.get("id"), "ch_", required=True),
                              payment_intent=_id(obj.get("payment_intent"), "pi_"),
                              currency=_usd(obj), fees=_fees(obj))
            if kind == "charge.refunded":
                normalized["cumulative_refund_cents"] = _amount(obj.get("amount_refunded"), "amount_refunded")
            refunds = obj.get("refunds")
            if isinstance(refunds, dict) and isinstance(refunds.get("data"), list):
                normalized["refunds"] = [self._refund(refund) for refund in refunds["data"]]
                normalized["refund_snapshot_complete"] = refunds.get("has_more") is False
        elif kind in REFUND_EVENTS:
            normalized.update(self._refund(obj))
        elif kind in DISPUTE_EVENTS:
            normalized.update(dispute_id=_id(obj.get("id"), "dp_", required=True),
                              charge_id=_id(obj.get("charge"), "ch_"),
                              payment_intent=_id(obj.get("payment_intent"), "pi_"), currency=_usd(obj),
                              amount_cents=_amount(obj.get("amount"), "amount"), fees=_fees(obj))
            normalized["status"] = obj.get("status") if obj.get("status") in (
                "warning_needs_response", "warning_under_review", "warning_closed", "needs_response",
                "under_review", "won", "lost") else None
        elif kind == "payment_intent.succeeded":
            charge = obj.get("latest_charge")
            normalized.update(payment_intent=_id(obj.get("id"), "pi_", required=True),
                              charge_id=_id(charge, "ch_"), currency=_usd(obj),
                              fees=_fees(charge) if isinstance(charge, dict) else [])
        elif kind in PAYOUT_EVENTS:
            if obj.get("status") not in ("paid", "failed", "canceled"):
                raise ValueError("Stripe payout status is required")
            normalized.update(payout_id=_id(obj.get("id"), "po_", required=True), currency=_usd(obj),
                              amount_cents=_amount(obj.get("amount"), "amount"), status=obj["status"])
        return normalized

    def _refund(self, obj):
        if not isinstance(obj, dict):
            raise ValueError("invalid Stripe refund")
        status = obj.get("status")
        if status not in ("pending", "requires_action", "succeeded", "failed", "canceled"):
            raise ValueError("Stripe refund status is required")
        return {"refund_id": _id(obj.get("id"), "re_", required=True),
                "charge_id": _id(obj.get("charge"), "ch_"),
                "payment_intent": _id(obj.get("payment_intent"), "pi_"), "currency": _usd(obj),
                "amount_cents": _amount(obj.get("amount"), "amount"), "status": status, "fees": _fees(obj)}

    def _local_event(self, kind, payload, external_id):
        old = self.store.db.execute("SELECT * FROM events WHERE external_id=?", (external_id,)).fetchone()
        if old:
            if old["kind"] != kind or json.loads(old["payload"]) != payload:
                raise ValueError("Stripe outcome identifier conflict")
            return {"id": old["id"], "payload": payload}
        return self.store._event(kind, payload, external_id)

    def _outcome(self, candidate_id, kind, amount_cents, external_id):
        current = self.store.candidate(candidate_id)
        if current["status"] != "published":
            raise ValueError("Outcomes require published candidates")
        if type(amount_cents) is not int or amount_cents <= 0:
            raise ValueError("Monetary outcome requires a positive integer amount")
        event = self._local_event(kind, {"candidate_id": candidate_id, "persona_id": current["persona_id"],
                                        "amount_cents": amount_cents}, external_id)
        # This private path runs only while processing already authenticated,
        # durable live Stripe evidence. Public Store.record_outcome has no such flag.
        old = self.store.db.execute("SELECT provider FROM verified_money_event WHERE event_id=?",
                                    (event["id"],)).fetchone()
        if old and old["provider"] != "stripe":
            raise ValueError("verified monetary provider conflict")
        self.store.db.execute("INSERT OR IGNORE INTO verified_money_event(event_id,provider) VALUES(?,?)",
                              (event["id"], "stripe"))
        return event

    def _resolve(self, hashes):
        links = self.store.db.execute("""SELECT co.candidate_id,co.offer_id,co.tracking_token,
                o.variable_cost_cents,c.persona_id,c.status FROM candidate_offer co
                JOIN offer o ON o.id=co.offer_id JOIN candidates c ON c.id=co.candidate_id""").fetchall()
        matches = {row["candidate_id"]: row for row in links
                   if hashlib.sha256(row["tracking_token"].encode()).hexdigest() in hashes}
        if len(matches) > 1:
            raise ValueError("Stripe tracking references resolve to different candidates")
        return next(iter(matches.values()), None)

    def _transaction(self, provider, session_id):
        return self.store.db.execute("SELECT * FROM stripe_transaction WHERE provider=? AND session_id=?",
                                     (provider, session_id)).fetchone()

    def _match(self, obj):
        db, provider = self.store.db, obj["provider"]
        matches = []
        if obj.get("payment_intent"):
            match = db.execute("SELECT * FROM stripe_transaction WHERE provider=? AND payment_intent=?",
                               (provider, obj["payment_intent"])).fetchone()
            if match:
                matches.append(match)
        if obj.get("charge_id"):
            match = db.execute("""SELECT t.* FROM stripe_transaction t JOIN stripe_charge c
                ON t.provider=c.provider AND t.session_id=c.session_id WHERE c.provider=? AND c.charge_id=?""",
                               (provider, obj["charge_id"])).fetchone()
            if match:
                matches.append(match)
        if len({match["session_id"] for match in matches}) > 1:
            raise ValueError("conflicting Stripe payment identifiers")
        return matches[0] if matches else None

    def _link_charge(self, provider, charge_id, session_id):
        if not charge_id:
            return
        old = self.store.db.execute("SELECT session_id FROM stripe_charge WHERE provider=? AND charge_id=?",
                                     (provider, charge_id)).fetchone()
        if old and old["session_id"] != session_id:
            raise ValueError("Stripe Charge already belongs to another Checkout Session")
        self.store.db.execute("INSERT OR IGNORE INTO stripe_charge(provider,charge_id,session_id) VALUES(?,?,?)",
                              (provider, charge_id, session_id))

    def _store_fees(self, obj, transaction, source_kind):
        db = self.store.db
        for fee in obj.get("fees", []):
            old = db.execute("SELECT * FROM stripe_fee WHERE provider=? AND balance_transaction_id=?",
                             (obj["provider"], fee["id"])).fetchone()
            if old and (old["session_id"] != transaction["session_id"] or old["amount_cents"] != fee["fee_cents"]):
                raise ValueError("Stripe balance transaction fee conflict")
            db.execute("""INSERT OR IGNORE INTO stripe_fee(provider,balance_transaction_id,session_id,
                    amount_cents,source_kind,source_event_id) VALUES(?,?,?,?,?,?)""",
                       (obj["provider"], fee["id"], transaction["session_id"], fee["fee_cents"],
                        source_kind, obj["event_id"]))
        if source_kind == "charge" and obj.get("charge_id") and obj.get("fees"):
            db.execute("UPDATE stripe_charge SET fee_known=1 WHERE provider=? AND charge_id=?",
                       (obj["provider"], obj["charge_id"]))

    def _store_refund(self, obj, transaction):
        db = self.store.db
        old = db.execute("SELECT * FROM stripe_refund WHERE provider=? AND refund_id=?",
                         (obj["provider"], obj["refund_id"])).fetchone()
        if old and (old["session_id"] != transaction["session_id"] or old["amount_cents"] != obj["amount_cents"]
                    or (old["charge_id"] and obj.get("charge_id") and old["charge_id"] != obj["charge_id"])):
            raise ValueError("Stripe refund identifier conflict")
        status = obj["status"]
        if old and old["status"] in ("succeeded", "failed", "canceled") and status in ("pending", "requires_action"):
            status = old["status"]
        if old and old["status"] == "succeeded":
            status = "succeeded"
        db.execute("""INSERT INTO stripe_refund(provider,refund_id,session_id,charge_id,amount_cents,status,source_event_id)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(provider,refund_id) DO UPDATE SET status=excluded.status,
            charge_id=COALESCE(stripe_refund.charge_id,excluded.charge_id)""",
                   (obj["provider"], obj["refund_id"], transaction["session_id"], obj.get("charge_id"),
                    obj["amount_cents"], status, obj["event_id"]))
        self._link_charge(obj["provider"], obj.get("charge_id"), transaction["session_id"])
        if status == "succeeded":
            self._store_fees(obj, transaction, "refund")
        return status

    def _refund_total(self, provider, session_id):
        db = self.store.db
        grouped = {}
        charges = db.execute("SELECT * FROM stripe_charge WHERE provider=? AND session_id=?",
                             (provider, session_id)).fetchall()
        for charge in charges:
            grouped[charge["charge_id"]] = {"cumulative": charge["cumulative_refund_cents"],
                "complete": bool(charge["refund_snapshot_complete"]),
                "included": set(json.loads(charge["refund_snapshot_ids_json"])), "refunds": {}}
        refunds = db.execute("""SELECT refund_id,charge_id,amount_cents FROM stripe_refund
            WHERE provider=? AND session_id=? AND status='succeeded'""",
                             (provider, session_id)).fetchall()
        unidentified = 0
        for refund in refunds:
            if refund["charge_id"]:
                group = grouped.setdefault(refund["charge_id"], {"cumulative": 0,
                    "complete": False, "included": set(), "refunds": {}})
                group["refunds"][refund["refund_id"]] = refund["amount_cents"]
            else:
                unidentified += refund["amount_cents"]
        total = known = 0
        incomplete = False
        for group in grouped.values():
            listed = sum(group["refunds"].values())
            known += listed
            if group["complete"]:
                # A complete signed snapshot identifies exactly which refunds overlap.
                total += group["cumulative"] + sum(amount for rid, amount in group["refunds"].items()
                                                    if rid not in group["included"])
            else:
                total += max(group["cumulative"], listed)
                incomplete |= group["cumulative"] > 0 and listed > 0
        incomplete |= unidentified > 0 and any(group["cumulative"] for group in grouped.values())
        return max(total, known + unidentified), incomplete

    def _reconcile(self, provider, session_id):
        db = self.store.db
        tx = self._transaction(provider, session_id)
        refund_total, incomplete = self._refund_total(provider, session_id)
        if refund_total > tx["gross_cents"]:
            raise ValueError("verified refunds exceed Checkout payment")
        db.execute("UPDATE stripe_transaction SET refund_cents=? WHERE provider=? AND session_id=?",
                   (refund_total, provider, session_id))
        if not tx["purchase_event_id"]:
            return incomplete
        delta = refund_total - tx["recorded_refund_cents"]
        if delta > 0:
            self._outcome(tx["candidate_id"], "refund", delta,
                          f"stripe:{provider}:refund-total:{session_id}:{refund_total}")
            db.execute("UPDATE stripe_transaction SET recorded_refund_cents=? WHERE provider=? AND session_id=?",
                       (refund_total, provider, session_id))
        for fee in db.execute("SELECT * FROM stripe_fee WHERE provider=? AND session_id=?", (provider, session_id)):
            if fee["amount_cents"] != 0:
                self._outcome(tx["candidate_id"], "commerce_cost" if fee["amount_cents"] > 0 else "commerce_cost_reversal",
                              abs(fee["amount_cents"]),
                              f"stripe:{provider}:fee:{fee['balance_transaction_id']}")
        for dispute in db.execute("SELECT * FROM stripe_dispute WHERE provider=? AND session_id=?",
                                  (provider, session_id)).fetchall():
            if not dispute["withdrawn"] or dispute["amount_cents"] == 0:
                continue
            if not dispute["loss_event_id"]:
                loss = self._outcome(tx["candidate_id"], "chargeback", dispute["amount_cents"],
                                     f"stripe:{provider}:chargeback:{dispute['dispute_id']}")
                db.execute("UPDATE stripe_dispute SET loss_event_id=? WHERE provider=? AND dispute_id=?",
                           (loss["id"], provider, dispute["dispute_id"]))
            if dispute["reinstated"] and not dispute["reversal_event_id"]:
                credit = self._outcome(tx["candidate_id"], "chargeback_reversal", dispute["amount_cents"],
                                       f"stripe:{provider}:chargeback-reversal:{dispute['dispute_id']}")
                db.execute("UPDATE stripe_dispute SET reversal_event_id=? WHERE provider=? AND dispute_id=?",
                           (credit["id"], provider, dispute["dispute_id"]))
        return incomplete

    def _process(self, obj):
        db, kind, provider = self.store.db, obj["event_type"], obj["provider"]
        result = {"event_id": obj["event_id"], "state": "processed", "provider": provider}
        if not obj["livemode"]:
            return {**result, "state": "test", "reason": "signed_test_event"}
        if not self.live_mode:
            return {**result, "state": "ignored", "reason": "live_event_on_test_endpoint"}
        if kind in CHECKOUT_EVENTS:
            if not obj["paid"] or obj["amount_cents"] == 0:
                return {**result, "state": "ignored", "reason": "checkout_not_paid"}
            session = obj["session_id"]
            tx = self._transaction(provider, session)
            if tx and (tx["gross_cents"] != obj["amount_cents"] or tx["currency"] != obj["currency"]
                       or (tx["payment_intent"] and obj["payment_intent"] and tx["payment_intent"] != obj["payment_intent"])):
                raise ValueError("Checkout Session payment details conflict")
            if obj["payment_intent"]:
                other = db.execute("SELECT session_id FROM stripe_transaction WHERE provider=? AND payment_intent=?",
                                   (provider, obj["payment_intent"])).fetchone()
                if other and other["session_id"] != session:
                    raise ValueError("PaymentIntent already belongs to another Checkout Session")
            if not tx:
                db.execute("""INSERT INTO stripe_transaction(provider,session_id,payment_intent,currency,
                    gross_cents,source_event_id,created_at) VALUES(?,?,?,?,?,?,?)""",
                           (provider, session, obj["payment_intent"], "USD", obj["amount_cents"], obj["event_id"], _now()))
            elif not tx["payment_intent"] and obj["payment_intent"]:
                db.execute("UPDATE stripe_transaction SET payment_intent=? WHERE provider=? AND session_id=?",
                           (obj["payment_intent"], provider, session))
            self._link_charge(provider, obj.get("charge_id"), session)
            tx = self._transaction(provider, session)
            self._store_fees(obj, tx, "charge")
            link = self._resolve(obj.get("references", []))
            if link and tx["candidate_id"] and tx["candidate_id"] != link["candidate_id"]:
                raise ValueError("Checkout Session attribution conflict")
            if not tx["purchase_event_id"]:
                if not link or link["status"] != "published":
                    return {**result, "state": "pending", "session_id": session,
                            "reason": "unknown_tracking_reference" if not link else "candidate_not_published"}
                cost = _amount(link["variable_cost_cents"], "variable_cost_cents")
                purchase = self._outcome(link["candidate_id"], "purchase", obj["amount_cents"],
                                         f"stripe:{provider}:purchase:{session}")
                if cost:
                    self._outcome(link["candidate_id"], "commerce_cost", cost,
                                  f"stripe:{provider}:unit-cost:{session}")
                db.execute("""UPDATE stripe_transaction SET candidate_id=?,persona_id=?,offer_id=?,
                    unit_cost_basis_cents=?,purchase_event_id=? WHERE provider=? AND session_id=?""",
                           (link["candidate_id"], link["persona_id"], link["offer_id"], cost, purchase["id"], provider, session))
                self._local_event("stripe_commerce_attributed", {
                    "provider": provider, "session_id": session, "payment_intent": obj["payment_intent"],
                    "candidate_id": link["candidate_id"], "offer_id": link["offer_id"],
                    "amount_cents": obj["amount_cents"], "currency": "USD", "livemode": True,
                    "source_event_id": obj["event_id"], "outcome_event_id": purchase["id"]},
                    f"stripe:{provider}:attribution:{session}")
            self._reconcile(provider, session)
            tx = self._transaction(provider, session)
            return {**result, "session_id": session, "candidate_id": tx["candidate_id"],
                    "amount_cents": tx["gross_cents"], "currency": "USD"}
        if kind in PAYOUT_EVENTS:
            expected_status = kind.split(".")[-1]
            if obj["status"] != expected_status:
                return {**result, "state": "ignored", "reason": "payout_not_paid"}
            old = db.execute("SELECT * FROM stripe_payout WHERE provider=? AND payout_id=?",
                             (provider, obj["payout_id"])).fetchone()
            if old and old["amount_cents"] != obj["amount_cents"]:
                raise ValueError("Stripe payout identifier conflict")
            db.execute("""INSERT INTO stripe_payout(provider,payout_id,amount_cents,source_event_id,status)
                VALUES(?,?,?,?,?) ON CONFLICT(provider,payout_id) DO UPDATE SET
                status=CASE WHEN stripe_payout.status IN ('failed','canceled') THEN stripe_payout.status
                ELSE excluded.status END""",
                       (provider, obj["payout_id"], obj["amount_cents"], obj["event_id"], obj["status"]))
            return result
        if kind not in CHARGE_EVENTS | REFUND_EVENTS | DISPUTE_EVENTS | {"payment_intent.succeeded"}:
            return {**result, "state": "ignored", "reason": "unsupported_event"}
        tx = self._match(obj)
        if not tx:
            return {**result, "state": "pending", "reason": "unmatched_payment"}
        session = tx["session_id"]
        result["session_id"] = session
        self._link_charge(provider, obj.get("charge_id"), session)
        if kind in CHARGE_EVENTS | {"payment_intent.succeeded"}:
            self._store_fees(obj, tx, "charge")
            if "cumulative_refund_cents" in obj:
                charge = db.execute("SELECT * FROM stripe_charge WHERE provider=? AND charge_id=?",
                                    (provider, obj["charge_id"])).fetchone()
                if obj["cumulative_refund_cents"] >= charge["cumulative_refund_cents"]:
                    successful = [refund for refund in obj.get("refunds", []) if refund["status"] == "succeeded"]
                    complete = bool(obj.get("refund_snapshot_complete")) and (
                        sum(refund["amount_cents"] for refund in successful) == obj["cumulative_refund_cents"])
                    # Do not discard a complete snapshot for an identical duplicate total.
                    if obj["cumulative_refund_cents"] > charge["cumulative_refund_cents"] or complete:
                        db.execute("""UPDATE stripe_charge SET cumulative_refund_cents=?,refund_snapshot_complete=?,
                            refund_snapshot_ids_json=? WHERE provider=? AND charge_id=?""",
                            (obj["cumulative_refund_cents"], int(complete),
                             json.dumps(sorted({refund["refund_id"] for refund in successful}) if complete else []),
                             provider, obj["charge_id"]))
            for refund in obj.get("refunds", []):
                self._store_refund({**refund, "provider": provider, "event_id": obj["event_id"],
                                    "charge_id": refund.get("charge_id") or obj["charge_id"]}, tx)
        elif kind in REFUND_EVENTS:
            status = self._store_refund(obj, tx)
            if status in ("pending", "requires_action"):
                return {**result, "state": "pending", "reason": "refund_not_succeeded"}
            if status in ("failed", "canceled"):
                return {**result, "state": "ignored", "reason": "refund_not_succeeded"}
        else:
            old = db.execute("SELECT * FROM stripe_dispute WHERE provider=? AND dispute_id=?",
                             (provider, obj["dispute_id"])).fetchone()
            if old and (old["session_id"] != session or old["amount_cents"] != obj["amount_cents"]):
                raise ValueError("Stripe dispute identifier conflict")
            withdrawn = kind == "charge.dispute.funds_withdrawn" or (kind == "charge.dispute.closed" and obj["status"] == "lost")
            reinstated = kind == "charge.dispute.funds_reinstated"
            db.execute("""INSERT INTO stripe_dispute(provider,dispute_id,session_id,amount_cents,withdrawn,reinstated)
                VALUES(?,?,?,?,?,?) ON CONFLICT(provider,dispute_id)
                DO UPDATE SET withdrawn=MAX(stripe_dispute.withdrawn,excluded.withdrawn),
                reinstated=MAX(stripe_dispute.reinstated,excluded.reinstated)""",
                       (provider, obj["dispute_id"], session, obj["amount_cents"], int(withdrawn), int(reinstated)))
            self._store_fees(obj, tx, "dispute")
            self._local_event("stripe_dispute_verified", {"provider": provider, "session_id": session,
                "dispute_id": obj["dispute_id"], "source_event_id": obj["event_id"],
                "amount_cents": obj["amount_cents"], "funds_withdrawn": withdrawn, "funds_reinstated": reinstated},
                f"stripe:{provider}:dispute-event:{obj['event_id']}")
        incomplete = self._reconcile(provider, session)
        if not tx["purchase_event_id"]:
            return {**result, "state": "pending", "reason": "payment_not_attributed"}
        if incomplete and kind in CHARGE_EVENTS | REFUND_EVENTS:
            return {**result, "state": "pending", "reason": "refund_reconciliation_incomplete"}
        return result

    def _save_result(self, obj, result):
        self.store.db.execute("""UPDATE stripe_webhook SET state=?,reason=?,result_json=?,attempts=attempts+1
            WHERE provider=? AND event_id=?""", (result["state"], result.get("reason"),
                json.dumps(result, sort_keys=True), obj["provider"], obj["event_id"]))

    def ingest(self, raw_body: bytes, signature_header: str) -> dict:
        self._verify(raw_body, signature_header)
        try:
            item = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError, RecursionError) as error:
            raise ValueError("invalid Stripe JSON body") from error
        obj = self._normalize(item)
        digest = hashlib.sha256(raw_body).hexdigest()
        with self._atomic():
            old = self.store.db.execute("SELECT * FROM stripe_webhook WHERE provider=? AND event_id=?",
                                       (obj["provider"], obj["event_id"])).fetchone()
            if old:
                if old["raw_sha256"] != digest:
                    raise ValueError("Stripe event ID reused with different payload")
                if old["state"] == "pending":
                    result = self._process(json.loads(old["normalized_json"]))
                    self._save_result(obj, result)
                else:
                    result = json.loads(old["result_json"])
                return {**result, "duplicate": True}
            self.store.db.execute("""INSERT INTO stripe_webhook(provider,event_id,raw_sha256,event_type,
                livemode,received_at,normalized_json,state,result_json) VALUES(?,?,?,?,?,?,?,?,?)""",
                (obj["provider"], obj["event_id"], digest, obj["event_type"], int(obj["livemode"]), _now(),
                 json.dumps(obj, sort_keys=True), "pending", "{}"))
            self._local_event("stripe_webhook_verified", {"provider": obj["provider"], "event_id": obj["event_id"],
                "event_type": obj["event_type"], "livemode": obj["livemode"]},
                f"stripe:{obj['provider']}:webhook:{obj['event_id']}")
            result = self._process(obj)
            self._save_result(obj, result)
            return {**result, "duplicate": False}

    def retry_pending(self, limit: int = 100) -> dict:
        """Retry previously verified durable evidence, with bounded fair scheduling."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("pending retry limit must be between 1 and 1000")
        rows = self.store.db.execute("""SELECT provider,event_id FROM stripe_webhook WHERE state='pending'
            ORDER BY attempts,seq LIMIT ?""", (limit,)).fetchall()
        resolved = failed = 0
        for row in rows:
            try:
                with self._atomic():
                    current = self.store.db.execute("SELECT * FROM stripe_webhook WHERE provider=? AND event_id=?",
                                                    (row["provider"], row["event_id"])).fetchone()
                    if current["state"] != "pending":
                        continue
                    obj = json.loads(current["normalized_json"])
                    result = self._process(obj)
                    self._save_result(obj, result)
                    resolved += result["state"] != "pending"
            except Exception:
                # Retain the verified receipt and rotate it behind untried work.
                # Exception text can contain secrets or customer data: do not persist it.
                failed += 1
                with self._atomic():
                    self.store.db.execute("""UPDATE stripe_webhook SET attempts=attempts+1,reason='processing_failed'
                        WHERE provider=? AND event_id=?""", (row["provider"], row["event_id"]))
        remaining = self.store.db.execute("SELECT COUNT(*) FROM stripe_webhook WHERE state='pending'").fetchone()[0]
        return {"processed": len(rows), "resolved": resolved, "failed": failed, "remaining": remaining}

    def verified_totals(self, candidate_ids=None) -> dict:
        """Read signed live money only; optionally scope it to known candidates.

        Manual and estimated Store outcomes never enter these totals. An empty
        candidate collection selects nothing; None includes unattributed receipts.
        All returned amounts are integer USD cents. Configured unit cost remains
        a cost basis, distinct from provider-verified fees.
        """
        if candidate_ids is not None:
            if isinstance(candidate_ids, (str, bytes)):
                raise ValueError("candidate_ids must be a collection of strings")
            selected = set(candidate_ids)
            if any(not isinstance(cid, str) or not cid for cid in selected):
                raise ValueError("candidate_ids must contain candidate identifiers")
        else:
            selected = None
        db = self.store.db
        txs = [tx for tx in db.execute("SELECT * FROM stripe_transaction")
               if selected is None or tx["candidate_id"] in selected]
        totals = {"currency": "USD", "transactions": len(txs),
                  "attributed_transactions": sum(bool(tx["purchase_event_id"]) for tx in txs),
                  "verified_gross_cents": sum(tx["gross_cents"] for tx in txs),
                  "attributed_gross_cents": sum(tx["gross_cents"] for tx in txs if tx["purchase_event_id"]),
                  "verified_refund_cents": sum(tx["refund_cents"] for tx in txs),
                  "verified_chargeback_cents": 0, "known_fee_cents": 0,
                  "configured_unit_cost_basis_cents": sum(tx["unit_cost_basis_cents"] for tx in txs),
                  "unknown_unit_cost_transactions": sum(not bool(tx["purchase_event_id"]) for tx in txs),
                  "unknown_fee_transactions": 0, "refund_reconciliation_incomplete_transactions": 0}
        for tx in txs:
            key = (tx["provider"], tx["session_id"])
            totals["known_fee_cents"] += db.execute("""SELECT COALESCE(SUM(amount_cents),0) FROM stripe_fee
                WHERE provider=? AND session_id=?""", key).fetchone()[0]
            totals["verified_chargeback_cents"] += db.execute("""SELECT COALESCE(SUM(amount_cents),0)
                FROM stripe_dispute WHERE provider=? AND session_id=? AND withdrawn=1 AND reinstated=0""",
                                                               key).fetchone()[0]
            if not db.execute("""SELECT 1 FROM stripe_fee WHERE provider=? AND session_id=?
                AND source_kind='charge' LIMIT 1""", key).fetchone():
                totals["unknown_fee_transactions"] += 1
            totals["refund_reconciliation_incomplete_transactions"] += self._refund_total(*key)[1]
        totals["unattributed_gross_cents"] = totals["verified_gross_cents"] - totals["attributed_gross_cents"]
        totals["verified_contribution_before_cost_basis_cents"] = (
            totals["verified_gross_cents"] - totals["verified_refund_cents"]
            - totals["verified_chargeback_cents"] - totals["known_fee_cents"])
        return totals

    def status(self) -> dict:
        db = self.store.db
        counts = {row["state"]: row["total"] for row in db.execute(
            "SELECT state,COUNT(*) AS total FROM stripe_webhook GROUP BY state")}
        txs = db.execute("SELECT * FROM stripe_transaction").fetchall()
        candidates = {tx["candidate_id"] for tx in txs if tx["purchase_event_id"]}
        money = self.verified_totals()
        unit_cost = money["configured_unit_cost_basis_cents"]
        attributed_generation = sum(self.store.candidate(cid)["cost_cents"] for cid in candidates)
        generation = db.execute("SELECT COALESCE(SUM(cost_cents),0) FROM candidates").fetchone()[0]
        distribution = attributed_distribution = 0
        for row in db.execute("SELECT payload FROM events WHERE kind='distribution_cost'"):
            payload = json.loads(row["payload"])
            distribution += payload.get("amount_cents", 0)
            if payload.get("candidate_id") in candidates:
                attributed_distribution += payload.get("amount_cents", 0)
        basis = unit_cost + generation + distribution
        transaction_basis = unit_cost + attributed_generation + attributed_distribution
        operating = money["verified_contribution_before_cost_basis_cents"] - basis
        provider_complete = (not money["unknown_fee_transactions"]
                             and not money["refund_reconciliation_incomplete_transactions"]
                             and not counts.get("pending", 0))
        return {**money, "provider": "stripe", "live_mode": self.live_mode, "currency": "USD",
                "received_events": sum(counts.values()), "pending_events": counts.get("pending", 0),
                "processed_events": counts.get("processed", 0), "verified_test_events": counts.get("test", 0),
                "ignored_events": counts.get("ignored", 0),
                "generation_cost_basis_cents": generation, "distribution_cost_basis_cents": distribution,
                "attributed_generation_cost_basis_cents": attributed_generation,
                "attributed_distribution_cost_basis_cents": attributed_distribution,
                "cost_basis_cents": basis, "cost_basis_scope": "all_recorded_store_costs",
                "transaction_cost_basis_cents": transaction_basis,
                "transaction_contribution_cents": money["verified_contribution_before_cost_basis_cents"] - transaction_basis,
                "transaction_contribution_scope": "verified_receipts_and_attributed_candidate_costs",
                "operating_contribution_cents": operating, "net_contribution_cents": operating,
                "provider_reconciliation_complete": provider_complete,
                "net_contribution_complete": False, "unrecorded_costs_cents": None,
                "cost_basis_limitations": [
                    "Asset and distribution spending includes only amounts recorded in this Store.",
                    "Unit costs are configured offer cost basis, not provider-verified expenses.",
                    "Unrecorded operating expenses and tax liabilities are excluded.",
                ],
                "cash_payout_cents": db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM stripe_payout WHERE status='paid'").fetchone()[0],
                "pending_reasons": {row["reason"]: row["total"] for row in db.execute(
                    "SELECT reason,COUNT(*) AS total FROM stripe_webhook WHERE state='pending' GROUP BY reason")}}

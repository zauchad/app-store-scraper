"""Lemon Squeezy webhook parsing and credit grants."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Optional

from sqlalchemy import select, func

from src.billing import analytics
from src.billing.credits import (
    PRO_PLAN,
    auto_unlock_after_payment,
    claw_back_credits,
    downgrade_from_pro,
    ensure_user,
    grant_credits,
    park_pending_grant,
    set_user_plan,
)
from src.config import settings
from src.db.models import CreditLedger, User, WebhookEvent
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

PAYMENT_EVENTS = frozenset({"order_created", "subscription_payment_success"})
PRO_ACTIVATE_EVENTS = frozenset({"subscription_created", "subscription_resumed"})
PRO_DOWNGRADE_EVENTS = frozenset({"subscription_expired"})
PRO_CANCEL_EVENTS = frozenset({"subscription_cancelled"})
REFUND_EVENTS = frozenset({"order_refunded"})
PAYMENT_FAILED_EVENTS = frozenset({"subscription_payment_failed"})


def verify_signature(raw_body: bytes, signature: str) -> bool:
    secret = settings.lemonsqueezy_webhook_secret.strip()
    if not secret:
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def _event_id(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    data = payload.get("data") or {}
    return str(meta.get("event_name") or "unknown") + ":" + str(data.get("id") or "")


def _custom_data(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta") or {}
    custom = meta.get("custom_data") or {}
    if isinstance(custom, dict):
        return custom
    return {}


def _variant_id(payload: dict[str, Any]) -> str:
    attrs = (payload.get("data") or {}).get("attributes") or {}
    if attrs.get("variant_id") is not None:
        return str(attrs["variant_id"])
    first = attrs.get("first_order_item") or {}
    if isinstance(first, dict) and first.get("variant_id") is not None:
        return str(first["variant_id"])
    return ""


def _user_email(payload: dict[str, Any]) -> str:
    attrs = (payload.get("data") or {}).get("attributes") or {}
    return str(attrs.get("user_email") or attrs.get("customer_email") or "").strip()


def _credits_for_variant(variant_id: str) -> tuple[int, Optional[str]]:
    vid = str(variant_id)
    if settings.lemonsqueezy_variant_1_credit and vid == settings.lemonsqueezy_variant_1_credit:
        return 1, None
    if settings.lemonsqueezy_variant_5_credits and vid == settings.lemonsqueezy_variant_5_credits:
        return 5, None
    if settings.lemonsqueezy_variant_pro and vid == settings.lemonsqueezy_variant_pro:
        return settings.pro_monthly_credits, PRO_PLAN
    return 0, None


def _credits_from_custom(custom: dict[str, Any]) -> tuple[int, Optional[str]]:
    raw = custom.get("credits")
    if raw is not None:
        try:
            amount = int(raw)
        except (TypeError, ValueError):
            amount = 0
        plan = custom.get("plan")
        return amount, str(plan) if plan else None
    return 0, None


def _is_pro_variant(variant_id: str) -> bool:
    pro_vid = settings.lemonsqueezy_variant_pro.strip()
    return bool(pro_vid and str(variant_id) == pro_vid)


def _mark_processed(event_id: str, event_name: str) -> None:
    with session_scope() as session:
        session.add(WebhookEvent(event_id=event_id, event_name=event_name))


def _unmark_processed(event_id: str) -> None:
    """Undo the idempotency marker so a Lemon Squeezy retry is not swallowed.

    The marker is written *before* the credit grant (so two concurrent deliveries
    cannot both grant). If the grant then fails, the marker must go away or the
    payment would be lost forever on retry.
    """
    try:
        with session_scope() as session:
            row = session.execute(
                select(WebhookEvent).where(WebhookEvent.event_id == event_id)
            ).scalar_one_or_none()
            if row is not None:
                session.delete(row)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not roll back webhook marker %s: %s", event_id, exc)


def _is_duplicate(event_id: str) -> bool:
    with session_scope() as session:
        return (
            session.execute(
                select(WebhookEvent.id).where(WebhookEvent.event_id == event_id)
            ).scalar_one_or_none()
            is not None
        )


def _user_id_for_email(email: str) -> str:
    """Find an existing account by buyer e-mail (checkout done while logged out)."""
    clean = email.lower().strip()
    if not clean or clean.endswith("@checkout.local"):
        return ""
    try:
        with session_scope() as session:
            return str(
                session.execute(
                    select(User.id).where(User.email == clean)
                ).scalar_one_or_none()
                or ""
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("E-mail lookup failed for %s: %s", clean, exc)
        return ""


def _resolve_user(custom: dict[str, Any], payload: dict[str, Any]) -> tuple[str, str]:
    """Resolve the buyer: custom user_id first, then the checkout e-mail."""
    user_id = str(custom.get("user_id") or "").strip()
    email = _user_email(payload)
    if not user_id and email:
        user_id = _user_id_for_email(email)
        if user_id:
            logger.info("Resolved user %s from checkout e-mail", user_id)
    return user_id, email or f"{user_id}@checkout.local"


def handle_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Process a Lemon Squeezy webhook payload. Idempotent by event id."""
    meta = payload.get("meta") or {}
    event_name = str(meta.get("event_name") or "")
    eid = _event_id(payload)
    if not eid or eid.endswith(":None"):
        return {"ok": False, "error": "missing event id"}

    if _is_duplicate(eid):
        return {"ok": True, "duplicate": True}

    custom = _custom_data(payload)

    # --- Subscription ended → revoke Pro (CSV export), keep credits & unlocks ---
    if event_name in PRO_DOWNGRADE_EVENTS:
        user_id, email = _resolve_user(custom, payload)
        if not user_id:
            return {"ok": False, "error": "missing user_id in custom_data"}
        _mark_processed(eid, event_name)
        ensure_user(user_id, email)
        downgrade_from_pro(user_id, event_name, reference_id=eid)
        logger.info("Downgraded Pro for user %s (%s)", user_id, event_name)
        return {"ok": True, "action": "downgrade", "user_id": user_id}

    # --- Cancelled but still active until period end — do not downgrade yet ---
    if event_name in PRO_CANCEL_EVENTS:
        user_id, _ = _resolve_user(custom, payload)
        if not user_id:
            return {"ok": False, "error": "missing user_id in custom_data"}
        _mark_processed(eid, event_name)
        logger.info("Subscription cancelled for user %s (access until period ends)", user_id)
        return {
            "ok": True,
            "action": "cancelled",
            "user_id": user_id,
            "note": "Pro access continues until subscription_expired",
        }

    # --- New / resumed Pro subscription → enable CSV before first renewal payment ---
    if event_name in PRO_ACTIVATE_EVENTS:
        user_id, email = _resolve_user(custom, payload)
        if not user_id:
            return {"ok": False, "error": "missing user_id in custom_data"}
        variant_id = _variant_id(payload)
        _, plan = _credits_for_variant(variant_id)
        if str(custom.get("plan") or "") == PRO_PLAN:
            plan = PRO_PLAN
        _mark_processed(eid, event_name)
        ensure_user(user_id, email)
        if plan == PRO_PLAN or _is_pro_variant(variant_id):
            set_user_plan(user_id, PRO_PLAN, reason=event_name, reference_id=eid)
            analytics.track(analytics.PRO_ACTIVATE, user_id=user_id, detail=event_name)
            return {"ok": True, "action": "activate_pro", "user_id": user_id}
        return {"ok": True, "ignored": True, "event": event_name}

    # --- Refunds → claw back credits granted for this order ---
    if event_name in REFUND_EVENTS:
        user_id, email = _resolve_user(custom, payload)
        order_id = str((payload.get("data") or {}).get("id") or "")
        orig_ref = f"order_created:{order_id}"
        claw_total = 0
        if user_id and order_id:
            with session_scope() as session:
                claw_total = session.execute(
                    select(func.coalesce(func.sum(CreditLedger.delta), 0)).where(
                        CreditLedger.user_id == user_id,
                        CreditLedger.reference_id == orig_ref,
                        CreditLedger.delta > 0,
                    )
                ).scalar_one()
                claw_total = int(claw_total or 0)
        _mark_processed(eid, event_name)
        if user_id and claw_total > 0:
            ensure_user(user_id, email)
            claw_back_credits(
                user_id,
                claw_total,
                "lemonsqueezy:order_refunded",
                reference_id=eid,
            )
            logger.info("Clawed back %d credits from %s (refund)", claw_total, user_id)
        analytics.track(analytics.REFUND, user_id=user_id or None, detail=str(claw_total))
        return {"ok": True, "action": "refund", "clawed_back": claw_total, "user_id": user_id}

    # --- Failed renewal → log it, keep access until the subscription expires ---
    if event_name in PAYMENT_FAILED_EVENTS:
        user_id, _ = _resolve_user(custom, payload)
        _mark_processed(eid, event_name)
        logger.warning("Subscription payment failed for user %s (dunning)", user_id or "?")
        return {"ok": True, "action": "payment_failed", "user_id": user_id}

    # --- One-off orders + subscription renewals → grant credits ---
    if event_name in PAYMENT_EVENTS:
        user_id, email = _resolve_user(custom, payload)
        variant_id = _variant_id(payload)
        credits, plan = _credits_for_variant(variant_id)
        if credits <= 0:
            credits, plan = _credits_from_custom(custom)

        if credits <= 0:
            _mark_processed(eid, event_name)
            return {"ok": True, "ignored": True, "event": event_name}

        # The niche the buyer had open when they clicked checkout — unlocked right
        # away so "paid" and "can read it" are the same moment.
        wanted_niche = str(custom.get("niche_key") or "").strip() or None

        # No account yet (bought from a link while logged out): park the credits
        # on the e-mail instead of failing, and claim them on first login.
        if not user_id:
            buyer_email = _user_email(payload)
            if not buyer_email:
                return {"ok": False, "error": "missing user_id and e-mail in payload"}
            _mark_processed(eid, event_name)
            try:
                park_pending_grant(
                    buyer_email,
                    credits=credits,
                    plan=plan,
                    reason=f"lemonsqueezy:{event_name}",
                    reference_id=eid,
                    niche_key=wanted_niche,
                )
            except Exception:
                _unmark_processed(eid)
                raise
            analytics.track(analytics.PURCHASE, detail=f"pending:{credits}")
            return {
                "ok": True,
                "action": "parked",
                "credits": credits,
                "email": buyer_email,
            }

        _mark_processed(eid, event_name)
        try:
            ensure_user(user_id, email)
            grant_credits(
                user_id,
                credits,
                f"lemonsqueezy:{event_name}",
                reference_id=eid,
                plan=plan,
            )
        except Exception:
            _unmark_processed(eid)
            raise

        unlocked = False
        if wanted_niche:
            unlocked = auto_unlock_after_payment(user_id, wanted_niche)

        logger.info(
            "Granted %d credits to %s (%s) from %s%s",
            credits,
            user_id,
            plan or "one-off",
            event_name,
            f", auto-unlocked {wanted_niche}" if unlocked else "",
        )
        analytics.track(analytics.PURCHASE, user_id=user_id, detail=f"{event_name}:{credits}")
        if unlocked:
            analytics.track(analytics.UNLOCK, user_id=user_id, detail="auto_after_payment")
        return {
            "ok": True,
            "credits": credits,
            "user_id": user_id,
            "plan": plan,
            "unlocked": wanted_niche if unlocked else None,
        }

    _mark_processed(eid, event_name)
    return {"ok": True, "ignored": True, "event": event_name}

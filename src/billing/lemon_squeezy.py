"""Lemon Squeezy webhook parsing and credit grants."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Optional

from sqlalchemy import select, func

from src.billing.credits import (
    PRO_PLAN,
    claw_back_credits,
    downgrade_from_pro,
    ensure_user,
    grant_credits,
    set_user_plan,
)
from src.config import settings
from src.db.models import CreditLedger, WebhookEvent
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

PAYMENT_EVENTS = frozenset({"order_created", "subscription_payment_success"})
PRO_ACTIVATE_EVENTS = frozenset({"subscription_created", "subscription_resumed"})
PRO_DOWNGRADE_EVENTS = frozenset({"subscription_expired"})
PRO_CANCEL_EVENTS = frozenset({"subscription_cancelled"})
REFUND_EVENTS = frozenset({"order_refunded"})


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


def _is_duplicate(event_id: str) -> bool:
    with session_scope() as session:
        return (
            session.execute(
                select(WebhookEvent.id).where(WebhookEvent.event_id == event_id)
            ).scalar_one_or_none()
            is not None
        )


def _resolve_user(custom: dict[str, Any], payload: dict[str, Any]) -> tuple[str, str]:
    user_id = str(custom.get("user_id") or "").strip()
    email = _user_email(payload) or f"{user_id}@checkout.local"
    return user_id, email


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
        return {"ok": True, "action": "refund", "clawed_back": claw_total, "user_id": user_id}

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

        if not user_id:
            return {"ok": False, "error": "missing user_id in custom_data"}

        _mark_processed(eid, event_name)
        ensure_user(user_id, email)
        grant_credits(
            user_id,
            credits,
            f"lemonsqueezy:{event_name}",
            reference_id=eid,
            plan=plan,
        )
        logger.info(
            "Granted %d credits to %s (%s) from %s",
            credits,
            user_id,
            plan or "one-off",
            event_name,
        )
        return {"ok": True, "credits": credits, "user_id": user_id, "plan": plan}

    _mark_processed(eid, event_name)
    return {"ok": True, "ignored": True, "event": event_name}

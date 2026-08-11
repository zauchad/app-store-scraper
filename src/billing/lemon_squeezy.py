"""Lemon Squeezy webhook parsing and credit grants."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Optional

from sqlalchemy import select

from src.billing.credits import PRO_PLAN, ensure_user, grant_credits
from src.config import settings
from src.db.models import WebhookEvent
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)


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
    attrs = (payload.get("data") or {}).get("attributes") or {}
    custom = attrs.get("custom_data") or {}
    if isinstance(custom, dict):
        return custom
    return {}


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


def handle_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Process a Lemon Squeezy webhook payload. Idempotent by event id."""
    meta = payload.get("meta") or {}
    event_name = str(meta.get("event_name") or "")
    eid = _event_id(payload)
    if not eid or eid.endswith(":None"):
        return {"ok": False, "error": "missing event id"}

    with session_scope() as session:
        seen = session.execute(
            select(WebhookEvent.id).where(WebhookEvent.event_id == eid)
        ).scalar_one_or_none()
        if seen:
            return {"ok": True, "duplicate": True}

        credits, plan = 0, None
        custom = _custom_data(payload)
        user_id = str(custom.get("user_id") or "").strip()
        email = _user_email(payload)

        if event_name in ("order_created", "subscription_payment_success"):
            variant_id = str(
                ((payload.get("data") or {}).get("attributes") or {}).get("variant_id") or ""
            )
            credits, plan = _credits_for_variant(variant_id)
            if credits <= 0:
                credits, plan = _credits_from_custom(custom)

        if credits <= 0:
            session.add(WebhookEvent(event_id=eid, event_name=event_name))
            return {"ok": True, "ignored": True, "event": event_name}

        if not user_id:
            return {"ok": False, "error": "missing user_id in custom_data"}

        if not email:
            email = f"{user_id}@checkout.local"

        session.add(WebhookEvent(event_id=eid, event_name=event_name))

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

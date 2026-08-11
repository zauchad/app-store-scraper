"""Tests for Lemon Squeezy webhooks and signature verification."""
from __future__ import annotations

import hashlib
import hmac
import uuid

import pytest

from src.billing.credits import PRO_PLAN, FREE_PLAN, ensure_user, get_user, grant_credits, set_user_plan
from src.billing.lemon_squeezy import handle_webhook, verify_signature


def _event_id() -> str:
    return uuid.uuid4().hex[:12]


def _order_payload(
    *,
    event_id: str | None = None,
    user_id: str | None = None,
    variant_id: int = 111,
    credits: int | None = None,
    plan: str | None = None,
) -> dict:
    event_id = event_id or _event_id()
    user_id = user_id or f"wh-{_event_id()}"
    custom: dict = {"user_id": user_id}
    if credits is not None:
        custom["credits"] = credits
    if plan:
        custom["plan"] = plan
    return {
        "meta": {"event_name": "order_created", "custom_data": custom},
        "data": {
            "id": event_id,
            "attributes": {
                "user_email": f"{user_id}@test.local",
                "first_order_item": {"variant_id": variant_id},
            },
        },
    }


def test_verify_signature_valid(billing_env):
    body = b'{"hello":"world"}'
    import hashlib
    import hmac

    secret = billing_env.lemonsqueezy_webhook_secret
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig)


def test_verify_signature_rejects_wrong_secret(billing_env):
    assert not verify_signature(b"payload", "deadbeef")


def test_order_created_grants_credits_via_variant(billing_env):
    uid = f"wh-{_event_id()}"
    ensure_user(uid, f"{uid}@test.local")
    eid = _event_id()
    result = handle_webhook(_order_payload(event_id=eid, user_id=uid, variant_id=111))
    assert result["ok"] is True
    assert result.get("credits") == 1
    assert get_user(uid).credits_balance == 1


def test_order_created_grants_credits_via_meta_custom_data(billing_env):
    uid = f"wh-{_event_id()}"
    ensure_user(uid, f"{uid}@test.local")
    result = handle_webhook(
        _order_payload(event_id=_event_id(), user_id=uid, variant_id=0, credits=5)
    )
    assert result["ok"] is True
    assert result.get("credits") == 5
    assert get_user(uid).credits_balance == 5


def test_webhook_is_idempotent(billing_env):
    uid = f"wh-{_event_id()}"
    ensure_user(uid, f"{uid}@test.local")
    eid = _event_id()
    payload = _order_payload(event_id=eid, user_id=uid)
    first = handle_webhook(payload)
    second = handle_webhook(payload)
    assert first["ok"] and first.get("credits") == 1
    assert second.get("duplicate") is True
    assert get_user(uid).credits_balance == 1


def test_webhook_missing_user_id_fails(billing_env):
    payload = _order_payload(event_id=_event_id(), credits=1)
    payload["meta"]["custom_data"] = {}
    result = handle_webhook(payload)
    assert result["ok"] is False
    assert "user_id" in result.get("error", "")


def test_subscription_created_activates_pro(billing_env):
    uid = f"sub-{_event_id()}"
    ensure_user(uid, f"{uid}@test.local")
    payload = {
        "meta": {
            "event_name": "subscription_created",
            "custom_data": {"user_id": uid, "plan": "pro"},
        },
        "data": {
            "id": _event_id(),
            "attributes": {"variant_id": 999, "user_email": f"{uid}@test.local"},
        },
    }
    result = handle_webhook(payload)
    assert result["ok"] is True
    assert result.get("action") == "activate_pro"
    assert get_user(uid).plan == PRO_PLAN


def test_subscription_expired_downgrades_pro(billing_env):
    uid = f"sub-{_event_id()}"
    ensure_user(uid, f"{uid}@test.local")
    grant_credits(uid, 3, "seed", plan=PRO_PLAN)
    payload = {
        "meta": {
            "event_name": "subscription_expired",
            "custom_data": {"user_id": uid},
        },
        "data": {"id": _event_id(), "attributes": {}},
    }
    result = handle_webhook(payload)
    assert result["ok"] is True
    assert result.get("action") == "downgrade"
    user = get_user(uid)
    assert user.plan == FREE_PLAN
    assert user.credits_balance == 3


def test_subscription_cancelled_does_not_downgrade(billing_env):
    uid = f"sub-{_event_id()}"
    ensure_user(uid, f"{uid}@test.local")
    set_user_plan(uid, PRO_PLAN, reason="test")
    payload = {
        "meta": {
            "event_name": "subscription_cancelled",
            "custom_data": {"user_id": uid},
        },
        "data": {"id": _event_id(), "attributes": {}},
    }
    result = handle_webhook(payload)
    assert result["ok"] is True
    assert result.get("action") == "cancelled"
    assert get_user(uid).plan == PRO_PLAN


def test_pro_payment_grants_monthly_credits(billing_env):
    uid = f"sub-{_event_id()}"
    ensure_user(uid, f"{uid}@test.local")
    payload = {
        "meta": {
            "event_name": "subscription_payment_success",
            "custom_data": {"user_id": uid},
        },
        "data": {
            "id": _event_id(),
            "attributes": {"variant_id": 999, "user_email": f"{uid}@test.local"},
        },
    }
    result = handle_webhook(payload)
    assert result["ok"] is True
    assert result.get("credits") == 15
    user = get_user(uid)
    assert user.credits_balance == 15
    assert user.plan == PRO_PLAN

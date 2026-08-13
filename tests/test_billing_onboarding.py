"""Onboarding + funnel: free first unlock, auto-unlock, conversion tracking."""
from __future__ import annotations

import uuid

import src.billing.credits as credits_mod
from src.billing import analytics
from src.billing.credits import (
    auto_unlock_after_payment,
    ensure_user,
    get_user,
    is_niche_unlocked,
    park_pending_grant,
    unlock_niche,
)


def _uid() -> str:
    return f"u-{uuid.uuid4().hex[:12]}"


def test_signup_bonus_gives_a_free_unlock(billing_env, monkeypatch):
    monkeypatch.setattr(credits_mod.settings, "signup_bonus_credits", 1)
    uid = _uid()
    user = ensure_user(uid, f"{uid}@test.local")
    assert user.credits_balance == 1

    unlock_niche(uid, "category:us:6015")
    assert is_niche_unlocked(uid, "category:us:6015")
    assert get_user(uid).credits_balance == 0


def test_signup_bonus_is_granted_once(billing_env, monkeypatch):
    monkeypatch.setattr(credits_mod.settings, "signup_bonus_credits", 1)
    uid = _uid()
    ensure_user(uid, f"{uid}@test.local")
    ensure_user(uid, f"{uid}@test.local")
    assert get_user(uid).credits_balance == 1


def test_auto_unlock_needs_a_credit(billing_env):
    uid = _uid()
    ensure_user(uid, f"{uid}@test.local")  # bonus is 0 in the fixture
    assert auto_unlock_after_payment(uid, "category:us:6015") is False
    assert not is_niche_unlocked(uid, "category:us:6015")


def test_auto_unlock_is_idempotent(billing_env, monkeypatch):
    monkeypatch.setattr(credits_mod.settings, "signup_bonus_credits", 2)
    uid = _uid()
    ensure_user(uid, f"{uid}@test.local")
    assert auto_unlock_after_payment(uid, "category:us:6015") is True
    assert auto_unlock_after_payment(uid, "category:us:6015") is False
    # Only one credit spent, no duplicate unlock row.
    assert get_user(uid).credits_balance == 1


def test_pending_grant_with_niche_unlocks_on_first_login(billing_env):
    email = f"{_uid()}@test.local"
    park_pending_grant(
        email,
        credits=1,
        plan=None,
        reason="lemonsqueezy:order_created",
        reference_id="order:1",
        niche_key="keyword:us:sleep tracker",
    )
    uid = _uid()
    user = ensure_user(uid, email)
    assert is_niche_unlocked(uid, "keyword:us:sleep tracker")
    assert user.credits_balance == 0  # the bought credit paid for the unlock


def test_pending_pro_plan_is_applied_on_claim(billing_env):
    email = f"{_uid()}@test.local"
    park_pending_grant(
        email,
        credits=15,
        plan="pro",
        reason="lemonsqueezy:subscription_payment_success",
        reference_id="sub:1",
    )
    uid = _uid()
    user = ensure_user(uid, email)
    assert user.plan == "pro"
    assert user.credits_balance == 15


def test_funnel_report_counts_steps(billing_env):
    uid = _uid()
    ensure_user(uid, f"{uid}@test.local")
    analytics.track(analytics.LANDING_VIEW)
    analytics.track(analytics.SIGNUP, user_id=uid)
    analytics.track(analytics.GATE_VIEW, user_id=uid, detail="category:us:6015")
    analytics.track(analytics.PURCHASE, user_id=uid, detail="order_created:1")

    counts = analytics.counts_since(days=1)
    assert counts[analytics.SIGNUP][0] == 1
    assert counts[analytics.PURCHASE][1] == 1

    report = analytics.format_funnel_report(days=1)
    assert "Konwersja rejestracja → zakup: 100.0%" in report


def test_tracking_never_raises(billing_env, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(analytics, "session_scope", _boom)
    analytics.track(analytics.PURCHASE, user_id="whoever")  # must not raise

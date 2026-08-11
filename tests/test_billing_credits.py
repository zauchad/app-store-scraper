"""Tests for credit balance, unlocks, and Pro access."""
from __future__ import annotations

import uuid

import pytest

from src.billing.credits import (
    CREDIT_COST_NICHE_UNLOCK,
    FREE_PLAN,
    PRO_PLAN,
    ensure_user,
    get_user,
    grant_credits,
    has_pro_access,
    is_niche_unlocked,
    keyword_niche_key,
    niche_key,
    set_user_plan,
    spend_credits,
    unlock_niche,
)


def _uid(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def test_ensure_user_starts_with_zero_credits(billing_env):
    uid = _uid()
    user = ensure_user(uid, f"{uid}@example.com")
    assert user.credits_balance == 0
    assert user.plan == FREE_PLAN


def test_grant_and_spend_credits(billing_env):
    uid = _uid()
    ensure_user(uid, f"{uid}@example.com")
    grant_credits(uid, 5, "test_grant")
    user = get_user(uid)
    assert user.credits_balance == 5

    spend_credits(uid, 2, "test_spend")
    user = get_user(uid)
    assert user.credits_balance == 3


def test_spend_raises_when_insufficient(billing_env):
    uid = _uid()
    ensure_user(uid, f"{uid}@example.com")
    with pytest.raises(ValueError, match="insufficient"):
        spend_credits(uid, 1, "test")


def test_unlock_niche_costs_one_credit(billing_env):
    uid = _uid()
    ensure_user(uid, f"{uid}@example.com")
    grant_credits(uid, 2, "seed")
    key = niche_key(kind="category", country="us", identifier=6013)

    unlock_niche(uid, key)
    user = get_user(uid)
    assert user.credits_balance == 2 - CREDIT_COST_NICHE_UNLOCK
    assert is_niche_unlocked(uid, key)


def test_unlock_niche_is_idempotent(billing_env):
    uid = _uid()
    ensure_user(uid, f"{uid}@example.com")
    grant_credits(uid, 1, "seed")
    key = niche_key(kind="category", country="us", identifier=6014)

    unlock_niche(uid, key)
    unlock_niche(uid, key)
    user = get_user(uid)
    assert user.credits_balance == 0


def test_keyword_niche_key_normalizes(billing_env):
    key = keyword_niche_key("  Sleep Tracker  ", "US")
    assert key == "keyword:us:sleep tracker"


def test_has_pro_access(billing_env):
    uid = _uid()
    ensure_user(uid, f"{uid}@example.com")
    assert not has_pro_access(uid)

    set_user_plan(uid, PRO_PLAN, reason="test")
    assert has_pro_access(uid)


def test_is_niche_unlocked_when_monetization_off(monkeypatch, tmp_path):
    db_path = tmp_path / "open.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MONETIZATION_ENABLED", "false")

    import src.billing.credits as credits_mod
    import src.config as config_mod
    import src.db.session as db_session
    from src.config import get_settings
    from src.db.session import init_db

    get_settings.cache_clear()
    fresh = get_settings()
    config_mod.settings = fresh
    credits_mod.settings = fresh
    db_session.settings = fresh
    db_session._engine = None
    db_session._SessionFactory = None
    init_db()

    from src.billing.credits import is_niche_unlocked, niche_key

    key = niche_key(kind="category", country="us", identifier=1)
    assert is_niche_unlocked(None, key)

    db_session._engine = None
    db_session._SessionFactory = None
    get_settings.cache_clear()

"""Shared fixtures for billing tests."""
from __future__ import annotations

import pytest

import src.billing.credits as credits_mod
import src.billing.lemon_squeezy as lemon_mod
import src.config as config_mod
import src.db.session as db_session
from src.config import get_settings
from src.db.session import init_db


def _reload_settings():
    get_settings.cache_clear()
    fresh = get_settings()
    config_mod.settings = fresh
    credits_mod.settings = fresh
    lemon_mod.settings = fresh
    db_session.settings = fresh
    return fresh


@pytest.fixture()
def billing_env(monkeypatch, tmp_path):
    """Isolated SQLite DB + monetization enabled."""
    db_path = tmp_path / "billing_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MONETIZATION_ENABLED", "true")
    monkeypatch.setenv("SIGNUP_BONUS_CREDITS", "0")
    monkeypatch.setenv("PRO_MONTHLY_CREDITS", "15")
    monkeypatch.setenv("LEMONSQUEEZY_VARIANT_1_CREDIT", "111")
    monkeypatch.setenv("LEMONSQUEEZY_VARIANT_5_CREDITS", "555")
    monkeypatch.setenv("LEMONSQUEEZY_VARIANT_PRO", "999")
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", "test-signing-secret")

    fresh = _reload_settings()
    db_session._engine = None
    db_session._SessionFactory = None
    init_db()

    yield fresh

    db_session._engine = None
    db_session._SessionFactory = None
    get_settings.cache_clear()

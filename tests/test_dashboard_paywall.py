"""Paywall rendering — the screen that has to convert, driven by Streamlit AppTest."""
from __future__ import annotations

import uuid

import pytest
from streamlit.testing.v1 import AppTest

import dashboard.auth as auth_mod
import dashboard.billing_ui as billing_ui
import src.billing.credits as credits_mod
from src.billing.credits import ensure_user, get_user, is_niche_unlocked

NICHE = "category:us:6015"
GATE_SCRIPT = """
import streamlit as st
from dashboard.billing_ui import render_unlock_gate

ok = render_unlock_gate(
    niche_key="category:us:6015",
    niche_label="Health & Fitness",
    teaser="crashe w 41% negatywnych recenzji",
)
st.write("UNLOCKED" if ok else "LOCKED")
"""


@pytest.fixture()
def paywall_env(billing_env, monkeypatch):
    """Monetization on, checkout URLs configured, dashboard modules rebound."""
    monkeypatch.setattr(
        billing_env,
        "lemonsqueezy_checkout_pro",
        "https://store.lemonsqueezy.com/checkout/buy/pro",
    )
    monkeypatch.setattr(
        billing_env,
        "lemonsqueezy_checkout_1_credit",
        "https://store.lemonsqueezy.com/checkout/buy/one",
    )
    monkeypatch.setattr(billing_env, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(billing_env, "supabase_anon_key", "anon")
    # Both dashboard modules bound `settings` at import time, before the fixture
    # rebuilt it from the test environment.
    monkeypatch.setattr(billing_ui, "settings", billing_env)
    monkeypatch.setattr(auth_mod, "settings", billing_env)
    return billing_env


def _user(credits: int = 0):
    uid = str(uuid.uuid4())
    user = ensure_user(uid, f"{uid[:8]}@example.com")
    if credits:
        credits_mod.grant_credits(uid, credits, "test_setup")
    return get_user(user.id)


def _run(user_id: str) -> AppTest:
    at = AppTest.from_string(GATE_SCRIPT, default_timeout=30)
    at.session_state["auth_user"] = user_id
    at.run()
    assert not at.exception, at.exception
    return at


def test_gate_without_credits_shows_checkout_with_niche_context(paywall_env):
    user = _user(credits=0)
    at = _run(user.id)

    assert at.markdown[-1].value == "LOCKED"
    urls = [el.proto.url for el in at.get("link_button")]
    assert len(urls) == 2
    # Pro is rendered first — it is the offer we want taken.
    assert "buy/pro" in urls[0]
    for url in urls:
        assert f"checkout[custom][user_id]={user.id}" in url
        assert "checkout%3Aus" not in url  # names stay literal, values encoded
        assert "checkout[custom][niche_key]=category%3Aus%3A6015" in url
        assert "checkout[email]=" in url


def test_gate_shows_a_concrete_teaser_from_behind_the_wall(paywall_env):
    user = _user(credits=0)
    at = _run(user.id)
    assert any("crashe w 41%" in md.value for md in at.markdown)


def test_free_credit_turns_the_gate_into_one_click(paywall_env):
    user = _user(credits=1)
    at = _run(user.id)

    labels = [b.label for b in at.button]
    assert any("Odblokuj" in label for label in labels)
    # No upsell needed when the user can already unlock.
    assert not at.get("link_button")

    at.button[0].click().run()
    assert is_niche_unlocked(user.id, NICHE)
    assert get_user(user.id).credits_balance == 0


def test_unlocked_niche_passes_the_gate(paywall_env):
    user = _user(credits=1)
    credits_mod.unlock_niche(user.id, NICHE)
    at = _run(user.id)
    assert at.markdown[-1].value == "UNLOCKED"


def test_anonymous_visitor_sees_value_prop_not_checkout(paywall_env):
    at = AppTest.from_string(GATE_SCRIPT, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert at.markdown[-1].value == "LOCKED"
    assert not at.get("link_button")
    assert any("Co dostaniesz" in md.value for md in at.markdown)


def test_keyword_niche_key_with_spaces_is_url_safe(paywall_env):
    user = _user(credits=0)
    url = billing_ui._checkout_url(
        "https://store.lemonsqueezy.com/checkout/buy/one",
        user,
        niche_key="keyword:us:sleep tracker for shift workers",
    )
    assert " " not in url
    assert "sleep%20tracker" in url

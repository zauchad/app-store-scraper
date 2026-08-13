"""Pure-logic tests for the Supabase REST auth client (no network)."""
from __future__ import annotations

import base64
import hashlib
import urllib.parse

import pytest

import dashboard.supabase_auth as sb


@pytest.fixture()
def auth_env(monkeypatch):
    monkeypatch.setattr(sb.settings, "supabase_url", "https://proj.supabase.co/")
    monkeypatch.setattr(sb.settings, "supabase_anon_key", "anon-key")
    return sb.settings


def test_pkce_challenge_matches_s256(auth_env):
    verifier = sb.new_pkce_verifier()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert sb.pkce_challenge(verifier) == expected
    assert "=" not in sb.pkce_challenge(verifier)


def test_new_verifier_is_random(auth_env):
    assert sb.new_pkce_verifier() != sb.new_pkce_verifier()


def test_authorize_url_carries_provider_and_challenge(auth_env):
    verifier = "test-verifier"
    url = sb.oauth_authorize_url(
        "google",
        redirect_to="https://app.example/",
        code_verifier=verifier,
    )
    assert url.startswith("https://proj.supabase.co/auth/v1/authorize?")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["provider"] == ["google"]
    assert query["redirect_to"] == ["https://app.example/"]
    assert query["code_challenge"] == [sb.pkce_challenge(verifier)]
    assert query["code_challenge_method"] == ["s256"]


def test_missing_config_raises_auth_error(monkeypatch):
    monkeypatch.setattr(sb.settings, "supabase_url", "")
    with pytest.raises(sb.AuthError):
        sb.oauth_authorize_url("google", redirect_to="x", code_verifier="y")


def test_session_from_requires_access_token_and_user():
    assert sb._session_from({"user": {"id": "u1", "email": "a@b.c"}}) is None
    session = sb._session_from(
        {
            "access_token": "at",
            "refresh_token": "rt",
            "user": {"id": "u1", "email": "A@B.c"},
        }
    )
    assert session is not None
    assert (session.user_id, session.email, session.refresh_token) == ("u1", "A@B.c", "rt")


def test_friendly_error_prefers_server_message():
    assert sb._friendly({"msg": "Invalid login credentials"}, 400) == (
        "Invalid login credentials"
    )
    assert sb._friendly({"error_description": "expired"}, 401) == "expired"
    assert "Za dużo prób" in sb._friendly({}, 429)
    assert "HTTP 500" in sb._friendly({}, 500)


def test_headers_use_anon_key(auth_env):
    headers = sb._headers()
    assert headers["apikey"] == "anon-key"
    assert headers["Authorization"] == "Bearer anon-key"
    # A user token overrides the anon bearer (needed for password updates).
    assert sb._headers("user-token")["Authorization"] == "Bearer user-token"


def test_base_url_normalises_trailing_slash(auth_env):
    assert sb._base() == "https://proj.supabase.co/auth/v1"

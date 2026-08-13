"""Thin Supabase (GoTrue) REST client.

Why REST instead of ``supabase-py``: the flows that actually remove signup
friction — Google OAuth and e-mail codes — need manual control. Streamlit reloads
the page on every OAuth redirect, so the PKCE verifier has to survive in *our*
storage (a cookie), not inside a client object that dies with the rerun. Talking
to GoTrue directly keeps all of that explicit, works on Python 3.9 and drops a
heavy dependency.

Everything here is pure HTTP + dataclasses: no Streamlit imports, so it is
unit-testable without a browser session.
"""
from __future__ import annotations

import base64
import hashlib
import os
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from src.config import settings

TIMEOUT = 20


class AuthError(Exception):
    """Supabase rejected the request; message is safe to show to the user."""


@dataclass
class AuthSession:
    user_id: str
    email: str
    access_token: str
    refresh_token: str


def _base() -> str:
    url = settings.supabase_url.strip().rstrip("/")
    if not url:
        raise AuthError("Supabase nie jest skonfigurowany (SUPABASE_URL).")
    return f"{url}/auth/v1"


def _headers(access_token: Optional[str] = None) -> Dict[str, str]:
    key = settings.supabase_anon_key.strip()
    if not key:
        raise AuthError("Supabase nie jest skonfigurowany (SUPABASE_ANON_KEY).")
    return {
        "apikey": key,
        "Authorization": f"Bearer {access_token or key}",
        "Content-Type": "application/json",
    }


def _friendly(payload: Any, status: int) -> str:
    """Turn a GoTrue error body into one sentence for the UI."""
    if isinstance(payload, dict):
        for field in ("msg", "message", "error_description", "error"):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if status == 400:
        return "Nieprawidłowe dane logowania."
    if status == 422:
        return "Nieprawidłowy e-mail lub hasło (min. 8 znaków)."
    if status == 429:
        return "Za dużo prób — odczekaj chwilę i spróbuj ponownie."
    return f"Błąd autoryzacji (HTTP {status})."


def _request(
    method: str,
    path: str,
    *,
    json: Optional[dict] = None,
    params: Optional[dict] = None,
    access_token: Optional[str] = None,
) -> dict:
    try:
        resp = requests.request(
            method,
            f"{_base()}{path}",
            json=json,
            params=params,
            headers=_headers(access_token),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AuthError(f"Brak połączenia z Supabase: {exc}") from exc

    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        body = {}

    if resp.status_code >= 400:
        raise AuthError(_friendly(body, resp.status_code))
    return body if isinstance(body, dict) else {}


def _session_from(body: dict) -> Optional[AuthSession]:
    """Build a session from a token response, or None if e-mail confirmation is pending."""
    access = str(body.get("access_token") or "")
    refresh = str(body.get("refresh_token") or "")
    user = body.get("user") if isinstance(body.get("user"), dict) else body
    user_id = str((user or {}).get("id") or "")
    email = str((user or {}).get("email") or "")
    if not access or not user_id:
        return None
    return AuthSession(
        user_id=user_id,
        email=email,
        access_token=access,
        refresh_token=refresh,
    )


# --------------------------------------------------------------------------- #
#  E-mail + password
# --------------------------------------------------------------------------- #
def sign_up(email: str, password: str, *, redirect_to: str = "") -> Optional[AuthSession]:
    """Create an account. Returns None when Supabase requires e-mail confirmation."""
    params = {"redirect_to": redirect_to} if redirect_to else None
    body = _request(
        "POST",
        "/signup",
        json={"email": email, "password": password},
        params=params,
    )
    return _session_from(body)


def sign_in_password(email: str, password: str) -> AuthSession:
    body = _request(
        "POST",
        "/token",
        params={"grant_type": "password"},
        json={"email": email, "password": password},
    )
    session = _session_from(body)
    if session is None:
        raise AuthError("Logowanie nie powiodło się — potwierdź e-mail i spróbuj ponownie.")
    return session


def refresh_session(refresh_token: str) -> AuthSession:
    body = _request(
        "POST",
        "/token",
        params={"grant_type": "refresh_token"},
        json={"refresh_token": refresh_token},
    )
    session = _session_from(body)
    if session is None:
        raise AuthError("Sesja wygasła — zaloguj się ponownie.")
    return session


def send_password_reset(email: str, *, redirect_to: str = "") -> None:
    params = {"redirect_to": redirect_to} if redirect_to else None
    _request("POST", "/recover", json={"email": email}, params=params)


def update_password(access_token: str, password: str) -> None:
    _request("PUT", "/user", json={"password": password}, access_token=access_token)


# --------------------------------------------------------------------------- #
#  Passwordless e-mail codes (no password to invent at signup)
# --------------------------------------------------------------------------- #
def send_email_code(email: str, *, create_user: bool = True) -> None:
    _request("POST", "/otp", json={"email": email, "create_user": create_user})


def verify_email_code(email: str, code: str) -> AuthSession:
    body = _request(
        "POST",
        "/verify",
        json={"type": "email", "email": email, "token": code.strip()},
    )
    session = _session_from(body)
    if session is None:
        raise AuthError("Kod nieprawidłowy lub wygasł — poproś o nowy.")
    return session


def verify_token_hash(token_hash: str, token_type: str) -> AuthSession:
    """Complete an e-mail link (confirmation / password recovery).

    Works with query-param links (``?token_hash=…&type=…``), which Streamlit can
    read — unlike the default fragment-based links.
    """
    body = _request(
        "POST",
        "/verify",
        json={"type": token_type, "token_hash": token_hash},
    )
    session = _session_from(body)
    if session is None:
        raise AuthError("Link wygasł lub został już użyty — poproś o nowy.")
    return session


# --------------------------------------------------------------------------- #
#  OAuth (PKCE, verifier persisted by the caller)
# --------------------------------------------------------------------------- #
def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def new_pkce_verifier() -> str:
    return _b64url(os.urandom(48))


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode()).digest())


def oauth_authorize_url(
    provider: str,
    *,
    redirect_to: str,
    code_verifier: str,
) -> str:
    query = urllib.parse.urlencode(
        {
            "provider": provider,
            "redirect_to": redirect_to,
            "code_challenge": pkce_challenge(code_verifier),
            "code_challenge_method": "s256",
        }
    )
    return f"{_base()}/authorize?{query}"


def exchange_code(auth_code: str, code_verifier: str) -> AuthSession:
    body = _request(
        "POST",
        "/token",
        params={"grant_type": "pkce"},
        json={"auth_code": auth_code, "code_verifier": code_verifier},
    )
    session = _session_from(body)
    if session is None:
        raise AuthError("Nie udało się dokończyć logowania Google — spróbuj ponownie.")
    return session

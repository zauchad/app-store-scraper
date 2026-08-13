"""Persist auth across browser refreshes via HTTP cookies.

All reads go through `_read_all`, which touches the cookie component **once per
script run** — every `CookieManager.get_all` call renders a keyed element, so two
independent reads in one run collide with StreamlitDuplicateElementKey.
"""
from __future__ import annotations

import time
from typing import Dict, Optional

import streamlit as st

_COOKIE_REFRESH = "mi_auth_refresh"
_COOKIE_USER = "mi_auth_user"
_COOKIE_PKCE = "mi_auth_pkce"
_STATE_CACHE = "_cookie_values"
_STATE_MANAGER = "_cookie_manager"
_STATE_PKCE = "auth_pkce_verifier"


def _cookie_manager():
    """One CookieManager per browser session.

    Not `@st.cache_resource`: the constructor renders a custom component, which
    Streamlit forbids inside cached functions (and a global cache would share one
    user's cookie widget with every other session).
    """
    cached = st.session_state.get(_STATE_MANAGER)
    if cached is not None:
        return cached if cached != "unavailable" else None
    try:
        from extra_streamlit_components import CookieManager

        manager = CookieManager()
    except Exception:  # noqa: BLE001
        st.session_state[_STATE_MANAGER] = "unavailable"
        return None
    st.session_state[_STATE_MANAGER] = manager
    return manager


def _read_all() -> Dict[str, str]:
    """Cookie values for this session.

    The component answers asynchronously, so an empty result is not cached — the
    next rerun tries again and picks up the values once the browser has replied.
    """
    cached = st.session_state.get(_STATE_CACHE)
    if cached:
        return cached
    cm = _cookie_manager()
    if cm is None:
        return {}
    try:
        cookies = cm.get_all(key="auth_cookie_read") or {}
    except Exception:  # noqa: BLE001
        return {}
    values = {str(k): str(v) for k, v in dict(cookies).items() if v}
    if values:
        st.session_state[_STATE_CACHE] = values
    return values


def save_auth_cookies(user_id: str, refresh_token: str) -> None:
    cm = _cookie_manager()
    if cm is None or not refresh_token:
        return
    expires = time.time() + 60 * 60 * 24 * 30  # 30 days
    cm.set(_COOKIE_REFRESH, refresh_token, expires_at=expires, key=f"set_refresh_{user_id}")
    cm.set(_COOKIE_USER, user_id, expires_at=expires, key=f"set_user_{user_id}")


def save_pkce_verifier(verifier: str) -> None:
    """Persist the OAuth PKCE verifier across the provider redirect.

    The redirect is a full page load, so session state is gone by the time the
    ``?code=`` comes back — the verifier has to live in a cookie.
    """
    st.session_state[_STATE_PKCE] = verifier
    cached = st.session_state.get(_STATE_CACHE)
    if isinstance(cached, dict):
        cached[_COOKIE_PKCE] = verifier
    cm = _cookie_manager()
    if cm is None:
        return
    expires = time.time() + 60 * 15  # short-lived: one login attempt
    try:
        cm.set(_COOKIE_PKCE, verifier, expires_at=expires, key="set_pkce")
    except Exception:  # noqa: BLE001
        pass


def read_pkce_verifier() -> Optional[str]:
    state = st.session_state.get(_STATE_PKCE)
    if state:
        return str(state)
    token = _read_all().get(_COOKIE_PKCE)
    return token or None


def read_refresh_from_cookies() -> Optional[str]:
    token = _read_all().get(_COOKIE_REFRESH)
    return token or None


def clear_auth_cookies() -> None:
    st.session_state.pop(_STATE_CACHE, None)
    st.session_state.pop(_STATE_PKCE, None)
    cm = _cookie_manager()
    if cm is None:
        return
    for name in (_COOKIE_REFRESH, _COOKIE_USER, _COOKIE_PKCE):
        try:
            cm.delete(name, key=f"del_{name}")
        except Exception:  # noqa: BLE001
            pass

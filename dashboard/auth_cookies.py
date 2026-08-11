"""Persist auth across browser refreshes via HTTP cookies."""
from __future__ import annotations

import time
from typing import Optional

import streamlit as st

_COOKIE_REFRESH = "mi_auth_refresh"
_COOKIE_USER = "mi_auth_user"
_COOKIE_INIT = "_cookie_manager_ready"


@st.cache_resource
def _cookie_manager():
    try:
        from extra_streamlit_components import CookieManager
    except ImportError:
        return None
    return CookieManager()


def _cookies_ready() -> bool:
    cm = _cookie_manager()
    if cm is None:
        return True
    if st.session_state.get(_COOKIE_INIT):
        return True
    cm.get_all(key="auth_cookie_bootstrap")
    st.session_state[_COOKIE_INIT] = True
    return True


def save_auth_cookies(user_id: str, refresh_token: str) -> None:
    cm = _cookie_manager()
    if cm is None or not refresh_token:
        return
    expires = time.time() + 60 * 60 * 24 * 30  # 30 days
    cm.set(_COOKIE_REFRESH, refresh_token, expires_at=expires, key=f"set_refresh_{user_id}")
    cm.set(_COOKIE_USER, user_id, expires_at=expires, key=f"set_user_{user_id}")


def clear_auth_cookies() -> None:
    cm = _cookie_manager()
    if cm is None:
        return
    for name in (_COOKIE_REFRESH, _COOKIE_USER):
        try:
            cm.delete(name, key=f"del_{name}")
        except Exception:  # noqa: BLE001
            pass


def read_refresh_from_cookies() -> Optional[str]:
    if not _cookies_ready():
        return None
    cm = _cookie_manager()
    if cm is None:
        return None
    cookies = cm.get_all(key="auth_cookie_read") or {}
    token = cookies.get(_COOKIE_REFRESH)
    return str(token) if token else None

"""Supabase Auth integration for the Streamlit dashboard."""
from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from src.billing.credits import ensure_user, get_user, monetization_active
from src.config import settings
from src.db.models import User

_SESSION_USER = "auth_user"
_SESSION_ACCESS = "auth_access_token"
_SESSION_REFRESH = "auth_refresh_token"
_PAYMENT_NOTICE = "billing_payment_notice"


def _supabase_client():
    from supabase import create_client

    return create_client(settings.supabase_url.strip(), settings.supabase_anon_key.strip())


def current_user() -> Optional[User]:
    if not monetization_active():
        return None
    uid = st.session_state.get(_SESSION_USER)
    if not uid:
        return None
    return get_user(uid)


def current_user_id() -> Optional[str]:
    user = current_user()
    return user.id if user else None


def is_logged_in() -> bool:
    if not monetization_active():
        return True
    if not settings.auth_enabled:
        return False
    return bool(st.session_state.get(_SESSION_USER))


def logout() -> None:
    for key in (_SESSION_USER, _SESSION_ACCESS, _SESSION_REFRESH):
        st.session_state.pop(key, None)


def _store_session(response: Any) -> User:
    session = response.session
    user_meta = response.user
    user_id = user_meta.id
    email = user_meta.email or ""
    st.session_state[_SESSION_USER] = user_id
    st.session_state[_SESSION_ACCESS] = session.access_token
    st.session_state[_SESSION_REFRESH] = session.refresh_token
    return ensure_user(user_id, email)


def init_auth() -> None:
    """Restore Supabase session from refresh token (long-lived browser tab)."""
    if not monetization_active() or not settings.auth_enabled:
        return
    if st.session_state.get(_SESSION_USER):
        return
    refresh = st.session_state.get(_SESSION_REFRESH)
    if not refresh:
        return
    try:
        client = _supabase_client()
        resp = client.auth.refresh_session(refresh)
        if resp.session:
            _store_session(resp)
    except Exception:  # noqa: BLE001
        logout()


def render_payment_banner() -> None:
    """Show notice after Lemon Squeezy redirect (?payment=success)."""
    if not monetization_active():
        return
    if st.session_state.get(_PAYMENT_NOTICE):
        return
    status = st.query_params.get("payment")
    if status == "success":
        st.session_state[_PAYMENT_NOTICE] = True
        st.success(
            "✅ Płatność przyjęta! Kredyty pojawią się w ciągu ~30 s "
            "(webhook). Kliknij **Odśwież saldo** w panelu bocznym, "
            "jeśli saldo się nie zaktualizowało.",
            icon=":material/payments:",
        )
        try:
            del st.query_params["payment"]
        except Exception:  # noqa: BLE001
            pass


def render_auth_sidebar() -> None:
    if not monetization_active():
        return

    init_auth()

    st.divider()
    st.markdown("**Konto**")

    if not settings.auth_enabled:
        st.warning(
            "Monetyzacja włączona, ale brak SUPABASE_URL / SUPABASE_ANON_KEY. "
            "Zaloguj się po skonfigurowaniu auth.",
            icon=":material/lock:",
        )
        return

    user = current_user()
    if user:
        plan_label = "Pro" if user.plan == "pro" else "Free"
        st.markdown(f"**{user.email}**")
        st.caption(f"Plan: **{plan_label}** · Kredyty: **{user.credits_balance}**")
        if st.button("Odśwież saldo", key="auth_refresh_balance", width="stretch"):
            st.session_state.pop(_PAYMENT_NOTICE, None)
            st.rerun()
        if st.button("Wyloguj", key="auth_logout", width="stretch"):
            logout()
            st.rerun()
        return

    tab_in, tab_up = st.tabs(["Logowanie", "Rejestracja"])
    with tab_in:
        email = st.text_input("E-mail", key="auth_signin_email")
        password = st.text_input("Hasło", type="password", key="auth_signin_pw")
        if st.button("Zaloguj", key="auth_signin_btn", width="stretch"):
            if not email or not password:
                st.error("Podaj e-mail i hasło.")
            else:
                try:
                    client = _supabase_client()
                    resp = client.auth.sign_in_with_password(
                        {"email": email.strip(), "password": password}
                    )
                    _store_session(resp)
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Logowanie nie powiodło się: {exc}")
        with st.expander("Zapomniałeś hasła?"):
            reset_email = st.text_input("E-mail do resetu", key="auth_reset_email")
            if st.button("Wyślij link resetujący", key="auth_reset_btn"):
                if not reset_email.strip():
                    st.error("Podaj e-mail.")
                else:
                    try:
                        client = _supabase_client()
                        client.auth.reset_password_for_email(reset_email.strip())
                        st.info("Sprawdź skrzynkę — link do resetu hasła.")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Nie udało się wysłać linku: {exc}")

    with tab_up:
        email_up = st.text_input("E-mail", key="auth_signup_email")
        password_up = st.text_input("Hasło", type="password", key="auth_signup_pw")
        if st.button("Utwórz konto", key="auth_signup_btn", width="stretch"):
            if not email_up or not password_up:
                st.error("Podaj e-mail i hasło.")
            elif len(password_up) < 8:
                st.error("Hasło musi mieć min. 8 znaków.")
            else:
                try:
                    client = _supabase_client()
                    resp = client.auth.sign_up(
                        {"email": email_up.strip(), "password": password_up}
                    )
                    if resp.session:
                        _store_session(resp)
                        st.success("Konto utworzone!")
                        st.rerun()
                    else:
                        st.info("Sprawdź skrzynkę — potwierdź e-mail, potem się zaloguj.")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Rejestracja nie powiodła się: {exc}")

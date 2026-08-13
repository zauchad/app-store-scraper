"""Supabase Auth integration for the Streamlit dashboard.

Three ways in, cheapest first: Google (one click), e-mail code (no password to
invent), e-mail + password (fallback). E-mail links come back as query params
(``?token_hash=…&type=…``) because Streamlit cannot read URL fragments — see
docs/MONETIZATION.md for the template change that makes this work.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from dashboard import supabase_auth as sb
from dashboard.auth_cookies import (
    clear_auth_cookies,
    read_pkce_verifier,
    read_refresh_from_cookies,
    save_auth_cookies,
    save_pkce_verifier,
)
from src.billing import analytics
from src.billing.credits import ensure_user, get_user, monetization_active
from src.config import settings
from src.db.models import User

_SESSION_USER = "auth_user"
_SESSION_ACCESS = "auth_access_token"
_SESSION_REFRESH = "auth_refresh_token"
_PAYMENT_NOTICE = "billing_payment_notice"
_RECOVERY_TOKEN = "auth_recovery_access"
_OTP_EMAIL = "auth_otp_email"


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
    for key in (_SESSION_USER, _SESSION_ACCESS, _SESSION_REFRESH, _RECOVERY_TOKEN):
        st.session_state.pop(key, None)
    clear_auth_cookies()


def _store_session(session: sb.AuthSession, *, event: str = "") -> User:
    st.session_state[_SESSION_USER] = session.user_id
    st.session_state[_SESSION_ACCESS] = session.access_token
    st.session_state[_SESSION_REFRESH] = session.refresh_token
    save_auth_cookies(session.user_id, session.refresh_token or "")
    user = ensure_user(session.user_id, session.email)
    if event:
        analytics.track(event, user_id=session.user_id)
    return user


def init_auth() -> None:
    """Restore a session, or finish an OAuth / e-mail-link round trip."""
    if not monetization_active() or not settings.auth_enabled:
        return

    if _consume_url_credentials():
        return

    if st.session_state.get(_SESSION_USER):
        return

    refresh = st.session_state.get(_SESSION_REFRESH) or read_refresh_from_cookies()
    if not refresh:
        return
    try:
        _store_session(sb.refresh_session(refresh))
    except sb.AuthError:
        logout()
    except Exception:  # noqa: BLE001
        logout()


def _consume_url_credentials() -> bool:
    """Handle ``?code=`` (Google) and ``?token_hash=`` (e-mail links)."""
    params = st.query_params

    code = params.get("code")
    if code:
        verifier = read_pkce_verifier() or ""
        try:
            del st.query_params["code"]
        except Exception:  # noqa: BLE001
            pass
        if not verifier:
            st.error(
                "Logowanie Google wygasło (brak weryfikatora w tej przeglądarce). "
                "Spróbuj ponownie."
            )
            return False
        try:
            _store_session(sb.exchange_code(code, verifier), event=analytics.LOGIN)
            save_pkce_verifier("")
            return True
        except sb.AuthError as exc:
            st.error(str(exc))
            return False

    token_hash = params.get("token_hash")
    link_type = str(params.get("type") or "")
    if token_hash and link_type:
        try:
            del st.query_params["token_hash"]
            del st.query_params["type"]
        except Exception:  # noqa: BLE001
            pass
        try:
            session = sb.verify_token_hash(token_hash, link_type)
        except sb.AuthError as exc:
            st.error(str(exc))
            return False
        if link_type == "recovery":
            # Do not log in yet — first let the user set a new password.
            st.session_state[_RECOVERY_TOKEN] = session.access_token
            return False
        _store_session(session, event=analytics.SIGNUP)
        st.success("E-mail potwierdzony — jesteś w środku.")
        return True

    return False


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
            "✅ Płatność przyjęta! Kredyty i dostęp nadajemy automatycznie "
            "(zwykle ~10 s). Jeśli nisza nie otworzy się sama, kliknij "
            "**Odśwież saldo** w panelu bocznym.",
            icon=":material/payments:",
        )
        try:
            del st.query_params["payment"]
        except Exception:  # noqa: BLE001
            pass


def render_password_recovery() -> bool:
    """Set-new-password form after a recovery link. True = form is on screen."""
    token = st.session_state.get(_RECOVERY_TOKEN)
    if not token:
        return False

    st.markdown("#### Ustaw nowe hasło")
    pw1 = st.text_input("Nowe hasło", type="password", key="recovery_pw1")
    pw2 = st.text_input("Powtórz hasło", type="password", key="recovery_pw2")
    if st.button("Zapisz hasło", type="primary", key="recovery_save"):
        if len(pw1) < 8:
            st.error("Hasło musi mieć min. 8 znaków.")
        elif pw1 != pw2:
            st.error("Hasła nie są identyczne.")
        else:
            try:
                sb.update_password(token, pw1)
                st.session_state.pop(_RECOVERY_TOKEN, None)
                st.success("Hasło zmienione — zaloguj się nowym hasłem.")
                st.rerun()
            except sb.AuthError as exc:
                st.error(str(exc))
    if st.button("Anuluj", key="recovery_cancel"):
        st.session_state.pop(_RECOVERY_TOKEN, None)
        st.rerun()
    return True


# --------------------------------------------------------------------------- #
#  Login / signup surfaces
# --------------------------------------------------------------------------- #
def render_auth_inline(
    *,
    key_prefix: str = "inline",
    mode: str = "both",
) -> None:
    """Compact login/register panel for the landing page (main content area).

    mode: ``both`` | ``login`` | ``signup``
    """
    if not monetization_active() or not settings.auth_enabled:
        _render_auth_misconfigured()
        return

    init_auth()
    if current_user():
        return
    if render_password_recovery():
        return

    _render_google_button(key_prefix)

    if mode == "login":
        st.markdown("#### Zaloguj się")
        _render_code_form(key_prefix, signup=False)
        with st.expander("Wolisz hasło?"):
            _render_login_form(key_prefix)
    elif mode == "signup":
        st.markdown("#### Załóż darmowe konto")
        _render_code_form(key_prefix, signup=True)
        with st.expander("Wolisz założyć konto hasłem?"):
            _render_signup_form(key_prefix)
    else:
        tab_code, tab_pw = st.tabs(["Kod e-mail (bez hasła)", "Hasło"])
        with tab_code:
            _render_code_form(key_prefix, signup=True)
        with tab_pw:
            sub_in, sub_up = st.tabs(["Logowanie", "Rejestracja"])
            with sub_in:
                _render_login_form(key_prefix)
            with sub_up:
                _render_signup_form(key_prefix)

    _render_legal_footer()


def _render_auth_misconfigured() -> None:
    """Monetization is on but login cannot work — say exactly what is missing."""
    missing = []
    if not settings.supabase_url.strip():
        missing.append("`SUPABASE_URL`")
    if not settings.supabase_anon_key.strip():
        missing.append("`SUPABASE_ANON_KEY`")
    st.error(
        "🔧 **Logowanie nieaktywne** — brakuje: "
        + (", ".join(missing) or "konfiguracji Supabase")
        + ". Ustaw sekrety w Streamlit Cloud, albo ustaw `MONETIZATION_ENABLED=false` "
        "w `.env`, żeby pracować lokalnie bez paywalla.",
        icon=":material/build:",
    )


def _render_google_button(key_prefix: str) -> None:
    if not settings.auth_google_enabled:
        return
    redirect = settings.auth_redirect_url
    if not redirect:
        st.caption("Google: ustaw `APP_BASE_URL`, żeby włączyć logowanie jednym kliknięciem.")
        return
    # Reuse the verifier across reruns: regenerating it would invalidate the
    # challenge baked into an already-rendered button.
    verifier = read_pkce_verifier()
    if not verifier:
        verifier = sb.new_pkce_verifier()
        save_pkce_verifier(verifier)
    url = sb.oauth_authorize_url("google", redirect_to=redirect, code_verifier=verifier)
    st.link_button(
        "Kontynuuj z Google",
        url,
        use_container_width=True,
        type="primary",
    )
    st.caption("Najszybciej — bez hasła i bez potwierdzania e-maila.")
    st.divider()


def _render_code_form(key_prefix: str, *, signup: bool) -> None:
    """Passwordless: e-mail → 6-digit code → logged in."""
    if not settings.auth_otp_enabled:
        if signup:
            _render_signup_form(key_prefix)
        else:
            _render_login_form(key_prefix)
        return

    pending = st.session_state.get(_OTP_EMAIL, "")
    email = st.text_input(
        "E-mail",
        value=pending,
        key=f"{key_prefix}_otp_email",
        placeholder="ty@example.com",
    )
    if st.button(
        "Wyślij kod na e-mail",
        key=f"{key_prefix}_otp_send",
        type="primary",
        width="stretch",
    ):
        if not email.strip():
            st.error("Podaj e-mail.")
        else:
            try:
                sb.send_email_code(email.strip(), create_user=True)
                st.session_state[_OTP_EMAIL] = email.strip()
                st.success("Kod wysłany — sprawdź skrzynkę (waży kilka sekund).")
            except sb.AuthError as exc:
                st.error(str(exc))

    if st.session_state.get(_OTP_EMAIL):
        code = st.text_input(
            "Kod z e-maila",
            key=f"{key_prefix}_otp_code",
            max_chars=8,
            placeholder="123456",
        )
        if st.button(
            "Zaloguj kodem",
            key=f"{key_prefix}_otp_verify",
            type="primary",
            width="stretch",
        ):
            if not code.strip():
                st.error("Wpisz kod z e-maila.")
            else:
                try:
                    session = sb.verify_email_code(
                        st.session_state[_OTP_EMAIL], code.strip()
                    )
                    existing = get_user(session.user_id) is not None
                    _store_session(
                        session,
                        event=analytics.LOGIN if existing else analytics.SIGNUP,
                    )
                    st.session_state.pop(_OTP_EMAIL, None)
                    st.rerun()
                except sb.AuthError as exc:
                    st.error(str(exc))


def _render_login_form(key_prefix: str) -> None:
    email = st.text_input("E-mail", key=f"{key_prefix}_signin_email")
    password = st.text_input("Hasło", type="password", key=f"{key_prefix}_signin_pw")
    if st.button(
        "Zaloguj i otwórz Radar",
        key=f"{key_prefix}_signin_btn",
        type="primary",
        width="stretch",
    ):
        if not email or not password:
            st.error("Podaj e-mail i hasło.")
        else:
            try:
                _store_session(
                    sb.sign_in_password(email.strip(), password),
                    event=analytics.LOGIN,
                )
                st.rerun()
            except sb.AuthError as exc:
                st.error(f"Logowanie nie powiodło się: {exc}")
    with st.expander("Zapomniałeś hasła?"):
        reset_email = st.text_input("E-mail do resetu", key=f"{key_prefix}_reset_email")
        if st.button("Wyślij link resetujący", key=f"{key_prefix}_reset_btn"):
            if not reset_email.strip():
                st.error("Podaj e-mail.")
            else:
                try:
                    sb.send_password_reset(
                        reset_email.strip(),
                        redirect_to=settings.auth_redirect_url,
                    )
                    st.info("Sprawdź skrzynkę — link do resetu hasła.")
                except sb.AuthError as exc:
                    st.error(f"Nie udało się wysłać linku: {exc}")


def _render_signup_form(key_prefix: str) -> None:
    email_up = st.text_input("E-mail", key=f"{key_prefix}_signup_email")
    password_up = st.text_input("Hasło", type="password", key=f"{key_prefix}_signup_pw")
    if st.button(
        "Utwórz darmowe konto",
        key=f"{key_prefix}_signup_btn",
        type="primary",
        width="stretch",
    ):
        if not email_up or not password_up:
            st.error("Podaj e-mail i hasło.")
        elif len(password_up) < 8:
            st.error("Hasło musi mieć min. 8 znaków.")
        else:
            try:
                session = sb.sign_up(
                    email_up.strip(),
                    password_up,
                    redirect_to=settings.auth_redirect_url,
                )
                if session is not None:
                    _store_session(session, event=analytics.SIGNUP)
                    st.rerun()
                else:
                    st.info(
                        "Sprawdź skrzynkę — **potwierdź e-mail**, wrócisz tu "
                        "zalogowany. Nie chcesz czekać? Użyj kodu e-mail lub Google."
                    )
            except sb.AuthError as exc:
                st.error(f"Rejestracja nie powiodła się: {exc}")


def render_auth_sidebar() -> None:
    if not monetization_active():
        return

    init_auth()

    st.divider()
    st.markdown("**Konto**")

    if not settings.auth_enabled:
        _render_auth_misconfigured()
        return

    user = current_user()
    if user:
        plan_label = "Pro" if user.plan == "pro" else "Free"
        st.markdown(f"**{user.email}**")
        st.caption(f"Plan: **{plan_label}** · Kredyty: **{user.credits_balance}**")
        if st.button("Odśwież saldo", key="auth_refresh_balance", width="stretch"):
            st.session_state.pop(_PAYMENT_NOTICE, None)
            st.rerun()
        portal = settings.lemonsqueezy_customer_portal_url.strip()
        if portal:
            st.link_button("Portal klienta", portal, use_container_width=True)
        if st.button("Wyloguj", key="auth_logout", width="stretch"):
            logout()
            st.rerun()
        return

    render_auth_inline(key_prefix="sidebar", mode="both")


def _render_legal_footer() -> None:
    links = []
    if settings.legal_terms_url.strip():
        links.append(f"[Regulamin]({settings.legal_terms_url.strip()})")
    if settings.legal_privacy_url.strip():
        links.append(f"[Prywatność]({settings.legal_privacy_url.strip()})")
    if settings.legal_refund_url.strip():
        links.append(f"[Zwroty]({settings.legal_refund_url.strip()})")
    if links:
        st.caption(" · ".join(links))
    else:
        st.caption("Regulamin i zwroty: zakładka **Konto**.")

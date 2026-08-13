"""Paywall UI: unlock niches, buy credits, Pro CSV gate.

Design rule: the distance between "I want this" and "I can read it" must be as
short as the payment provider allows. Checkout links therefore carry the buyer's
e-mail *and* the niche they are looking at, the webhook unlocks that niche on
arrival, and the gate polls for it so the content appears in the open tab
without the user hunting for a refresh button.
"""
from __future__ import annotations

from urllib.parse import quote

import streamlit as st

from dashboard.auth import current_user, is_logged_in
from src.billing import analytics
from src.billing.credits import (
    CREDIT_COST_NICHE_UNLOCK,
    can_export_csv,
    has_pro_access,
    is_niche_unlocked,
    monetization_active,
    unlock_niche,
)
from src.config import settings

RADAR_FREE_APP_ROWS = 3
RADAR_FREE_NICHE_ROWS = 5

# How long the gate keeps watching for an incoming payment (seconds).
PAYMENT_WATCH_SECONDS = 180
PAYMENT_POLL_SECONDS = 5


def _pro_access() -> bool:
    user = current_user()
    return has_pro_access(user.id if user else None)


def _credits_pl(n: int) -> str:
    """Polish plural: 1 kredyt, 2–4 kredyty, 5+ kredytów."""
    if n == 1:
        return "1 kredyt"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} kredyty"
    return f"{n} kredytów"


def _track_once(event: str, *, user_id: str, detail: str) -> None:
    """Funnel steps are per-session facts, not per-rerun — Streamlit reruns a lot."""
    marker = f"_tracked_{event}_{detail}"
    if st.session_state.get(marker):
        return
    st.session_state[marker] = True
    analytics.track(event, user_id=user_id, detail=detail)


def is_content_unlocked(niche_key: str) -> bool:
    """Whether full paid content for this niche key is accessible."""
    if not monetization_active():
        return True
    user = current_user()
    if user is None:
        return False
    return is_niche_unlocked(user.id, niche_key)


def _locked_label() -> str:
    return "🔒 odblokuj"


def limit_radar_apps(df, *, limit: int = RADAR_FREE_APP_ROWS):
    """Return (visible_df, hidden_count) for Radar app-name tables."""
    if _pro_access() or df is None or getattr(df, "empty", True):
        return df, 0
    hidden = max(0, len(df) - limit)
    return df.head(limit), hidden


def limit_radar_niches(df, *, limit: int = RADAR_FREE_NICHE_ROWS):
    """Return (visible_df, hidden_count) for the category decision table."""
    if _pro_access() or df is None or getattr(df, "empty", True):
        return df, 0
    hidden = max(0, len(df) - limit)
    return df.head(limit), hidden


def render_radar_pro_upsell(*, hidden: int, kind: str = "aplikacji") -> None:
    if hidden <= 0 or _pro_access():
        return
    st.caption(
        f"🔒 **+{hidden}** więcej {kind} w planie **Pro** ($39/mies.) — "
        "pełne nazwy, deweloperzy, CSV i 15 kredytów/mies."
    )
    user = current_user()
    if user is None and monetization_active():
        st.caption("Zaloguj się w panelu bocznym, aby wykupić Pro.")
    elif user and not has_pro_access(user.id):
        render_checkout_links(context="radar")


def _checkout_url(base: str, user, *, niche_key: str = "") -> str:
    """Prefill the checkout so the buyer types as little as possible.

    ``checkout[custom][niche_key]`` is what lets the webhook hand over access to
    the exact niche that triggered the purchase.
    """
    url = base.strip()
    if not url:
        return ""
    # Values are encoded (keyword niches contain spaces); Lemon Squeezy expects the
    # bracketed parameter *names* literal.
    params = [f"checkout[custom][user_id]={quote(str(user.id), safe='')}"]
    if user.email:
        params.append(f"checkout[email]={quote(user.email, safe='')}")
    if niche_key:
        params.append(f"checkout[custom][niche_key]={quote(niche_key, safe='')}")
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}" + "&".join(params)


def render_checkout_links(*, niche_key: str = "", context: str = "") -> None:
    """Pricing buttons. Pro is the highlighted default; single credit is the taste."""
    user = current_user()
    if user is None:
        st.caption("Zaloguj się, aby kupić kredyty.")
        return

    _track_once(
        analytics.CHECKOUT_VIEW,
        user_id=user.id,
        detail=context or niche_key or "generic",
    )

    options = [
        (
            "Pro — $39/mies.",
            settings.lemonsqueezy_checkout_pro,
            f"{settings.pro_monthly_credits} kredytów/mies. · pełny Radar · CSV · "
            "anulujesz kiedy chcesz",
            "primary",
        ),
        (
            "1 nisza — $19",
            settings.lemonsqueezy_checkout_1_credit,
            "Jednorazowo, dostęp na zawsze",
            "secondary",
        ),
    ]
    if settings.credit_pack_enabled:
        options.append(
            (
                "5 nisz — $49",
                settings.lemonsqueezy_checkout_5_credits,
                "Pakiet pięciu odblokowań",
                "secondary",
            )
        )

    cols = st.columns(len(options))
    for col, (label, base, sub, kind) in zip(cols, options):
        url = _checkout_url(base, user, niche_key=niche_key)
        with col:
            if url:
                st.link_button(label, url, use_container_width=True, type=kind)
                st.caption(sub)
            else:
                st.caption(f"{label} (skonfiguruj checkout URL)")

    st.caption(
        "Płatność przez Lemon Squeezy (karta / PayPal). Dostęp nadajemy "
        "automatycznie po zaksięgowaniu — nie musisz nic klikać."
    )


def _render_payment_watcher(niche_key: str, user_id: str) -> None:
    """Poll for an incoming payment so the content opens in this very tab.

    Bounded on purpose: after PAYMENT_WATCH_SECONDS the polling stops hitting the
    DB and falls back to a manual button, so an abandoned tab costs nothing.
    """
    state_key = f"pay_watch_{niche_key}"
    max_ticks = max(1, PAYMENT_WATCH_SECONDS // PAYMENT_POLL_SECONDS)

    @st.fragment(run_every=PAYMENT_POLL_SECONDS)
    def _watch() -> None:
        ticks = st.session_state.get(state_key, 0) + 1
        st.session_state[state_key] = ticks
        if ticks > max_ticks:
            st.caption("Płatność nadal nie widoczna?")
            if st.button("Sprawdź teraz", key=f"pay_check_{niche_key}"):
                st.session_state[state_key] = 0
                st.rerun(scope="app")
            return
        if is_niche_unlocked(user_id, niche_key) or has_pro_access(user_id):
            st.rerun(scope="app")
        st.caption("🔄 Czekam na potwierdzenie płatności — odświeżę stronę sam.")

    _watch()


def render_unlock_gate(
    *,
    niche_key: str,
    niche_label: str,
    content: str = "analiza",
    teaser: str = "",
) -> bool:
    """Return True if premium content may be shown.

    content: short label for unlock copy — "analiza" (category) or "mikro-nisza".
    teaser: one concrete finding from the locked part, to make the value real.
    """
    if not monetization_active():
        return True

    if content == "mikro-nisza":
        bullets = (
            "- Geo-radar (US vs PL i inne rynki)\n"
            "- Popyt na Reddicie („szukam apki do…\")\n"
            "- Kandydaci „sklonuj i ulepsz” + pełna lista konkurentów\n"
            "- Pain mining z recenzji konkurencji"
        )
    else:
        bullets = (
            "- Rozbicie score i ekonomia wejścia\n"
            "- Analiza recenzji (pain mining) + AI insights\n"
            "- Kandydaci „sklonuj i ulepsz” + raport Markdown\n"
            "- Test 5 pytań i pełna lista konkurentów"
        )

    if not is_logged_in():
        st.warning(
            "🔒 **Pełna analiza wymaga konta.** Rejestracja trwa ~20 s "
            "(Google lub kod e-mail) i pierwsze odblokowanie jest **darmowe**."
            if settings.signup_bonus_credits > 0
            else "🔒 **Pełna analiza wymaga konta.** Zaloguj się w panelu bocznym, "
            "a potem odblokuj za 1 kredyt.",
            icon=":material/lock:",
        )
        with st.container(border=True):
            st.markdown("#### Co dostaniesz po odblokowaniu?")
            st.markdown(bullets)
            if teaser:
                st.markdown(f"🕳️ **Podgląd:** {teaser}")
        return False

    user = current_user()
    if user is None:
        return False

    if is_niche_unlocked(user.id, niche_key):
        return True

    _track_once(analytics.GATE_VIEW, user_id=user.id, detail=niche_key)

    what = "mikro-niszy" if content == "mikro-nisza" else "niszy"
    free_credit = user.credits_balance >= CREDIT_COST_NICHE_UNLOCK

    if free_credit:
        st.success(
            f"🔓 **{niche_label}** — masz {_credits_pl(user.credits_balance)}. "
            f"Odblokuj pełną analizę {what} jednym kliknięciem (dostęp na zawsze).",
            icon=":material/lock_open:",
        )
    else:
        st.info(
            f"🔒 **{niche_label}** — podgląd darmowy powyżej. Pełna analiza {what} "
            f"kosztuje **{_credits_pl(CREDIT_COST_NICHE_UNLOCK)}** "
            "(jednorazowo, na zawsze).",
            icon=":material/lock_open:",
        )

    with st.container(border=True):
        st.markdown("#### Co odblokujesz")
        st.markdown(bullets)
        if teaser:
            st.markdown(f"🕳️ **Podgląd:** {teaser}")

    if free_credit:
        if st.button(
            f"Odblokuj „{niche_label}” ({CREDIT_COST_NICHE_UNLOCK} kredyt)",
            type="primary",
            key=f"unlock_{niche_key}",
            width="stretch",
        ):
            try:
                unlock_niche(user.id, niche_key)
                analytics.track(analytics.UNLOCK, user_id=user.id, detail=niche_key)
                st.success("Nisza odblokowana!")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        left = user.credits_balance - CREDIT_COST_NICHE_UNLOCK
        st.caption(f"Zostanie Ci: **{_credits_pl(left)}**")
    else:
        st.markdown("**Wybierz plan — dostęp otworzy się tutaj automatycznie**")
        render_checkout_links(niche_key=niche_key, context=f"gate:{content}")
        _render_payment_watcher(niche_key, user.id)

    return False


def render_csv_gate() -> bool:
    """Return True if CSV download button should be shown."""
    user = current_user()
    uid = user.id if user else None
    if can_export_csv(uid):
        return True
    st.caption(
        "🔒 Eksport CSV dostępny w planie **Pro** ($39/mies.). "
        "Zaloguj się i wykup subskrypcję w panelu bocznym."
    )
    if user and not can_export_csv(user.id):
        render_checkout_links(context="csv")
    return False

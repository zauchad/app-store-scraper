"""Paywall UI: unlock niches, buy credits, Pro CSV gate."""
from __future__ import annotations

import streamlit as st

from dashboard.auth import current_user, is_logged_in
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


def _pro_access() -> bool:
    user = current_user()
    return has_pro_access(user.id if user else None)


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
        render_checkout_links()


def _checkout_url(base: str, user_id: str) -> str:
    url = base.strip()
    if not url:
        return ""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}checkout[custom][user_id]={user_id}"


def render_checkout_links() -> None:
    user = current_user()
    if user is None:
        st.caption("Zaloguj się, aby kupić kredyty.")
        return

    links = [
        ("1 kredyt — $19", settings.lemonsqueezy_checkout_1_credit),
        ("5 kredytów — $49", settings.lemonsqueezy_checkout_5_credits),
        ("Pro — $39/mies. (15 kredytów)", settings.lemonsqueezy_checkout_pro),
    ]
    cols = st.columns(len(links))
    for col, (label, base) in zip(cols, links):
        url = _checkout_url(base, user.id)
        if url:
            col.link_button(label, url, use_container_width=True)
        else:
            col.caption(f"{label} (skonfiguruj checkout URL)")


def render_unlock_gate(
    *,
    niche_key: str,
    niche_label: str,
    content: str = "analiza",
) -> bool:
    """Return True if premium content may be shown.

    content: short label for unlock copy — "analiza" (category) or "mikro-nisza".
    """
    if not monetization_active():
        return True

    if not is_logged_in():
        st.warning(
            "🔒 **Pełna analiza wymaga konta.** Zaloguj się w panelu bocznym, "
            "a potem odblokuj za 1 kredyt.",
            icon=":material/lock:",
        )
        with st.container(border=True):
            if content == "mikro-nisza":
                st.markdown("#### Co dostaniesz po odblokowaniu?")
                st.markdown(
                    "- Geo-radar (US vs PL i inne rynki)\n"
                    "- Popyt na Reddicie („szukam apki do…\")\n"
                    "- Kandydaci „sklonuj i ulepsz” + pełna lista konkurentów\n"
                    "- Pain mining z recenzji konkurencji"
                )
            else:
                st.markdown("#### Co dostaniesz po odblokowaniu?")
                st.markdown(
                    "- Rozbicie score i ekonomia wejścia\n"
                    "- Analiza recenzji (pain mining) + AI insights\n"
                    "- Kandydaci „sklonuj i ulepsz” + raport Markdown\n"
                    "- Test 5 pytań i pełna lista konkurentów"
                )
        return False

    user = current_user()
    if user is None:
        return False

    if is_niche_unlocked(user.id, niche_key):
        return True

    label = "mikro-niszy" if content == "mikro-nisza" else "niszy"
    st.info(
        f"🔒 **{niche_label}** — podgląd darmowy powyżej. Pełna {label} kosztuje "
        f"**{CREDIT_COST_NICHE_UNLOCK} kredyt** (jednorazowo, na zawsze).",
        icon=":material/lock_open:",
    )

    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Twoje kredyty", user.credits_balance)
        if st.button(
            f"Odblokuj ({CREDIT_COST_NICHE_UNLOCK} kredyt)",
            type="primary",
            key=f"unlock_{niche_key}",
            width="stretch",
        ):
            try:
                unlock_niche(user.id, niche_key)
                st.success("Nisza odblokowana!")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    with c2:
        st.markdown("**Kup kredyty**")
        render_checkout_links()

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
    user = current_user()
    if user and not can_export_csv(user.id):
        render_checkout_links()
    return False

"""Paywall UI: unlock niches, buy credits, Pro CSV gate."""
from __future__ import annotations

import streamlit as st

from dashboard.auth import current_user, is_logged_in
from src.billing.credits import (
    CREDIT_COST_NICHE_UNLOCK,
    can_export_csv,
    is_niche_unlocked,
    monetization_active,
    unlock_niche,
)
from src.config import settings


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


def render_unlock_gate(*, niche_key: str, niche_label: str) -> bool:
    """Return True if premium Analiza content may be shown."""
    if not monetization_active():
        return True

    if not is_logged_in():
        st.warning(
            "🔒 **Pełna analiza wymaga konta.** Zaloguj się w panelu bocznym, "
            "a potem odblokuj tę niszę za 1 kredyt.",
            icon=":material/lock:",
        )
        with st.container(border=True):
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

    st.info(
        f"🔒 **{niche_label}** — podgląd darmowy powyżej. Pełna analiza kosztuje "
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

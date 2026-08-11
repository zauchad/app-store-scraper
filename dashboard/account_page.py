"""Account page — credits, unlocks, ledger, legal links."""
from __future__ import annotations

import streamlit as st

from dashboard.auth import current_user, is_logged_in
from dashboard.billing_ui import render_checkout_links
from dashboard.legal_content import PRIVACY_PL, REFUND_PL, SUPPORT_PLAYBOOK_PL, TERMS_PL
from src.billing.account import format_niche_key, list_credit_ledger, list_unlocked_niches
from src.billing.credits import monetization_active
from src.billing.usage import keyword_scans_remaining
from src.config import settings


def page_account() -> None:
    st.markdown("## Konto i rozliczenia")

    if not monetization_active():
        st.info("Monetyzacja wyłączona — pełny dostęp bez logowania (tryb dev).")
        return

    if not is_logged_in():
        st.warning("Zaloguj się w panelu bocznym, aby zobaczyć konto.")
        return

    user = current_user()
    if user is None:
        st.warning("Sesja wygasła — zaloguj się ponownie.")
        return

    plan = "Pro" if user.plan == "pro" else "Free"
    c1, c2, c3 = st.columns(3)
    c1.metric("Plan", plan)
    c2.metric("Kredyty", user.credits_balance)
    remaining = keyword_scans_remaining(user.id)
    c3.metric("Skany mikro-nisz dziś", "∞" if remaining is None else remaining)

    st.divider()
    st.markdown("#### Odblokowane nisze")
    unlocks = list_unlocked_niches(user.id)
    if not unlocks:
        st.caption("Brak odblokowań — kup kredyt na stronie Analiza lub Mikro-nisze.")
    else:
        for u in unlocks:
            st.markdown(f"- **{format_niche_key(u.niche_key)}** · {u.unlocked_at:%Y-%m-%d}")

    st.markdown("#### Historia kredytów")
    ledger = list_credit_ledger(user.id)
    if not ledger:
        st.caption("Brak ruchów na koncie.")
    else:
        rows = [
            {
                "Data": e.created_at.strftime("%Y-%m-%d %H:%M"),
                "Zmiana": f"{e.delta:+d}",
                "Powód": e.reason,
                "Ref": e.reference_id or "—",
            }
            for e in ledger
        ]
        st.dataframe(rows, width="stretch", hide_index=True)

    st.divider()
    st.markdown("#### Kup kredyty / Pro")
    render_checkout_links()

    portal = settings.lemonsqueezy_customer_portal_url.strip()
    if portal:
        st.link_button(
            "Portal klienta (faktury, anuluj Pro)",
            portal,
            use_container_width=True,
        )

    if settings.support_email.strip():
        st.caption(f"Wsparcie: **{settings.support_email.strip()}**")

    with st.expander("Płatność OK, brak kredytów?"):
        st.markdown(SUPPORT_PLAYBOOK_PL)

    with st.expander("Regulamin"):
        if settings.legal_terms_url.strip():
            st.link_button("Pełny regulamin", settings.legal_terms_url.strip())
        st.markdown(TERMS_PL)

    with st.expander("Prywatność"):
        if settings.legal_privacy_url.strip():
            st.link_button("Pełna polityka", settings.legal_privacy_url.strip())
        st.markdown(PRIVACY_PL)

    with st.expander("Zwroty"):
        if settings.legal_refund_url.strip():
            st.link_button("Pełna polityka zwrotów", settings.legal_refund_url.strip())
        st.markdown(REFUND_PL)

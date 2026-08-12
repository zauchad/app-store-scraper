"""Pre-login product landing — Polish marketing copy + inline signup."""
from __future__ import annotations

import streamlit as st

from dashboard.auth import render_auth_inline

_SESSION_AUTH_PANEL = "landing_auth_panel"  # "signup" | "login" | None


def render_landing_page() -> None:
    """Full product page shown before login when monetization is active."""
    st.markdown(
        """
        <div class="mi-hero">
          <div class="mi-hero-badge">Market Intel</div>
          <h1>Znajdź niszę w App Store,<br><em>zanim zbudujesz kolejną apkę na ślepo</em></h1>
          <p class="mi-hero-sub">
            Codzienny skan kategorii, Opportunity Score, analiza bólu użytkowników
            i do pięciu konkretnych celów do ulepszenia — bez ręcznego czytania setek recenzji.
          </p>
          <p class="mi-trust">
            App Store · aktualizacja codziennie · darmowy Radar · bez karty
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Załóż konto — otwórz Radar",
            type="primary",
            use_container_width=True,
            key="landing_cta_primary",
        ):
            st.session_state[_SESSION_AUTH_PANEL] = "signup"
    with c2:
        if st.button(
            "Mam konto",
            use_container_width=True,
            key="landing_cta_login",
        ):
            st.session_state[_SESSION_AUTH_PANEL] = "login"

    auth_panel = st.session_state.get(_SESSION_AUTH_PANEL)
    if auth_panel:
        with st.container(border=True):
            render_auth_inline(key_prefix="landing", mode=auth_panel)

    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Dlaczego top-charty kłamią</div>
          <div class="mi-section-sub">Większość founderów rezygnuje, zanim dotrze do realnych okazji.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    p1, p2, p3 = st.columns(3)
    problems = [
        (
            "mi-card-accent-pain",
            "Kategoria wygląda na zamkniętą",
            "Finance = 3/100 na poziomie kategorii — mikro-nisza „budgeting for couples” "
            "może mieć 55/100. Giganci maskują luki poniżej.",
        ),
        (
            "mi-card-accent-caution",
            "Recenzje 1–3★ to sygnał — nikt ich nie czyta",
            "Crashe, subskrypcje, brak synchronizacji — mapa funkcji, których konkurencja "
            "nie dowozi. Ręcznie to setki godzin.",
        ),
        (
            "mi-card-accent-opp",
            "Czy ludzie w tej niszy płacą?",
            "Mierzymy, ile top-free apek jest też w top-grossing — darmowy dowód "
            "monetyzacji rynku, którego większość narzędzi nie pokazuje.",
        ),
    ]
    for col, (accent, title, body) in zip((p1, p2, p3), problems):
        with col:
            st.markdown(
                f"""
                <div class="mi-card {accent}">
                  <h4>{title}</h4>
                  <p>{body}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Trzy warstwy</div>
          <div class="mi-section-sub">Od przeglądu rynku po głęboką analizę jednej niszy.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    l1, l2, l3 = st.columns(3)
    layers = [
        (
            "mi-card-accent-brand",
            "mi-tag-brand",
            "Radar",
            "Darmowy podgląd",
            "Ranking nisz z Opportunity Score, mapą popytu vs luki jakościowej "
            "i szacunkiem instalacji przy Twoim budżecie.",
            "Free: top 5 · Pro: pełna lista + CSV",
        ),
        (
            "mi-card-accent-pain",
            "mi-tag-opp",
            "Analiza",
            "1 kredyt · na zawsze",
            "Pain mining z 100k+ recenzji, AI insights, kandydaci do ulepszenia, "
            "checklist weryfikacji, eksport .md.",
            "Free: podgląd · Paid: pełny raport",
        ),
        (
            "mi-card-accent-sky",
            "mi-tag-sky",
            "Mikro-nisze",
            "1 kredyt · na zawsze",
            "Long-tail poniżej top-chartów: geo-radar, popyt z autocomplete, "
            "Reddit, pełna lista konkurentów pod frazą.",
            "Free: ranking · Paid: deep-dive",
        ),
    ]
    for col, (accent, tag_cls, title, tag, desc, tier) in zip((l1, l2, l3), layers):
        with col:
            st.markdown(
                f"""
                <div class="mi-card {accent}">
                  <span class="mi-tag {tag_cls}">{tag}</span>
                  <h4>{title}</h4>
                  <p>{desc}</p>
                  <p class="mi-tier-note">{tier}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Jak to działa</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    s1, s2, s3, s4 = st.columns(4)
    steps = [
        ("01", "Skan", "Codziennie wszystkie kategorie App Store."),
        ("02", "Score", "Popyt × luka × nasycenie × momentum → 0–100."),
        ("03", "Pain mining", "Analiza recenzji: crashe, subskrypcje, braki."),
        ("04", "Plan", "5 celów do ulepszenia + szansa przy Twoim budżecie."),
    ]
    for col, (num, title, body) in zip((s1, s2, s3, s4), steps):
        with col:
            st.markdown(
                f"""
                <div class="mi-card">
                  <div class="mi-step-num">{num}</div>
                  <h4>{title}</h4>
                  <p>{body}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.caption(
        "Gemini tylko na TOP niszach — reszta to deterministyczne obliczenia na pełnym korpusie."
    )

    st.markdown(
        """
        <div class="mi-callout">
          <span class="mi-tag mi-tag-opp">Przykład</span>
          <h4>Kategoria vs mikro-nisza</h4>
          <p>
            <span class="mi-stat-bad">Finance (kategoria): 3/100</span> — rynek gigantów.<br>
            <span class="mi-stat-good">„budgeting for couples”: 55/100</span> — zero gigantów,
            słaba konkurencja. Tego nie widać na top-chartach.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Cennik</div>
          <div class="mi-section-sub">Kredyt = jedna nisza na zawsze.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <table class="mi-price-table">
          <thead>
            <tr><th>Plan</th><th>Cena</th><th>Zakres</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>Free</td>
              <td>$0</td>
              <td>Radar (top 5), podgląd Analizy i Mikro-nisz, 3 skany/dzień</td>
            </tr>
            <tr>
              <td>1 kredyt</td>
              <td class="mi-price-highlight">$19</td>
              <td>Pełna Analiza lub Mikro-nisza — jednorazowo</td>
            </tr>
            <tr>
              <td>5 kredytów</td>
              <td class="mi-price-highlight">$49</td>
              <td>Pięć odblokowań (−18% vs pojedyncze)</td>
            </tr>
            <tr>
              <td>Pro</td>
              <td class="mi-price-highlight">$39/mo</td>
              <td>15 kredytów/mies. · pełny Radar · CSV</td>
            </tr>
          </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.caption("Płatność dopiero po założeniu konta i wyborze niszy.")

    st.markdown(
        '<div class="mi-section"><div class="mi-section-title">FAQ</div></div>',
        unsafe_allow_html=True,
    )

    with st.expander("Czy potrzebuję konta Apple Developer?"):
        st.markdown(
            "Nie. Publiczne dane App Store wystarczą do researchu. "
            "Konto dev potrzebne dopiero przy publikacji."
        )
    with st.expander("Czy gwarantujecie sukces aplikacji?"):
        st.markdown(
            "Nie — to narzędzie badawcze. Sygnały popytu i luki konkurencji, "
            "decyzja należy do Ciebie."
        )
    with st.expander("US czy Polska?"):
        st.markdown(
            "Domyślnie US. PL też dostępne. Geo-radar porównuje rynki — "
            "przydatne przy budowaniu z PL na USA."
        )
    with st.expander("Co jeśli nisza mi nie pasuje po odblokowaniu?"):
        st.markdown(
            "Przed odblokowaniem masz darmowy podgląd. Zużyty kredyt = dostarczona treść — "
            "szczegóły w zakładce Konto."
        )
    with st.expander("Czy muszę płacić od razu?"):
        st.markdown(
            "Nie. Załóż konto, przejrzyj Radar. Płatność tylko przy pełnej analizie lub Pro."
        )

    if not auth_panel:
        st.markdown(
            """
            <div class="mi-cta-box">
              <h3>Zacznij od darmowego Radaru</h3>
              <p>Bez karty. Bez zobowiązań.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

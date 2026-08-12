"""Pre-login product landing — Polish marketing copy + inline signup."""
from __future__ import annotations

import streamlit as st

from dashboard.auth import render_auth_inline
from dashboard.theme import ACCENT, PRIMARY, TEXT_MUTED

_SESSION_AUTH_FOCUS = "landing_auth_focus"


def _focus_auth() -> None:
    st.session_state[_SESSION_AUTH_FOCUS] = True


def render_landing_page() -> None:
    """Full product page shown before login when monetization is active."""
    st.markdown(
        f"""
        <div class="mi-hero">
          <div class="mi-hero-badge">App Store Niche Radar</div>
          <h1>Znajdź niszę w App Store,<br><span> zanim zbudujesz kolejną apkę na ślepo</span></h1>
          <p class="mi-hero-sub">
            Codzienny skan wszystkich kategorii → Opportunity Score → analiza bólu
            użytkowników → do 5 konkretnych celów „sklonuj i ulepsz”. Bez czytania
            setek recenzji ręcznie.
          </p>
          <p class="mi-trust">
            Dane z App Store · aktualizowane codziennie · darmowy Radar bez karty
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Otwórz darmowy Radar — załóż konto",
            type="primary",
            use_container_width=True,
            key="landing_cta_primary",
        ):
            _focus_auth()
            st.rerun()
    with c2:
        if st.button(
            "Mam konto — zaloguj się",
            use_container_width=True,
            key="landing_cta_login",
        ):
            _focus_auth()
            st.rerun()

    # ---- Problem ----
    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Dlaczego top-charty kłamią</div>
          <div class="mi-section-sub">Większość founderów rezygnuje, zanim dotrą do prawdziwych okazji.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    p1, p2, p3 = st.columns(3)
    problems = [
        (
            "📊",
            "Kategoria wygląda na zamkniętą",
            "Finance = 3/100 na poziomie kategorii — ale mikro-nisza "
            "„budgeting for couples” może mieć 55/100. Giganci maskują luki poniżej.",
        ),
        (
            "⭐",
            "Recenzje 1–3★ to złoto — nikt ich nie czyta",
            "Crashe, agresywne subskrypcje, brak synchronizacji — to gotowa mapa "
            "funkcji, których konkurencja nie dowozi. Ręcznie? Setki godzin.",
        ),
        (
            "💳",
            "„Czy ludzie w tej niszy płacą?”",
            "Większość narzędzi tego nie pokazuje. My mierzymy, ile top-free apek "
            "jest też w top-grossing — jedyny darmowy dowód monetyzacji rynku.",
        ),
    ]
    for col, (icon, title, body) in zip((p1, p2, p3), problems):
        with col:
            st.markdown(
                f"""
                <div class="mi-card">
                  <div class="mi-card-icon">{icon}</div>
                  <h4>{title}</h4>
                  <p>{body}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ---- Product layers ----
    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Trzy warstwy inteligencji</div>
          <div class="mi-section-sub">Od szybkiego przeglądu po głęboką analizę jednej niszy.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    l1, l2, l3 = st.columns(3)
    layers = [
        (
            "📡 Radar",
            "mi-card-free",
            "mi-tag-free",
            "Darmowy podgląd",
            "Ranking wszystkich nisz App Store z Opportunity Score, mapą popytu vs luki "
            "jakościowej i szacunkiem instalacji przy Twoim budżecie marketingowym.",
            "Free: top 5 nisz · Pro: pełna lista + CSV",
        ),
        (
            "🔬 Analiza",
            "mi-card-paid",
            "mi-tag-paid",
            "1 kredyt = nisza na zawsze",
            "Pełny raport kategorii: pain mining z 100k+ recenzji, AI insights, "
            "kandydaci „sklonuj i ulepsz”, checklist 5 pytań weryfikacji, eksport .md.",
            "Free: podgląd score + wstęp · Paid: pełna analiza",
        ),
        (
            "🎯 Mikro-nisze",
            "mi-card-paid",
            "mi-tag-paid",
            "1 kredyt = fraza na zawsze",
            "Long-tail poniżej top-chartów: geo-radar US vs PL, popyt z autocomplete, "
            "Reddit „szukam apki do…”, pełna lista konkurentów pod frazą.",
            "Free: ranking + podgląd · Paid: pełny deep-dive",
        ),
    ]
    for col, (icon_title, card_cls, tag_cls, tag, desc, tier) in zip((l1, l2, l3), layers):
        with col:
            st.markdown(
                f"""
                <div class="mi-card {card_cls}">
                  <span class="{tag_cls}">{tag}</span>
                  <h4>{icon_title}</h4>
                  <p>{desc}</p>
                  <p style="margin-top:0.75rem;font-size:0.8rem;color:{TEXT_MUTED};">{tier}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ---- How it works ----
    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Jak to działa</div>
          <div class="mi-section-sub">Cztery kroki — bez ręcznego researchu i bez zgadywania.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    s1, s2, s3, s4 = st.columns(4)
    steps = [
        ("1", "Skan", "Codziennie wszystkie kategorie App Store (gry wykluczone domyślnie)."),
        ("2", "Score", "Popyt × luka jakościowa × nasycenie × momentum → Opportunity 0–100."),
        ("3", "Pain mining", "Deterministyczna analiza recenzji: crashe, subskrypcje, braki funkcji."),
        ("4", "Plan", "5 kandydatów do ulepszenia + szansa sukcesu przy Twoim budżecie reklam."),
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
        "AI (Gemini) uruchamiane tylko na TOP niszach — reszta to tanie, "
        "powtarzalne obliczenia na pełnym korpusie danych."
    )

    # ---- Example callout ----
    st.markdown(
        f"""
        <div class="mi-card" style="border-color:rgba(251,191,36,0.35);margin-top:1.5rem;">
          <span class="mi-tag-paid">Przykład z żywych danych</span>
          <h4>Kategoria vs mikro-nisza</h4>
          <p>
            <strong style="color:{ACCENT};">Finance (kategoria): 3/100</strong> — rynek gigantów,
            praktycznie nie do wejścia.<br>
            <strong style="color:{PRIMARY};">„budgeting for couples” (mikro-nisza): 55/100</strong>
            — zero gigantów, słaba jakość konkurencji. Tego nie widać na top-chartach.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Pricing ----
    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Prosty cennik</div>
          <div class="mi-section-sub">Kredyt = jedna nisza odblokowana na zawsze. Bez ukrytych opłat.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <table class="mi-price-table">
          <thead>
            <tr>
              <th>Plan</th>
              <th>Cena</th>
              <th>Co dostajesz</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Free</strong></td>
              <td>$0</td>
              <td>Radar (top 5 nisz), podgląd Analizy i Mikro-nisz, 3 skany fraz/dzień</td>
            </tr>
            <tr>
              <td><strong>1 kredyt</strong></td>
              <td class="mi-price-highlight">$19</td>
              <td>Pełna Analiza <em>lub</em> pełna Mikro-nisza — jednorazowo, na zawsze</td>
            </tr>
            <tr>
              <td><strong>5 kredytów</strong></td>
              <td class="mi-price-highlight">$49</td>
              <td>Pięć odblokowań nisz (pakiet −18% vs pojedyncze)</td>
            </tr>
            <tr>
              <td><strong>Pro</strong></td>
              <td class="mi-price-highlight">$39/mies.</td>
              <td>15 kredytów/mies. + pełny Radar + eksport CSV + priorytetowe limity skanów</td>
            </tr>
          </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        "Płatność dopiero po założeniu konta — najpierw zobacz darmowy Radar, "
        "potem odblokuj niszę, która Cię interesuje."
    )

    # ---- FAQ ----
    st.markdown(
        """
        <div class="mi-section">
          <div class="mi-section-title">Najczęstsze pytania</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Czy potrzebuję konta Apple Developer?"):
        st.markdown(
            "Nie. Korzystamy z publicznych danych App Store (rankingi, metadane, recenzje). "
            "Apple Developer account przydaje się dopiero, gdy zdecydujesz się publikować apkę."
        )
    with st.expander("Czy gwarantujecie sukces aplikacji?"):
        st.markdown(
            "Nie — to narzędzie badawcze, nie porada inwestycyjna. Dajemy sygnały popytu, "
            "luki konkurencji i plan wejścia — decyzja i ryzyko należą do Ciebie."
        )
    with st.expander("US czy Polska? Czy mogę budować na rynek amerykański?"):
        st.markdown(
            "Domyślnie skanujemy storefront **US** (największy wolumen recenzji). "
            "Dane **PL** też są dostępne. W Mikro-niszach geo-radar porównuje rynki — "
            "idealne, gdy budujesz z Polski na USA."
        )
    with st.expander("Co jeśli odblokuję niszę i mi nie pasuje?"):
        st.markdown(
            "Przed odblokowaniem widzisz **darmowy podgląd** (score, wstęp, fragment checklisty). "
            "Zużyty kredyt = dostarczona treść cyfrowa — szczegóły zwrotów w zakładce **Konto**."
        )
    with st.expander("Czy muszę płacić od razu?"):
        st.markdown(
            "Nie. Załóż darmowe konto, przejrzyj Radar i podglądy. Płatność tylko wtedy, "
            "gdy chcesz pełną analizę konkretnej niszy lub plan Pro."
        )

    # ---- Final CTA + auth ----
    st.markdown(
        """
        <div class="mi-cta-box">
          <h3>Gotowy znaleźć swoją niszę?</h3>
          <p>Darmowy Radar czeka — bez karty kredytowej, bez zobowiązań.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    focus = st.session_state.get(_SESSION_AUTH_FOCUS, False)
    if focus:
        st.info(
            "👇 Załóż konto poniżej (lub zaloguj się). Po rejestracji przejdziesz "
            "od razu do darmowego Radaru.",
            icon=":material/login:",
        )

    render_auth_inline(key_prefix="landing")

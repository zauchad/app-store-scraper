"""Reusable UI building blocks for the Streamlit dashboard.

Kept separate from app.py so the page files stay readable and the "explain how a
number is computed" content lives in one auditable place. Everything here is
presentation only - no DB or scoring logic. Rendering leans on native Streamlit
components (containers, popovers, badges) for maximum readability and robustness.
"""
from __future__ import annotations

from typing import List, Optional

import streamlit as st

# --------------------------------------------------------------------------- #
#  Methodology - the "on what data is this computed?" content.
#  Each entry: key -> (human title, markdown explaining SOURCE + FORMULA).
# --------------------------------------------------------------------------- #
METHODOLOGY = {
    "opportunity_score": (
        "Opportunity Score (0–100)",
        "**Co to jest:** jedna liczba mówiąca, jak atrakcyjna i *zdobywalna* jest "
        "nisza.\n\n"
        "**Wzór:** `Opportunity = atrakcyjność × contestability × 100`, gdzie "
        "atrakcyjność to ważona suma: popytu, luki jakościowej, niskiego nasycenia "
        "i momentum.\n\n"
        "**Dane źródłowe:** publiczne top-charty App Store (RSS) + iTunes Lookup "
        "(dokładne oceny i liczby ocen) — zebrane podczas skanów.",
    ),
    "success_probability": (
        "Szansa sukcesu (%)",
        "**Co to jest:** szacunek, czy przy Twoim budżecie realnie zdobędziesz "
        "przyczółek w niszy.\n\n"
        "**Wzór:** łączy atrakcyjność niszy, lukę jakościową, realny zasięg płatny "
        "(budżet ÷ CPI) oraz contestability (mnożnik gigantów).\n\n"
        "**Dane źródłowe:** metryki niszy + benchmark CPI kategorii + Twój budżet "
        "marketingowy z konfiguracji.",
    ),
    "demand": (
        "Popyt",
        "**Co to jest:** jak duże jest realne zainteresowanie w niszy.\n\n"
        "**Wzór:** znormalizowana (logarytmicznie) **mediana liczby ocen** apek w "
        "niszy — mediana jest odporna na 1–2 gigantów zawyżających średnią.\n\n"
        "**Dane źródłowe:** `userRatingCount` z iTunes Lookup dla apek w top-charcie "
        "/ wynikach wyszukiwania.",
    ),
    "quality_gap": (
        "Luka jakości",
        "**Co to jest:** jak słaba jest konkurencja (wyżej = gorsze apki = większa "
        "szansa dla lepszego produktu).\n\n"
        "**Wzór:** odległość średniej oceny konkurentów od progu **4.6★** "
        "(im niżej oceniona konkurencja, tym większa luka).\n\n"
        "**Dane źródłowe:** `averageUserRating` z iTunes Lookup.",
    ),
    "low_saturation": (
        "Niskie nasycenie",
        "**Co to jest:** jak mało jest silnych, ugruntowanych graczy.\n\n"
        "**Wzór:** `1 − (liczba twierdz ÷ próg nasycenia)`. Twierdza = apka z "
        "dużą liczbą ocen i wysoką oceną.\n\n"
        "**Dane źródłowe:** oceny + liczby ocen z iTunes Lookup.",
    ),
    "momentum": (
        "Momentum",
        "**Co to jest:** czy nisza rośnie w czasie.\n\n"
        "**Wzór:** miks tempa przyrostu recenzji i awansów w rankingu między "
        "kolejnymi skanami. Pojawia się po **≥2 skanach**.\n\n"
        "**Dane źródłowe:** porównanie snapshotów (`app_snapshots`) dzień do dnia.",
    ),
    "contestability": (
        "Contestability (0–1)",
        "**Co to jest:** mnożnik mówiący, czy *lean founder* w ogóle ma szansę "
        "wejść.\n\n"
        "**Wzór:** startuje od 1.0 i drastycznie spada za każdego giganta (>3 mln "
        "ocen) i za wysokie nasycenie twierdzami. To dlatego Social Networking "
        "ląduje nisko mimo ogromnego popytu.\n\n"
        "**Dane źródłowe:** liczby ocen konkurentów z iTunes Lookup.",
    ),
    "mega_incumbents": (
        "Giganci (>3 mln ocen)",
        "**Co to jest:** liczba apek z ponad 3 mln ocen — praktycznie nie do "
        "pobicia przy budżecie lean.\n\n"
        "**Dane źródłowe:** `userRatingCount` z iTunes Lookup. 2+ gigantów = "
        "automatyczny werdykt SKIP.",
    ),
    "strong_incumbents": (
        "Twierdze (silni gracze)",
        "**Co to jest:** apki jednocześnie z dużą liczbą ocen i wysoką oceną — "
        "dobrze okopani konkurenci.\n\n"
        "**Dane źródłowe:** oceny + liczby ocen z iTunes Lookup.",
    ),
    "stale_incumbents": (
        "Porzucone forty",
        "**Co to jest:** silne apki bez aktualizacji **>12 miesięcy** — dojrzałe do "
        "podbicia aktywnie rozwijanym produktem.\n\n"
        "**Dane źródłowe:** `currentVersionReleaseDate` z iTunes Lookup.",
    ),
    "installs": (
        "Instalacje (heurystyka)",
        "**Co to jest:** rząd wielkości pobrań — **nie** dokładny pomiar.\n\n"
        "**Wzór:** `instalacje ≈ liczba ocen ÷ współczynnik ocen (1–3%)`, stąd "
        "widełki. Do rankingu/filtrowania nisz, nie do wyceny.\n\n"
        "**Dane źródłowe:** publiczna liczba ocen (iTunes Lookup). Dokładne pobrania "
        "mają tylko płatne panele (Sensor Tower, data.ai).",
    ),
    "cpi": (
        "CPI (koszt instalacji)",
        "**Co to jest:** szacowany koszt pozyskania jednego użytkownika płatnie.\n\n"
        "**Dane źródłowe:** benchmark per kategoria (edytowalny w seedzie), "
        "przeliczony na PLN.",
    ),
    "est_installs_month": (
        "Instalacje/mies. przy budżecie",
        "**Wzór:** `budżet marketingowy ÷ CPI`. Ile płatnych instalacji miesięcznie "
        "kupisz za swój budżet.\n\n"
        "**Dane źródłowe:** Twój budżet z konfiguracji + benchmark CPI kategorii.",
    ),
    "search_interest": (
        "Popyt wyszukiwań (0–1)",
        "**Co to jest:** czy ludzie *faktycznie szukają* tej frazy.\n\n"
        "**Dane źródłowe:** podpowiedzi autouzupełniania App Store (MZSearchHints) — "
        "darmowy proxy popularności wyszukiwań.",
    ),
    "difficulty": (
        "Trudność ASO (0–1)",
        "**Co to jest:** jak trudno wyprzedzić apki już rankujące na tę frazę.\n\n"
        "**Wzór:** rośnie z medianą liczby ocen i liczbą twierdz/gigantów na "
        "zapytaniu.\n\n"
        "**Dane źródłowe:** wyniki iTunes Search API dla frazy.",
    ),
    "growth": (
        "Wzrost N-tygodniowy",
        "**Co to jest:** mediana przyrostu zaangażowania (liczby ocen) na apkę w "
        "oknie N tygodni.\n\n"
        "**Dane źródłowe:** porównanie snapshotów (`app_snapshots`). Wymaga historii "
        "obejmującej wybrane okno.",
    ),
    "candidates": (
        "Kandydaci do „sklonuj i ulepsz\"",
        "**Co to jest:** do 5 apek, które najlepiej nadają się jako wzorzec do "
        "zbudowania lepszej wersji.\n\n"
        "**Wzór (beatability):** `0.45×popyt + 0.40×luka_jakości + 0.15×porzucenie`. "
        "Nagradzamy apki z **udowodnionym popytem** (dużo ocen) ale z **słabością** "
        "(przeciętna ocena lub brak aktualizacji). Apka kochana (4.9★) dostaje niski "
        "wynik — nie jest realnym celem.\n\n"
        "**Dane źródłowe:** oceny, liczby ocen i data ostatniej aktualizacji z iTunes "
        "Lookup / Search.",
    ),
    "verdict": (
        "Werdykt (STRONG / WATCH / SKIP)",
        "**Reguły:**\n"
        "- **SKIP** — 2+ gigantów lub contestability <0.25 (rynek gigantów), albo "
        "słaby sygnał / za drogo.\n"
        "- **STRONG** — Opportunity ≥55 i szansa ≥45%.\n"
        "- **WATCH** — Opportunity ≥35 (obiecujące, obserwuj momentum).\n\n"
        "Guardrail gigantów ma priorytet nad wysokim score.",
    ),
}


def how_button(keys: List[str], *, key: str, label: str = "Na jakich danych?") -> None:
    """Inline popover that explains the sources & formulas for the given metrics."""
    with st.popover(f":material/info: {label}", use_container_width=False):
        st.caption(
            "Pełna transparentność — źródła i wzory każdego wskaźnika w tej sekcji."
        )
        for k in keys:
            entry = METHODOLOGY.get(k)
            if not entry:
                continue
            title, body = entry
            st.markdown(f"**{title}**")
            st.markdown(body)
            st.divider()
        st.caption(
            "Wszystkie dane pochodzą z darmowych, publicznych endpointów Apple. "
            "Płatne panele (Sensor Tower / data.ai) dają dokładniejsze pobrania, "
            "ale nie są potrzebne do rankingu okazji."
        )


# --------------------------------------------------------------------------- #
#  Clone-and-improve candidate cards (native containers, no raw HTML)
# --------------------------------------------------------------------------- #
def render_candidates(candidates: List, missing_features: Optional[list] = None) -> None:
    """Render up to 5 clone-and-improve candidate apps as native cards."""
    if not candidates:
        st.info(
            "Brak wyraźnych kandydatów (za mało apek z udowodnionym popytem "
            "w tej niszy). Spróbuj szerszej kategorii lub innej frazy."
        )
        return

    for i, c in enumerate(candidates, start=1):
        with st.container(border=True):
            head, score = st.columns([0.72, 0.28], vertical_alignment="center")
            with head:
                st.markdown(f"**#{i} · {c.name or '—'}**")
                rating_txt = f"{c.rating:.2f}★" if c.rating is not None else "b/d"
                ratings_txt = f"{c.ratings:,}".replace(",", " ")
                meta = f"{c.developer or '—'} · {rating_txt} · {ratings_txt} ocen"
                st.caption(meta)
            with score:
                st.markdown(
                    f":violet-background[**beatability {c.beatability:.0f}/100**]"
                )
                if c.url:
                    st.markdown(f"[App Store ↗]({c.url})")

            for r in c.reasons:
                st.markdown(f"- {r}")
            st.success(f"🎯 **Jak wygrać:** {c.angle}")

    if missing_features:
        feats = ", ".join(
            f.get("label", "") for f in missing_features[:5] if f.get("label")
        )
        if feats:
            st.caption(
                "💡 Dodatkowo, brakujące funkcje w tej niszy (z analizy recenzji): "
                f"**{feats}** — to gotowa lista przewag konkurencyjnych."
            )


# --------------------------------------------------------------------------- #
#  Glossary
# --------------------------------------------------------------------------- #
GLOSSARY = [
    ("Opportunity Score", "Łączna atrakcyjność niszy × szansa wejścia (0–100)."),
    ("Contestability", "Czy lean founder ma szansę (0–1). Giganci ją zabijają."),
    ("Twierdza", "Silny konkurent: dużo ocen + wysoka ocena."),
    ("Gigant", "Apka z >3 mln ocen — praktycznie nie do pobicia."),
    ("Luka jakości", "Jak słaba jest konkurencja pod progiem 4.6★."),
    ("Porzucony fort", "Silna apka bez aktualizacji >12 mies. = okazja."),
    ("CPI", "Koszt jednej instalacji z reklam (per kategoria)."),
    ("Beatability", "Jak dobrze apka nadaje się jako wzorzec do ulepszenia."),
    ("Instalacje (heur.)", "Rząd wielkości pobrań z liczby ocen — nie pomiar."),
]


def render_glossary() -> None:
    for term, desc in GLOSSARY:
        st.markdown(f"**{term}** — {desc}")

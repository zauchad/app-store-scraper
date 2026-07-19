"""Streamlit dashboard - the analyst's cockpit.

Two views mirroring the two-level model:
  1. Opportunity Radar - auto-ranked niche heatmap (Level 1, quantitative).
  2. Niche Deep Dive    - Executive Summary + pain points + missing features +
                          suggested direction + marketing feasibility (Level 2).

Design intent: NO raw tables as the headline. Every screen leads with a business
conclusion AND is honest about whether a lean founder can actually win the niche
(the "Goliath guardrail").
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

# Bridge Streamlit Cloud secrets -> env vars BEFORE importing settings.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:  # noqa: BLE001
    pass

from src.config import settings  # noqa: E402
from src.db.session import init_db  # noqa: E402
from src.reporting import (  # noqa: E402
    has_any_data,
    latest_insight,
    latest_keyword_scores_df,
    latest_scores_df,
    rising_apps_df,
    top_apps_for_category,
)
from src.scraper.categories import CATEGORY_SEEDS  # noqa: E402

st.set_page_config(
    page_title="Market Intel — App Store Niche Radar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# --------------------------------------------------------------------------- #
#  Styling
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1300px;}
      .mi-hero {
        background: linear-gradient(135deg, #1e3a8a 0%, #4c1d95 100%);
        padding: 22px 28px; border-radius: 16px; margin-bottom: 18px;
      }
      .mi-hero h1 {color:#fff; margin:0; font-size:1.7rem;}
      .mi-hero p {color:#c7d2fe; margin:.35rem 0 0; font-size:.95rem;}
      .mi-badge {
        display:inline-block; padding:4px 12px; border-radius:999px;
        font-weight:700; font-size:.82rem; letter-spacing:.02em;
      }
      .mi-strong {background:#052e1a; color:#4ade80; border:1px solid #16a34a;}
      .mi-watch  {background:#2e2603; color:#facc15; border:1px solid #ca8a04;}
      .mi-skip   {background:#2e0b0b; color:#f87171; border:1px solid #dc2626;}
      .mi-card {
        background:#111827; border:1px solid #1f2937; border-radius:14px;
        padding:16px 18px; height:100%;
      }
      .mi-card h4 {margin:0 0 4px; color:#e5e7eb; font-size:.9rem;}
      .mi-pain {border-left:3px solid #dc2626; padding:6px 12px; margin:8px 0;
                background:#161616; border-radius:0 8px 8px 0;}
      .mi-pain.med {border-left-color:#ca8a04;}
      .mi-pain.low {border-left-color:#4b5563;}
      .mi-feat {border-left:3px solid #2563eb; padding:6px 12px; margin:8px 0;
                background:#0f1420; border-radius:0 8px 8px 0;}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300)
def load_scores() -> pd.DataFrame:
    return latest_scores_df()


def pln(x) -> str:
    try:
        return f"{x:,.0f} zł".replace(",", " ")
    except (TypeError, ValueError):
        return "-"


def pct(x) -> str:
    try:
        return f"{x * 100:.0f}%"
    except (TypeError, ValueError):
        return "-"


def num(x) -> str:
    try:
        return f"{int(x):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "-"


def verdict(row) -> tuple:
    """Return (level, css_class, explanation). Giant guardrail first."""
    opp = row["opportunity_score"] or 0
    prob = row["success_probability"] or 0
    mega = int(row.get("mega_incumbents", 0) or 0)
    contest = row.get("contestability", 1.0) or 1.0

    if mega >= 2 or contest < 0.25:
        return ("SKIP", "mi-skip",
                "Rynek zdominowany przez gigantów — nie do pobicia przy lean budżecie")
    if opp >= 55 and prob >= 0.45:
        return ("STRONG", "mi-strong",
                "Realna, osiągalna nisza przy Twoim budżecie")
    if opp >= 35:
        return ("WATCH", "mi-watch",
                "Obiecująca — obserwuj momentum kolejnych dni")
    return ("SKIP", "mi-skip", "Słaby sygnał lub zbyt ciasno / za drogo")


def badge(level: str, css: str, text: str = "") -> str:
    label = f"{level} — {text}" if text else level
    return f'<span class="mi-badge {css}">{label}</span>'


# --------------------------------------------------------------------------- #
#  Sidebar
# --------------------------------------------------------------------------- #
st.sidebar.markdown("### 📡 Market Intel")
view = st.sidebar.radio(
    "Widok",
    ["Opportunity Radar", "Niche Deep Dive", "Micro-Niche Explorer"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.caption(f"Storefront: **{settings.store_country.upper()}**")
st.sidebar.caption(f"Budżet marketingowy: **{pln(settings.marketing_budget_pln)}/mies.**")
st.sidebar.caption("Gry wykluczone (kapitałochłonne).")
if not settings.llm_enabled:
    st.sidebar.warning("LLM OFF — brak GEMINI_API_KEY.")

with st.sidebar.expander("Jak liczymy Opportunity Score?"):
    st.markdown(
        "**Opportunity = atrakcyjność × contestability**\n\n"
        "- **Popyt** — mediana liczby ocen (odporna na 1-2 gigantów)\n"
        "- **Luka jakości** — jak nisko konkurencja jest pod progiem 4.6★\n"
        "- **Niskie nasycenie** — mało silnych graczy\n"
        "- **Momentum** — wzrost recenzji + awans w rankingu (po kilku skanach)\n"
        "- **Porzucone forty** — silne apki bez aktualizacji >12 mies. = okazja\n\n"
        "**Contestability** to mnożnik 0-1: czy lean founder w ogóle może "
        "wejść. Każdy gigant (>3 mln ocen) drastycznie go obniża — dlatego "
        "rynki typu Social Networking lądują nisko, mimo dużego popytu."
    )

# --------------------------------------------------------------------------- #
#  View 3: Micro-Niche Explorer (self-contained, no category scan required)
# --------------------------------------------------------------------------- #
if view == "Micro-Niche Explorer":
    st.markdown(
        '<div class="mi-hero"><h1>Micro-Niche Explorer</h1>'
        '<p>Poziom PONIŻEJ top-chartów. LLM proponuje konkretne mikro-nisze '
        '(słowa kluczowe), a Search API waliduje je ilościowo tym samym '
        'guardrailem contestability. Tu żyją realne okazje.</p></div>',
        unsafe_allow_html=True,
    )

    enabled = [s for s in CATEGORY_SEEDS if s.enabled]
    genre_options = {"— dowolna —": None}
    genre_options.update({s.name: s.genre_id for s in enabled})

    with st.form("kw_form"):
        colf1, colf2 = st.columns([3, 2])
        with colf1:
            terms_raw = st.text_area(
                "Słowa kluczowe (po przecinku lub w nowych liniach)",
                placeholder="sleep tracker for shift workers, budgeting for couples",
                height=90,
            )
        with colf2:
            genre_name = st.selectbox("Kontekst kategorii (CPI + LLM)", list(genre_options))
            theme = st.text_input("Motyw dla generatora AI", placeholder="np. habit tracking for ADHD")
        cA, cB = st.columns(2)
        gen = cA.checkbox("Wygeneruj kandydatów przez AI", value=False,
                          help="Wymaga GEMINI_API_KEY. LLM zaproponuje mikro-nisze dla motywu/kategorii.")
        n_kw = cB.slider("Ile wygenerować", 5, 25, 12)
        submitted = st.form_submit_button("Analizuj mikro-nisze", type="primary", use_container_width=True)

    if submitted:
        genre_id = genre_options[genre_name]
        terms = [t.strip() for t in terms_raw.replace("\n", ",").split(",") if t.strip()]
        if gen and not settings.llm_enabled:
            st.warning("Generator AI wymaga GEMINI_API_KEY. Podaj słowa ręcznie albo skonfiguruj klucz.")
        elif not terms and not gen:
            st.warning("Podaj przynajmniej jedno słowo kluczowe albo włącz generator AI.")
        else:
            with st.spinner("Szukam i oceniam mikro-nisze (Search API + LLM)…"):
                from src.pipeline.keyword_scan import run_keyword_scan
                try:
                    run_keyword_scan(terms=terms, theme=theme, genre_id=genre_id,
                                     generate=gen, n=n_kw)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Analiza nie powiodła się: {exc}")

    kdf = latest_keyword_scores_df()
    if kdf.empty:
        st.info("Brak przeanalizowanych mikro-nisz. Wpisz słowa kluczowe powyżej i kliknij Analizuj.")
        st.stop()

    top = kdf.iloc[0]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Najlepsza mikro-nisza", top["term"], f"{top['opportunity_score']:.0f}/100")
    k2.metric("Szansa sukcesu", pct(top["success_probability"]))
    k3.metric("Giganci w top", num(top["mega_incumbents"]))
    k4.metric("Przeanalizowanych", len(kdf))

    st.divider()
    st.markdown("#### Ranking mikro-nisz")
    kdisp = kdf.copy()
    kdisp["Werdykt"] = kdisp.apply(lambda r: verdict(r)[0], axis=1)
    kdisp["Szansa"] = kdisp["success_probability"].apply(pct)
    kdisp["Contest."] = kdisp["contestability"].apply(lambda x: f"{x:.2f}")
    kdisp["Popyt wysz."] = kdisp.get("search_interest", pd.Series(dtype=float)).apply(
        lambda x: f"{x:.2f}" if pd.notna(x) else "-")
    kdisp["Trudność"] = kdisp.get("difficulty", pd.Series(dtype=float)).apply(
        lambda x: f"{x:.2f}" if pd.notna(x) else "-")
    kdisp["CPI"] = kdisp["est_cpi_pln"].apply(pln)
    st.dataframe(
        kdisp[["term", "opportunity_score", "Szansa", "Popyt wysz.", "Trudność",
               "avg_rating_top", "strong_incumbents", "mega_incumbents", "Contest.",
               "est_installs_month", "CPI", "Werdykt"]]
        .rename(columns={"term": "Mikro-nisza", "opportunity_score": "Opportunity",
                         "avg_rating_top": "Śr. ocena", "strong_incumbents": "Twierdze",
                         "mega_incumbents": "Giganci", "est_installs_month": "Instalacje/mies."}),
        use_container_width=True, hide_index=True,
        column_config={"Opportunity": st.column_config.ProgressColumn(
            "Opportunity", min_value=0, max_value=100, format="%.0f")},
    )
    st.caption("💡 Sweet spot ASO: **wysoki Popyt wysz. + niska Trudność** "
               "(dużo szukają, słabi konkurenci do wyprzedzenia).")

    st.markdown("#### Szczegóły mikro-niszy")
    pick = st.selectbox("Wybierz", kdf["term"].tolist())
    krow = kdf[kdf["term"] == pick].iloc[0]
    lvl, css, expl = verdict(krow)
    st.markdown(badge(lvl, css, expl), unsafe_allow_html=True)
    d1, d2, d3, d4, d5, d6 = st.columns(6)
    d1.metric("Opportunity", f"{krow['opportunity_score']:.0f}/100")
    d2.metric("Popyt (mediana ocen)", num(krow["median_rating_count"]))
    si = krow.get("search_interest")
    d3.metric("Search interest", f"{si:.2f}" if si is not None and pd.notna(si) else "-")
    diff = krow.get("difficulty")
    d4.metric("Trudność ASO", f"{diff:.2f}" if diff is not None and pd.notna(diff) else "-")
    d5.metric("Luka jakości", f"{krow['quality_gap']:.2f}")
    d6.metric("Contestability", f"{krow['contestability']:.2f}")
    apps = krow.get("top_apps") or []
    if apps:
        st.caption("Aplikacje konkurujące o to zapytanie:")
        st.dataframe(pd.DataFrame(apps).rename(columns={
            "name": "Aplikacja", "developer": "Wydawca",
            "rating": "Ocena", "ratings": "Liczba ocen"}),
            use_container_width=True, hide_index=True)
    st.stop()


if not has_any_data():
    st.markdown('<div class="mi-hero"><h1>Brak danych</h1>'
                '<p>Uruchom pipeline, aby zobaczyć okazje.</p></div>',
                unsafe_allow_html=True)
    st.code("python run.py scan\npython run.py deep-dive", language="bash")
    st.stop()

df = load_scores()


# --------------------------------------------------------------------------- #
#  View 1: Opportunity Radar
# --------------------------------------------------------------------------- #
if view == "Opportunity Radar":
    st.markdown(
        '<div class="mi-hero"><h1>Opportunity Radar</h1>'
        '<p>Automatyczny ranking nisz: duży <b>realny</b> popyt + słaba jakość '
        'konkurencji + niskie nasycenie — przefiltrowane przez to, czy lean '
        'founder ma szansę wygrać (guardrail gigantów).</p></div>',
        unsafe_allow_html=True,
    )

    # Best CONTESTABLE niche (skip giant-owned even if raw score high).
    contestable = df[df["mega_incumbents"].fillna(0) < 2]
    top = (contestable if not contestable.empty else df).iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Najlepsza (osiągalna) nisza", top["category"], f"{top['opportunity_score']:.0f}/100")
    c2.metric("Szansa sukcesu", pct(top["success_probability"]))
    c3.metric("Instalacje/mies. @ budżet", num(top["est_installs_month"]))
    c4.metric("Analizowanych nisz", len(df))

    st.divider()

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Mapa okazji: popyt vs luka jakościowa")
        st.caption("Prawy-górny róg = duży popyt i słaba konkurencja. "
                   "Rozmiar bąbla = contestability (małe bąble = rynek gigantów).")
        plot = df.copy()
        plot["size"] = (plot["contestability"].fillna(0.1) * 40 + 6)
        fig = px.scatter(
            plot, x="demand", y="quality_gap", size="size",
            color="opportunity_score", hover_name="category",
            hover_data={"size": False, "demand": ":.2f", "quality_gap": ":.2f",
                        "mega_incumbents": True, "success_probability": ":.0%"},
            labels={"demand": "Popyt (mediana, znormalizowany)",
                    "quality_gap": "Luka jakościowa (wyżej = gorsza konkurencja)",
                    "opportunity_score": "Opportunity"},
            color_continuous_scale="Turbo", height=470,
        )
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(17,24,39,0.5)")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("#### Ranking Opportunity Score")
        rank = df.head(12).sort_values("opportunity_score")
        colors = ["#dc2626" if m >= 2 else "#4ade80"
                  for m in rank["mega_incumbents"].fillna(0)]
        fig2 = go.Figure(go.Bar(
            x=rank["opportunity_score"], y=rank["category"], orientation="h",
            marker_color=colors,
            text=[f"{v:.0f}" for v in rank["opportunity_score"]],
            textposition="outside",
        ))
        fig2.update_layout(height=470, margin=dict(l=10, r=10, t=10, b=10),
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(17,24,39,0.5)",
                           xaxis_title="Opportunity (czerwony = rynek gigantów)")
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.markdown("#### Tabela decyzyjna")
    disp = df.copy()
    disp["Werdykt"] = disp.apply(lambda r: verdict(r)[0], axis=1)
    disp["Szansa"] = disp["success_probability"].apply(pct)
    disp["CPI"] = disp["est_cpi_pln"].apply(pln)
    disp["Contest."] = disp["contestability"].apply(lambda x: f"{x:.2f}")
    st.dataframe(
        disp[["category", "opportunity_score", "Szansa", "avg_rating_top",
              "strong_incumbents", "mega_incumbents", "Contest.",
              "est_installs_month", "CPI", "Werdykt"]]
        .rename(columns={"category": "Kategoria", "opportunity_score": "Opportunity",
                         "avg_rating_top": "Śr. ocena", "strong_incumbents": "Twierdze",
                         "mega_incumbents": "Giganci", "est_installs_month": "Instalacje/mies."}),
        use_container_width=True, hide_index=True,
        column_config={
            "Opportunity": st.column_config.ProgressColumn(
                "Opportunity", min_value=0, max_value=100, format="%.0f"),
        },
    )

    st.divider()
    st.markdown("#### 🚀 Breakout — apki najszybciej pnące się w rankingu")
    st.caption("Największy skok pozycji względem poprzedniego skanu = rosnące "
               "zainteresowanie (odpowiednik listy Rising/Breakout z data.ai). "
               "Wymaga ≥2 dni historii.")
    rising = rising_apps_df(limit=15)
    if rising.empty:
        st.info("Brak danych o breakoutach — potrzebne min. 2 uruchomienia skanu "
                "(momentum liczony między snapshotami).")
    else:
        rdisp = rising.rename(columns={
            "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
            "rank_now": "Pozycja teraz", "rank_prev": "Poprzednio",
            "rank_delta": "Skok (↑)", "rating_count": "Liczba ocen"})
        st.dataframe(rdisp, use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
#  View 2: Niche Deep Dive
# --------------------------------------------------------------------------- #
else:
    names = df["category"].tolist()
    choice = st.selectbox("Wybierz niszę", names, index=0)
    row = df[df["category"] == choice].iloc[0]
    genre_id = int(row["genre_id"])
    level, css, expl = verdict(row)

    st.markdown(
        f'<div class="mi-hero"><h1>{choice}</h1>'
        f'<p>{badge(level, css, expl)}</p></div>',
        unsafe_allow_html=True,
    )

    mega = int(row.get("mega_incumbents", 0) or 0)
    if mega >= 2:
        st.error(
            f"🛑 **Guardrail gigantów:** ta kategoria ma **{mega}** aplikacje z "
            f"ponad 3 mln ocen (np. dominujące platformy). Konkurowanie z nimi "
            f"przy budżecie {pln(settings.marketing_budget_pln)}/mies. jest "
            f"nierealne — niezależnie od tego, jak kuszące są pain-pointy poniżej. "
            f"Potraktuj wnioski jako inspirację do **węższej pod-niszy**, nie do "
            f"frontalnego ataku na całą kategorię."
        )

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Opportunity", f"{row['opportunity_score']:.0f}/100")
    m2.metric("Szansa sukcesu", pct(row["success_probability"]))
    m3.metric("Śr. ocena konk.", f"{row['avg_rating_top']:.2f}" if row["avg_rating_top"] else "-")
    m4.metric("Twierdze", num(row["strong_incumbents"]))
    m5.metric("Giganci (>3M)", num(row.get("mega_incumbents", 0)))
    m6.metric("Contestability", f"{row.get('contestability', 1):.2f}")

    stale = int(row.get("stale_incumbents", 0) or 0)
    days_upd = row.get("median_days_since_update")
    if stale > 0:
        st.warning(
            f"🕳️ **Porzucone forty:** {stale} silnych aplikacji nie było "
            f"aktualizowanych >12 miesięcy — potencjalnie zaniedbane, dojrzałe "
            f"do podbicia lepszym, aktywnie rozwijanym produktem."
        )
    if days_upd is not None and pd.notna(days_upd):
        st.caption(f"Mediana czasu od ostatniej aktualizacji w niszy: "
                   f"**{int(days_upd)} dni**. Rank momentum: "
                   f"**{row.get('rank_momentum', 0):+.2f}** (dodatni = apki pną się w górę).")

    st.divider()

    left, right = st.columns([2, 3])
    with left:
        st.markdown("#### Rozbicie score")
        comp = pd.DataFrame({
            "Składnik": ["Popyt", "Luka jakości", "Niskie nasycenie", "Momentum"],
            "Wartość": [row["demand"], row["quality_gap"], row["low_saturation"], row["momentum"]],
        })
        figc = go.Figure(go.Bar(
            x=comp["Wartość"], y=comp["Składnik"], orientation="h",
            marker_color="#6366f1", text=[f"{v:.2f}" for v in comp["Wartość"]],
            textposition="outside",
        ))
        figc.update_layout(height=230, margin=dict(l=10, r=10, t=6, b=6),
                           xaxis_range=[0, 1], paper_bgcolor="rgba(0,0,0,0)",
                           plot_bgcolor="rgba(17,24,39,0.5)")
        st.plotly_chart(figc, use_container_width=True)
        st.caption(f"Mnożnik contestability: **{row.get('contestability', 1):.2f}** "
                   "(1.0 = wolne pole, →0 = rynek gigantów).")

    with right:
        st.markdown("#### Ekonomia wejścia (przy Twoim budżecie)")
        e1, e2, e3 = st.columns(3)
        e1.metric("Budżet / mies.", pln(row["marketing_cost_pln"]))
        e2.metric("Szac. CPI", pln(row["est_cpi_pln"]))
        e3.metric("Instalacje / mies.", num(row["est_installs_month"]))
        st.caption("CPI = benchmark kategorii (edytowalny w seedzie). "
                   "Instalacje = budżet / CPI. Szansa sukcesu łączy atrakcyjność "
                   "niszy, lukę jakościową, realny zasięg płatny i contestability.")

    st.divider()

    insight = latest_insight(genre_id)
    if insight is None:
        st.warning("Brak analizy LLM dla tej niszy. Uruchom:")
        st.code(f"python run.py deep-dive --genre {genre_id}", language="bash")
    else:
        mode = (insight.raw_json or {}).get("_source_mode", "reviews")
        if mode == "positioning":
            st.caption("🔎 Tryb: POZYCJONOWANIE — brak tekstu recenzji (feed Apple "
                       "martwy w 2026). Wnioski z opisów konkurentów + metryk. "
                       "Podłącz provider recenzji dla pełnych pain-pointów (README).")
        else:
            st.caption(f"🔎 Tryb: RECENZJE — analiza {insight.reviews_analyzed} recenzji.")

        st.markdown("#### Executive Summary")
        st.info(insight.executive_summary or "—")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### Główne problemy użytkowników")
            for p in (insight.pain_points or []):
                sev = (p.get("severity") or "").lower()
                cls = {"high": "", "medium": "med", "low": "low"}.get(sev, "")
                tag = {"high": "HIGH", "medium": "MED", "low": "LOW"}.get(sev, "")
                st.markdown(
                    f'<div class="mi-pain {cls}"><b>[{tag}] {p.get("label","")}</b>'
                    f'<br>{p.get("description","")}</div>', unsafe_allow_html=True)
        with col_b:
            st.markdown("#### Brakujące funkcje (popyt niezaspokojony)")
            for f in (insight.missing_features or []):
                st.markdown(
                    f'<div class="mi-feat"><b>{f.get("label","")}</b>'
                    f'<br>{f.get("description","")}</div>', unsafe_allow_html=True)

        st.markdown("#### Sugerowany kierunek dla Twojej aplikacji")
        st.success(insight.suggested_direction or "—")
        if insight.market_saturation_note:
            st.caption(f"Nasycenie rynku: {insight.market_saturation_note}")
        st.caption(f"model: {insight.llm_model} | {insight.generated_at:%Y-%m-%d %H:%M}")

    with st.expander("Konkurenci w tej niszy"):
        apps_df = top_apps_for_category(genre_id)
        if apps_df.empty:
            st.caption("Brak danych o aplikacjach.")
        else:
            st.dataframe(apps_df, use_container_width=True, hide_index=True)

"""Market Intel — App Store Niche Radar (Streamlit dashboard).

Design intent: a modern, minimal, website-like console that a NON-EXPERT can
navigate. Every screen leads with a plain-language business conclusion, exposes
"on what data is this computed?" modals for full transparency, links every app to
the App Store, and — crucially — hands the user up to 5 concrete "clone &
improve" targets. Navigation is a top pill-bar (no clunky radio buttons).
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

import dashboard.ui as ui  # noqa: E402
from src.analysis.candidates import rank_candidates  # noqa: E402
from src.analysis.estimates import lifetime_installs  # noqa: E402
from src.config import settings  # noqa: E402
from src.db.session import init_db  # noqa: E402
from src.reporting import (  # noqa: E402
    category_growth_df,
    category_rating_history,
    competitors_for_category,
    has_any_data,
    latest_insight,
    latest_keyword_scores_df,
    latest_scores_df,
    quality_movers_df,
    rising_apps_df,
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
#  Styling — modern / minimal
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      /* Hide Streamlit chrome that overlays / clips the custom top nav */
      header[data-testid="stHeader"],
      .stAppHeader,
      div[data-testid="stDecoration"],
      div[data-testid="stToolbar"],
      div[data-testid="stStatusWidget"] {
        display: none !important;
        height: 0 !important;
        visibility: hidden !important;
      }
      /* Reclaim the space the sticky header used to cover */
      .stApp > header { display: none !important; }
      .block-container {
        padding-top: 1.2rem !important;
        max-width: 1280px;
      }
      /* Hero */
      .mi-hero {
        background: linear-gradient(135deg, #1e3a8a 0%, #4c1d95 100%);
        padding: 20px 26px; border-radius: 18px; margin: 6px 0 18px;
        box-shadow: 0 8px 30px rgba(76,29,149,.25);
      }
      .mi-hero h1 {color:#fff; margin:0; font-size:1.6rem; letter-spacing:-.01em;}
      .mi-hero p {color:#c7d2fe; margin:.4rem 0 0; font-size:.94rem; line-height:1.5;}
      /* Badges */
      .mi-badge {display:inline-block; padding:4px 12px; border-radius:999px;
        font-weight:700; font-size:.82rem; letter-spacing:.02em;}
      .mi-strong {background:#052e1a; color:#4ade80; border:1px solid #16a34a;}
      .mi-watch  {background:#2e2603; color:#facc15; border:1px solid #ca8a04;}
      .mi-skip   {background:#2e0b0b; color:#f87171; border:1px solid #dc2626;}
      /* Cards / insight blocks */
      .mi-card {background:#111827; border:1px solid #1f2937; border-radius:14px;
        padding:16px 18px; height:100%;}
      .mi-pain {border-left:3px solid #dc2626; padding:6px 12px; margin:8px 0;
        background:#161616; border-radius:0 8px 8px 0;}
      .mi-pain.med {border-left-color:#ca8a04;}
      .mi-pain.low {border-left-color:#4b5563;}
      .mi-feat {border-left:3px solid #2563eb; padding:6px 12px; margin:8px 0;
        background:#0f1420; border-radius:0 8px 8px 0;}
      /* Clone-and-improve candidate cards */
      .mi-cand {background:#0f1524; border:1px solid #24304a; border-radius:14px;
        padding:14px 16px; margin:10px 0;}
      .mi-cand-head {display:flex; align-items:center; gap:10px; flex-wrap:wrap;}
      .mi-cand-rank {background:#4c1d95; color:#e9d5ff; font-weight:800;
        border-radius:8px; padding:2px 9px; font-size:.85rem;}
      .mi-cand-name {font-weight:700; color:#f1f5f9; font-size:1.05rem;}
      .mi-cand-score {margin-left:auto; color:#a5b4fc; font-size:.8rem;
        border:1px solid #312e81; border-radius:999px; padding:2px 10px;}
      .mi-cand-meta {color:#94a3b8; font-size:.85rem; margin:4px 0 2px;}
      .mi-cand-meta a {color:#60a5fa; text-decoration:none;}
      .mi-cand-reasons {margin:6px 0 6px 2px; padding-left:18px; color:#cbd5e1;
        font-size:.88rem;}
      .mi-cand-angle {background:#052e1a; border:1px solid #14532d; color:#bbf7d0;
        border-radius:10px; padding:8px 12px; font-size:.88rem; margin-top:6px;}
      /* Custom top nav buttons */
      div[data-testid="stHorizontalBlock"]:has(button[kind="primary"]),
      div[data-testid="stHorizontalBlock"]:has(button[kind="secondary"]) {
        gap: 0.4rem;
        margin-bottom: 0.4rem;
      }
      /* Tighten metric labels */
      div[data-testid="stMetricLabel"] p {font-size:.82rem; color:#94a3b8;}
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


def installs_label(rating_count) -> str:
    try:
        return lifetime_installs(int(rating_count)).label
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
        return ("STRONG", "mi-strong", "Realna, osiągalna nisza przy Twoim budżecie")
    if opp >= 35:
        return ("WATCH", "mi-watch", "Obiecująca — obserwuj momentum kolejnych dni")
    return ("SKIP", "mi-skip", "Słaby sygnał lub zbyt ciasno / za drogo")


def badge(level: str, css: str, text: str = "") -> str:
    label = f"{level} — {text}" if text else level
    return f'<span class="mi-badge {css}">{label}</span>'


def hero(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="mi-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
                unsafe_allow_html=True)


def app_link_table(df: pd.DataFrame, colmap: dict, url_col: str = "url") -> None:
    """Render a table where the App Store url becomes a clickable 'Otwórz ↗'."""
    show = df.rename(columns=colmap)
    cfg = {}
    if url_col in show.columns:
        cfg[url_col] = st.column_config.LinkColumn("Sklep", display_text="Otwórz ↗")
    st.dataframe(show, width="stretch", hide_index=True, column_config=cfg)


# --------------------------------------------------------------------------- #
#  Sidebar — global context + help
# --------------------------------------------------------------------------- #
st.sidebar.markdown("### 📡 Market Intel")
st.sidebar.caption(f"Storefront: **{settings.store_country.upper()}**")
st.sidebar.caption(f"Budżet marketingowy: **{pln(settings.marketing_budget_pln)}/mies.**")
st.sidebar.caption("Gry wykluczone (kapitałochłonne).")
if not settings.llm_enabled:
    st.sidebar.warning("LLM OFF — brak GEMINI_API_KEY.")
st.sidebar.divider()
with st.sidebar.expander("📖 Słowniczek pojęć"):
    ui.render_glossary()
with st.sidebar.expander("🧭 Jak czytać ten panel?"):
    st.markdown(
        "1. **Radar okazji** — zacznij tu: ranking nisz + mapa.\n"
        "2. **Głęboka analiza** — wybierz niszę: problemy, braki, kandydaci do "
        "ulepszenia.\n"
        "3. **Mikro-nisze** — konkretne frazy poniżej top-chartów (tu żyją okazje).\n"
        "4. **Co się zmieniło** — cotygodniowy skrót zmian.\n\n"
        "Wszędzie kliknij **ℹ️ Na jakich danych?**, by zobaczyć źródła i wzory."
    )


# --------------------------------------------------------------------------- #
#  Top navigation — 4 equal buttons (never clipped by Streamlit header)
# --------------------------------------------------------------------------- #
NAV = ["radar", "deep", "micro", "digest"]
NAV_LABELS = {
    "radar": "📡 Radar",
    "deep": "🔬 Analiza",
    "micro": "🎯 Mikro-nisze",
    "digest": "📈 Zmiany",
}
_legacy = {
    "📡 Radar okazji": "radar",
    "🔬 Głęboka analiza": "deep",
    "🎯 Mikro-nisze": "micro",
    "📈 Co się zmieniło": "digest",
}
if st.session_state.get("nav") in _legacy:
    st.session_state["nav"] = _legacy[st.session_state["nav"]]
if "nav" not in st.session_state or st.session_state["nav"] not in NAV:
    st.session_state["nav"] = NAV[0]

nav_cols = st.columns(len(NAV), gap="small")
for col, key in zip(nav_cols, NAV):
    with col:
        active = st.session_state["nav"] == key
        if st.button(
            NAV_LABELS[key],
            key=f"nav_btn_{key}",
            type="primary" if active else "secondary",
            use_container_width=True,
        ):
            st.session_state["nav"] = key
            st.rerun()

page = st.session_state["nav"]


# =========================================================================== #
#  PAGE: Micro-Niche Explorer
# =========================================================================== #
if page == "micro":
    hero("Mikro-nisze",
         "Poziom PONIŻEJ top-chartów. AI proponuje konkretne mikro-nisze (frazy), "
         "a Search API waliduje je tym samym guardrailem contestability. "
         "Kliknij wiersz w tabeli, aby zobaczyć szczegóły.")

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
            genre_name = st.selectbox("Kontekst kategorii (CPI + AI)", list(genre_options))
            theme = st.text_input("Motyw dla generatora AI", placeholder="np. habit tracking for ADHD")
        cA, cB = st.columns(2)
        gen = cA.checkbox("Wygeneruj kandydatów przez AI", value=False,
                          help="Wymaga GEMINI_API_KEY. AI zaproponuje mikro-nisze dla motywu/kategorii.")
        n_kw = cB.slider("Ile wygenerować", 5, 25, 12)
        submitted = st.form_submit_button("Analizuj mikro-nisze", type="primary",
                                          width="stretch")

    if submitted:
        genre_id = genre_options[genre_name]
        terms = [t.strip() for t in terms_raw.replace("\n", ",").split(",") if t.strip()]
        if gen and not settings.llm_enabled:
            st.warning("Generator AI wymaga GEMINI_API_KEY. Podaj słowa ręcznie albo skonfiguruj klucz.")
        elif not terms and not gen:
            st.warning("Podaj przynajmniej jedno słowo kluczowe albo włącz generator AI.")
        else:
            with st.spinner("Szukam i oceniam mikro-nisze (Search API + AI)…"):
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
    ui.how_button(["opportunity_score", "success_probability", "mega_incumbents"],
                  key="kw_how_top")

    st.divider()
    st.markdown("#### Ranking mikro-nisz — kliknij wiersz, by zobaczyć szczegóły")
    kdisp = kdf.copy()
    kdisp["Werdykt"] = kdisp.apply(lambda r: verdict(r)[0], axis=1)
    kdisp["Szansa"] = kdisp["success_probability"].apply(pct)
    kdisp["Contest."] = kdisp["contestability"].apply(lambda x: f"{x:.2f}")
    kdisp["Popyt wysz."] = kdisp.get("search_interest", pd.Series(dtype=float)).apply(
        lambda x: f"{x:.2f}" if pd.notna(x) else "-")
    kdisp["Trudność"] = kdisp.get("difficulty", pd.Series(dtype=float)).apply(
        lambda x: f"{x:.2f}" if pd.notna(x) else "-")
    kdisp["Instalacje (life.)"] = kdisp["median_rating_count"].apply(installs_label)
    kdisp["CPI"] = kdisp["est_cpi_pln"].apply(pln)
    view_cols = ["term", "opportunity_score", "Szansa", "Popyt wysz.", "Trudność",
                 "avg_rating_top", "Instalacje (life.)", "strong_incumbents",
                 "mega_incumbents", "Contest.", "est_installs_month", "CPI", "Werdykt"]
    event = st.dataframe(
        kdisp[view_cols].rename(columns={
            "term": "Mikro-nisza", "opportunity_score": "Opportunity",
            "avg_rating_top": "Śr. ocena", "strong_incumbents": "Twierdze",
            "mega_incumbents": "Giganci", "est_installs_month": "Instalacje/mies. (budżet)"}),
        width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row", key="kw_table",
        column_config={"Opportunity": st.column_config.ProgressColumn(
            "Opportunity", min_value=0, max_value=100, format="%.0f")},
    )
    st.caption("💡 Sweet spot ASO: **wysoki Popyt wysz. + niska Trudność** "
               "(dużo szukają, słabi konkurenci do wyprzedzenia).")
    ui.how_button(["opportunity_score", "search_interest", "difficulty",
                   "installs", "cpi", "verdict"], key="kw_how_table")

    # Row click drives the detail panel (falls back to first / selectbox).
    picked = st.session_state.get("kw_pick", kdf["term"].iloc[0])
    if event.selection.rows:
        picked = kdf.iloc[event.selection.rows[0]]["term"]
        st.session_state["kw_pick"] = picked

    st.divider()
    terms_list = kdf["term"].tolist()
    idx = terms_list.index(picked) if picked in terms_list else 0
    picked = st.selectbox("Szczegóły mikro-niszy", terms_list, index=idx)
    krow = kdf[kdf["term"] == picked].iloc[0]

    lvl, css, expl = verdict(krow)
    st.markdown(f"### {picked} &nbsp; {badge(lvl, css, expl)}", unsafe_allow_html=True)
    d1, d2, d3, d4, d5, d6 = st.columns(6)
    d1.metric("Opportunity", f"{krow['opportunity_score']:.0f}/100")
    d2.metric("Popyt (mediana ocen)", num(krow["median_rating_count"]))
    si = krow.get("search_interest")
    d3.metric("Search interest", f"{si:.2f}" if si is not None and pd.notna(si) else "-")
    diff = krow.get("difficulty")
    d4.metric("Trudność ASO", f"{diff:.2f}" if diff is not None and pd.notna(diff) else "-")
    d5.metric("Luka jakości", f"{krow['quality_gap']:.2f}")
    d6.metric("Contestability", f"{krow['contestability']:.2f}")
    ui.how_button(["opportunity_score", "demand", "search_interest", "difficulty",
                   "quality_gap", "contestability"], key="kw_how_detail")

    apps = krow.get("top_apps") or []
    if apps:
        st.markdown("#### 🏆 Kandydaci do stworzenia lepszej apki (sklonuj i ulepsz)")
        st.caption("Do 5 apek z udowodnionym popytem ale wykorzystywalną słabością — "
                   "najlepsze wzorce do zbudowania lepszej wersji.")
        ui.render_candidates(rank_candidates(apps, limit=5))
        ui.how_button(["candidates"], key="kw_how_cand")

        with st.expander("Wszystkie apki konkurujące o to zapytanie"):
            adf = pd.DataFrame(apps)
            if "ratings" in adf.columns:
                adf["Instalacje (life.)"] = adf["ratings"].apply(installs_label)
            app_link_table(
                adf,
                {"name": "Aplikacja", "developer": "Wydawca",
                 "rating": "Ocena", "ratings": "Liczba ocen"},
            )
    st.stop()


# =========================================================================== #
#  PAGE: Co się zmieniło
# =========================================================================== #
if page == "digest":
    hero("Co się zmieniło",
         "Cotygodniowy brief: rosnące nisze, najlepsze osiągalne okazje, nowe "
         "mikro-nisze, breakouty, spadki jakości i porzucone forty — w jednym miejscu.")
    if not has_any_data():
        st.info("Brak danych. Uruchom `python run.py scan`, a najlepszy sygnał "
                "pojawi się po kilku dniach zbierania.")
        st.stop()
    weeks = st.slider("Okno wzrostu (tygodnie)", 1, 12, 4)
    with st.spinner("Składam digest…"):
        from src.pipeline.digest import build_digest
        st.markdown(build_digest(weeks=weeks))
    st.stop()


# --------------------------------------------------------------------------- #
#  Data guard for the two category pages
# --------------------------------------------------------------------------- #
if not has_any_data():
    hero("Brak danych", "Uruchom pipeline, aby zobaczyć okazje.")
    st.code("python run.py scan\npython run.py deep-dive", language="bash")
    st.stop()

df = load_scores()


# =========================================================================== #
#  PAGE: Opportunity Radar
# =========================================================================== #
if page == "radar":
    hero("Radar okazji",
         "Automatyczny ranking nisz: duży <b>realny</b> popyt + słaba jakość "
         "konkurencji + niskie nasycenie — przefiltrowane przez to, czy lean "
         "founder ma szansę wygrać (guardrail gigantów).")

    contestable = df[df["mega_incumbents"].fillna(0) < 2]
    top = (contestable if not contestable.empty else df).iloc[0]

    tlvl, tcss, texpl = verdict(top)
    st.markdown(
        f"🎯 **Rekomendacja na start:** najlepsza *osiągalna* nisza to "
        f"**{top['category']}** — Opportunity **{top['opportunity_score']:.0f}/100**, "
        f"szansa sukcesu **{pct(top['success_probability'])}**. {badge(tlvl, tcss, texpl)}",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Najlepsza (osiągalna) nisza", top["category"], f"{top['opportunity_score']:.0f}/100")
    c2.metric("Szansa sukcesu", pct(top["success_probability"]))
    c3.metric("Instalacje/mies. @ budżet", num(top["est_installs_month"]))
    c4.metric("Analizowanych nisz", len(df))
    ui.how_button(["opportunity_score", "success_probability", "est_installs_month"],
                  key="radar_how_top")

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
            marker_color=colors, text=[f"{v:.0f}" for v in rank["opportunity_score"]],
            textposition="outside"))
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
    disp["Skala (life.)"] = disp["median_rating_count"].apply(installs_label)
    gdf = category_growth_df(weeks=4)
    if not gdf.empty:
        disp = disp.merge(gdf[["genre_id", "growth_pct"]], on="genre_id", how="left")
        disp["Wzrost 4-tyg."] = disp["growth_pct"].apply(
            lambda x: f"{x * 100:+.0f}%" if pd.notna(x) else "n/d")
    else:
        disp["Wzrost 4-tyg."] = "n/d"
    st.dataframe(
        disp[["category", "opportunity_score", "Szansa", "Wzrost 4-tyg.",
              "avg_rating_top", "Skala (life.)", "strong_incumbents",
              "mega_incumbents", "Contest.", "est_installs_month", "CPI", "Werdykt"]]
        .rename(columns={"category": "Kategoria", "opportunity_score": "Opportunity",
                         "avg_rating_top": "Śr. ocena", "strong_incumbents": "Twierdze",
                         "mega_incumbents": "Giganci", "est_installs_month": "Instalacje/mies. (budżet)"}),
        width="stretch", hide_index=True,
        column_config={"Opportunity": st.column_config.ProgressColumn(
            "Opportunity", min_value=0, max_value=100, format="%.0f")},
    )
    st.caption("Przejdź do **🔬 Głęboka analiza**, by zobaczyć problemy użytkowników "
               "i kandydatów do ulepszenia w wybranej niszy.")
    ui.how_button(["opportunity_score", "growth", "installs", "contestability",
                   "cpi", "verdict"], key="radar_how_table")

    st.divider()
    st.markdown("#### 🚀 Breakout — apki najszybciej pnące się w rankingu")
    st.caption("Największy skok pozycji względem poprzedniego skanu = rosnące "
               "zainteresowanie (odpowiednik listy Rising/Breakout z data.ai). "
               "Wymaga ≥2 dni historii.")
    rising = rising_apps_df(limit=15)
    if rising.empty:
        st.info("Brak danych o breakoutach — potrzebne min. 2 uruchomienia skanu.")
    else:
        st.dataframe(rising.rename(columns={
            "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
            "rank_now": "Pozycja teraz", "rank_prev": "Poprzednio",
            "rank_delta": "Skok (↑)", "rating_count": "Liczba ocen"}),
            width="stretch", hide_index=True)

    st.markdown("#### 📉 Spadki jakości — świeże luki")
    st.caption("Silne apki, których średnia ocena spada między skanami = "
               "użytkownicy niezadowoleni = okno na lepszy produkt. Wymaga ≥2 dni historii.")
    movers = quality_movers_df(limit=15)
    if movers.empty:
        st.info("Brak wykrytych spadków ocen (potrzebne min. 2 skany).")
    else:
        st.dataframe(movers.rename(columns={
            "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
            "rating_now": "Ocena teraz", "rating_prev": "Poprzednio",
            "rating_drop": "Spadek (★)", "rating_count": "Liczba ocen"}),
            width="stretch", hide_index=True)
    st.stop()


# =========================================================================== #
#  PAGE: Niche Deep Dive
# =========================================================================== #
names = df["category"].tolist()
choice = st.selectbox("Wybierz niszę", names, index=0)
row = df[df["category"] == choice].iloc[0]
genre_id = int(row["genre_id"])
level, css, expl = verdict(row)

hero(choice, badge(level, css, expl))

mega = int(row.get("mega_incumbents", 0) or 0)
if mega >= 2:
    st.error(
        f"🛑 **Guardrail gigantów:** ta kategoria ma **{mega}** aplikacje z ponad "
        f"3 mln ocen. Konkurowanie z nimi przy budżecie "
        f"{pln(settings.marketing_budget_pln)}/mies. jest nierealne — potraktuj "
        f"wnioski jako inspirację do **węższej pod-niszy**, nie do frontalnego ataku."
    )

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Opportunity", f"{row['opportunity_score']:.0f}/100")
m2.metric("Szansa sukcesu", pct(row["success_probability"]))
m3.metric("Śr. ocena konk.", f"{row['avg_rating_top']:.2f}" if row["avg_rating_top"] else "-")
m4.metric("Twierdze", num(row["strong_incumbents"]))
m5.metric("Giganci (>3M)", num(row.get("mega_incumbents", 0)))
m6.metric("Contestability", f"{row.get('contestability', 1):.2f}")
ui.how_button(["opportunity_score", "success_probability", "quality_gap",
               "strong_incumbents", "mega_incumbents", "contestability"],
              key="dd_how_metrics")

stale = int(row.get("stale_incumbents", 0) or 0)
days_upd = row.get("median_days_since_update")
if stale > 0:
    st.warning(
        f"🕳️ **Porzucone forty:** {stale} silnych aplikacji nie było aktualizowanych "
        f">12 miesięcy — dojrzałe do podbicia aktywnie rozwijanym produktem."
    )
if days_upd is not None and pd.notna(days_upd):
    st.caption(f"Mediana czasu od ostatniej aktualizacji: **{int(days_upd)} dni**. "
               f"Rank momentum: **{row.get('rank_momentum', 0):+.2f}** "
               f"(dodatni = apki pną się w górę).")

typ_band = installs_label(row.get("median_rating_count"))
st.caption(f"📦 **Skala rynku (heurystyka):** typowa apka to **{typ_band}** instalacji "
           f"(lifetime), szacowane rzędem wielkości z liczby ocen.")

st.divider()
left, right = st.columns([2, 3])
with left:
    st.markdown("#### Rozbicie score")
    comp = pd.DataFrame({
        "Składnik": ["Popyt", "Luka jakości", "Niskie nasycenie", "Momentum"],
        "Wartość": [row["demand"], row["quality_gap"], row["low_saturation"], row["momentum"]],
    })
    figc = go.Figure(go.Bar(
        x=comp["Wartość"], y=comp["Składnik"], orientation="h", marker_color="#6366f1",
        text=[f"{v:.2f}" for v in comp["Wartość"]], textposition="outside"))
    figc.update_layout(height=230, margin=dict(l=10, r=10, t=6, b=6), xaxis_range=[0, 1],
                       paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(17,24,39,0.5)")
    st.plotly_chart(figc, use_container_width=True)
    ui.how_button(["demand", "quality_gap", "low_saturation", "momentum"],
                  key="dd_how_breakdown")

    hist = category_rating_history(genre_id)
    if len(hist) >= 2:
        st.markdown("#### Trend jakości konkurencji")
        figt = go.Figure(go.Scatter(x=hist["date"], y=hist["avg_rating"],
                                    mode="lines+markers", line=dict(color="#f59e0b")))
        figt.update_layout(height=200, margin=dict(l=10, r=10, t=6, b=6),
                           yaxis_title="Śr. ocena", paper_bgcolor="rgba(0,0,0,0)",
                           plot_bgcolor="rgba(17,24,39,0.5)")
        st.plotly_chart(figt, use_container_width=True)
        delta = hist["avg_rating"].iloc[-1] - hist["avg_rating"].iloc[0]
        arrow = "↓ spada (luka rośnie)" if delta < -0.01 else (
            "↑ rośnie (luka się zamyka)" if delta > 0.01 else "→ stabilna")
        st.caption(f"Zmiana od początku historii: **{delta:+.2f}★** — {arrow}.")
    else:
        st.caption("Trend jakości pojawi się po ≥2 skanach.")

with right:
    st.markdown("#### Ekonomia wejścia (przy Twoim budżecie)")
    e1, e2, e3 = st.columns(3)
    e1.metric("Budżet / mies.", pln(row["marketing_cost_pln"]))
    e2.metric("Szac. CPI", pln(row["est_cpi_pln"]))
    e3.metric("Instalacje / mies.", num(row["est_installs_month"]))
    ui.how_button(["cpi", "est_installs_month", "success_probability"],
                  key="dd_how_economy")
    st.caption("CPI = benchmark kategorii. Instalacje = budżet / CPI. Szansa sukcesu "
               "łączy atrakcyjność niszy, lukę jakościową, zasięg płatny i contestability.")

st.divider()

insight = latest_insight(genre_id)
missing_features = None
if insight is None:
    st.warning("Brak analizy AI dla tej niszy. Uruchom:")
    st.code(f"python run.py deep-dive --genre {genre_id}", language="bash")
else:
    missing_features = insight.missing_features or []
    mode = (insight.raw_json or {}).get("_source_mode", "reviews")
    if mode == "positioning":
        st.caption("🔎 Tryb: POZYCJONOWANIE — brak tekstu recenzji. Wnioski z opisów "
                   "konkurentów + metryk. Podłącz provider recenzji dla pełnych pain-pointów.")
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

st.divider()
st.markdown("#### 🏆 Kandydaci do stworzenia lepszej apki (sklonuj i ulepsz)")
st.caption("Do 5 apek z udowodnionym popytem ale wykorzystywalną słabością — "
           "najlepsze wzorce, na których warto oprzeć własny, lepszy produkt.")
comp_df = competitors_for_category(genre_id)
candidates = rank_candidates(comp_df.to_dict("records"), limit=5) if not comp_df.empty else []
ui.render_candidates(candidates, missing_features=missing_features)
ui.how_button(["candidates"], key="dd_how_cand")

with st.expander("Wszyscy konkurenci w tej niszy (z linkami do App Store)"):
    if comp_df.empty:
        st.caption("Brak danych o aplikacjach.")
    else:
        show = comp_df.copy()
        show["Instalacje (life.)"] = show["ratings"].apply(installs_label)
        show = show[["name", "developer", "rating", "ratings", "Instalacje (life.)",
                     "days_since_update", "url"]]
        app_link_table(show, {
            "name": "Aplikacja", "developer": "Wydawca", "rating": "Ocena",
            "ratings": "Liczba ocen", "days_since_update": "Dni od aktualizacji"})

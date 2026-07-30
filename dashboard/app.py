"""Market Intel — App Store Niche Radar (Streamlit dashboard).

A modern, minimal, website-like console that a NON-EXPERT can navigate. Every
screen leads with a plain-language business conclusion, exposes "on what data is
this computed?" popovers for full transparency, links every app to the App Store,
and hands the user up to 5 concrete "clone & improve" targets.

The UI is built almost entirely from native Streamlit components (native top
navigation, bordered containers, metrics, badges) so it stays readable and robust
across themes. Data access lives in `src.reporting`; this file is view-only.
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
#  Light-touch styling — cards for metrics + comfortable spacing.
#  Everything else is left to the native theme (see .streamlit/config.toml).
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      .block-container { max-width: 1240px; padding-top: 2.2rem; }

      /* Metrics rendered as tidy cards */
      div[data-testid="stMetric"] {
        background: var(--secondary-background-color, #171C29);
        border: 1px solid rgba(255,255,255,.06);
        border-radius: 14px;
        padding: 14px 16px 12px;
      }
      div[data-testid="stMetricLabel"] p { font-size: .82rem; opacity: .75; }
      div[data-testid="stMetricValue"] { font-size: 1.55rem; }

      /* Native top navigation: pill-style links */
      div[data-testid="stNavSectionHeader"] { display: none; }

      /* Dataframes a touch softer */
      div[data-testid="stDataFrame"] { border-radius: 12px; }

      /* Tighten expander/heading rhythm */
      h3, h4 { letter-spacing: -.01em; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
#  Formatting helpers
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


_VERDICT_COLOR = {"STRONG": "green", "WATCH": "orange", "SKIP": "red"}


def verdict(row) -> tuple:
    """Return (level, explanation). Giant guardrail first."""
    opp = row["opportunity_score"] or 0
    prob = row["success_probability"] or 0
    mega = int(row.get("mega_incumbents", 0) or 0)
    contest = row.get("contestability", 1.0) or 1.0

    if mega >= 2 or contest < 0.25:
        return ("SKIP",
                "Rynek zdominowany przez gigantów — nie do pobicia przy lean budżecie")
    if opp >= 55 and prob >= 0.45:
        return ("STRONG", "Realna, osiągalna nisza przy Twoim budżecie")
    if opp >= 35:
        return ("WATCH", "Obiecująca — obserwuj momentum kolejnych dni")
    return ("SKIP", "Słaby sygnał lub zbyt ciasno / za drogo")


def verdict_md(level: str, text: str = "") -> str:
    """Inline colored badge (markdown) for headers and callouts."""
    color = _VERDICT_COLOR.get(level, "gray")
    body = f":{color}-background[**{level}**]"
    return f"{body} {text}" if text else body


def style_fig(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        font=dict(color="#E7EAF3"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.1)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.1)")
    return fig


def app_link_table(df: pd.DataFrame, colmap: dict, url_col: str = "url") -> None:
    """Render a table where the App Store url becomes a clickable 'Otwórz ↗'."""
    show = df.rename(columns=colmap)
    cfg = {}
    if url_col in show.columns:
        cfg[url_col] = st.column_config.LinkColumn("Sklep", display_text="Otwórz ↗")
    st.dataframe(show, width="stretch", hide_index=True, column_config=cfg)


def page_header(title: str, subtitle: str) -> None:
    st.title(title)
    st.caption(subtitle)


# --------------------------------------------------------------------------- #
#  Sidebar — global context + help (rendered once, shown on every page)
# --------------------------------------------------------------------------- #
def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 📡 Market Intel")
        st.caption("App Store Niche Radar")
        st.divider()

        st.markdown("**Konfiguracja**")
        c1, c2 = st.columns(2)
        c1.metric("Storefront", settings.store_country.upper())
        c2.metric("Budżet / mies.", pln(settings.marketing_budget_pln))
        st.caption("Gry wykluczone (kapitałochłonne).")

        if settings.llm_enabled:
            st.success("LLM: aktywny (Gemini)", icon=":material/check_circle:")
        else:
            st.warning("LLM OFF — brak GEMINI_API_KEY.", icon=":material/warning:")

        st.divider()
        with st.expander("📖 Słowniczek pojęć"):
            ui.render_glossary()
        with st.expander("🧭 Jak czytać ten panel?"):
            st.markdown(
                "1. **Radar** — zacznij tu: ranking nisz + mapa okazji.\n"
                "2. **Analiza** — wybierz niszę: problemy, braki, kandydaci do "
                "ulepszenia.\n"
                "3. **Mikro-nisze** — konkretne frazy poniżej top-chartów.\n"
                "4. **Zmiany** — cotygodniowy skrót zmian.\n\n"
                "Wszędzie kliknij **ℹ️ Na jakich danych?**, by zobaczyć źródła."
            )


# =========================================================================== #
#  PAGE: Opportunity Radar
# =========================================================================== #
def page_radar() -> None:
    page_header(
        "Radar okazji",
        "Automatyczny ranking nisz: duży realny popyt + słaba jakość konkurencji "
        "+ niskie nasycenie — przefiltrowane przez to, czy lean founder ma szansę "
        "wygrać (guardrail gigantów).",
    )

    if not has_any_data():
        st.info("Brak danych. Uruchom pipeline, aby zobaczyć okazje.")
        st.code("python run.py scan\npython run.py deep-dive", language="bash")
        return

    df = load_scores()
    contestable = df[df["mega_incumbents"].fillna(0) < 2]
    top = (contestable if not contestable.empty else df).iloc[0]
    tlvl, texpl = verdict(top)

    with st.container(border=True):
        st.markdown(
            f"🎯 **Rekomendacja na start:** najlepsza *osiągalna* nisza to "
            f"**{top['category']}** — Opportunity **{top['opportunity_score']:.0f}/100**, "
            f"szansa sukcesu **{pct(top['success_probability'])}**."
        )
        st.markdown(verdict_md(tlvl, texpl))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Najlepsza (osiągalna) nisza", top["category"],
              f"{top['opportunity_score']:.0f}/100")
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
            color_continuous_scale="Turbo",
        )
        st.plotly_chart(style_fig(fig, 470), use_container_width=True)
    with right:
        st.markdown("#### Ranking Opportunity Score")
        st.caption("Czerwony = rynek gigantów (2+ apki >3 mln ocen).")
        rank = df.head(12).sort_values("opportunity_score")
        colors = ["#EF4444" if m >= 2 else "#22C55E"
                  for m in rank["mega_incumbents"].fillna(0)]
        fig2 = go.Figure(go.Bar(
            x=rank["opportunity_score"], y=rank["category"], orientation="h",
            marker_color=colors, text=[f"{v:.0f}" for v in rank["opportunity_score"]],
            textposition="outside"))
        fig2.update_layout(xaxis_title="Opportunity")
        st.plotly_chart(style_fig(fig2, 470), use_container_width=True)

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
                         "mega_incumbents": "Giganci",
                         "est_installs_month": "Instalacje/mies. (budżet)"}),
        width="stretch", hide_index=True,
        column_config={"Opportunity": st.column_config.ProgressColumn(
            "Opportunity", min_value=0, max_value=100, format="%.0f")},
    )
    st.caption("Przejdź do **Analiza**, by zobaczyć problemy użytkowników "
               "i kandydatów do ulepszenia w wybranej niszy.")
    ui.how_button(["opportunity_score", "growth", "installs", "contestability",
                   "cpi", "verdict"], key="radar_how_table")

    st.divider()
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("#### 🚀 Breakout — apki najszybciej rosnące")
        st.caption("Największy skok pozycji względem poprzedniego skanu. "
                   "Wymaga ≥2 dni historii.")
        rising = rising_apps_df(limit=15)
        if rising.empty:
            st.info("Brak danych o breakoutach — potrzebne min. 2 skany.")
        else:
            st.dataframe(rising.rename(columns={
                "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
                "rank_now": "Pozycja teraz", "rank_prev": "Poprzednio",
                "rank_delta": "Skok (↑)", "rating_count": "Liczba ocen"}),
                width="stretch", hide_index=True)
    with m2:
        st.markdown("#### 📉 Spadki jakości — świeże luki")
        st.caption("Silne apki, których średnia ocena spada między skanami. "
                   "Wymaga ≥2 dni historii.")
        movers = quality_movers_df(limit=15)
        if movers.empty:
            st.info("Brak wykrytych spadków ocen (potrzebne min. 2 skany).")
        else:
            st.dataframe(movers.rename(columns={
                "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
                "rating_now": "Ocena teraz", "rating_prev": "Poprzednio",
                "rating_drop": "Spadek (★)", "rating_count": "Liczba ocen"}),
                width="stretch", hide_index=True)


# =========================================================================== #
#  PAGE: Niche Deep Dive
# =========================================================================== #
def page_deep() -> None:
    page_header(
        "Głęboka analiza niszy",
        "Wybierz niszę, by zobaczyć rozbicie score, problemy użytkowników, "
        "brakujące funkcje i konkretnych kandydatów do „sklonuj i ulepsz\".",
    )

    if not has_any_data():
        st.info("Brak danych. Uruchom pipeline, aby zobaczyć okazje.")
        st.code("python run.py scan\npython run.py deep-dive", language="bash")
        return

    df = load_scores()
    names = df["category"].tolist()

    # Annotate each option with its score + verdict so the user picks informed,
    # instead of choosing a category name blind.
    _emoji = {"STRONG": "🟢", "WATCH": "🟡", "SKIP": "🔴"}
    _meta = {}
    for _, r in df.iterrows():
        lvl, _ = verdict(r)
        _meta[r["category"]] = (r["opportunity_score"] or 0, lvl)

    def _fmt(name: str) -> str:
        opp, lvl = _meta.get(name, (0, "SKIP"))
        return f"{_emoji.get(lvl, '⚪')} {name} — {opp:.0f}/100 · {lvl}"

    choice = st.selectbox("Wybierz niszę", names, index=0, format_func=_fmt)
    row = df[df["category"] == choice].iloc[0]
    genre_id = int(row["genre_id"])
    level, expl = verdict(row)

    st.markdown(f"### {choice} &nbsp; {verdict_md(level, expl)}")

    # Bridge the potential contradiction between the hard-metric verdict and the
    # (often enthusiastic) qualitative AI analysis further down the page.
    if level == "STRONG":
        st.success("✅ **Werdykt STRONG.** Twarde metryki i szansa wejścia są po "
                   "Twojej stronie — to realny cel przy Twoim budżecie. Poniżej "
                   "znajdziesz konkretne słabości konkurencji do wykorzystania.")
    elif level == "WATCH":
        st.info("👀 **Werdykt WATCH.** Obiecujące, ale sygnał nie jest jeszcze "
                "pewny — obserwuj momentum i potraktuj analizę poniżej jako "
                "kierunek do przetestowania na węższej pod-niszy.")
    else:  # SKIP
        st.info("🔴 **Werdykt SKIP** opiera się na *twardych metrykach* całej "
                "kategorii (popyt, nasycenie, budżet). To **nie** znaczy, że nie ma "
                "tu okazji — analiza AI poniżej często wskazuje realne luki. "
                "Potraktuj ją jako inspirację do **węższej, konkretnej pod-niszy**, "
                "a nie do frontalnego ataku na całą kategorię.")

    mega = int(row.get("mega_incumbents", 0) or 0)
    if mega >= 2:
        st.error(
            f"🛑 **Guardrail gigantów:** ta kategoria ma **{mega}** aplikacje z ponad "
            f"3 mln ocen. Konkurowanie z nimi przy budżecie "
            f"{pln(settings.marketing_budget_pln)}/mies. jest nierealne — potraktuj "
            f"wnioski jako inspirację do **węższej pod-niszy**, nie do frontalnego ataku."
        )

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Opportunity", f"{row['opportunity_score']:.0f}/100",
              help="0–100. ⬆️ wyżej = lepiej. Łączny wskaźnik atrakcyjności "
                   "i zdobywalności niszy.")
    m2.metric("Szansa sukcesu", pct(row["success_probability"]),
              help="⬆️ wyżej = lepiej. Szansa zdobycia przyczółka przy Twoim budżecie.")
    m3.metric("Śr. ocena konk.",
              f"{row['avg_rating_top']:.2f}" if row["avg_rating_top"] else "-",
              help="Średnia ocena konkurentów. ⬇️ NIŻEJ = lepiej dla Ciebie "
                   "(słaba konkurencja = łatwiej ją pobić jakością).")
    m4.metric("Twierdze", num(row["strong_incumbents"]),
              help="Silni, okopani gracze (dużo ocen + wysoka ocena). "
                   "⬇️ NIŻEJ = lepiej.")
    m5.metric("Giganci (>3M)", num(row.get("mega_incumbents", 0)),
              help="Apki z >3 mln ocen — praktycznie nie do pobicia. "
                   "2+ = automatyczny SKIP. ⬇️ NIŻEJ = lepiej.")
    m6.metric("Contestability", f"{row.get('contestability', 1):.2f}",
              help="0–1. Czy lean founder ma realną szansę wejść. "
                   "⬆️ WYŻEJ = lepiej.")
    ui.how_button(["opportunity_score", "success_probability", "quality_gap",
                   "strong_incumbents", "mega_incumbents", "contestability"],
                  key="dd_how_metrics")

    stale = int(row.get("stale_incumbents", 0) or 0)
    days_upd = row.get("median_days_since_update")
    if stale > 0:
        st.warning(
            f"🕳️ **Porzucone forty:** {stale} silnych aplikacji nie było "
            f"aktualizowanych >12 miesięcy — dojrzałe do podbicia aktywnie "
            f"rozwijanym produktem."
        )
    if days_upd is not None and pd.notna(days_upd):
        st.caption(f"Mediana czasu od ostatniej aktualizacji: **{int(days_upd)} dni**. "
                   f"Rank momentum: **{row.get('rank_momentum', 0):+.2f}** "
                   f"(dodatni = apki pną się w górę).")

    typ_band = installs_label(row.get("median_rating_count"))
    st.caption(f"📦 **Skala rynku (heurystyka):** typowa apka to **{typ_band}** "
               f"instalacji (lifetime), szacowane rzędem wielkości z liczby ocen.")

    st.divider()
    left, right = st.columns([2, 3])
    with left:
        st.markdown("#### Rozbicie score")
        comp = pd.DataFrame({
            "Składnik": ["Popyt", "Luka jakości", "Niskie nasycenie", "Momentum"],
            "Wartość": [row["demand"], row["quality_gap"], row["low_saturation"],
                        row["momentum"]],
        })
        figc = go.Figure(go.Bar(
            x=comp["Wartość"], y=comp["Składnik"], orientation="h",
            marker_color="#7C5CFC",
            text=[f"{v:.2f}" for v in comp["Wartość"]], textposition="outside"))
        figc.update_layout(xaxis_range=[0, 1])
        st.plotly_chart(style_fig(figc, 240), use_container_width=True)
        ui.how_button(["demand", "quality_gap", "low_saturation", "momentum"],
                      key="dd_how_breakdown")

        hist = category_rating_history(genre_id)
        if len(hist) >= 2:
            st.markdown("#### Trend jakości konkurencji")
            figt = go.Figure(go.Scatter(
                x=hist["date"], y=hist["avg_rating"],
                mode="lines+markers", line=dict(color="#F59E0B")))
            figt.update_layout(yaxis_title="Śr. ocena")
            st.plotly_chart(style_fig(figt, 210), use_container_width=True)
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
        st.caption("CPI = benchmark kategorii. Instalacje = budżet / CPI. Szansa "
                   "sukcesu łączy atrakcyjność niszy, lukę jakościową, zasięg płatny "
                   "i contestability.")

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
            st.caption("🔎 Tryb: POZYCJONOWANIE — brak tekstu recenzji. Wnioski z "
                       "opisów konkurentów + metryk. Podłącz provider recenzji dla "
                       "pełnych pain-pointów.")
        else:
            st.caption(f"🔎 Tryb: RECENZJE — analiza {insight.reviews_analyzed} recenzji.")

        st.markdown("#### Executive Summary")
        st.info(insight.executive_summary or "—")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### Główne problemy użytkowników")
            pains = insight.pain_points or []
            if not pains:
                st.caption("Brak wyodrębnionych problemów.")
            for p in pains:
                sev = (p.get("severity") or "").lower()
                color = {"high": "red", "medium": "orange", "low": "gray"}.get(sev, "gray")
                tag = {"high": "HIGH", "medium": "MED", "low": "LOW"}.get(sev, "—")
                with st.container(border=True):
                    st.markdown(f":{color}-background[**{tag}**] **{p.get('label','')}**")
                    if p.get("description"):
                        st.caption(p.get("description"))
        with col_b:
            st.markdown("#### Brakujące funkcje (popyt niezaspokojony)")
            feats = insight.missing_features or []
            if not feats:
                st.caption("Brak wyodrębnionych braków.")
            for f in feats:
                with st.container(border=True):
                    st.markdown(f":blue-background[**FEATURE**] **{f.get('label','')}**")
                    if f.get("description"):
                        st.caption(f.get("description"))

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
    candidates = (rank_candidates(comp_df.to_dict("records"), limit=5)
                  if not comp_df.empty else [])
    ui.render_candidates(candidates, missing_features=missing_features)
    ui.how_button(["candidates"], key="dd_how_cand")

    # ---- Action plan: turn all the analysis above into concrete next steps ---
    st.divider()
    with st.container(border=True):
        st.markdown("#### ✅ Co zrobić dalej? (plan działania)")
        steps: list[str] = []
        if candidates:
            c0 = candidates[0]
            steps.append(
                f"**1. Wybierz wzorzec do pobicia:** zacznij od **{c0.name}** "
                f"(beatability {c0.beatability:.0f}/100) — udowodniony popyt "
                f"i wykorzystywalna słabość."
            )
        feats = [f.get("label", "") for f in (missing_features or []) if f.get("label")]
        if feats:
            steps.append(
                "**2. Zbuduj przewagę:** zaadresuj brakujące funkcje: "
                f"**{', '.join(feats[:3])}**."
            )
        elif insight and (insight.pain_points or []):
            top_pain = (insight.pain_points or [])[0].get("label", "")
            if top_pain:
                steps.append(f"**2. Zbuduj przewagę:** rozwiąż główny ból "
                             f"użytkowników: **{top_pain}**.")
        steps.append(
            "**3. Zawęź pozycjonowanie:** wejdź w konkretną pod-niszę "
            "(patrz zakładka **Mikro-nisze**), zamiast atakować całą kategorię."
        )
        steps.append(
            f"**4. Sprawdź ekonomię:** przy budżecie "
            f"{pln(row['marketing_cost_pln'])}/mies. i CPI {pln(row['est_cpi_pln'])} "
            f"kupisz ok. **{num(row['est_installs_month'])} instalacji/mies.** — "
            f"upewnij się, że to wystarczy na pierwszą trakcję."
        )
        for s in steps:
            st.markdown(f"- {s}")
        if level == "SKIP":
            st.caption("⚠️ Pamiętaj: werdykt tej kategorii to SKIP. Powyższy plan "
                       "ma sens tylko dla **wąskiej pod-niszy**, nie dla całego rynku.")

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


# =========================================================================== #
#  PAGE: Micro-Niche Explorer
# =========================================================================== #
def page_micro() -> None:
    page_header(
        "Mikro-nisze",
        "Poziom PONIŻEJ top-chartów. AI proponuje konkretne mikro-nisze (frazy), "
        "a Search API waliduje je tym samym guardrailem contestability. "
        "Kliknij wiersz w tabeli, aby zobaczyć szczegóły.",
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
            genre_name = st.selectbox("Kontekst kategorii (CPI + AI)",
                                      list(genre_options))
            theme = st.text_input("Motyw dla generatora AI",
                                  placeholder="np. habit tracking for ADHD")
        cA, cB = st.columns(2)
        gen = cA.checkbox("Wygeneruj kandydatów przez AI", value=False,
                          help="Wymaga GEMINI_API_KEY. AI zaproponuje mikro-nisze.")
        n_kw = cB.slider("Ile wygenerować", 5, 25, 12)
        submitted = st.form_submit_button("Analizuj mikro-nisze", type="primary",
                                          width="stretch")

    if submitted:
        genre_id = genre_options[genre_name]
        terms = [t.strip() for t in terms_raw.replace("\n", ",").split(",") if t.strip()]
        if gen and not settings.llm_enabled:
            st.warning("Generator AI wymaga GEMINI_API_KEY. Podaj słowa ręcznie "
                       "albo skonfiguruj klucz.")
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
        st.info("Brak przeanalizowanych mikro-nisz. Wpisz słowa kluczowe powyżej "
                "i kliknij Analizuj.")
        return

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

    picked = st.session_state.get("kw_pick", kdf["term"].iloc[0])
    if event.selection.rows:
        picked = kdf.iloc[event.selection.rows[0]]["term"]
        st.session_state["kw_pick"] = picked

    st.divider()
    terms_list = kdf["term"].tolist()
    idx = terms_list.index(picked) if picked in terms_list else 0
    picked = st.selectbox("Szczegóły mikro-niszy", terms_list, index=idx)
    krow = kdf[kdf["term"] == picked].iloc[0]

    lvl, expl = verdict(krow)
    st.markdown(f"### {picked} &nbsp; {verdict_md(lvl, expl)}")
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
        st.caption("Do 5 apek z udowodnionym popytem ale wykorzystywalną słabością.")
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


# =========================================================================== #
#  PAGE: What changed (weekly digest)
# =========================================================================== #
def page_digest() -> None:
    page_header(
        "Co się zmieniło",
        "Cotygodniowy brief: rosnące nisze, najlepsze osiągalne okazje, nowe "
        "mikro-nisze, breakouty, spadki jakości i porzucone forty — w jednym miejscu.",
    )
    if not has_any_data():
        st.info("Brak danych. Uruchom `python run.py scan`, a najlepszy sygnał "
                "pojawi się po kilku dniach zbierania.")
        return
    weeks = st.slider("Okno wzrostu (tygodnie)", 1, 12, 4)
    with st.spinner("Składam digest…"):
        from src.pipeline.digest import build_digest
        with st.container(border=True):
            st.markdown(build_digest(weeks=weeks))


# --------------------------------------------------------------------------- #
#  App shell — sidebar + native top navigation
# --------------------------------------------------------------------------- #
render_sidebar()

nav = st.navigation(
    [
        st.Page(page_radar, title="Radar", icon=":material/radar:", default=True),
        st.Page(page_deep, title="Analiza", icon=":material/biotech:"),
        st.Page(page_micro, title="Mikro-nisze", icon=":material/target:"),
        st.Page(page_digest, title="Zmiany", icon=":material/trending_up:"),
    ],
    position="top",
)
nav.run()

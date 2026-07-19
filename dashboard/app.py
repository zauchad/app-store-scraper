"""Streamlit dashboard - the analyst's cockpit.

Two views, mirroring the two-level model:
  1. Opportunity Radar  - the auto-ranked niche heatmap (Level 1, quantitative).
  2. Niche Deep Dive     - Executive Summary + pain points + missing features +
                            suggested direction + marketing feasibility (Level 2).

Design intent: NO raw tables as the headline. Every screen leads with a business
conclusion ("here is where the opportunity is and whether you can afford it").
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `src` importable when Streamlit runs this file directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

# Bridge Streamlit Cloud secrets -> env vars BEFORE importing settings, so
# pydantic-settings picks them up regardless of platform behaviour.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:  # noqa: BLE001 - no secrets file locally is fine
    pass

from src.config import settings  # noqa: E402
from src.db.session import init_db  # noqa: E402
from src.reporting import (  # noqa: E402
    has_any_data,
    latest_insight,
    latest_scores_df,
    top_apps_for_category,
)

st.set_page_config(
    page_title="Market Research Intelligence", page_icon="", layout="wide"
)

init_db()


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


def verdict(row) -> str:
    opp = row["opportunity_score"]
    prob = row["success_probability"] or 0
    if opp >= 65 and prob >= 0.5:
        return "STRONG — realna, osiągalna nisza przy Twoim budżecie"
    if opp >= 50:
        return "WATCH — obiecująca, obserwuj momentum kolejnych dni"
    return "SKIP — słaby sygnał lub zbyt drogo/za ciasno"


# --------------------------------------------------------------------------- #
#  Sidebar
# --------------------------------------------------------------------------- #
st.sidebar.title("Market Intel")
view = st.sidebar.radio("Widok", ["Opportunity Radar", "Niche Deep Dive"])
st.sidebar.caption(
    f"Storefront: `{settings.store_country}`  |  Budżet: {pln(settings.marketing_budget_pln)}/mies."
)
st.sidebar.caption(
    "Gry są domyślnie wykluczone (kapitałochłonne). "
    "Zmień w `.env` (EXCLUDED_GENRE_IDS)."
)
if not settings.llm_enabled:
    st.sidebar.warning("LLM wyłączony — brak GEMINI_API_KEY. Deep Dive niedostępny.")

if not has_any_data():
    st.title("Brak danych")
    st.info(
        "Nie ma jeszcze żadnego skanu. Uruchom pipeline:\n\n"
        "```bash\npython run.py scan\npython run.py deep-dive\n```\n\n"
        "Potem odśwież tę stronę."
    )
    st.stop()

df = load_scores()


# --------------------------------------------------------------------------- #
#  View 1: Opportunity Radar
# --------------------------------------------------------------------------- #
if view == "Opportunity Radar":
    st.title("Opportunity Radar")
    st.caption(
        "Automatyczny ranking nisz. Szukamy: wysoki popyt + słaba jakość konkurencji "
        "+ niskie nasycenie + rosnące momentum — a wszystko przefiltrowane przez to, "
        "czy Twój budżet marketingowy realnie wystarczy."
    )

    top = df.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Najlepsza nisza", top["category"], f"{top['opportunity_score']:.0f}/100")
    c2.metric("Szansa sukcesu", pct(top["success_probability"]))
    c3.metric("Szac. instalacje/mies.", f"{int(top['est_installs_month'] or 0):,}".replace(",", " "))
    c4.metric("Analizowane nisze", len(df))

    st.divider()

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Mapa okazji: popyt vs luka jakościowa")
        st.caption(
            "Prawy-górny róg = duży popyt i słabe oceny konkurencji = najlepsze "
            "polowanie. Rozmiar bąbla = szansa sukcesu przy Twoim budżecie."
        )
        fig = px.scatter(
            df,
            x="demand",
            y="quality_gap",
            size=(df["success_probability"].fillna(0.05) * 100 + 5),
            color="opportunity_score",
            hover_name="category",
            labels={
                "demand": "Popyt (znormalizowany)",
                "quality_gap": "Luka jakościowa (im wyżej, tym gorsza konkurencja)",
                "opportunity_score": "Opportunity",
            },
            color_continuous_scale="Viridis",
            height=460,
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Ranking Opportunity Score")
        fig2 = px.bar(
            df.head(12).sort_values("opportunity_score"),
            x="opportunity_score",
            y="category",
            orientation="h",
            color="opportunity_score",
            color_continuous_scale="Viridis",
            height=460,
        )
        fig2.update_layout(showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("Tabela decyzyjna")
    display = df.copy()
    display["verdict"] = display.apply(verdict, axis=1)
    display["success"] = display["success_probability"].apply(pct)
    display["cpi"] = display["est_cpi_pln"].apply(pln)
    display["budget"] = display["marketing_cost_pln"].apply(pln)
    st.dataframe(
        display[
            [
                "category",
                "opportunity_score",
                "success",
                "avg_rating_top",
                "strong_incumbents",
                "est_installs_month",
                "cpi",
                "verdict",
            ]
        ].rename(
            columns={
                "category": "Kategoria",
                "opportunity_score": "Opportunity",
                "success": "Szansa",
                "avg_rating_top": "Śr. ocena TOP",
                "strong_incumbents": "Twierdze",
                "est_installs_month": "Instalacje/mies.",
                "cpi": "CPI",
                "verdict": "Werdykt",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


# --------------------------------------------------------------------------- #
#  View 2: Niche Deep Dive
# --------------------------------------------------------------------------- #
else:
    st.title("Niche Deep Dive")
    names = df["category"].tolist()
    choice = st.selectbox("Wybierz niszę", names, index=0)
    row = df[df["category"] == choice].iloc[0]
    genre_id = int(row["genre_id"])

    st.subheader(f"{choice}  —  {verdict(row)}")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Opportunity", f"{row['opportunity_score']:.0f}/100")
    m2.metric("Szansa sukcesu", pct(row["success_probability"]))
    m3.metric("Śr. ocena konkurencji", f"{row['avg_rating_top']:.2f}" if row["avg_rating_top"] else "-")
    m4.metric("Silne twierdze", int(row["strong_incumbents"]))
    m5.metric("Momentum", f"{row['momentum']:.2f}")

    st.divider()

    insight = latest_insight(genre_id)

    if insight is None:
        st.warning(
            "Brak analizy LLM dla tej niszy. Uruchom:\n\n"
            f"```bash\npython run.py deep-dive --genre {genre_id}\n```"
        )
    else:
        source_mode = (insight.raw_json or {}).get("_source_mode", "reviews")
        if source_mode == "positioning":
            st.caption(
                "Tryb: POZYCJONOWANIE — brak tekstu recenzji (feed Apple martwy w 2026). "
                "Wnioski wyprowadzone z opisów konkurentów + metryk. Podłącz provider "
                "recenzji, by uzyskać pełne pain-pointy (patrz README)."
            )
        else:
            st.caption(f"Tryb: RECENZJE — analiza {insight.reviews_analyzed} recenzji.")

        st.subheader("Executive Summary")
        st.info(insight.executive_summary or "—")

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Główne problemy użytkowników")
            for p in (insight.pain_points or []):
                sev = (p.get("severity") or "").lower()
                badge = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}.get(sev, "")
                st.markdown(f"**{badge} {p.get('label', '')}**  \n{p.get('description', '')}")
        with col_b:
            st.subheader("Brakujące funkcje (popyt niezaspokojony)")
            for f in (insight.missing_features or []):
                st.markdown(f"**{f.get('label', '')}**  \n{f.get('description', '')}")

        st.divider()
        st.subheader("Sugerowany kierunek dla Twojej aplikacji")
        st.success(insight.suggested_direction or "—")
        if insight.market_saturation_note:
            st.caption(f"Nasycenie rynku: {insight.market_saturation_note}")
        st.caption(
            f"Analiza: {insight.reviews_analyzed} recenzji  |  model: {insight.llm_model}  "
            f"|  {insight.generated_at:%Y-%m-%d %H:%M}"
        )

    st.divider()
    st.subheader("Ekonomia wejścia (przy Twoim budżecie)")
    e1, e2, e3 = st.columns(3)
    e1.metric("Budżet / mies.", pln(row["marketing_cost_pln"]))
    e2.metric("Szac. CPI", pln(row["est_cpi_pln"]))
    e3.metric("Instalacje / mies.", f"{int(row['est_installs_month'] or 0):,}".replace(",", " "))
    st.caption(
        "CPI to szacunek benchmarkowy dla kategorii (edytowalny w seedzie kategorii). "
        "Instalacje = budżet / CPI. Szansa sukcesu łączy atrakcyjność niszy, lukę "
        "jakościową (potencjał organiczny) oraz realny zasięg płatny vs skala konkurencji."
    )

    with st.expander("Konkurenci w tej niszy"):
        apps_df = top_apps_for_category(genre_id)
        if apps_df.empty:
            st.caption("Brak danych o aplikacjach.")
        else:
            st.dataframe(apps_df, use_container_width=True, hide_index=True)

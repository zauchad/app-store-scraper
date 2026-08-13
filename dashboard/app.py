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
from dashboard.landing_page import render_landing_page  # noqa: E402
from dashboard.theme import (  # noqa: E402
    inject_global_styles,
    CHART_PRIMARY,
    CHART_OPPORTUNITY_SCALE,
    CHART_BARS_GOOD,
    CHART_BARS_BAD,
    CHART_TREND,
    CHART_PAIN,
    TEXT,
)
from src.analysis.candidates import rank_candidates  # noqa: E402
from src.analysis.estimates import lifetime_installs  # noqa: E402
from src.config import settings  # noqa: E402
from src.db.session import init_db  # noqa: E402
from src.reporting import (  # noqa: E402
    category_growth_df,
    category_rating_history,
    competitors_for_category,
    declining_apps_df,
    developer_concentration_df,
    has_any_data,
    latest_insight,
    latest_keyword_scores_df,
    latest_scores_df,
    localization_gap_df,
    pain_mining_for_apps,
    pain_mining_for_category,
    quality_movers_df,
    recent_release_notes_df,
    rising_apps_df,
    young_winners_df,
)
from dashboard.account_page import page_account  # noqa: E402
from dashboard.auth import (  # noqa: E402
    init_auth,
    is_logged_in,
    render_auth_sidebar,
    render_password_recovery,
    render_payment_banner,
)
from src.billing.credits import monetization_active  # noqa: E402
from dashboard.billing_ui import (  # noqa: E402
    is_content_unlocked,
    limit_radar_apps,
    limit_radar_niches,
    render_csv_gate,
    render_radar_pro_upsell,
    render_unlock_gate,
    _locked_label,
)
from src.billing.usage import (  # noqa: E402
    can_run_keyword_scan,
    keyword_scans_remaining,
    record_keyword_scan,
)
from dashboard.auth import current_user_id  # noqa: E402
from src.billing.credits import niche_key as billing_niche_key  # noqa: E402
from src.billing.credits import keyword_niche_key  # noqa: E402
from src.scraper.categories import CATEGORY_SEEDS  # noqa: E402

from src.scraper.storefronts import STOREFRONTS  # noqa: E402

# Sidebar controls — budget recalculates marketing math live; storefront switches
# between US / PL data collected by the daily scan.
STOREFRONT_OPTIONS = STOREFRONTS
BUDGET_OPTIONS_PLN = [3000, 5000, 7500, 10000, 15000, 20000, 25000]

st.set_page_config(
    page_title="Market Intel — App Store Niche Radar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# Global theme — see dashboard/theme.py + .streamlit/config.toml
inject_global_styles(landing=False)


# --------------------------------------------------------------------------- #
#  Formatting helpers
# --------------------------------------------------------------------------- #
def dashboard_budget_pln() -> float:
    return float(
        st.session_state.get("dashboard_budget_pln", settings.marketing_budget_pln)
    )


def dashboard_storefront() -> str:
    return str(
        st.session_state.get("dashboard_storefront", "us")
    ).lower()


def report_country() -> str:
    return dashboard_storefront()


def _apply_marketing_budget(df: pd.DataFrame, budget: float) -> pd.DataFrame:
    """Recompute installs / success for the sidebar budget (CPI stays from scan)."""
    if df.empty:
        return df
    from src.analysis.marketing import estimate

    out = df.copy()
    for idx, row in out.iterrows():
        cpi = row.get("est_cpi_pln")
        if cpi is None or pd.isna(cpi) or float(cpi) <= 0:
            continue
        base_cpi_usd = float(cpi) / settings.usd_pln_rate
        m = estimate(
            base_cpi_usd=base_cpi_usd,
            opportunity_0_100=float(row.get("opportunity_score") or 0),
            quality_gap_0_1=float(row.get("quality_gap") or 0),
            contestability=float(row.get("contestability") or 1.0),
            total_rating_count=int(
                row.get("total_rating_count")
                or (row.get("median_rating_count") or 0)
                * max(int(row.get("num_apps") or row.get("num_results") or 0), 1)
            ),
            num_apps=int(row.get("num_apps") or row.get("num_results") or 0),
            budget_pln=budget,
        )
        out.at[idx, "est_installs_month"] = m.est_installs_month
        out.at[idx, "marketing_cost_pln"] = m.marketing_cost_pln
        out.at[idx, "success_probability"] = m.success_probability
    return out


@st.cache_data(ttl=300)
def _scores_raw(country: str) -> pd.DataFrame:
    return latest_scores_df(country)


@st.cache_data(ttl=300)
def _keywords_raw() -> pd.DataFrame:
    return latest_keyword_scores_df()


def load_scores() -> pd.DataFrame:
    cc = report_country()
    return _apply_marketing_budget(_scores_raw(cc), dashboard_budget_pln())


def load_keyword_scores() -> pd.DataFrame:
    return _apply_marketing_budget(_keywords_raw(), dashboard_budget_pln())


@st.cache_data(ttl=3600, show_spinner=False)
def load_pain_mining(genre_id: int):
    """Full-corpus review mining is heavy (100k+ rows) -> cache for an hour."""
    return pain_mining_for_category(genre_id)


def keyword_pain_teaser(krow) -> str:
    """Same idea as `pain_teaser`, scoped to a micro-niche's competitor set."""
    apps = krow.get("top_apps") or []
    app_ids = tuple(int(a["app_id"]) for a in apps if a.get("app_id"))
    if not app_ids:
        return ""
    try:
        mining = load_pain_mining_apps(app_ids)
    except Exception:  # noqa: BLE001
        return ""
    if not mining or not mining.themes or mining.reviews_negative <= 0:
        return (
            f"{len(app_ids)} konkurentów walczy o tę frazę — pełna lista "
            "z ocenami i wydawcami po odblokowaniu."
        )
    top = mining.themes[0]
    return (
        f"konkurenci tej frazy najczęściej zawodzą przy **{top.theme}** "
        f"({top.share * 100:.0f}% negatywnych recenzji). "
        "Geo-radar, popyt z Reddita i pełna lista konkurentów — po odblokowaniu."
    )


def pain_teaser(genre_id: int) -> str:
    """One real finding from behind the paywall — a concrete promise beats bullets."""
    try:
        mining = load_pain_mining(genre_id)
    except Exception:  # noqa: BLE001
        return ""
    if not mining or not mining.themes or mining.reviews_negative <= 0:
        return ""
    top = mining.themes[0]
    return (
        f"najczęstszy ból konkurencji to **{top.theme}** — "
        f"{top.share * 100:.0f}% negatywnych recenzji "
        f"(z {num(mining.reviews_total)} przeanalizowanych). "
        "Pełna lista tematów, cytaty i apki najbardziej znienawidzone — po odblokowaniu."
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_pain_mining_apps(app_ids: tuple):
    return pain_mining_for_apps(list(app_ids))


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
        plot_bgcolor="rgba(129, 140, 248, 0.04)",
        font=dict(color=TEXT),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)", zerolinecolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)", zerolinecolor="rgba(255,255,255,0.08)")
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
    if "dashboard_storefront" not in st.session_state:
        st.session_state.dashboard_storefront = "us"
    if "dashboard_budget_pln" not in st.session_state:
        default_budget = int(settings.marketing_budget_pln)
        st.session_state.dashboard_budget_pln = (
            default_budget
            if default_budget in BUDGET_OPTIONS_PLN
            else BUDGET_OPTIONS_PLN[2]  # 7500
        )

    with st.sidebar:
        st.markdown("### 📡 Market Intel")
        st.caption("App Store Niche Radar")
        st.divider()

        st.markdown("**Konfiguracja**")
        st.selectbox(
            "Storefront",
            list(STOREFRONT_OPTIONS),
            format_func=lambda c: STOREFRONT_OPTIONS.get(c, c.upper()),
            key="dashboard_storefront",
            help="Przełącz między danymi ze skanów US i PL (zbierane codziennie w CI).",
        )
        st.selectbox(
            "Budżet / mies.",
            BUDGET_OPTIONS_PLN,
            format_func=lambda b: pln(b),
            key="dashboard_budget_pln",
            help=(
                "Twój miesięczny budżet marketingowy (PLN). Przelicza na żywo "
                "instalacje/mies. i szansę sukcesu (CPI z niszy × budżet ÷ CPI)."
            ),
        )
        st.caption(
            f"Skanowane rynki: **{' · '.join(c.upper() for c in STOREFRONT_OPTIONS)}**."
        )
        st.caption("Gry wykluczone (kapitałochłonne).")

        if settings.llm_enabled:
            st.success("LLM: aktywny (Gemini)", icon=":material/check_circle:")
        else:
            st.warning("LLM OFF — brak GEMINI_API_KEYS.", icon=":material/warning:")

        vol = settings.volume_provider.lower()
        st.caption(f"Popyt wyszukiwań: **{'Apple Ads (oficjalny)' if vol == 'asa' else 'proxy autocomplete (darmowy)'}**")
        from src.scraper.reddit_demand import is_configured as _reddit_ok
        st.caption(f"Reddit demand: **{'aktywny' if _reddit_ok() else 'OFF (darmowa konfiguracja w .env)'}**")

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

        render_auth_sidebar()


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
            color_continuous_scale=CHART_OPPORTUNITY_SCALE,
        )
        st.plotly_chart(style_fig(fig, 470), use_container_width=True)
    with right:
        st.markdown("#### Ranking Opportunity Score")
        st.caption("Czerwony = rynek gigantów (2+ apki >3 mln ocen).")
        rank = df.head(12).sort_values("opportunity_score")
        colors = [CHART_BARS_BAD if m >= 2 else CHART_BARS_GOOD
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
    cc = report_country()
    gdf = category_growth_df(weeks=4, country=cc)
    if not gdf.empty:
        disp = disp.merge(gdf[["genre_id", "growth_pct"]], on="genre_id", how="left")
        disp["Wzrost 4-tyg."] = disp["growth_pct"].apply(
            lambda x: f"{x * 100:+.0f}%" if pd.notna(x) else "n/d")
    else:
        disp["Wzrost 4-tyg."] = "n/d"
    disp_show, hidden_niches = limit_radar_niches(disp)
    st.dataframe(
        disp_show[["category", "opportunity_score", "Szansa", "Wzrost 4-tyg.",
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
    render_radar_pro_upsell(hidden=hidden_niches, kind="nisz w rankingu")
    st.caption("Przejdź do **Analiza**, by zobaczyć problemy użytkowników "
               "i kandydatów do ulepszenia w wybranej niszy.")
    cexp1, cexp2 = st.columns([1, 4])
    if render_csv_gate():
        cexp1.download_button(
            "⬇️ Eksport CSV", data=disp.to_csv(index=False).encode("utf-8"),
            file_name="radar-nisz.csv", mime="text/csv", key="radar_csv",
        )
    with cexp2:
        ui.how_button(["opportunity_score", "growth", "installs", "contestability",
                       "cpi", "verdict"], key="radar_how_table")

    st.divider()
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("#### 🚀 Breakout — apki najszybciej rosnące")
        st.caption("Największy skok pozycji względem poprzedniego skanu. "
                   "Wymaga ≥2 dni historii.")
        rising = rising_apps_df(limit=15, country=cc)
        if rising.empty:
            st.info("Brak danych o breakoutach — potrzebne min. 2 skany.")
        else:
            rising_show, hidden_r = limit_radar_apps(rising)
            st.dataframe(rising_show.rename(columns={
                "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
                "rank_now": "Pozycja teraz", "rank_prev": "Poprzednio",
                "rank_delta": "Skok (↑)", "rating_count": "Liczba ocen"}),
                width="stretch", hide_index=True)
            render_radar_pro_upsell(hidden=hidden_r, kind="breakoutów")
    with m2:
        st.markdown("#### 📉 Spadki jakości — świeże luki")
        st.caption("Silne apki, których średnia ocena spada między skanami. "
                   "Wymaga ≥2 dni historii.")
        movers = quality_movers_df(limit=15, country=cc)
        if movers.empty:
            st.info("Brak wykrytych spadków ocen (potrzebne min. 2 skany).")
        else:
            movers_show, hidden_m = limit_radar_apps(movers)
            st.dataframe(movers_show.rename(columns={
                "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
                "rating_now": "Ocena teraz", "rating_prev": "Poprzednio",
                "rating_drop": "Spadek (★)", "rating_count": "Liczba ocen"}),
                width="stretch", hide_index=True)
            render_radar_pro_upsell(hidden=hidden_m, kind="spadków jakości")

    dec_all = declining_apps_df(country=cc)
    if not dec_all.empty:
        st.divider()
        st.markdown("#### 🩹 Bieżąca wersja gorsza niż średnia — użytkownicy "
                    "odwracają się TERAZ")
        st.caption("Porównanie oceny bieżącej wersji z oceną lifetime (iTunes "
                   "Lookup) — świeża luka widoczna już po jednym skanie.")
        dec_show, hidden_d = limit_radar_apps(dec_all)
        st.dataframe(dec_show.rename(columns={
            "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
            "rating_lifetime": "Ocena lifetime",
            "rating_current_version": "Ocena bieżącej wersji",
            "delta": "Spadek (★)", "rating_count": "Liczba ocen"}),
            width="stretch", hide_index=True)
        render_radar_pro_upsell(hidden=hidden_d, kind="psujących się apek")
        ui.how_button(["declining"], key="radar_how_declining")


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
    cc = report_country()
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
    nk = billing_niche_key(kind="category", country=cc, identifier=genre_id)
    full_access = is_content_unlocked(nk)
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
            f"{pln(dashboard_budget_pln())}/mies. jest nierealne — potraktuj "
            f"wnioski jako inspirację do **węższej pod-niszy**, nie do frontalnego ataku."
        )

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Opportunity", f"{row['opportunity_score']:.0f}/100",
              help="0–100. ⬆️ wyżej = lepiej. Łączny wskaźnik atrakcyjności "
                   "i zdobywalności niszy.")
    m2.metric("Szansa sukcesu",
              pct(row["success_probability"]) if full_access else _locked_label(),
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
    m6.metric("Contestability",
              f"{row.get('contestability', 1):.2f}" if full_access else _locked_label(),
              help="0–1. Czy lean founder ma realną szansę wejść. "
                   "⬆️ WYŻEJ = lepiej.")
    ui.how_button(["opportunity_score", "success_probability", "quality_gap",
                   "strong_incumbents", "mega_incumbents", "contestability"],
                  key="dd_how_metrics")

    # Monetization + market fluidity (blog test #3 and #4, answered with data).
    mon = row.get("monetization_score")
    paid = row.get("paid_share")
    newc = row.get("newcomer_share")
    b1, b2, b3 = st.columns(3)
    if full_access:
        b1.metric("Monetyzacja (free→grossing)",
                  pct(mon) if pd.notna(mon) else "n/d",
                  help="Odsetek top-free apek, które są TAKŻE w top-grossing.")
        b2.metric("Apki płatne w top", pct(paid) if pd.notna(paid) else "n/d")
        b3.metric("Świeżość rynku", pct(newc) if pd.notna(newc) else "n/d")
    else:
        b1.metric("Monetyzacja (free→grossing)", _locked_label())
        b2.metric("Apki płatne w top", _locked_label())
        b3.metric("Świeżość rynku", _locked_label())
    ui.how_button(["monetization", "newcomer_share"], key="dd_how_monet")

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

    if not render_unlock_gate(
        niche_key=nk,
        niche_label=choice,
        teaser="" if full_access else pain_teaser(genre_id),
    ):
        return

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
            marker_color=CHART_PRIMARY,
            text=[f"{v:.2f}" for v in comp["Wartość"]], textposition="outside"))
        figc.update_layout(xaxis_range=[0, 1])
        st.plotly_chart(style_fig(figc, 240), use_container_width=True)
        ui.how_button(["demand", "quality_gap", "low_saturation", "momentum"],
                      key="dd_how_breakdown")

        hist = category_rating_history(genre_id, country=cc)
        if len(hist) >= 2:
            st.markdown("#### Trend jakości konkurencji")
            figt = go.Figure(go.Scatter(
                x=hist["date"], y=hist["avg_rating"],
                mode="lines+markers", line=dict(color=CHART_TREND, width=2)))
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

    # ---- Structural signals: publishers, localization, current-version -----
    st.divider()
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("#### 🏢 Kto kontroluje niszę?")
        st.caption("10 apek od 10 firm ≠ 10 apek jednej firmy. Dominujący "
                   "wydawca out-shipuje każdego nowego gracza.")
        n_devs = row.get("num_developers")
        dev_share = row.get("top_dev_share")
        cd1, cd2 = st.columns(2)
        cd1.metric("Niezależni wydawcy", num(n_devs) if pd.notna(n_devs) else "n/d")
        cd2.metric("Udział największego", pct(dev_share) if pd.notna(dev_share) else "n/d")
        if pd.notna(dev_share) and dev_share >= 0.5:
            st.warning("⚠️ Jeden wydawca kontroluje ponad połowę ocen w tej "
                       "niszy — to portfolio play, trudny przeciwnik.")
        ddf = developer_concentration_df(genre_id, country=cc)
        if not ddf.empty:
            show = ddf.copy()
            show["share"] = show["share"].apply(pct)
            st.dataframe(show.rename(columns={
                "developer": "Wydawca", "apps": "Apek w top",
                "ratings": "Suma ocen", "share": "Udział"}),
                width="stretch", hide_index=True)
        ui.how_button(["dev_concentration"], key="dd_how_devs")
    with g2:
        st.markdown("#### 🌍 Luka lokalizacyjna")
        st.caption("Duzi konkurenci tylko po angielsku = otwarta nisza "
                   "„ta sama wartość, ale w językach, których nikt nie obsługuje\".")
        en_share = row.get("english_only_share")
        st.metric("Duże apki EN-only", pct(en_share) if pd.notna(en_share) else "n/d",
                  help="Odsetek dużych konkurentów wydających apkę wyłącznie "
                       "po angielsku. ⬆️ WYŻEJ = większa okazja lokalizacyjna.")
        ldf = localization_gap_df(genre_id, country=cc)
        if ldf.empty:
            st.caption("Dane o językach pojawią się po pierwszym skanie "
                       "z rozszerzonym scraperem.")
        else:
            show = ldf.copy()
            show["english_only"] = show["english_only"].map({True: "🟠 tak", False: "nie"})
            st.dataframe(show[["name", "ratings", "num_languages", "english_only"]]
                         .rename(columns={
                             "name": "Aplikacja", "ratings": "Liczba ocen",
                             "num_languages": "Języki", "english_only": "Tylko EN"}),
                         width="stretch", hide_index=True)
        ui.how_button(["localization_gap"], key="dd_how_l10n")

    st.markdown("#### 📉 Psujące się apki — bieżąca wersja gorsza niż lifetime")
    st.caption("Użytkownicy odwracają się od apki *teraz* — najświeższy sygnał "
               "otwierającej się luki (nie wymaga historii skanów).")
    dec = declining_apps_df(genre_id, country=cc)
    if dec.empty:
        st.caption("Brak wykrytych spadków — dane bieżącej wersji pojawią się "
                   "po pierwszym skanie z rozszerzonym scraperem.")
    else:
        st.dataframe(dec.rename(columns={
            "name": "Aplikacja", "developer": "Wydawca", "category": "Kategoria",
            "rating_lifetime": "Ocena lifetime",
            "rating_current_version": "Ocena bieżącej wersji",
            "delta": "Spadek (★)", "rating_count": "Liczba ocen"}),
            width="stretch", hide_index=True)
    ui.how_button(["declining"], key="dd_how_declining")

    st.markdown("#### 🌱 Młodzi zwycięzcy — nowe apki, które już się przebiły")
    st.caption("Apki wydane w ciągu 24 miesięcy, które są już w top-chartach. "
               "Najlepszy dowód, że w tej niszy wciąż da się wejść — ich "
               "pozycjonowanie pokazuje działające punkty wejścia.")
    young = young_winners_df(genre_id, country=cc)
    if young.empty:
        st.caption("Brak młodych apek w top — rynek wygląda na zabetonowany "
                   "(to ważny sygnał ostrzegawczy).")
    else:
        yshow = young.copy()
        yshow["Instalacje (life.)"] = yshow["ratings"].apply(installs_label)
        app_link_table(
            yshow[["name", "developer", "age_months", "rank", "rating",
                   "ratings", "Instalacje (life.)", "url"]],
            {"name": "Aplikacja", "developer": "Wydawca",
             "age_months": "Wiek (mies.)", "rank": "Pozycja",
             "rating": "Ocena", "ratings": "Liczba ocen"})
    ui.how_button(["young_winners"], key="dd_how_young")

    rn = recent_release_notes_df(genre_id)
    if not rn.empty:
        with st.expander("🆕 Co konkurencja właśnie wydała (release notes)"):
            for _, r in rn.iterrows():
                st.markdown(f"**{r['name']}** — {r['updated']:%Y-%m-%d}")
                st.caption(r["release_notes"] or "—")

    # ---- LLM-free review mining over the FULL corpus ------------------------
    st.divider()
    st.markdown("#### 🔬 Analiza recenzji — pełny korpus (bez AI)")
    st.caption("Systematyczna wersja zasady „przeczytaj 100+ recenzji każdego "
               "konkurenta\": wzorce policzone na WSZYSTKICH zebranych "
               "recenzjach tej niszy, nie na próbce.")
    mining = load_pain_mining(genre_id)
    if mining.reviews_total == 0:
        st.info("Brak recenzji w bazie dla tej kategorii — uruchom "
                "`python run.py scan`.")
    else:
        p1, p2, p3 = st.columns(3)
        p1.metric("Recenzje przeanalizowane", num(mining.reviews_total))
        p2.metric("Negatywne (≤3★)", num(mining.reviews_negative))
        p3.metric("Odsetek negatywnych",
                  pct(mining.reviews_negative / max(mining.reviews_total, 1)),
                  help="⬆️ wyżej = więcej niezadowolonych użytkowników do "
                       "przejęcia lepszym produktem.")
        ui.how_button(["pain_mining"], key="dd_how_mining")

        if mining.themes:
            tcol, qcol = st.columns([2, 3])
            with tcol:
                st.markdown("**Powtarzające się problemy (tematy bólu)**")
                tdf = pd.DataFrame(
                    [{"theme": t.theme, "share": t.share, "hits": t.hits}
                     for t in mining.themes[:8]]
                ).sort_values("share")
                figp = go.Figure(go.Bar(
                    x=tdf["share"], y=tdf["theme"], orientation="h",
                    marker_color=CHART_PAIN,
                    text=[f"{s * 100:.0f}%" for s in tdf["share"]],
                    textposition="outside"))
                figp.update_layout(
                    xaxis_title="% negatywnych recenzji",
                    xaxis_tickformat=".0%")
                st.plotly_chart(style_fig(figp, 320), use_container_width=True)
            with qcol:
                st.markdown("**Głos użytkowników (cytaty)**")
                for t in mining.themes[:4]:
                    if not t.example:
                        continue
                    with st.container(border=True):
                        st.markdown(f":orange-background[**{t.theme}**] "
                                    f"· {t.hits} recenzji ({t.share * 100:.0f}%)")
                        st.caption(f"„{t.example}\" — o *{t.example_app}*")

        if mining.bigrams:
            st.caption("**Najczęstsze frazy w negatywnych recenzjach:** " +
                       " · ".join(f"`{b}` ({c})" for b, c in mining.bigrams[:12]))

        if mining.app_negative_share:
            with st.expander("😡 Apki z największym odsetkiem złych recenzji "
                             "(najłatwiejsze cele)"):
                adf = pd.DataFrame(mining.app_negative_share,
                                   columns=["name", "neg_share", "reviews"])
                adf["neg_share"] = adf["neg_share"].apply(pct)
                st.dataframe(adf.rename(columns={
                    "name": "Aplikacja", "neg_share": "% negatywnych",
                    "reviews": "Recenzji w bazie"}),
                    width="stretch", hide_index=True)

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
    comp_df = competitors_for_category(genre_id, country=cc)
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

    # ---- Niche validation: the 5-question test, auto-filled from data --------
    st.divider()
    with st.container(border=True):
        st.markdown("#### 🧪 Weryfikacja niszy — test 5 pytań")
        st.caption("Zanim wejdziesz w niszę, wszystkie odpowiedzi powinny brzmieć "
                   "„tak\". Pytania 1–4 wypełniamy automatycznie z danych; na "
                   "piąte możesz odpowiedzieć tylko Ty.")

        top_theme = mining.themes[0] if mining.themes else None
        q1_ok = top_theme is not None and top_theme.share >= 0.20
        q1_note = (f"najczęstszy ból „{top_theme.theme}\" dotyczy "
                   f"{top_theme.share * 100:.0f}% negatywnych recenzji"
                   if top_theme else "brak danych z recenzji")

        qg = row["quality_gap"] or 0
        n_dec = len(dec) if not dec.empty else 0
        q2_ok = qg >= 0.3 or stale > 0 or n_dec > 0
        q2_bits = []
        if qg >= 0.3:
            q2_bits.append(f"luka jakościowa {qg:.2f}")
        if stale > 0:
            q2_bits.append(f"{stale} porzuconych fortów")
        if n_dec > 0:
            q2_bits.append(f"{n_dec} psujących się apek")
        q2_note = ", ".join(q2_bits) or "konkurencja jest dobra i aktywna"

        paid_local = (float((comp_df["price"] > 0).mean())
                      if not comp_df.empty else 0.0)
        if pd.notna(paid):
            paid_local = float(paid)
        pricing_theme = next(
            (t for t in mining.themes if t.theme == "Ceny i subskrypcje"), None)
        q3_ok = (
            (pd.notna(mon) and float(mon) >= 0.2)
            or paid_local >= 0.10
            or (pricing_theme is not None and pricing_theme.share >= 0.10)
        )
        q3_bits = []
        if pd.notna(mon):
            q3_bits.append(f"{float(mon) * 100:.0f}% top-free apek zarabia "
                           "(jest też w top-grossing)")
        if paid_local > 0:
            q3_bits.append(f"{paid_local * 100:.0f}% apek płatnych")
        if pricing_theme:
            q3_bits.append("użytkownicy realnie płacą (skarżą się na subskrypcje "
                           f"w {pricing_theme.share * 100:.0f}% negatywnych recenzji)")
        q3_note = ", ".join(q3_bits) or "brak sygnałów płacenia w tej niszy"

        growth_val = None
        gdf_all = category_growth_df(weeks=4, country=report_country())
        if not gdf_all.empty:
            hit = gdf_all[gdf_all["genre_id"] == genre_id]
            if not hit.empty and pd.notna(hit["growth_pct"].iloc[0]):
                growth_val = float(hit["growth_pct"].iloc[0])
        mom = row.get("momentum") or 0
        q4_ok = (growth_val is not None and growth_val > 0) or mom > 0.5
        q4_note = (f"wzrost 4-tyg. {growth_val * 100:+.0f}%"
                   if growth_val is not None
                   else "za mało historii — obserwuj momentum")

        def _check(ok: bool, label: str, note: str) -> None:
            icon = "✅" if ok else "⚠️"
            st.markdown(f"{icon} **{label}** — {note}.")

        _check(q1_ok, "1. Czy problem jest wystarczająco dotkliwy?", q1_note)
        _check(q2_ok, "2. Czy możesz być znacząco lepszy w kluczowym aspekcie?",
               q2_note)
        _check(q3_ok, "3. Czy nisza się monetyzuje?", q3_note)
        _check(q4_ok, "4. Czy nisza ma potencjał wzrostu?", q4_note)
        q5 = st.checkbox(
            "5. Mam unikalną przewagę w tej niszy (doświadczenie, wiedza "
            "branżowa, dostęp do grupy odbiorców)",
            key=f"q5_{genre_id}",
        )
        score5 = sum([q1_ok, q2_ok, q3_ok, q4_ok, q5])
        if score5 >= 4:
            st.success(f"**{score5}/5** — nisza przechodzi test. Czas na MVP "
                       "w wąskiej pod-niszy.")
        elif score5 >= 3:
            st.info(f"**{score5}/5** — obiecujące, ale domknij brakujące punkty "
                    "zanim zainwestujesz.")
        else:
            st.warning(f"**{score5}/5** — za słabo. Szukaj węższej pod-niszy "
                       "albo innej kategorii.")
        ui.how_button(["niche_checklist"], key="dd_how_checklist")

    # ---- One-click niche report: the shareable deliverable -------------------
    st.divider()
    rc1, rc2 = st.columns([1, 3], vertical_alignment="center")
    with rc1:
        if st.button("📄 Generuj raport niszy", key=f"gen_report_{genre_id}"):
            from src.pipeline.niche_report import build_niche_report
            with st.spinner("Składam raport…"):
                st.session_state[f"report_{genre_id}"] = build_niche_report(genre_id)
    with rc2:
        report_md = st.session_state.get(f"report_{genre_id}")
        if report_md:
            st.download_button(
                "⬇️ Pobierz raport (.md)", data=report_md,
                file_name=f"raport-niszy-{choice.lower().replace(' ', '-')}.md",
                mime="text/markdown", key=f"dl_report_{genre_id}",
            )
        else:
            st.caption("Raport łączy wszystko z tej strony w jeden plik Markdown "
                       "— do udostępnienia, archiwum lub porównań między niszami.")

    with st.expander("Wszyscy konkurenci w tej niszy (z linkami do App Store)"):
        if comp_df.empty:
            st.caption("Brak danych o aplikacjach.")
        else:
            show = comp_df.copy()
            show["Instalacje (life.)"] = show["ratings"].apply(installs_label)
            show["monthly_installs"] = show["monthly_installs"].fillna("n/d")
            show = show[["name", "developer", "rating", "ratings", "Instalacje (life.)",
                         "monthly_installs", "days_since_update", "url"]]
            app_link_table(show, {
                "name": "Aplikacja", "developer": "Wydawca", "rating": "Ocena",
                "ratings": "Liczba ocen", "days_since_update": "Dni od aktualizacji",
                "monthly_installs": "Instalacje/mies. (teraz)"})
            st.caption("„Instalacje/mies. (teraz)\" = tempo przyrostu ocen między "
                       "skanami ÷ współczynnik ocen (1–3%) — popyt DZIŚ, nie "
                       "suma historyczna.")


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

    if settings.monetization_enabled:
        rem = keyword_scans_remaining(current_user_id())
        if rem is not None:
            st.caption(
                f"Plan Free: **{rem}** skanów mikro-nisz pozostało dziś "
                f"(limit {settings.free_daily_keyword_scans}/dzień). "
                "Generator AI wymaga **Pro**."
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
        cA, cB, cC = st.columns(3)
        gen = cA.checkbox("Wygeneruj kandydatów przez AI", value=False,
                          help="Wymaga planu Pro + GEMINI_API_KEYS.")
        expand = cB.checkbox("Rozszerz przez autocomplete Apple", value=False,
                             help="Crawluje podpowiedzi App Store (fraza + a–z): "
                                  "long-tail frazy, które ludzie FAKTYCZNIE "
                                  "wpisują — w przeciwieństwie do zgadywania AI.")
        n_kw = cC.slider("Ile wygenerować", 5, 25, 12)
        submitted = st.form_submit_button("Analizuj mikro-nisze", type="primary",
                                          width="stretch")

    if submitted:
        uid = current_user_id()
        genre_id = genre_options[genre_name]
        terms = [t.strip() for t in terms_raw.replace("\n", ",").split(",") if t.strip()]
        ok_scan, scan_msg = can_run_keyword_scan(uid, use_ai=gen)
        if not ok_scan:
            st.error(scan_msg)
        elif gen and not settings.llm_enabled:
            st.warning("Generator AI wymaga GEMINI_API_KEYS. Podaj słowa ręcznie "
                       "albo skonfiguruj klucz.")
        elif not terms and not gen:
            st.warning("Podaj przynajmniej jedno słowo kluczowe albo włącz generator AI.")
        else:
            if expand and terms:
                from src.analysis.microniche import expand_keywords_autocomplete
                with st.spinner("Crawluję autocomplete App Store (frazy, które "
                                "ludzie naprawdę wpisują)…"):
                    harvested: list = []
                    for seed in terms[:3]:
                        harvested += expand_keywords_autocomplete(seed, max_terms=15)
                    new_terms = [t for t in harvested if t not in terms]
                    if new_terms:
                        st.success(f"Autocomplete dodał {len(new_terms)} realnych "
                                   f"fraz: {', '.join(new_terms[:8])}…")
                        terms = list(dict.fromkeys(terms + new_terms))
            with st.spinner("Szukam i oceniam mikro-nisze (Search API + AI)…"):
                from src.pipeline.keyword_scan import run_keyword_scan
                try:
                    run_keyword_scan(terms=terms, theme=theme, genre_id=genre_id,
                                     generate=gen, n=n_kw)
                    if uid:
                        record_keyword_scan(uid)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Analiza nie powiodła się: {exc}")

    kdf = load_keyword_scores()
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
    kdisp_show, hidden_kw = limit_radar_niches(kdisp)
    event = st.dataframe(
        kdisp_show[view_cols].rename(columns={
            "term": "Mikro-nisza", "opportunity_score": "Opportunity",
            "avg_rating_top": "Śr. ocena", "strong_incumbents": "Twierdze",
            "mega_incumbents": "Giganci", "est_installs_month": "Instalacje/mies. (budżet)"}),
        width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row", key="kw_table",
        column_config={"Opportunity": st.column_config.ProgressColumn(
            "Opportunity", min_value=0, max_value=100, format="%.0f")},
    )
    render_radar_pro_upsell(hidden=hidden_kw, kind="mikro-nisz w rankingu")
    st.caption("💡 Sweet spot ASO: **wysoki Popyt wysz. + niska Trudność** "
               "(dużo szukają, słabi konkurenci do wyprzedzenia).")
    ce1, ce2 = st.columns([1, 4])
    if render_csv_gate():
        ce1.download_button(
            "⬇️ Eksport CSV", data=kdisp[view_cols].to_csv(index=False).encode("utf-8"),
            file_name="mikro-nisze.csv", mime="text/csv", key="kw_csv",
        )
    with ce2:
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

    cc = report_country()
    kw_key = keyword_niche_key(picked, cc)
    if not render_unlock_gate(
        niche_key=kw_key,
        niche_label=picked,
        content="mikro-nisza",
        teaser="" if is_content_unlocked(kw_key) else keyword_pain_teaser(krow),
    ):
        return

    # Geo arbitrage: the same niche can be besieged in the US and open in DE/PL.
    st.markdown("##### 🌍 Geo-radar — ta sama nisza w innych krajach")
    if st.button(
        f"Porównaj US vs PL (priorytet: {dashboard_storefront().upper()})",
        key=f"geo_{picked}",
    ):
        from src.analysis.microniche import GEO_COUNTRIES, geo_scan

        sf = dashboard_storefront()
        countries = tuple(dict.fromkeys((sf,) + GEO_COUNTRIES))
        with st.spinner("Odpytuję storefronty…"):
            st.session_state[f"geo_res_{picked}"] = geo_scan(picked, countries=countries)
    geo_res = st.session_state.get(f"geo_res_{picked}")
    if geo_res:
        gdf_geo = pd.DataFrame(geo_res)
        gdf_geo["difficulty"] = gdf_geo["difficulty"].apply(lambda x: f"{x:.2f}")
        st.dataframe(gdf_geo.rename(columns={
            "country": "Kraj", "num_results": "Wyników",
            "avg_rating": "Śr. ocena", "median_ratings": "Mediana ocen",
            "fortresses": "Twierdze", "megas": "Giganci",
            "difficulty": "Trudność ASO", "top_app": "Lider"}),
            width="stretch", hide_index=True)
        easiest = geo_res[0]
        st.success(f"🎯 Najłatwiejszy rynek dla tej frazy: **{easiest['country']}** "
                   f"(trudność {easiest['difficulty']:.2f}, "
                   f"{easiest['fortresses']} twierdz). Ta sama apka, "
                   f"zlokalizowana, może wejść tam najtaniej.")
        ui.how_button(["geo_scan"], key=f"kw_how_geo_{picked}")

    # Upstream demand: people asking for this app on Reddit BEFORE it exists.
    st.markdown("##### 🗣️ Popyt na Reddicie — „szukam apki do…\"")
    from src.scraper.reddit_demand import is_configured as reddit_configured
    if not reddit_configured():
        st.caption("Ludzie proszą o apki na Reddicie, zanim nisza pojawi się "
                   "w danych App Store. Włącz ten sygnał **za darmo**: utwórz "
                   "aplikację typu *script* na reddit.com/prefs/apps i ustaw "
                   "`REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` w `.env`.")
    else:
        if st.button("Szukaj postów „is there an app for…\"",
                     key=f"reddit_{picked}"):
            from src.scraper.reddit_demand import demand_scan
            with st.spinner("Przeszukuję Reddita (4 zapytania)…"):
                st.session_state[f"reddit_res_{picked}"] = demand_scan(picked)
        rres = st.session_state.get(f"reddit_res_{picked}")
        if rres is not None:
            if rres.error:
                st.warning("Reddit nie odpowiedział (limit/blokada) — spróbuj "
                           "za chwilę.")
            elif rres.total_matches == 0:
                st.info("Zero postów z prośbą o taką apkę — słaby popyt "
                        "oddolny albo zbyt wąska fraza.")
            else:
                r1, r2, r3 = st.columns(3)
                r1.metric("Postów „szukam apki\"", rres.total_matches)
                r2.metric("W ostatnich 12 mies.", rres.recent_12mo,
                          help="⬆️ dużo świeżych próśb = popyt rośnie TERAZ.")
                r3.metric("Top subreddit",
                          f"r/{rres.top_subreddits[0][0]}"
                          if rres.top_subreddits else "—")
                rdf = pd.DataFrame([
                    {"Post": p.title, "Subreddit": f"r/{p.subreddit}",
                     "Głosy": p.score, "Komentarze": p.num_comments,
                     "Data": p.created.date().isoformat(), "url": p.url}
                    for p in rres.posts[:15]
                ])
                app_link_table(rdf, {}, url_col="url")
                ui.how_button(["reddit_demand"], key=f"kw_how_reddit_{picked}")

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

        # Full-corpus pain mining for the keyword's competitors - works when
        # any of them are already tracked (reviews in DB).
        kw_app_ids = tuple(
            int(a["app_id"]) for a in apps if a.get("app_id")
        )
        if kw_app_ids:
            kw_mining = load_pain_mining_apps(kw_app_ids)
            if kw_mining.reviews_negative > 0 and kw_mining.themes:
                st.markdown("#### 🔬 Problemy użytkowników konkurencji (z recenzji)")
                st.caption(f"Przeanalizowano {num(kw_mining.reviews_total)} recenzji "
                           "konkurentów tej frazy zebranych w bazie.")
                for t in kw_mining.themes[:5]:
                    line = (f"- **{t.theme}** — {t.hits} recenzji "
                            f"({t.share * 100:.0f}% negatywnych)")
                    if t.example:
                        line += f' · np. „{t.example[:140]}"'
                    st.markdown(line)
                ui.how_button(["pain_mining"], key="kw_how_mining")


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
init_auth()
_on_landing = monetization_active() and not is_logged_in()

render_payment_banner()

if _on_landing:
    inject_global_styles(landing=True)
    # A recovery link must be finishable before anything else, otherwise the user
    # is stuck on the landing page with a valid token and nowhere to use it.
    if not render_password_recovery():
        render_landing_page()
    st.stop()

render_sidebar()

_nav_pages = [
    st.Page(page_radar, title="Radar", icon=":material/radar:", default=True),
    st.Page(page_deep, title="Analiza", icon=":material/biotech:"),
    st.Page(page_micro, title="Mikro-nisze", icon=":material/target:"),
    st.Page(page_digest, title="Zmiany", icon=":material/trending_up:"),
]
if settings.monetization_enabled:
    _nav_pages.append(
        st.Page(page_account, title="Konto", icon=":material/account_circle:")
    )

nav = st.navigation(_nav_pages, position="top")
nav.run()

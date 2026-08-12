"""Global visual theme — Midnight Intel palette for Market Intel SaaS.

Color strategy (research / analytics product for app founders):
  • Indigo/violet — brand, trust, „inteligencja danych” (Amplitude, Linear)
  • Emerald — okazje, pozytywne sygnały, STRONG verdict
  • Sky blue — eksploracja, wykresy trendów, geo-radar
  • Amber — ostrożność, WATCH, średnie sygnały
  • Rose — ból użytkowników, giganci, SKIP, pain mining
  • Slate-blue backgrounds — głębia bez czystej czerni
"""
from __future__ import annotations

import streamlit as st

# ---- Surfaces (slate-blue dark, not pure black) ----
BG = "#0F1219"
BG_SURFACE = "#161B26"
BG_CARD = "#1C2233"
BG_ELEVATED = "#232A3D"
BORDER = "#2E3650"
BORDER_SUBTLE = "#252B3D"

# ---- Text ----
TEXT = "#F0F2F7"
TEXT_SECONDARY = "#A8B0C4"
TEXT_MUTED = "#6B7590"

# ---- Brand ----
BRAND = "#818CF8"          # indigo-400 — primary actions, links, nav
BRAND_DIM = "#6366F1"      # indigo-500 — hover
BRAND_GLOW = "rgba(129, 140, 248, 0.15)"
PRIMARY = BRAND
PRIMARY_FG = "#FFFFFF"
LINK = "#A5B4FC"

# ---- Semantic (data + verdicts) ----
OPPORTUNITY = "#34D399"    # emerald-400 — good niches, success
INSIGHT = "#38BDF8"        # sky-400 — trends, secondary charts
CAUTION = "#FBBF24"        # amber-400 — watch / moderate
PAIN = "#FB7185"           # rose-400 — pain mining, giants, skip
SUCCESS = OPPORTUNITY
WARNING = CAUTION
DANGER = PAIN

# ---- Charts ----
CHART_PRIMARY = BRAND
CHART_SECONDARY = INSIGHT
CHART_OPPORTUNITY_SCALE = [
    [0, "#312E81"],
    [0.35, "#6366F1"],
    [0.7, "#818CF8"],
    [1, "#34D399"],
]
CHART_BARS_GOOD = OPPORTUNITY
CHART_BARS_BAD = PAIN
CHART_TREND = INSIGHT
CHART_PAIN = PAIN

# Legacy aliases
ACCENT = BRAND
ACCENT_SOFT = INSIGHT
ACCENT_MUTED = "#4F46E5"
PRIMARY_DIM = BRAND_DIM


def inject_global_styles(*, landing: bool = False) -> None:
    """Inject CSS aligned with .streamlit/config.toml theme tokens."""
    landing_extra = ""
    if landing:
        landing_extra = f"""
      .block-container {{ padding-top: 1rem; max-width: 980px; }}
      section[data-testid="stSidebar"],
      [data-testid="stSidebarCollapsedControl"],
      [data-testid="collapsedControl"] {{
        display: none !important;
      }}
      section[data-testid="stMain"] > div {{
        max-width: 100%;
      }}
        """

    st.markdown(
        f"""
    <style>
      :root {{
        --mi-bg: {BG};
        --mi-surface: {BG_SURFACE};
        --mi-card: {BG_CARD};
        --mi-text: {TEXT};
        --mi-text-secondary: {TEXT_SECONDARY};
        --mi-text-muted: {TEXT_MUTED};
        --mi-border: {BORDER};
        --mi-brand: {BRAND};
        --mi-opportunity: {OPPORTUNITY};
        --mi-insight: {INSIGHT};
        --mi-caution: {CAUTION};
        --mi-pain: {PAIN};
      }}

      .stApp {{
        background: linear-gradient(165deg, {BG} 0%, #121827 45%, {BG} 100%);
      }}

      .block-container {{ max-width: 1200px; padding-top: 2rem; }}
      {landing_extra}

      header[data-testid="stHeader"] {{
        background: rgba(15, 18, 25, 0.88);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid {BORDER_SUBTLE};
      }}

      div[data-testid="stMetric"] {{
        background: linear-gradient(145deg, {BG_CARD} 0%, {BG_SURFACE} 100%);
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 14px 16px 12px;
      }}
      div[data-testid="stMetricLabel"] p {{
        font-size: .8rem;
        color: {TEXT_MUTED};
      }}
      div[data-testid="stMetricValue"] {{
        font-size: 1.5rem;
        color: {TEXT};
        font-weight: 600;
      }}

      div[data-testid="stNavSectionHeader"] {{ display: none; }}
      a[data-testid="stPageLink"] {{
        border-radius: 8px !important;
        font-size: 0.875rem !important;
      }}
      a[data-testid="stPageLink"][aria-current="page"] {{
        background: {BRAND_GLOW} !important;
        border-color: rgba(129, 140, 248, 0.4) !important;
        color: {BRAND} !important;
      }}

      div[data-testid="stDataFrame"] {{ border-radius: 10px; }}
      div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-color: {BORDER} !important;
        border-radius: 12px;
        background: {BG_SURFACE};
      }}

      h1, h2, h3, h4 {{
        letter-spacing: -0.025em;
        color: {TEXT};
        font-weight: 600;
      }}

      div[data-testid="stButton"] button[kind="primary"],
      div[data-testid="stButton"] button[data-testid="baseButton-primary"] {{
        background: {BRAND_DIM} !important;
        border: 1px solid rgba(129, 140, 248, 0.5) !important;
        color: {PRIMARY_FG} !important;
        font-weight: 500 !important;
        border-radius: 8px !important;
        box-shadow: none !important;
      }}
      div[data-testid="stButton"] button[kind="primary"]:hover {{
        background: {BRAND} !important;
      }}
      div[data-testid="stButton"] button[kind="secondary"] {{
        border-radius: 8px !important;
        border-color: {BORDER} !important;
        background: {BG_CARD} !important;
        color: {TEXT_SECONDARY} !important;
      }}

      a[data-testid="stLinkButton"] {{
        border-color: rgba(129, 140, 248, 0.35) !important;
        border-radius: 8px !important;
        background: {BG_CARD} !important;
        color: {LINK} !important;
      }}

      /* ---- Landing ---- */
      .mi-hero {{
        text-align: center;
        padding: 3rem 1.5rem 2.75rem;
        margin-bottom: 2rem;
        border-radius: 16px;
        background:
          radial-gradient(ellipse 70% 55% at 50% -5%, {BRAND_GLOW}, transparent 55%),
          radial-gradient(ellipse 45% 35% at 85% 90%, rgba(52, 211, 153, 0.07), transparent),
          {BG_CARD};
        border: 1px solid {BORDER};
      }}
      .mi-hero-badge {{
        display: inline-block;
        background: {BRAND_GLOW};
        border: 1px solid rgba(129, 140, 248, 0.35);
        color: {BRAND};
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 0.3rem 0.75rem;
        border-radius: 999px;
        margin-bottom: 1.25rem;
      }}
      .mi-hero h1 {{
        font-size: clamp(1.75rem, 3.5vw, 2.4rem);
        line-height: 1.2;
        margin: 0 0 1rem;
        font-weight: 600;
        letter-spacing: -0.03em;
      }}
      .mi-hero h1 em {{
        font-style: normal;
        color: {BRAND};
      }}
      .mi-hero-sub {{
        color: {TEXT_SECONDARY};
        font-size: 1rem;
        line-height: 1.65;
        max-width: 540px;
        margin: 0 auto;
      }}
      .mi-trust {{
        color: {TEXT_MUTED};
        font-size: 0.78rem;
        margin-top: 1.25rem;
      }}
      .mi-section {{ margin: 2.5rem 0 0.75rem; }}
      .mi-section-title {{
        font-size: 1.125rem;
        font-weight: 600;
        letter-spacing: -0.02em;
      }}
      .mi-section-sub {{
        color: {TEXT_MUTED};
        font-size: 0.875rem;
        margin-bottom: 1rem;
      }}

      .mi-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 1.25rem;
        height: 100%;
      }}
      .mi-card-accent-brand {{ border-top: 3px solid {BRAND}; }}
      .mi-card-accent-pain {{ border-top: 3px solid {PAIN}; }}
      .mi-card-accent-opp {{ border-top: 3px solid {OPPORTUNITY}; }}
      .mi-card-accent-sky {{ border-top: 3px solid {INSIGHT}; }}
      .mi-card-accent-caution {{ border-top: 3px solid {CAUTION}; }}

      .mi-card h4 {{
        margin: 0 0 0.45rem;
        font-size: 0.9375rem;
        font-weight: 600;
        color: {TEXT};
      }}
      .mi-card p {{ color: {TEXT_SECONDARY}; font-size: 0.8125rem; line-height: 1.55; margin: 0; }}

      .mi-tag {{
        display: inline-block;
        font-size: 0.6875rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        padding: 0.15rem 0.5rem;
        border-radius: 5px;
        margin-bottom: 0.55rem;
      }}
      .mi-tag-brand {{ background: {BRAND_GLOW}; color: {BRAND}; }}
      .mi-tag-opp {{ background: rgba(52, 211, 153, 0.12); color: {OPPORTUNITY}; }}
      .mi-tag-sky {{ background: rgba(56, 189, 248, 0.12); color: {INSIGHT}; }}

      .mi-step-num {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.75rem;
        height: 1.75rem;
        background: {BRAND_GLOW};
        color: {BRAND};
        border-radius: 8px;
        font-size: 0.7rem;
        font-weight: 700;
        margin-bottom: 0.55rem;
      }}

      .mi-price-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.8125rem;
        border: 1px solid {BORDER};
        border-radius: 12px;
        overflow: hidden;
      }}
      .mi-price-table th, .mi-price-table td {{
        padding: 0.7rem 1rem;
        border-bottom: 1px solid {BORDER};
        text-align: left;
      }}
      .mi-price-table th {{
        background: {BG_SURFACE};
        color: {TEXT_MUTED};
        font-size: 0.6875rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .mi-price-table tr:last-child td {{ border-bottom: none; }}
      .mi-price-highlight {{ color: {OPPORTUNITY}; font-weight: 600; }}

      .mi-cta-box {{
        background: linear-gradient(135deg, {BRAND_GLOW} 0%, rgba(52, 211, 153, 0.08) 100%);
        border: 1px solid rgba(129, 140, 248, 0.3);
        border-radius: 14px;
        padding: 2rem 1.5rem;
        text-align: center;
        margin: 2.5rem 0 1rem;
      }}
      .mi-cta-box h3 {{ margin: 0 0 0.35rem; font-size: 1.125rem; }}
      .mi-cta-box p {{ color: {TEXT_SECONDARY}; margin: 0; font-size: 0.875rem; }}

      .mi-callout {{
        background: {BG_SURFACE};
        border: 1px solid {BORDER};
        border-left: 4px solid {OPPORTUNITY};
        border-radius: 12px;
        padding: 1.25rem;
        margin-top: 1.5rem;
      }}
      .mi-stat-bad {{ color: {PAIN}; font-weight: 600; }}
      .mi-stat-good {{ color: {OPPORTUNITY}; font-weight: 600; }}
      .mi-tier-note {{ margin-top: 0.6rem; font-size: 0.75rem; color: {TEXT_MUTED}; }}
    </style>
    """,
        unsafe_allow_html=True,
    )

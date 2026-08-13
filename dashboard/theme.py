"""Global visual theme — Daylight Intel palette for Market Intel SaaS.

Light analytics theme: paper-white surfaces, indigo brand, data hues stepped dark
enough to hold their own on white.

Every value here is computed, not eyeballed (see the dataviz validator):
  • Mark colors clear 3:1 against the white card surface.
  • Text colors clear 4.5:1 against BOTH the page and the inset surface, which is
    why each data hue has a darker `*_TEXT` step — emerald-600 is a fine bar fill
    but too light for 13px bold type.
  • CHART_OPPORTUNITY_SCALE is a single-hue emerald ramp, light→dark (low→high):
    monotone lightness, ΔL ≥ 0.06 per step, light end ≥ 2:1 on white.
  • Known and accepted: amber (CAUTION) and rose (PAIN) collide under deuteranopia
    (ΔE 4.7). They are *status* colors here and never appear as color alone — every
    verdict carries its STRONG/WATCH/SKIP label, so identity survives.

Color roles:
  • Indigo — brand, actions, links, nav
  • Emerald — okazje, pozytywne sygnały, STRONG verdict
  • Sky — eksploracja, wykresy trendów, geo-radar
  • Amber — ostrożność, WATCH
  • Rose — ból użytkowników, giganci, SKIP, pain mining
"""
from __future__ import annotations

import streamlit as st

# ---- Surfaces (paper white on a faintly cool page) ----
BG = "#F7F8FA"             # page
BG_SURFACE = "#F1F3F7"     # insets: table headers, wells
BG_CARD = "#FFFFFF"        # cards, metrics, bordered containers
BG_ELEVATED = "#FFFFFF"
BORDER = "#DDE1E9"
BORDER_SUBTLE = "#E9ECF2"
SHADOW_SM = "0 1px 2px rgba(20, 22, 28, 0.05)"
SHADOW_MD = "0 1px 3px rgba(20, 22, 28, 0.07), 0 4px 12px rgba(20, 22, 28, 0.04)"

# ---- Text (contrast on page / inset: 17.0 / 16.3 · 7.1 / 6.8 · 5.0 / 4.8) ----
TEXT = "#14161C"
TEXT_SECONDARY = "#4B5468"
TEXT_MUTED = "#5F6B84"

# ---- Brand ----
BRAND = "#4F46E5"          # indigo-600 — 5.9:1 on page, white type on it 6.3:1
BRAND_DIM = "#4338CA"      # indigo-700 — hover goes *darker* in a light theme
BRAND_GLOW = "rgba(79, 70, 229, 0.10)"
PRIMARY = BRAND
PRIMARY_FG = "#FFFFFF"
LINK = "#4338CA"

# ---- Semantic marks (fills, borders, chart series) ----
OPPORTUNITY = "#059669"    # emerald-600 — good niches, success
INSIGHT = "#0284C7"        # sky-600 — trends, secondary charts
CAUTION = "#D97706"        # amber-600 — watch / moderate
PAIN = "#E11D48"           # rose-600 — pain mining, giants, skip
SUCCESS = OPPORTUNITY
WARNING = CAUTION
DANGER = PAIN

# ---- Semantic text (same hues, one step darker so small type stays legible) ----
OPPORTUNITY_TEXT = "#047857"   # emerald-700
INSIGHT_TEXT = "#0369A1"       # sky-700
CAUTION_TEXT = "#B45309"       # amber-700
PAIN_TEXT = "#BE123C"          # rose-700

# ---- Charts ----
CHART_PRIMARY = BRAND
CHART_SECONDARY = INSIGHT
CHART_OPPORTUNITY_SCALE = [
    [0, "#10B981"],
    [0.33, "#059669"],
    [0.66, "#047857"],
    [1, "#064E3B"],
]
CHART_BARS_GOOD = OPPORTUNITY
CHART_BARS_BAD = PAIN
CHART_TREND = INSIGHT
CHART_PAIN = PAIN
# Plot furniture: recessive on white, unlike the white-on-dark values it replaces.
CHART_PLOT_BG = "rgba(79, 70, 229, 0.03)"
CHART_GRID = "rgba(20, 22, 28, 0.07)"
CHART_ZEROLINE = "rgba(20, 22, 28, 0.16)"

# Legacy aliases
ACCENT = BRAND
ACCENT_SOFT = INSIGHT
ACCENT_MUTED = "#6366F1"
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
        background:
          radial-gradient(ellipse 80% 50% at 50% -10%, {BRAND_GLOW}, transparent 60%),
          {BG};
      }}

      .block-container {{ max-width: 1200px; padding-top: 2rem; }}
      {landing_extra}

      header[data-testid="stHeader"] {{
        background: rgba(247, 248, 250, 0.85);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid {BORDER_SUBTLE};
      }}

      div[data-testid="stMetric"] {{
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 14px 16px 12px;
        box-shadow: {SHADOW_SM};
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
        border-color: rgba(79, 70, 229, 0.28) !important;
        color: {BRAND_DIM} !important;
      }}

      div[data-testid="stDataFrame"] {{
        border-radius: 10px;
        border: 1px solid {BORDER};
      }}
      div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-color: {BORDER} !important;
        border-radius: 12px;
        background: {BG_CARD};
        box-shadow: {SHADOW_SM};
      }}

      h1, h2, h3, h4 {{
        letter-spacing: -0.025em;
        color: {TEXT};
        font-weight: 600;
      }}

      div[data-testid="stButton"] button[kind="primary"],
      div[data-testid="stButton"] button[data-testid="baseButton-primary"] {{
        background: {BRAND} !important;
        border: 1px solid {BRAND} !important;
        color: {PRIMARY_FG} !important;
        font-weight: 500 !important;
        border-radius: 8px !important;
        box-shadow: {SHADOW_SM} !important;
      }}
      div[data-testid="stButton"] button[kind="primary"]:hover {{
        background: {BRAND_DIM} !important;
        border-color: {BRAND_DIM} !important;
      }}
      div[data-testid="stButton"] button[kind="secondary"] {{
        border-radius: 8px !important;
        border-color: {BORDER} !important;
        background: {BG_CARD} !important;
        color: {TEXT_SECONDARY} !important;
        box-shadow: {SHADOW_SM} !important;
      }}
      div[data-testid="stButton"] button[kind="secondary"]:hover {{
        border-color: {BRAND} !important;
        color: {BRAND_DIM} !important;
      }}

      a[data-testid="stLinkButton"] {{
        border-color: rgba(79, 70, 229, 0.3) !important;
        border-radius: 8px !important;
        background: {BG_CARD} !important;
        color: {LINK} !important;
        box-shadow: {SHADOW_SM} !important;
      }}
      a[data-testid="stLinkButton"][kind="primary"] {{
        background: {BRAND} !important;
        border-color: {BRAND} !important;
        color: {PRIMARY_FG} !important;
      }}

      /* ---- Landing ---- */
      .mi-hero {{
        text-align: center;
        padding: 3rem 1.5rem 2.75rem;
        margin-bottom: 2rem;
        border-radius: 16px;
        background:
          radial-gradient(ellipse 70% 55% at 50% -5%, {BRAND_GLOW}, transparent 55%),
          radial-gradient(ellipse 45% 35% at 85% 90%, rgba(5, 150, 105, 0.06), transparent),
          {BG_CARD};
        border: 1px solid {BORDER};
        box-shadow: {SHADOW_MD};
      }}
      .mi-hero-badge {{
        display: inline-block;
        background: {BRAND_GLOW};
        border: 1px solid rgba(79, 70, 229, 0.25);
        color: {BRAND_DIM};
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
        box-shadow: {SHADOW_SM};
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
      .mi-tag-brand {{ background: {BRAND_GLOW}; color: {BRAND_DIM}; }}
      .mi-tag-opp {{ background: rgba(5, 150, 105, 0.10); color: {OPPORTUNITY_TEXT}; }}
      .mi-tag-sky {{ background: rgba(2, 132, 199, 0.10); color: {INSIGHT_TEXT}; }}

      .mi-step-num {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.75rem;
        height: 1.75rem;
        background: {BRAND_GLOW};
        color: {BRAND_DIM};
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
        background: {BG_CARD};
        box-shadow: {SHADOW_SM};
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
      .mi-price-highlight {{ color: {OPPORTUNITY_TEXT}; font-weight: 600; }}

      /* Locked rows on the pre-login teaser: readable shape, unreadable content. */
      .mi-blur td {{
        filter: blur(4.5px);
        opacity: 0.45;
        user-select: none;
      }}

      .mi-cta-box {{
        background: linear-gradient(135deg, {BRAND_GLOW} 0%, rgba(5, 150, 105, 0.07) 100%);
        border: 1px solid rgba(79, 70, 229, 0.22);
        border-radius: 14px;
        padding: 2rem 1.5rem;
        text-align: center;
        margin: 2.5rem 0 1rem;
      }}
      .mi-cta-box h3 {{ margin: 0 0 0.35rem; font-size: 1.125rem; }}
      .mi-cta-box p {{ color: {TEXT_SECONDARY}; margin: 0; font-size: 0.875rem; }}

      .mi-callout {{
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-left: 4px solid {OPPORTUNITY};
        border-radius: 12px;
        padding: 1.25rem;
        margin-top: 1.5rem;
        box-shadow: {SHADOW_SM};
      }}
      .mi-stat-bad {{ color: {PAIN_TEXT}; font-weight: 600; }}
      .mi-stat-good {{ color: {OPPORTUNITY_TEXT}; font-weight: 600; }}
      .mi-tier-note {{ margin-top: 0.6rem; font-size: 0.75rem; color: {TEXT_MUTED}; }}
    </style>
    """,
        unsafe_allow_html=True,
    )

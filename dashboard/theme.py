"""Global visual theme — teal opportunity palette for Market Intel."""
from __future__ import annotations

import streamlit as st

# Core palette (AA contrast on dark backgrounds)
PRIMARY = "#2DD4BF"       # teal-400 — trust, growth, primary actions
PRIMARY_DIM = "#14B8A6"   # teal-500 — hover / emphasis
ACCENT = "#FBBF24"        # amber-400 — opportunity highlights
ACCENT_SOFT = "#F59E0B"   # amber-500
BG = "#0A1018"            # warm navy black
BG_CARD = "#141C2B"       # elevated surfaces
BG_CARD_HOVER = "#1A2438"
TEXT = "#F1F5F9"          # slate-100
TEXT_MUTED = "#94A3B8"    # slate-400
BORDER = "#243047"
SUCCESS = "#34D399"
WARNING = "#FBBF24"
DANGER = "#F87171"
LINK = "#5EEAD4"


def inject_global_styles(*, landing: bool = False) -> None:
    """Inject CSS aligned with .streamlit/config.toml theme tokens."""
    landing_extra = ""
    if landing:
        landing_extra = """
      .block-container { padding-top: 1rem; max-width: 1080px; }
      section[data-testid="stSidebar"] { background: linear-gradient(
        180deg, #0A1018 0%, #0F1623 100%
      ); }
        """

    st.markdown(
        f"""
    <style>
      :root {{
        --mi-primary: {PRIMARY};
        --mi-primary-dim: {PRIMARY_DIM};
        --mi-accent: {ACCENT};
        --mi-bg: {BG};
        --mi-bg-card: {BG_CARD};
        --mi-text: {TEXT};
        --mi-text-muted: {TEXT_MUTED};
        --mi-border: {BORDER};
        --mi-success: {SUCCESS};
        --mi-link: {LINK};
      }}

      .block-container {{ max-width: 1240px; padding-top: 2rem; }}
      {landing_extra}

      /* Softer app chrome */
      header[data-testid="stHeader"] {{
        background: rgba(10, 16, 24, 0.85);
        backdrop-filter: blur(8px);
      }}

      /* Metric cards */
      div[data-testid="stMetric"] {{
        background: var(--mi-bg-card);
        border: 1px solid var(--mi-border);
        border-radius: 14px;
        padding: 14px 16px 12px;
        box-shadow: 0 1px 0 rgba(45, 212, 191, 0.04);
      }}
      div[data-testid="stMetricLabel"] p {{ font-size: .82rem; color: var(--mi-text-muted); }}
      div[data-testid="stMetricValue"] {{ font-size: 1.55rem; color: var(--mi-text); }}

      /* Navigation pills */
      div[data-testid="stNavSectionHeader"] {{ display: none; }}
      a[data-testid="stPageLink"] {{
        border-radius: 10px !important;
      }}
      a[data-testid="stPageLink"][aria-current="page"] {{
        background: rgba(45, 212, 191, 0.12) !important;
        border-color: rgba(45, 212, 191, 0.35) !important;
      }}

      /* Dataframes & containers */
      div[data-testid="stDataFrame"] {{ border-radius: 12px; }}
      div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-color: var(--mi-border) !important;
        border-radius: 14px;
      }}

      h1, h2, h3, h4 {{ letter-spacing: -.02em; color: var(--mi-text); }}

      /* Primary buttons — teal glow */
      div[data-testid="stButton"] button[kind="primary"],
      div[data-testid="stButton"] button[data-testid="baseButton-primary"] {{
        background: linear-gradient(135deg, {PRIMARY_DIM} 0%, {PRIMARY} 100%);
        border: none;
        color: #042f2e;
        font-weight: 600;
        box-shadow: 0 0 20px rgba(45, 212, 191, 0.25);
      }}
      div[data-testid="stButton"] button[kind="primary"]:hover {{
        box-shadow: 0 0 28px rgba(45, 212, 191, 0.38);
      }}

      /* Link buttons */
      a[data-testid="stLinkButton"] {{
        border-color: var(--mi-border) !important;
        border-radius: 10px !important;
      }}

      /* Landing page components */
      .mi-hero {{
        text-align: center;
        padding: 2.5rem 1rem 2rem;
        margin-bottom: 0.5rem;
      }}
      .mi-hero-badge {{
        display: inline-block;
        background: rgba(45, 212, 191, 0.12);
        border: 1px solid rgba(45, 212, 191, 0.35);
        color: {PRIMARY};
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        margin-bottom: 1.25rem;
      }}
      .mi-hero h1 {{
        font-size: clamp(1.85rem, 4vw, 2.65rem);
        line-height: 1.15;
        margin: 0 0 1rem;
        font-weight: 700;
      }}
      .mi-hero h1 span {{ color: {ACCENT}; }}
      .mi-hero-sub {{
        color: {TEXT_MUTED};
        font-size: 1.08rem;
        line-height: 1.55;
        max-width: 640px;
        margin: 0 auto 1.5rem;
      }}
      .mi-trust {{
        color: {TEXT_MUTED};
        font-size: 0.82rem;
        margin-top: 1rem;
      }}
      .mi-section {{
        margin: 2.5rem 0 1rem;
      }}
      .mi-section-title {{
        font-size: 1.45rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
      }}
      .mi-section-sub {{
        color: {TEXT_MUTED};
        font-size: 0.95rem;
        margin-bottom: 1.25rem;
      }}
      .mi-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 16px;
        padding: 1.35rem 1.25rem;
        height: 100%;
        transition: border-color 0.2s;
      }}
      .mi-card:hover {{ border-color: rgba(45, 212, 191, 0.35); }}
      .mi-card-icon {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
      .mi-card h4 {{
        margin: 0 0 0.5rem;
        font-size: 1.05rem;
        color: {TEXT};
      }}
      .mi-card p, .mi-card li {{
        color: {TEXT_MUTED};
        font-size: 0.88rem;
        line-height: 1.5;
        margin: 0;
      }}
      .mi-card ul {{ padding-left: 1.1rem; margin: 0.5rem 0 0; }}
      .mi-card-free {{
        border-color: rgba(45, 212, 191, 0.25);
      }}
      .mi-card-paid {{
        border-color: rgba(251, 191, 36, 0.25);
      }}
      .mi-tag-free {{
        display: inline-block;
        background: rgba(45, 212, 191, 0.15);
        color: {PRIMARY};
        font-size: 0.72rem;
        font-weight: 600;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        margin-bottom: 0.5rem;
      }}
      .mi-tag-paid {{
        display: inline-block;
        background: rgba(251, 191, 36, 0.15);
        color: {ACCENT};
        font-size: 0.72rem;
        font-weight: 600;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        margin-bottom: 0.5rem;
      }}
      .mi-step-num {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 2rem;
        height: 2rem;
        background: rgba(45, 212, 191, 0.15);
        color: {PRIMARY};
        border-radius: 50%;
        font-weight: 700;
        font-size: 0.9rem;
        margin-bottom: 0.65rem;
      }}
      .mi-price-table {{
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        font-size: 0.88rem;
      }}
      .mi-price-table th, .mi-price-table td {{
        padding: 0.75rem 1rem;
        border-bottom: 1px solid {BORDER};
        text-align: left;
      }}
      .mi-price-table th {{
        color: {TEXT_MUTED};
        font-weight: 600;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }}
      .mi-price-table tr:last-child td {{ border-bottom: none; }}
      .mi-price-highlight {{ color: {ACCENT}; font-weight: 600; }}
      .mi-cta-box {{
        background: linear-gradient(135deg, rgba(45,212,191,0.08) 0%, rgba(251,191,36,0.06) 100%);
        border: 1px solid rgba(45, 212, 191, 0.3);
        border-radius: 18px;
        padding: 2rem 1.5rem;
        text-align: center;
        margin: 2rem 0 1rem;
      }}
      .mi-cta-box h3 {{ margin: 0 0 0.5rem; font-size: 1.35rem; }}
      .mi-cta-box p {{ color: {TEXT_MUTED}; margin: 0 0 1rem; }}
      .mi-problem-item {{
        display: flex;
        gap: 0.85rem;
        align-items: flex-start;
        margin-bottom: 1rem;
      }}
      .mi-problem-icon {{
        flex-shrink: 0;
        width: 2.25rem;
        height: 2.25rem;
        background: rgba(248, 113, 113, 0.12);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem;
      }}
      .mi-problem-text strong {{ color: {TEXT}; display: block; margin-bottom: 0.2rem; }}
      .mi-problem-text span {{ color: {TEXT_MUTED}; font-size: 0.88rem; line-height: 1.45; }}
    </style>
    """,
        unsafe_allow_html=True,
    )

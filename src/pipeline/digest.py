"""Weekly "what changed" digest - the payoff of collecting data over time.

Synthesises the freshest signals into one scannable brief so you don't have to
click through the dashboard every day:
  * niches with the strongest N-week engagement growth (heating up),
  * best still-CONTESTABLE opportunities right now,
  * top newly-scored micro-niches,
  * breakout apps (climbing the charts) + biggest quality drops (fresh gaps),
  * categories with abandoned forts (stale incumbents).

Returns Markdown (rendered in the dashboard, logged, and saved to data/).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import ROOT_DIR
from src.logging_config import get_logger
from src.reporting import (
    category_growth_df,
    latest_keyword_scores_df,
    latest_scores_df,
    quality_movers_df,
    rising_apps_df,
)

logger = get_logger(__name__)


def _pct(x) -> str:
    try:
        return f"{x * 100:+.0f}%"
    except (TypeError, ValueError):
        return "n/d"


def build_digest(weeks: int = 4) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"# Market Intel — digest ({datetime.now():%Y-%m-%d})")

    scores = latest_scores_df()
    growth = category_growth_df(weeks=weeks)

    # 1) Heating up (N-week growth)
    add(f"\n## Nisze rosnące ({weeks} tyg.)")
    if not growth.empty and growth["growth_pct"].notna().any():
        g = growth.dropna(subset=["growth_pct"]).sort_values(
            "growth_pct", ascending=False
        ).head(5)
        for _, r in g.iterrows():
            add(f"- **{r['category']}**: {_pct(r['growth_pct'])} "
                f"(n={int(r['apps_with_history'])})")
    else:
        add("- _Za mało historii — pojawi się po kilku tygodniach skanów._")

    # 2) Best contestable opportunities
    add("\n## Najlepsze osiągalne nisze (teraz)")
    if not scores.empty:
        contestable = scores[scores["mega_incumbents"].fillna(0) < 2].head(5)
        for _, r in contestable.iterrows():
            add(f"- **{r['category']}** — Opportunity {r['opportunity_score']:.0f}/100, "
                f"szansa {_pct(r['success_probability'])}, "
                f"contest. {r['contestability']:.2f}")

    # 3) Top micro-niches
    add("\n## Top mikro-nisze")
    kdf = latest_keyword_scores_df()
    if not kdf.empty:
        for _, r in kdf.head(5).iterrows():
            si = r.get("search_interest")
            si_s = f"{si:.2f}" if si is not None and si == si else "-"  # NaN check
            add(f"- **{r['term']}** — Opportunity {r['opportunity_score']:.0f}, "
                f"popyt wysz. {si_s}")
    else:
        add("- _Brak — uruchom `discover` / `keywords`._")

    # 4) Breakouts + quality drops
    add("\n## Breakout (pną się w rankingu)")
    rising = rising_apps_df(limit=5)
    if not rising.empty:
        for _, r in rising.iterrows():
            add(f"- **{r['name']}** ({r['category']}): #{r['rank_prev']} → "
                f"#{r['rank_now']} (↑{r['rank_delta']})")
    else:
        add("- _Brak ruchu / za mało historii._")

    add("\n## Spadki jakości (świeże luki)")
    movers = quality_movers_df(limit=5)
    if not movers.empty:
        for _, r in movers.iterrows():
            add(f"- **{r['name']}** ({r['category']}): "
                f"{r['rating_prev']}★ → {r['rating_now']}★ (−{r['rating_drop']})")
    else:
        add("- _Brak wykrytych spadków / za mało historii._")

    # 5) Abandoned forts
    add("\n## Porzucone forty")
    if not scores.empty and "stale_incumbents" in scores.columns:
        stale = scores[scores["stale_incumbents"].fillna(0) > 0].sort_values(
            "stale_incumbents", ascending=False
        ).head(5)
        if not stale.empty:
            for _, r in stale.iterrows():
                add(f"- **{r['category']}**: {int(r['stale_incumbents'])} "
                    f"silnych apek bez aktualizacji >12 mies.")
        else:
            add("- _Brak — czołowe apki są aktywnie utrzymywane._")
    else:
        add("- _Brak danych._")

    return "\n".join(lines)


def run_digest(weeks: int = 4, send: bool = False) -> str:
    md = build_digest(weeks=weeks)
    out_dir = ROOT_DIR / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"digest_{datetime.now():%Y%m%d}.md"
    try:
        path.write_text(md, encoding="utf-8")
        logger.info("Digest saved to %s", path)
    except OSError as exc:
        logger.warning("Could not write digest file: %s", exc)
    logger.info("=== WEEKLY DIGEST ===\n%s", md)
    if send:
        from src.pipeline.notify import send_digest

        send_digest(md)
    return md

"""One-click niche report (Markdown) - the shareable/sellable deliverable.

Bundles everything the platform knows about one category into a single
document: scores, structural signals, full-corpus review mining, AI insight,
clone-and-improve candidates and the 5-question niche validation. Rendered
from data already in the DB - no network calls, safe to run any time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.analysis.candidates import rank_candidates
from src.analysis.estimates import lifetime_installs
from src.reporting import (
    competitors_for_category,
    developer_concentration_df,
    latest_insight,
    latest_scores_df,
    localization_gap_df,
    pain_mining_for_category,
    young_winners_df,
)


def _pct(x: Optional[float]) -> str:
    return f"{x * 100:.0f}%" if x is not None else "n/d"


def build_niche_report(genre_id: int) -> str:
    df = latest_scores_df()
    row = df[df["genre_id"] == genre_id]
    if row.empty:
        return "# Brak danych dla tej kategorii\n"
    r = row.iloc[0]
    name = r["category"]

    lines = [
        f"# Raport niszy: {name}",
        f"*Wygenerowano: {datetime.now():%Y-%m-%d %H:%M} · Market Intel*",
        "",
        "## Werdykt ilościowy",
        f"- **Opportunity Score:** {r['opportunity_score']:.0f}/100",
        f"- **Szansa sukcesu przy budżecie:** {_pct(r['success_probability'])}",
        f"- **Popyt (znorm.):** {r['demand']:.2f} · **Luka jakości:** "
        f"{r['quality_gap']:.2f} · **Contestability:** {r['contestability']:.2f}",
        f"- **Śr. ocena konkurencji:** {r['avg_rating_top']} · "
        f"**Twierdze:** {int(r['strong_incumbents'])} · "
        f"**Giganci (>3M ocen):** {int(r['mega_incumbents'])}",
        f"- **Typowa apka (lifetime):** "
        f"{lifetime_installs(r['median_rating_count']).label} instalacji",
        "",
        "## Struktura rynku",
        f"- **Niezależni wydawcy w top:** {r.get('num_developers') or 'n/d'} · "
        f"**udział największego:** {_pct(r.get('top_dev_share'))}",
        f"- **Duże apki tylko po angielsku:** {_pct(r.get('english_only_share'))} "
        "(luka lokalizacyjna)",
        f"- **Monetyzacja (free→grossing):** {_pct(r.get('monetization_score'))} · "
        f"**apki płatne:** {_pct(r.get('paid_share'))}",
        f"- **Świeżość rynku (apki <2 lat w top):** {_pct(r.get('newcomer_share'))}",
        "",
    ]

    mining = pain_mining_for_category(genre_id)
    if mining.reviews_total:
        lines += [
            "## Głos użytkowników (pełny korpus recenzji, bez AI)",
            f"Przeanalizowano **{mining.reviews_total}** recenzji "
            f"({mining.reviews_negative} negatywnych).",
            "",
            "| Temat bólu | Recenzji | % negatywnych |",
            "|---|---|---|",
        ]
        for t in mining.themes[:8]:
            lines.append(f"| {t.theme} | {t.hits} | {t.share * 100:.0f}% |")
        if mining.bigrams:
            lines += ["", "**Najczęstsze frazy:** " +
                      ", ".join(f"„{b}” ({c})" for b, c in mining.bigrams[:10])]
        for t in mining.themes[:3]:
            if t.example:
                lines += ["", f"> „{t.example}” — o *{t.example_app}*"]
        lines.append("")

    insight = latest_insight(genre_id)
    if insight is not None:
        lines += ["## Analiza AI", insight.executive_summary or "", ""]
        pains = insight.pain_points or []
        if pains:
            lines.append("**Problemy użytkowników:**")
            for p in pains:
                lines.append(f"- [{(p.get('severity') or '?').upper()}] "
                             f"{p.get('label')}: {p.get('description')}")
        feats = insight.missing_features or []
        if feats:
            lines.append("\n**Brakujące funkcje (przewagi do zbudowania):**")
            for f in feats:
                lines.append(f"- {f.get('label')}: {f.get('description')}")
        if insight.suggested_direction:
            lines += ["", f"**Sugerowany kierunek:** {insight.suggested_direction}"]
        lines.append("")

    comp = competitors_for_category(genre_id)
    cands = rank_candidates(comp.to_dict("records"), limit=5) if not comp.empty else []
    if cands:
        lines.append("## Kandydaci „sklonuj i ulepsz”")
        for i, c in enumerate(cands, 1):
            rating = f"{c.rating:.2f}★" if c.rating is not None else "b/d"
            lines += [
                f"### {i}. {c.name} — beatability {c.beatability:.0f}/100",
                f"{c.developer or ''} · {rating} · {c.ratings:,} ocen".replace(",", " "),
                *[f"- {reason}" for reason in c.reasons],
                f"- **Jak wygrać:** {c.angle}",
                "",
            ]

    young = young_winners_df(genre_id)
    if not young.empty:
        lines += ["## Młodzi zwycięzcy (dowód, że da się wejść)",
                  "| Aplikacja | Wiek (mies.) | Pozycja | Ocena | Liczba ocen |",
                  "|---|---|---|---|---|"]
        for _, y in young.head(8).iterrows():
            lines.append(f"| {y['name']} | {y['age_months']} | {y['rank']} | "
                         f"{y['rating']} | {y['ratings']} |")
        lines.append("")

    devs = developer_concentration_df(genre_id)
    if not devs.empty:
        top_dev = devs.iloc[0]
        lines += ["## Koncentracja wydawców",
                  f"Największy wydawca: **{top_dev['developer']}** "
                  f"({_pct(top_dev['share'])} wszystkich ocen, "
                  f"{int(top_dev['apps'])} apek w top).", ""]

    loc = localization_gap_df(genre_id)
    if not loc.empty:
        en_only = loc[loc["english_only"]]
        if not en_only.empty:
            lines += ["## Luka lokalizacyjna — duże apki tylko po angielsku",
                      ", ".join(en_only["name"].head(8)), ""]

    lines += [
        "## Ekonomia wejścia",
        f"- Budżet: {r['marketing_cost_pln']:.0f} zł/mies. · CPI: "
        f"{r['est_cpi_pln']:.0f} zł · **~{int(r['est_installs_month'] or 0)} "
        "instalacji/mies.**",
        "",
        "---",
        "*Dane: darmowe publiczne endpointy Apple (top-charty RSS, iTunes "
        "Lookup/Search, recenzje RSS). Instalacje szacowane heurystycznie "
        "z liczby ocen (1–3%).*",
    ]
    return "\n".join(lines)

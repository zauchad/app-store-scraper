"""Level 2: LLM synthesis into actionable business conclusions.

This is the deliverable. It works in TWO modes, chosen automatically:

  MODE A - REVIEWS (preferred): mine real user reviews (esp. 1-3 star) for
           concrete pain points and missing features. Requires review TEXT.

  MODE B - COMPETITOR POSITIONING (free-tier fallback): as of 2026 Apple has
           killed anonymous free access to review text (RSS feed is dead). When
           no review text is available, we still produce value by analysing the
           competitors' OWN app descriptions (free via iTunes Lookup) plus the
           quantitative signals (ratings, saturation) to infer positioning gaps
           and where incumbents are weak. Less granular than reviews, but real.

To unlock Mode A for free-tier users, plug a paid reviews API (see README) into
the scraper; nothing else in the pipeline changes.
"""
from __future__ import annotations

import json
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis.llm import LLMError, get_llm_client
from src.db.models import App, Category, CategoryInsight, CategoryScore, Review
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

MAX_REVIEWS_FOR_LLM = 120
MAX_REVIEW_CHARS = 600
MAX_APPS_FOR_POSITIONING = 25
MAX_DESC_CHARS = 700

SYSTEM_PROMPT = (
    "You are a senior market research analyst specialising in mobile app niches. "
    "You turn raw App Store signals into sharp, actionable business conclusions "
    "for a solo founder with a LEAN marketing budget (about 5,000-10,000 PLN/month) "
    "who explicitly avoids capital-heavy games. Be concrete and commercial, not generic. "
    "Always respond with a single valid JSON object and nothing else."
)

_JSON_SCHEMA = {
    "executive_summary": "2-4 sentence TL;DR of the niche opportunity for a founder",
    "market_saturation_note": "1-2 sentences: how crowded/defensible is this niche",
    "pain_points": [
        {"label": "short name", "description": "the unmet need / weakness", "severity": "high|medium|low"}
    ],
    "missing_features": [
        {"label": "feature", "description": "why it is an opening / who wants it"}
    ],
    "suggested_direction": "concrete product angle for MY new app to win this niche",
}


def _select_reviews(session: Session, genre_id: int) -> List[Review]:
    """Prioritise negative/mixed reviews (where opportunity hides), then recent."""
    app_ids = [
        row[0]
        for row in session.execute(select(App.id).where(App.genre_id == genre_id)).all()
    ]
    if not app_ids:
        return []

    negative = list(
        session.execute(
            select(Review)
            .where(Review.app_id.in_(app_ids))
            .where(Review.rating.isnot(None))
            .where(Review.rating <= 3)
            .order_by(Review.fetched_at.desc())
            .limit(MAX_REVIEWS_FOR_LLM)
        ).scalars()
    )
    if len(negative) >= MAX_REVIEWS_FOR_LLM:
        return negative

    seen = {r.id for r in negative}
    extra = [
        r
        for r in session.execute(
            select(Review)
            .where(Review.app_id.in_(app_ids))
            .order_by(Review.fetched_at.desc())
            .limit(MAX_REVIEWS_FOR_LLM)
        ).scalars()
        if r.id not in seen
    ][: MAX_REVIEWS_FOR_LLM - len(negative)]
    return negative + extra


def _select_competitors(session: Session, genre_id: int) -> List[App]:
    return list(
        session.execute(
            select(App)
            .where(App.genre_id == genre_id)
            .where(App.description.isnot(None))
            .limit(MAX_APPS_FOR_POSITIONING)
        ).scalars()
    )


def _latest_score(session: Session, genre_id: int) -> Optional[CategoryScore]:
    return session.execute(
        select(CategoryScore)
        .where(CategoryScore.genre_id == genre_id)
        .order_by(CategoryScore.computed_at.desc())
        .limit(1)
    ).scalars().first()


def _mining_context(genre_id: int) -> str:
    """Deterministic full-corpus stats so the LLM's sample of ~120 reviews is
    grounded in what the WHOLE corpus (often 10k+) actually says."""
    try:
        from src.analysis.review_mining import mine_pains

        mining = mine_pains(genre_id=genre_id)
    except Exception as exc:  # noqa: BLE001 - mining must never block the LLM
        logger.warning("Pain mining failed for %s: %s", genre_id, exc)
        return ""
    if not mining.themes:
        return ""
    themes = "; ".join(
        f"{t.theme}: {t.hits} negative reviews ({t.share * 100:.0f}%)"
        for t in mining.themes[:8]
    )
    phrases = ", ".join(f'"{b}"' for b, _ in mining.bigrams[:10])
    return (
        f"FULL-CORPUS STATS (computed over ALL {mining.reviews_total} stored "
        f"reviews, {mining.reviews_negative} negative - use these to weigh how "
        f"representative the sampled reviews below are):\n"
        f"Recurring pain themes: {themes}\n"
        f"Most repeated phrases in negative reviews: {phrases}\n\n"
    )


def _reviews_prompt(cat_name: str, reviews: List[Review], genre_id: int) -> str:
    lines = []
    for r in reviews:
        body = (r.body or "").strip().replace("\n", " ")[:MAX_REVIEW_CHARS]
        title = (r.title or "").strip()
        lines.append(f"[{r.rating or '?'}star] {title} :: {body}")
    corpus = "\n".join(lines)
    return (
        f"App Store category: {cat_name}\n"
        f"Below are {len(reviews)} real user reviews (mostly critical - that is where "
        f"unmet needs surface). Analyse them.\n\n"
        f"{_mining_context(genre_id)}"
        f"Return STRICTLY this JSON shape (5-8 pain_points, 3-6 missing_features, "
        f"ranked by frequency/severity):\n{json.dumps(_JSON_SCHEMA, indent=2)}\n\n"
        f"REVIEWS:\n{corpus}"
    )


def _positioning_prompt(
    cat_name: str, apps: List[App], score: Optional[CategoryScore]
) -> str:
    lines = []
    for a in apps:
        desc = (a.description or "").strip().replace("\n", " ")[:MAX_DESC_CHARS]
        lines.append(f"- {a.name} (by {a.developer}): {desc}")
    corpus = "\n".join(lines)

    metrics = ""
    if score is not None:
        metrics = (
            f"Quantitative signals: avg incumbent rating = {score.avg_rating_top}, "
            f"strong 'fortress' incumbents = {score.num_strong_incumbents}, "
            f"opportunity score = {score.opportunity_score}/100, "
            f"quality-gap signal = {score.quality_gap_score} (higher = weaker incumbents).\n"
        )

    return (
        f"App Store category: {cat_name}\n"
        f"NOTE: user review text is unavailable, so infer the opportunity from what "
        f"COMPETITORS say about THEMSELVES (their store descriptions) plus the metrics.\n"
        f"{metrics}\n"
        f"Interpret pain_points as 'likely unmet needs / weak spots implied by what "
        f"incumbents emphasise or omit', and missing_features as 'gaps not covered by "
        f"any competitor'. Be explicit that this is positioning-based inference.\n\n"
        f"Return STRICTLY this JSON shape (4-6 pain_points, 3-5 missing_features):\n"
        f"{json.dumps(_JSON_SCHEMA, indent=2)}\n\n"
        f"COMPETITOR DESCRIPTIONS:\n{corpus}"
    )


def _build(session: Session, genre_id: int, cat_name: str) -> Optional[Tuple[str, str, int]]:
    """Return (prompt, source, n_analyzed) or None if we have nothing to work with."""
    reviews = _select_reviews(session, genre_id)
    if reviews:
        return _reviews_prompt(cat_name, reviews, genre_id), "reviews", len(reviews)

    apps = _select_competitors(session, genre_id)
    if apps:
        score = _latest_score(session, genre_id)
        return _positioning_prompt(cat_name, apps, score), "positioning", len(apps)

    return None


def generate_insight_for_category(genre_id: int) -> Optional[CategoryInsight]:
    client = get_llm_client()
    if client is None:
        logger.warning("Skipping insight for %s: LLM not configured", genre_id)
        return None

    with session_scope() as session:
        cat = session.get(Category, genre_id)
        cat_name = cat.name if cat else str(genre_id)
        built = _build(session, genre_id, cat_name)

    if built is None:
        logger.warning("No data (reviews or descriptions) for category %s", genre_id)
        return None

    prompt, source, n = built
    logger.info("Synthesising %s via mode=%s on %d items", cat_name, source, n)
    try:
        data = client.generate_json(prompt, system=SYSTEM_PROMPT)
    except LLMError as exc:
        logger.error("LLM synthesis failed for %s: %s", genre_id, exc)
        return None

    data["_source_mode"] = source
    with session_scope() as session:
        insight = CategoryInsight(
            genre_id=genre_id,
            llm_model=client.model_name,
            reviews_analyzed=n if source == "reviews" else 0,
            executive_summary=data.get("executive_summary"),
            market_saturation_note=data.get("market_saturation_note"),
            suggested_direction=data.get("suggested_direction"),
            pain_points=data.get("pain_points"),
            missing_features=data.get("missing_features"),
            raw_json=data,
        )
        session.add(insight)
        session.flush()
        insight_id = insight.id

    with session_scope() as session:
        return session.get(CategoryInsight, insight_id)

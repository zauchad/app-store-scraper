"""LLM-driven micro-niche hypothesis generation.

The automation loop: the LLM PROPOSES specific, targetable search terms (niche
hypotheses), and the Search API + scoring then VALIDATE them quantitatively.
This is how we discover niches below the top charts without you hand-picking.

The prompt is deliberately biased AWAY from giant-owned generic terms (e.g.
"messenger", "photo editor") and TOWARD specific audiences / use-cases where a
lean founder can realistically win.
"""
from __future__ import annotations

from typing import List, Optional

from src.analysis.llm import LLMError, get_llm_client
from src.logging_config import get_logger
from src.scraper.categories import CATEGORY_SEEDS

logger = get_logger(__name__)

SYSTEM = (
    "You are an App Store market research analyst who finds under-served micro-"
    "niches for a solo founder with a lean marketing budget (~5,000-10,000 PLN/"
    "month), who avoids capital-heavy games. You propose specific, long-tail "
    "search terms - not generic, giant-owned categories. Respond with a single "
    "valid JSON object only."
)


def _genre_name(genre_id: Optional[int]) -> Optional[str]:
    if genre_id is None:
        return None
    for seed in CATEGORY_SEEDS:
        if seed.genre_id == genre_id:
            return seed.name
    return None


def generate_keywords(
    theme: str, n: int = 15, genre_id: Optional[int] = None
) -> List[str]:
    """Return up to `n` candidate micro-niche search terms for a theme/category."""
    client = get_llm_client()
    if client is None:
        logger.warning("Cannot generate keywords: LLM not configured.")
        return []

    context = theme.strip()
    genre_name = _genre_name(genre_id)
    if genre_name:
        context = f"{context} (App Store category: {genre_name})" if context else genre_name

    prompt = (
        f"Propose {n} specific App Store SEARCH TERMS that represent promising "
        f"micro-niches within: {context}.\n\n"
        "Rules:\n"
        "- Each term = what a user would actually type in App Store search.\n"
        "- Favour a specific AUDIENCE or USE-CASE (e.g. 'budgeting for couples', "
        "'sleep tracker for shift workers', 'invoice app for freelancers').\n"
        "- AVOID generic giant-owned terms (e.g. 'chat', 'photo editor', 'bank').\n"
        "- 2-4 words each, lowercase, no punctuation.\n\n"
        'Return JSON: {"keywords": ["term one", "term two", ...]}'
    )
    try:
        data = client.generate_json(prompt, system=SYSTEM)
    except LLMError as exc:
        logger.error("Keyword generation failed: %s", exc)
        return []

    raw = data.get("keywords") or []
    terms = []
    seen = set()
    for t in raw:
        if not isinstance(t, str):
            continue
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            terms.append(t)
    logger.info("Generated %d candidate keywords for %r", len(terms), context)
    return terms[:n]

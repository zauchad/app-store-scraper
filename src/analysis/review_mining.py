"""LLM-free text mining over the FULL review corpus.

The LLM deep-dive reads ~120 reviews; this module reads ALL of them (100k+)
and answers, deterministically and for free:

  * Which pain themes repeat across negative reviews (crash? ads? paywall?)
    -> the "analyse patterns in competitor reviews" step of niche research,
       done systematically instead of reading 100 reviews by hand.
  * Which exact phrases users repeat (top bigrams of 1-3 star reviews).
  * Which apps have the highest share of angry reviews (most beatable).

Everything is computed straight from the `reviews` table, so it works even
when the LLM is off, and it scales to the whole corpus.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from src.db.models import App, Review
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

# Ratings at/below this count as "negative" (pain fuel).
NEGATIVE_MAX_RATING = 3
# Minimum reviews fetched for an app before its negative-share is meaningful.
MIN_REVIEWS_FOR_APP_STATS = 30

# Pain-theme lexicon. Order matters only for display; a review can hit many
# themes. Patterns are lowercase substrings (fast, dependency-free).
PAIN_THEMES: Dict[str, List[str]] = {
    "Crashe i bugi": [
        "crash", "freez", "glitch", "broken", "bug", "won't open", "wont open",
        "not working", "doesn't work", "doesnt work", "stopped working",
        "keeps closing", "error",
    ],
    "Reklamy": [
        "too many ads", "so many ads", "ad every", "full of ads", "ads are",
        "unskippable", "advertis", "pop-up", "popup",
    ],
    "Ceny i subskrypcje": [
        "subscription", "paywall", "expensive", "overpriced", "money grab",
        "cash grab", "free trial", "charged me", "auto-renew", "refund",
        "rip off", "ripoff", "pay to", "have to pay", "not free",
    ],
    "Logowanie i konto": [
        "can't log", "cant log", "log in", "login", "sign in", "signin",
        "account locked", "password reset", "verification code",
    ],
    "Synchronizacja i utrata danych": [
        "sync", "lost my", "lost all", "data loss", "deleted my", "disappear",
        "backup", "restore purchase", "progress lost",
    ],
    "Wydajność": [
        "slow", "laggy", "lagging", "takes forever", "loading", "battery drain",
        "drains battery", "overheat",
    ],
    "UX i nowy design": [
        "confusing", "clunky", "hard to use", "complicated", "unusable",
        "new update ruined", "hate the new", "bring back the old", "redesign",
        "user interface", "cluttered",
    ],
    "Wsparcie klienta": [
        "customer service", "customer support", "no response", "support team",
        "contacted support", "no help",
    ],
    "Spam powiadomień": [
        "notification", "spams", "spamming", "constant reminders",
    ],
    "Prywatność i uprawnienia": [
        "privacy", "tracking me", "sells your data", "personal data",
        "permission",
    ],
    "Tryb offline": [
        "offline", "no internet", "without internet", "wifi only",
        "internet connection",
    ],
}

# Stopwords for the bigram miner (small on purpose - we WANT domain words).
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "you", "your", "have", "has",
    "was", "are", "but", "not", "can", "cant", "can't", "all", "its", "it's",
    "app", "just", "get", "got", "out", "very", "too", "than", "then", "them",
    "when", "what", "why", "how", "would", "will", "there", "their", "they",
    "from", "been", "being", "because", "into", "only", "even", "also", "some",
    "still", "much", "more", "most", "other", "which", "were", "had", "his",
    "her", "she", "him", "who", "about", "after", "before", "over", "under",
    "again", "once", "here", "any", "each", "few", "our", "ours", "off", "own",
    "same", "an", "of", "to", "in", "on", "it", "is", "as", "at", "by", "or",
    "be", "if", "so", "no", "do", "did", "does", "my", "me", "we", "us", "am",
    "one", "two", "now", "way", "use", "using", "used", "don", "don't", "dont",
    "im", "i'm", "ive", "i've", "really", "like", "want", "make", "makes",
    "time", "times", "every", "never", "always", "back", "since", "should",
    "could", "these", "those", "while", "where", "doing", "down", "up",
}

_WORD_RE = re.compile(r"[a-z']{2,}")


@dataclass
class ThemeStat:
    theme: str
    hits: int                      # negative reviews matching the theme
    share: float                   # hits / all negative reviews analysed
    example: Optional[str] = None  # representative quote
    example_app: Optional[str] = None


@dataclass
class PainMiningResult:
    genre_id: Optional[int]
    reviews_total: int             # all reviews for the niche in DB
    reviews_negative: int          # rating <= NEGATIVE_MAX_RATING
    themes: List[ThemeStat] = field(default_factory=list)
    bigrams: List[Tuple[str, int]] = field(default_factory=list)
    # (app name, negative share 0..1, reviews fetched) - most-hated first.
    app_negative_share: List[Tuple[str, float, int]] = field(default_factory=list)


def _match_themes(text: str) -> List[str]:
    hits = []
    for theme, patterns in PAIN_THEMES.items():
        if any(p in text for p in patterns):
            hits.append(theme)
    return hits


def _bigrams(text: str) -> List[str]:
    words = [w for w in _WORD_RE.findall(text) if w not in _STOPWORDS]
    return [f"{a} {b}" for a, b in zip(words, words[1:])]


def mine_pains(
    genre_id: Optional[int] = None,
    app_ids: Optional[List[int]] = None,
    max_reviews: int = 100_000,
) -> PainMiningResult:
    """Mine pain themes + repeated phrases from negative reviews of a niche.

    Scope by `genre_id` (all tracked apps of a category) or an explicit
    `app_ids` list (e.g. keyword competitors). Newest reviews win when the
    corpus exceeds `max_reviews`.
    """
    with session_scope() as session:
        stmt = (
            select(Review.rating, Review.title, Review.body, App.name)
            .join(App, App.id == Review.app_id)
        )
        if app_ids:
            stmt = stmt.where(Review.app_id.in_(app_ids))
        elif genre_id is not None:
            stmt = stmt.where(App.genre_id == genre_id)
        stmt = stmt.order_by(Review.fetched_at.desc()).limit(max_reviews)
        rows = session.execute(stmt).all()

    total = len(rows)
    theme_hits: Counter = Counter()
    theme_example: Dict[str, Tuple[str, str]] = {}
    bigram_counts: Counter = Counter()
    per_app: Dict[str, List[int]] = {}  # name -> [negative, total]

    negative = 0
    for rating, title, body, app_name in rows:
        text_raw = f"{title or ''}. {body or ''}".strip(". ")
        stats = per_app.setdefault(app_name, [0, 0])
        stats[1] += 1
        if rating is None or rating > NEGATIVE_MAX_RATING:
            continue
        negative += 1
        stats[0] += 1
        text = text_raw.lower()
        for theme in _match_themes(text):
            theme_hits[theme] += 1
            # Prefer short, punchy examples (a full quote fits in a card).
            if theme not in theme_example and 30 <= len(text_raw) <= 220:
                theme_example[theme] = (text_raw, app_name)
        bigram_counts.update(_bigrams(text))

    themes = [
        ThemeStat(
            theme=t,
            hits=h,
            share=round(h / negative, 4) if negative else 0.0,
            example=theme_example.get(t, (None, None))[0],
            example_app=theme_example.get(t, (None, None))[1],
        )
        for t, h in theme_hits.most_common()
    ]

    app_share = [
        (name, round(neg / tot, 4), tot)
        for name, (neg, tot) in per_app.items()
        if tot >= MIN_REVIEWS_FOR_APP_STATS
    ]
    app_share.sort(key=lambda x: x[1], reverse=True)

    logger.info(
        "Pain mining genre=%s: %d reviews (%d negative), %d themes",
        genre_id, total, negative, len(themes),
    )
    return PainMiningResult(
        genre_id=genre_id,
        reviews_total=total,
        reviews_negative=negative,
        themes=themes,
        bigrams=bigram_counts.most_common(15),
        app_negative_share=app_share[:15],
    )

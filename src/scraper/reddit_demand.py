"""Reddit demand mining - FREE upstream demand signal.

People ask for apps on Reddit BEFORE a niche shows up in App Store data:
"is there an app for...", "looking for an app that...". Counting and reading
those posts answers the blog-methodology questions "is the problem painful?"
and "is the niche growing?" straight from the audience's mouth.

Cost: FREE. Reddit blocks anonymous JSON since 2023, so this uses the official
OAuth API (100 req/min free): create a "script" app at
https://www.reddit.com/prefs/apps (2 minutes, no payment), set
REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET in .env.

Best-effort by design: if unconfigured or rate-limited, we return an empty
result flagged `error`/`unconfigured` and the UI says so - scoring never
depends on this signal.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import requests

from src.config import settings
from src.logging_config import get_logger

logger = get_logger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SEARCH_URL = "https://oauth.reddit.com/search"
HEADERS = {"User-Agent": "macos:market-intel:v0.1 (niche research)"}
TIMEOUT = 15

_token_cache = {"token": None, "exp": 0.0}


def is_configured() -> bool:
    return bool(settings.reddit_client_id and settings.reddit_client_secret)


def _get_token(session: requests.Session) -> Optional[str]:
    if _token_cache["token"] and time.time() < _token_cache["exp"] - 60:
        return _token_cache["token"]
    resp = session.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(settings.reddit_client_id, settings.reddit_client_secret),
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data.get("access_token")
    _token_cache["exp"] = time.time() + int(data.get("expires_in", 3600))
    return _token_cache["token"]

# Phrases people use when they WANT an app that doesn't exist / disappoints.
DEMAND_TEMPLATES = [
    '"is there an app" {topic}',
    '"looking for an app" {topic}',
    '"app recommendation" {topic}',
    '"i wish there was an app" {topic}',
]


@dataclass
class RedditPost:
    title: str
    subreddit: str
    score: int
    num_comments: int
    created: datetime
    url: str
    query: str


@dataclass
class RedditDemand:
    topic: str
    posts: List[RedditPost] = field(default_factory=list)
    total_matches: int = 0
    recent_12mo: int = 0
    top_subreddits: List[tuple] = field(default_factory=list)
    error: bool = False
    unconfigured: bool = False


def _search(session: requests.Session, query: str, limit: int = 25) -> List[dict]:
    headers = dict(HEADERS)
    headers["Authorization"] = f"Bearer {_get_token(session)}"
    resp = session.get(
        SEARCH_URL,
        params={"q": query, "limit": limit, "sort": "relevance", "t": "all",
                "type": "link"},
        headers=headers,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    children = (resp.json().get("data") or {}).get("children") or []
    return [c.get("data") or {} for c in children if c.get("kind") == "t3"]


def demand_scan(topic: str, max_per_query: int = 25) -> RedditDemand:
    """Scan Reddit for 'I need an app for <topic>' style demand posts."""
    topic = topic.strip()
    result = RedditDemand(topic=topic)
    if not is_configured():
        result.unconfigured = True
        result.error = True
        return result
    session = requests.Session()
    seen: set = set()
    sub_counts: Dict[str, int] = {}
    now = datetime.utcnow()
    any_success = False

    for template in DEMAND_TEMPLATES:
        query = template.format(topic=topic)
        try:
            items = _search(session, query, limit=max_per_query)
            any_success = True
        except Exception as exc:  # noqa: BLE001 - best effort
            logger.warning("Reddit search failed %r: %s", query, exc)
            continue
        for d in items:
            pid = d.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            created = datetime.utcfromtimestamp(d.get("created_utc") or 0)
            sub = d.get("subreddit") or "?"
            sub_counts[sub] = sub_counts.get(sub, 0) + 1
            result.posts.append(
                RedditPost(
                    title=(d.get("title") or "")[:200],
                    subreddit=sub,
                    score=int(d.get("score") or 0),
                    num_comments=int(d.get("num_comments") or 0),
                    created=created,
                    url="https://www.reddit.com" + (d.get("permalink") or ""),
                    query=query,
                )
            )
            if (now - created).days <= 365:
                result.recent_12mo += 1
        time.sleep(1.0)  # be a polite, boring guest

    result.error = not any_success
    result.total_matches = len(result.posts)
    result.posts.sort(key=lambda p: p.score, reverse=True)
    result.top_subreddits = sorted(
        sub_counts.items(), key=lambda kv: kv[1], reverse=True
    )[:5]
    logger.info("Reddit demand %r: %d posts (%d recent)", topic,
                result.total_matches, result.recent_12mo)
    return result

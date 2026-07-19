"""CLI entry point.

Examples:
    python run.py init                 # create the DB schema
    python run.py scan                 # Level 1: scrape + score (daily)
    python run.py scan --no-reviews    # Level 1 without pulling reviews (fast)
    python run.py deep-dive            # Level 2: LLM insights for top-K niches
    python run.py deep-dive --genre 6013
    python run.py all                  # scan + deep-dive (full daily job)
"""
from __future__ import annotations

import argparse
import sys

from src.db.session import init_db
from src.logging_config import get_logger

logger = get_logger("cli")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Market Research Intelligence Platform")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create database schema")

    p_scan = sub.add_parser("scan", help="Level 1: scrape + Opportunity Score")
    p_scan.add_argument("--no-reviews", action="store_true", help="Skip review fetch")

    p_deep = sub.add_parser("deep-dive", help="Level 2: LLM synthesis")
    p_deep.add_argument("--top-k", type=int, default=None)
    p_deep.add_argument("--genre", type=int, action="append", help="Specific genre id(s)")

    p_all = sub.add_parser("all", help="Full daily job: scan + deep-dive")
    p_all.add_argument("--no-reviews", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "init":
        init_db()
        return 0

    if args.command == "scan":
        from src.pipeline.daily_scan import run_daily_scan

        run_daily_scan(fetch_reviews=not args.no_reviews)
        return 0

    if args.command == "deep-dive":
        from src.pipeline.deep_dive import run_deep_dive

        run_deep_dive(top_k=args.top_k, genre_ids=args.genre)
        return 0

    if args.command == "all":
        from src.pipeline.daily_scan import run_daily_scan
        from src.pipeline.deep_dive import run_deep_dive

        run_daily_scan(fetch_reviews=not args.no_reviews)
        run_deep_dive()
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

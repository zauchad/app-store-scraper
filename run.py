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
import os
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
    p_scan.add_argument(
        "--country",
        type=str,
        default=None,
        help="Storefront code (e.g. us, pl). Defaults to STORE_COUNTRY.",
    )

    p_deep = sub.add_parser("deep-dive", help="Level 2: LLM synthesis")
    p_deep.add_argument("--top-k", type=int, default=None)
    p_deep.add_argument("--genre", type=int, action="append", help="Specific genre id(s)")

    p_all = sub.add_parser("all", help="Full daily job: scan + deep-dive + discover")
    p_all.add_argument("--no-reviews", action="store_true")

    p_disc = sub.add_parser("discover", help="Auto-drill top categories into micro-niches (LLM)")
    p_disc.add_argument("--top-k", type=int, default=None)
    p_disc.add_argument("--per-category", type=int, default=None)

    p_ret = sub.add_parser("retention", help="Downsample old snapshots (DISABLED by default)")
    p_ret.add_argument("--daily-days", type=int, default=None)
    p_ret.add_argument("--force", action="store_true",
                       help="Run even if RETENTION_ENABLED is false")

    sub.add_parser("webhook-server", help="Lemon Squeezy billing webhook (FastAPI)")

    p_bill = sub.add_parser("billing-check", help="Validate monetization config")
    p_bill.add_argument(
        "--strict",
        action="store_true",
        help="Fail on missing vars even if MONETIZATION_ENABLED=false",
    )
    p_bill.add_argument(
        "--simulate-webhook",
        action="store_true",
        help="Grant test credits via a fake order_created webhook payload",
    )
    p_bill.add_argument(
        "--user-id",
        type=str,
        default="test-billing-user",
        help="Supabase user UUID for --simulate-webhook",
    )
    p_bill.add_argument(
        "--variant",
        choices=["1", "5", "pro"],
        default="1",
        help="Which product variant to simulate",
    )

    p_dig = sub.add_parser("digest", help="Build the weekly 'what changed' brief")
    p_dig.add_argument("--weeks", type=int, default=4)
    p_dig.add_argument("--send", action="store_true",
                       help="Deliver to Slack/e-mail (whatever is configured)")

    p_kw = sub.add_parser("keywords", help="Micro-niche discovery below the top charts")
    p_kw.add_argument("--terms", type=str, default=None,
                      help="Comma-separated search terms to validate")
    p_kw.add_argument("--generate", action="store_true",
                      help="Let the LLM propose candidate niche keywords")
    p_kw.add_argument("--theme", type=str, default=None,
                      help="Theme/context for --generate (e.g. 'habit tracking')")
    p_kw.add_argument("--genre", type=int, default=None, help="Category genre id")
    p_kw.add_argument("--n", type=int, default=15, help="How many keywords to generate")

    args = parser.parse_args(argv)

    if args.command == "init":
        init_db()
        return 0

    if args.command == "scan":
        from src.pipeline.daily_scan import run_daily_scan

        run_daily_scan(fetch_reviews=not args.no_reviews, country=args.country)
        return 0

    if args.command == "deep-dive":
        from src.pipeline.deep_dive import run_deep_dive

        run_deep_dive(top_k=args.top_k, genre_ids=args.genre)
        return 0

    if args.command == "all":
        from src.pipeline.daily_scan import run_daily_scan
        from src.pipeline.deep_dive import run_deep_dive
        from src.pipeline.discover import run_discovery
        from src.pipeline.retention import run_retention

        run_daily_scan(fetch_reviews=not args.no_reviews)
        run_deep_dive()
        run_discovery()
        run_retention()
        return 0

    if args.command == "discover":
        from src.pipeline.discover import run_discovery

        run_discovery(top_k=args.top_k, per_category=args.per_category)
        return 0

    if args.command == "retention":
        from src.pipeline.retention import run_retention

        run_retention(daily_days=args.daily_days, force=args.force)
        return 0

    if args.command == "webhook-server":
        import uvicorn

        uvicorn.run(
            "billing.webhook_server:app",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "8080")),
            reload=False,
        )
        return 0

    if args.command == "billing-check":
        from src.billing.check_config import format_check_report, run_billing_check

        if args.simulate_webhook:
            import time

            from src.billing.lemon_squeezy import handle_webhook
            from src.config import settings

            credits_map = {"1": 1, "5": 5, "pro": settings.pro_monthly_credits}
            variant_map = {
                "1": settings.lemonsqueezy_variant_1_credit or "999001",
                "5": settings.lemonsqueezy_variant_5_credits or "999005",
                "pro": settings.lemonsqueezy_variant_pro or "999039",
            }
            custom: dict = {
                "user_id": args.user_id,
                "credits": credits_map[args.variant],
            }
            if args.variant == "pro":
                custom["plan"] = "pro"
            sim_id = f"sim-{int(time.time())}"
            payload = {
                "meta": {
                    "event_name": "order_created",
                    "custom_data": custom,
                },
                "data": {
                    "id": sim_id,
                    "attributes": {
                        "user_email": f"{args.user_id}@test.local",
                        "first_order_item": {"variant_id": int(variant_map[args.variant])},
                    },
                },
            }
            result = handle_webhook(payload)
            print("Simulated webhook:", result)
            return 0 if result.get("ok") else 1

        res = run_billing_check(strict=args.strict)
        print(format_check_report(res))
        return 0 if res.ok else 1

    if args.command == "digest":
        from src.pipeline.digest import run_digest

        run_digest(weeks=args.weeks, send=args.send)
        return 0

    if args.command == "keywords":
        from src.pipeline.keyword_scan import run_keyword_scan

        terms = [t for t in (args.terms.split(",") if args.terms else []) if t.strip()]
        results = run_keyword_scan(
            terms=terms,
            theme=args.theme,
            genre_id=args.genre,
            generate=args.generate,
            n=args.n,
        )
        for r in results:
            logger.info(
                "%-32s opp=%5.1f contest=%.2f giants=%d fortresses=%d gap=%.2f",
                r.term, r.opportunity_score, r.contestability,
                r.num_mega_incumbents, r.num_strong_incumbents, r.quality_gap_score,
            )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

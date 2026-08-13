"""Validate monetization / billing configuration before go-live."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.config import settings


@dataclass
class CheckResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def run_billing_check(*, strict: bool | None = None) -> CheckResult:
    """Return configuration health for monetization stack.

    strict defaults to settings.monetization_enabled.
    """
    if strict is None:
        strict = settings.monetization_enabled

    res = CheckResult(ok=True)

    if not settings.monetization_enabled:
        res.notes.append(
            "MONETIZATION_ENABLED=false — dashboard is open (dev mode). "
            "Set true in Streamlit secrets when going live."
        )
        if not strict:
            return res

    # --- Shared (Streamlit + webhook server) ---
    if not settings.database_url.strip():
        res.errors.append("DATABASE_URL is empty (required for users/credits in prod).")
    elif settings.resolved_database_url.startswith("sqlite"):
        res.warnings.append(
            "DATABASE_URL points to SQLite — OK locally, use Supabase Postgres in prod."
        )

    # --- Streamlit dashboard ---
    if not settings.supabase_url.strip():
        res.errors.append("SUPABASE_URL is missing (required for login).")
    if not settings.supabase_anon_key.strip():
        res.errors.append("SUPABASE_ANON_KEY is missing (required for login).")

    if not settings.app_base_url.strip():
        res.warnings.append(
            "APP_BASE_URL is empty — Google sign-in and e-mail confirmation links "
            "cannot redirect back into the app."
        )
    if settings.auth_google_enabled and not settings.app_base_url.strip():
        res.errors.append("AUTH_GOOGLE_ENABLED=true requires APP_BASE_URL.")

    checkouts = [
        ("LEMONSQUEEZY_CHECKOUT_1_CREDIT", settings.lemonsqueezy_checkout_1_credit),
        ("LEMONSQUEEZY_CHECKOUT_PRO", settings.lemonsqueezy_checkout_pro),
    ]
    if settings.credit_pack_enabled:
        checkouts.append(
            ("LEMONSQUEEZY_CHECKOUT_5_CREDITS", settings.lemonsqueezy_checkout_5_credits)
        )
    missing_checkouts = [name for name, val in checkouts if not val.strip()]
    if len(missing_checkouts) == len(checkouts):
        res.errors.append("No Lemon Squeezy checkout URLs configured.")
    elif missing_checkouts:
        res.warnings.append(f"Missing checkout URLs: {', '.join(missing_checkouts)}")

    for name, url in checkouts:
        if url.strip() and "lemonsqueezy.com" not in url:
            res.warnings.append(f"{name} does not look like a Lemon Squeezy URL.")

    # --- Webhook server (deployed separately) ---
    if not settings.lemonsqueezy_webhook_secret.strip():
        res.errors.append(
            "LEMONSQUEEZY_WEBHOOK_SECRET is missing (webhook signature verification)."
        )

    variants = [
        ("LEMONSQUEEZY_VARIANT_1_CREDIT", settings.lemonsqueezy_variant_1_credit, 1),
        ("LEMONSQUEEZY_VARIANT_PRO", settings.lemonsqueezy_variant_pro, "Pro"),
    ]
    if settings.credit_pack_enabled:
        variants.append(
            ("LEMONSQUEEZY_VARIANT_5_CREDITS", settings.lemonsqueezy_variant_5_credits, 5)
        )
    missing_variants = [name for name, val, _ in variants if not val.strip()]
    if missing_variants:
        res.warnings.append(
            "Missing variant IDs (webhook won't map purchases → credits): "
            + ", ".join(missing_variants)
        )

    if settings.pro_monthly_credits <= 0:
        res.warnings.append("PRO_MONTHLY_CREDITS should be > 0.")

    if settings.signup_bonus_credits <= 0:
        res.notes.append(
            "SIGNUP_BONUS_CREDITS=0 — new accounts never see a full report before "
            "paying. 1 is the recommended value."
        )
    else:
        res.notes.append(
            f"New accounts get {settings.signup_bonus_credits} free unlock(s)."
        )

    # --- DB schema ---
    try:
        from src.db.session import init_db

        init_db()
        res.notes.append("DB schema OK (billing tables ensured).")
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"DB init failed: {exc}")

    res.ok = len(res.errors) == 0
    return res


def format_check_report(res: CheckResult) -> str:
    lines: List[str] = []
    if res.ok:
        lines.append("✅ Billing configuration looks ready.")
    else:
        lines.append("❌ Billing configuration has blocking issues.")
    for msg in res.errors:
        lines.append(f"  ERROR: {msg}")
    for msg in res.warnings:
        lines.append(f"  WARN:  {msg}")
    for msg in res.notes:
        lines.append(f"  NOTE:  {msg}")
    return "\n".join(lines)

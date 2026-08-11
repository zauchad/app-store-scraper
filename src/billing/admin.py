"""Admin operations (grant credits, support)."""
from __future__ import annotations

from src.billing.account import get_user_by_email
from src.billing.credits import grant_credits
from src.config import settings


def grant_credits_admin(
    *,
    email: str,
    amount: int,
    reason: str = "admin_grant",
    admin_secret: str,
) -> int:
    if not settings.billing_admin_secret.strip():
        raise ValueError("BILLING_ADMIN_SECRET is not configured")
    if admin_secret != settings.billing_admin_secret.strip():
        raise ValueError("invalid admin secret")

    user = get_user_by_email(email)
    if user is None:
        raise ValueError(
            f"No user with email {email}. User must sign up in the dashboard first."
        )

    grant_credits(user.id, amount, reason, reference_id="admin")
    user = get_user_by_email(email)
    assert user is not None
    return user.credits_balance

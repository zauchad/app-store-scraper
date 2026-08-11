"""Credit balance, niche unlocks, and Pro entitlements."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import CreditLedger, UnlockedNiche, User
from src.db.session import session_scope
from src.logging_config import get_logger

logger = get_logger(__name__)

CREDIT_COST_NICHE_UNLOCK = 1
PRO_PLAN = "pro"
FREE_PLAN = "free"


def niche_key(*, kind: str, country: str, identifier: int | str) -> str:
    """Stable key for a paid unlock (category or keyword niche)."""
    return f"{kind}:{country.lower()}:{identifier}"


def keyword_niche_key(term: str, country: str) -> str:
    """Unlock key for a micro-niche search phrase."""
    safe = term.strip().lower().replace(":", "_")[:80]
    return niche_key(kind="keyword", country=country, identifier=safe)


def monetization_active() -> bool:
    return settings.monetization_enabled


def get_user(user_id: str) -> Optional[User]:
    with session_scope() as session:
        return session.get(User, user_id)


def ensure_user(user_id: str, email: str) -> User:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            user = User(id=user_id, email=email.lower().strip())
            session.add(user)
            if settings.signup_bonus_credits > 0:
                _apply_delta(
                    session,
                    user,
                    settings.signup_bonus_credits,
                    "signup_bonus",
                    reference_id=None,
                )
            session.flush()
            logger.info("Created user %s (%s)", user_id, email)
        elif user.email != email.lower().strip():
            user.email = email.lower().strip()
            user.updated_at = datetime.utcnow()
        return user


def _apply_delta(
    session: Session,
    user: User,
    delta: int,
    reason: str,
    *,
    reference_id: Optional[str],
) -> None:
    user.credits_balance = max(0, user.credits_balance + delta)
    user.updated_at = datetime.utcnow()
    session.add(
        CreditLedger(
            user_id=user.id,
            delta=delta,
            reason=reason,
            reference_id=reference_id,
        )
    )


def grant_credits(
    user_id: str,
    amount: int,
    reason: str,
    *,
    reference_id: Optional[str] = None,
    plan: Optional[str] = None,
) -> User:
    if amount <= 0:
        raise ValueError("grant amount must be positive")
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        _apply_delta(session, user, amount, reason, reference_id=reference_id)
        if plan:
            user.plan = plan
        session.flush()
        return user


def claw_back_credits(
    user_id: str,
    amount: int,
    reason: str,
    *,
    reference_id: Optional[str] = None,
) -> User:
    """Remove up to `amount` credits (e.g. on refund). Does not go below zero."""
    if amount <= 0:
        user = get_user(user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        return user
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        claw = min(amount, user.credits_balance)
        if claw > 0:
            _apply_delta(session, user, -claw, reason, reference_id=reference_id)
        session.flush()
        return user


def set_user_plan(
    user_id: str,
    plan: str,
    *,
    reason: str = "plan_change",
    reference_id: Optional[str] = None,
) -> User:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        if user.plan != plan:
            old_plan = user.plan
            user.plan = plan
            user.updated_at = datetime.utcnow()
            logger.info(
                "User %s plan %s -> %s (%s, ref=%s)",
                user_id,
                old_plan,
                plan,
                reason,
                reference_id,
            )
        session.flush()
        return user


def downgrade_from_pro(
    user_id: str,
    reason: str,
    *,
    reference_id: Optional[str] = None,
) -> User:
    user = get_user(user_id)
    if user is None:
        raise ValueError(f"unknown user {user_id}")
    if user.plan != PRO_PLAN:
        return user
    return set_user_plan(
        user_id,
        FREE_PLAN,
        reason=reason,
        reference_id=reference_id,
    )


def spend_credits(
    user_id: str,
    amount: int,
    reason: str,
    *,
    reference_id: Optional[str] = None,
) -> User:
    if amount <= 0:
        raise ValueError("spend amount must be positive")
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        if user.credits_balance < amount:
            raise ValueError("insufficient credits")
        _apply_delta(session, user, -amount, reason, reference_id=reference_id)
        session.flush()
        return user


def is_niche_unlocked(user_id: Optional[str], key: str) -> bool:
    if not monetization_active():
        return True
    if not user_id:
        return False
    with session_scope() as session:
        hit = session.execute(
            select(UnlockedNiche.id).where(
                UnlockedNiche.user_id == user_id,
                UnlockedNiche.niche_key == key,
            )
        ).scalar_one_or_none()
        return hit is not None


def unlock_niche(user_id: str, key: str, *, cost: int = CREDIT_COST_NICHE_UNLOCK) -> User:
    if is_niche_unlocked(user_id, key):
        user = get_user(user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        return user
    with session_scope() as session:
        existing = session.execute(
            select(UnlockedNiche).where(
                UnlockedNiche.user_id == user_id,
                UnlockedNiche.niche_key == key,
            )
        ).scalar_one_or_none()
        if existing:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError(f"unknown user {user_id}")
            return user

        user = session.get(User, user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        if user.credits_balance < cost:
            raise ValueError("insufficient credits")

        _apply_delta(
            session,
            user,
            -cost,
            "niche_unlock",
            reference_id=key,
        )
        session.add(UnlockedNiche(user_id=user_id, niche_key=key))
        session.flush()
        logger.info("Unlocked %s for user %s", key, user_id)
        return user


def has_pro_access(user_id: Optional[str]) -> bool:
    if not monetization_active():
        return True
    if not user_id:
        return False
    user = get_user(user_id)
    return user is not None and user.plan == PRO_PLAN


def can_export_csv(user_id: Optional[str]) -> bool:
    return has_pro_access(user_id)

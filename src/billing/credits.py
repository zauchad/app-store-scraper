"""Credit balance, niche unlocks, and Pro entitlements."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import CreditLedger, PendingGrant, UnlockedNiche, User
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
            # Column defaults are applied by the INSERT, not by the constructor —
            # set them here so a bonus grant can do arithmetic before the flush.
            user = User(
                id=user_id,
                email=email.lower().strip(),
                plan=FREE_PLAN,
                credits_balance=0,
            )
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
        _claim_pending_grants(session, user)
        session.flush()
        return user


def _claim_pending_grants(session: Session, user: User) -> int:
    """Apply credits bought before this account existed. Returns credits claimed."""
    pending = (
        session.execute(
            select(PendingGrant).where(
                PendingGrant.email == user.email,
                PendingGrant.claimed_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    claimed = 0
    for grant in pending:
        # Claim the row first, conditional on it still being unclaimed: two
        # simultaneous logins must not pay out the same purchase twice.
        won = session.execute(
            update(PendingGrant)
            .where(PendingGrant.id == grant.id, PendingGrant.claimed_at.is_(None))
            .values(claimed_at=datetime.utcnow(), claimed_by=user.id)
        ).rowcount
        if not won:
            continue
        if grant.credits > 0:
            _apply_delta(
                session,
                user,
                grant.credits,
                grant.reason or "pending_grant",
                reference_id=grant.reference_id,
            )
            claimed += grant.credits
        if grant.plan:
            user.plan = grant.plan
        if grant.niche_key:
            # Same economics as paying while logged in: the credit just bought
            # pays for the niche the buyer was looking at.
            try:
                _unlock_in_session(session, user, grant.niche_key)
            except ValueError:
                pass  # not enough credits — user unlocks manually later
        logger.info(
            "Claimed pending grant for %s: %d credits, plan=%s",
            user.email,
            grant.credits,
            grant.plan,
        )
    return claimed


def park_pending_grant(
    email: str,
    *,
    credits: int,
    plan: Optional[str],
    reason: str,
    reference_id: Optional[str],
    niche_key: Optional[str] = None,
) -> None:
    """Store a payment that has no account yet, to be claimed on first login."""
    with session_scope() as session:
        session.add(
            PendingGrant(
                email=email.lower().strip(),
                credits=max(0, credits),
                plan=plan,
                niche_key=niche_key,
                reason=reason[:64],
                reference_id=reference_id,
            )
        )
    logger.info("Parked %d credits for %s (no account yet)", credits, email)


def _apply_delta(
    session: Session,
    user: User,
    delta: int,
    reason: str,
    *,
    reference_id: Optional[str],
) -> None:
    user.credits_balance = max(0, (user.credits_balance or 0) + delta)
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


def _unlock_in_session(
    session: Session,
    user: User,
    key: str,
    *,
    cost: int = CREDIT_COST_NICHE_UNLOCK,
) -> bool:
    """Unlock `key` for `user` inside an open transaction. False = already had it."""
    existing = session.execute(
        select(UnlockedNiche.id).where(
            UnlockedNiche.user_id == user.id,
            UnlockedNiche.niche_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    if cost > 0:
        if user.credits_balance < cost:
            raise ValueError("insufficient credits")
        _apply_delta(session, user, -cost, "niche_unlock", reference_id=key)
    session.add(UnlockedNiche(user_id=user.id, niche_key=key))
    session.flush()
    logger.info("Unlocked %s for user %s (cost %d)", key, user.id, cost)
    return True


def unlock_niche(user_id: str, key: str, *, cost: int = CREDIT_COST_NICHE_UNLOCK) -> User:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise ValueError(f"unknown user {user_id}")
        _unlock_in_session(session, user, key, cost=cost)
        return user


def auto_unlock_after_payment(user_id: str, key: str) -> bool:
    """Spend a credit on the niche the buyer was looking at when they paid.

    Returns True when this call performed the unlock. Silently returns False if
    the niche is already unlocked or the balance is too low — the user simply
    keeps the credit and can unlock manually.
    """
    if not key:
        return False
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            return False
        try:
            return _unlock_in_session(session, user, key)
        except ValueError:
            return False


def has_pro_access(user_id: Optional[str]) -> bool:
    if not monetization_active():
        return True
    if not user_id:
        return False
    user = get_user(user_id)
    return user is not None and user.plan == PRO_PLAN


def can_export_csv(user_id: Optional[str]) -> bool:
    return has_pro_access(user_id)

"""Account data: ledger, unlocks, lookup by email."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from src.db.models import CreditLedger, UnlockedNiche, User
from src.db.session import session_scope


def get_user_by_email(email: str) -> Optional[User]:
    with session_scope() as session:
        return session.execute(
            select(User).where(User.email == email.lower().strip())
        ).scalar_one_or_none()


def list_unlocked_niches(user_id: str, *, limit: int = 50) -> List[UnlockedNiche]:
    with session_scope() as session:
        return list(
            session.execute(
                select(UnlockedNiche)
                .where(UnlockedNiche.user_id == user_id)
                .order_by(UnlockedNiche.unlocked_at.desc())
                .limit(limit)
            ).scalars()
        )


def list_credit_ledger(user_id: str, *, limit: int = 30) -> List[CreditLedger]:
    with session_scope() as session:
        return list(
            session.execute(
                select(CreditLedger)
                .where(CreditLedger.user_id == user_id)
                .order_by(CreditLedger.created_at.desc())
                .limit(limit)
            ).scalars()
        )


def format_niche_key(key: str) -> str:
    """Human-readable label from stored niche_key."""
    parts = key.split(":", 2)
    if len(parts) != 3:
        return key
    kind, country, ident = parts
    if kind == "category":
        return f"Kategoria · {country.upper()} · genre {ident}"
    if kind == "keyword":
        return f"Mikro-nisza · {country.upper()} · «{ident}»"
    return key

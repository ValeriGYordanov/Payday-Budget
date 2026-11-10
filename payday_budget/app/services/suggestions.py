"""Suggestions from history (v1.2 §6, SG1-SG3). SQL over existing transactions; nothing stored."""

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EXPENSE, Budget, Transaction

BUDGET_WINDOW_DAYS = 90  # D15
MAX_DESCRIPTIONS = 5  # D15


def for_category(session: Session, category_id: int, today: dt.date) -> dict[str, Any]:
    since = today - dt.timedelta(days=BUDGET_WINDOW_DAYS)
    # SG1: the budget used most with this category lately; ties go to the most recent use.
    # Archived budgets can't be chosen for a new transaction (B4), so they aren't offered.
    budget = session.execute(
        select(Budget.id, Budget.name)
        .join(Transaction, Transaction.budget_id == Budget.id)
        .where(
            Transaction.category_id == category_id,
            Transaction.kind == EXPENSE,
            Transaction.date >= since,
            Budget.archived.is_(False),
        )
        .group_by(Budget.id, Budget.name)
        .order_by(
            func.count(Transaction.id).desc(),
            func.max(Transaction.date).desc(),
            func.max(Transaction.id).desc(),
        )
        .limit(1)
    ).first()
    # SG2: previous descriptions for this category, most recent first.
    descriptions = list(
        session.scalars(
            select(Transaction.description)
            .where(Transaction.category_id == category_id, Transaction.description.is_not(None))
            .group_by(Transaction.description)
            .order_by(func.max(Transaction.date).desc(), func.max(Transaction.id).desc())
            .limit(MAX_DESCRIPTIONS)
        )
    )
    return {
        "budget_id": budget.id if budget else None,
        "budget_name": budget.name if budget else None,
        "descriptions": descriptions,
    }

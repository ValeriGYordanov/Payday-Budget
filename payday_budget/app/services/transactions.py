"""Transactions (§5.4). Periods are derived from `date`, never stored (P1)."""

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session

from app.errors import InvalidInput, NotFound, RuleViolation
from app.models import INCOME, KINDS, Budget, Category, Transaction, TransactionTag, iso_utc
from app.services import periods, tags
from app.users import Actor

_FIELDS = ("kind", "amount_minor", "category_id", "budget_id", "date", "description", "tags")


@dataclass
class Filters:
    period: str | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    kind: str | None = None
    category: int | None = None
    budget: int | None = None
    tag: int | None = None
    user: str | None = None
    q: str | None = None


def get(session: Session, transaction_id: int) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise NotFound("Transaction")
    return transaction


def check_category(session: Session, category_id: int, kind: str, *, changed: bool) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise NotFound("Category", field="category_id")
    if category.kind != kind:
        raise RuleViolation("T2", f"Category must be an {kind} category", field="category_id")
    if changed and category.archived:
        raise RuleViolation("C2", "Archived categories cannot be chosen", field="category_id")
    return category


def check_budget(
    session: Session, budget_id: int | None, kind: str, *, changed: bool
) -> Budget | None:
    if kind == INCOME:
        if budget_id is not None:
            raise RuleViolation("B6", "Incomes must not have a budget", field="budget_id")
        return None
    if budget_id is None:
        raise RuleViolation("B6", "Expenses require a budget", field="budget_id")
    budget = session.get(Budget, budget_id)
    if budget is None:
        raise NotFound("Budget", field="budget_id")
    if changed and budget.archived:
        raise RuleViolation("B4", "Archived budgets cannot be chosen", field="budget_id")
    return budget


def check_amount(amount: object) -> int:
    """T1: positive integer minor units."""
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise RuleViolation("T1", "amount_minor must be a positive integer", field="amount_minor")
    return amount


def _apply(
    session: Session,
    transaction: Transaction,
    values: dict[str, Any],
    *,
    is_new: bool,
) -> None:
    """Validate the merged state (T1, T2, B4, B6, C2, P6) and write it."""
    for name in ("kind", "amount_minor", "category_id", "date"):
        if values.get(name) is None:
            raise RuleViolation("T2", f"{name} is required", field=name)
    kind = values["kind"]
    if kind not in KINDS:
        raise InvalidInput("kind must be income or expense", field="kind")
    amount = check_amount(values["amount_minor"])

    category = check_category(
        session,
        values["category_id"],
        kind,
        changed=is_new or values["category_id"] != transaction.category_id,
    )
    budget = check_budget(
        session,
        values.get("budget_id"),
        kind,
        changed=is_new or values.get("budget_id") != transaction.budget_id,
    )

    day: dt.date = values["date"]
    earliest = periods.earliest_start(session)
    if earliest is None or day < earliest:
        raise RuleViolation(
            "P6", "Transactions before the first period are not allowed", field="date"
        )

    description = values.get("description")
    if description is not None:
        description = description.strip() or None

    transaction.kind = kind
    transaction.amount_minor = amount
    transaction.category = category
    transaction.budget = budget
    transaction.date = day
    transaction.description = description
    if "tags" in values:
        transaction.tags = tags.by_names(session, values["tags"] or [])


def create(
    session: Session, *, values: dict[str, Any], actor: Actor, today: dt.date
) -> Transaction:
    values = {k: values.get(k) for k in _FIELDS}
    values["date"] = values["date"] or today
    transaction = Transaction(created_by_id=actor.id, created_by_name=actor.name)
    _apply(session, transaction, values, is_new=True)
    session.add(transaction)
    session.flush()
    return transaction


def update(session: Session, transaction: Transaction, *, fields: dict[str, Any]) -> Transaction:
    values: dict[str, Any] = {
        "kind": transaction.kind,
        "amount_minor": transaction.amount_minor,
        "category_id": transaction.category_id,
        "budget_id": transaction.budget_id,
        "date": transaction.date,
        "description": transaction.description,
    }
    values.update({k: v for k, v in fields.items() if k in _FIELDS})
    _apply(session, transaction, values, is_new=False)
    session.flush()
    return transaction


def remove(session: Session, transaction: Transaction) -> None:
    session.delete(transaction)
    session.flush()


def _filtered(session: Session, query: Select[Any], f: Filters, today: dt.date) -> Select[Any]:
    if f.period is not None:
        b = periods.bounds(session, periods.resolve(session, f.period, today))
        query = query.where(Transaction.date >= b.start)
        if b.next_start is not None:
            query = query.where(Transaction.date < b.next_start)
    if f.date_from is not None:
        query = query.where(Transaction.date >= f.date_from)
    if f.date_to is not None:
        query = query.where(Transaction.date <= f.date_to)
    if f.kind is not None:
        query = query.where(Transaction.kind == f.kind)
    if f.category is not None:
        query = query.where(Transaction.category_id == f.category)
    if f.budget is not None:
        query = query.where(Transaction.budget_id == f.budget)
    if f.tag is not None:
        query = query.where(
            exists().where(
                TransactionTag.transaction_id == Transaction.id, TransactionTag.tag_id == f.tag
            )
        )
    if f.user is not None:
        query = query.where(Transaction.created_by_id == f.user)
    if f.q:
        escaped = f.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Transaction.description.ilike(f"%{escaped}%", escape="\\"))
    return query


def listing(
    session: Session, f: Filters, *, limit: int, offset: int, today: dt.date
) -> dict[str, Any]:
    total = session.scalar(_filtered(session, select(func.count(Transaction.id)), f, today)) or 0
    items = session.scalars(
        _filtered(session, select(Transaction), f, today)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).unique()
    all_periods = periods.ordered(session)
    return {
        "items": [serialize(t, periods.period_id_for(all_periods, t.date)) for t in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def serialize(transaction: Transaction, period_id: int | None) -> dict[str, Any]:
    return {
        "id": transaction.id,
        "kind": transaction.kind,
        "amount_minor": transaction.amount_minor,
        "date": transaction.date.isoformat(),
        "period_id": period_id,
        "category_id": transaction.category_id,
        "category_name": transaction.category.name,
        "budget_id": transaction.budget_id,
        "budget_name": transaction.budget.name if transaction.budget else None,
        "description": transaction.description,
        "tags": sorted(t.name for t in transaction.tags),
        "recurring_rule_id": transaction.recurring_rule_id,
        "occurrence_date": transaction.occurrence_date.isoformat()
        if transaction.occurrence_date
        else None,
        "created_by_id": transaction.created_by_id,
        "created_by_name": transaction.created_by_name,
        "created_at": iso_utc(transaction.created_at),
        "updated_at": iso_utc(transaction.updated_at),
    }


def serialize_one(session: Session, transaction: Transaction) -> dict[str, Any]:
    return serialize(transaction, periods.period_id_for(periods.ordered(session), transaction.date))

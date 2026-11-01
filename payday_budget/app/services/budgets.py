"""Budgets (§5.2)."""

import datetime as dt
from typing import Any

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.errors import Conflict, InvalidInput, NotFound, RuleViolation
from app.models import EXPENSE, Budget, PeriodBudget, RecurringRule, Transaction, iso_utc
from app.money import FULL_PERCENT_BP, format_percent, parse_percent
from app.services import periods


def get(session: Session, budget_id: int) -> Budget:
    budget = session.get(Budget, budget_id)
    if budget is None:
        raise NotFound("Budget")
    return budget


def ordered(session: Session) -> list[Budget]:
    return list(session.scalars(select(Budget).order_by(Budget.sort_order, Budget.name)))


def _percent_bp(value: str | int) -> int:
    bp = parse_percent(value)
    if bp is None:
        raise RuleViolation("B1", "percent must be 0-100 with at most 2 decimals", field="percent")
    return bp


def _active_sum_bp(session: Session, exclude_id: int | None = None) -> int:
    query = select(func.coalesce(func.sum(Budget.percent_bp), 0)).where(Budget.archived.is_(False))
    if exclude_id is not None:
        query = query.where(Budget.id != exclude_id)
    return int(session.scalar(query) or 0)


def _check_sum(session: Session, bp: int, exclude_id: int | None = None) -> None:
    """B1: non-archived budgets sum to <= 100 %."""
    if _active_sum_bp(session, exclude_id) + bp > FULL_PERCENT_BP:
        raise RuleViolation("B1", "Budgets would sum to more than 100%", field="percent")


def _clean_name(session: Session, name: str, exclude_id: int | None = None) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise InvalidInput("name must not be empty", field="name")
    query = select(Budget.id).where(Budget.name == cleaned)
    if exclude_id is not None:
        query = query.where(Budget.id != exclude_id)
    if session.scalar(query) is not None:
        raise Conflict("A budget with this name already exists", field="name")
    return cleaned


def _set_current_snapshot(session: Session, budget: Budget, today: dt.date) -> None:
    """B3: the current period's snapshot follows the budget's default."""
    period = periods.current(session, today)
    if period is None:
        return
    row = session.get(PeriodBudget, (period.id, budget.id))
    if row is None:
        session.add(
            PeriodBudget(period_id=period.id, budget_id=budget.id, percent_bp=budget.percent_bp)
        )
    else:
        row.percent_bp = budget.percent_bp


def _drop_from_current_snapshot(session: Session, budget: Budget, today: dt.date) -> None:
    """Archiving removes the budget from the current snapshot unless it has expenses there."""
    period = periods.current(session, today)
    if period is None:
        return
    b = periods.bounds(session, period)
    in_period = [
        Transaction.budget_id == budget.id,
        Transaction.kind == EXPENSE,
        Transaction.date >= b.start,
    ]
    if b.next_start is not None:
        in_period.append(Transaction.date < b.next_start)
    if not session.scalar(select(exists().where(*in_period))):
        session.execute(
            delete(PeriodBudget).where(
                PeriodBudget.period_id == period.id, PeriodBudget.budget_id == budget.id
            )
        )


def create(
    session: Session, *, name: str, percent: str | int, sort_order: int, today: dt.date
) -> Budget:
    bp = _percent_bp(percent)
    _check_sum(session, bp)
    budget = Budget(name=_clean_name(session, name), percent_bp=bp, sort_order=sort_order)
    session.add(budget)
    session.flush()
    _set_current_snapshot(session, budget, today)
    session.flush()
    return budget


def update(session: Session, budget: Budget, *, fields: dict[str, Any], today: dt.date) -> Budget:
    if "name" in fields:
        if fields["name"] is None:
            raise InvalidInput("name must not be empty", field="name")
        budget.name = _clean_name(session, fields["name"], exclude_id=budget.id)
    if fields.get("sort_order") is not None:
        budget.sort_order = fields["sort_order"]

    new_bp = budget.percent_bp
    if fields.get("percent") is not None:
        new_bp = _percent_bp(fields["percent"])
    was_archived = budget.archived
    archived = was_archived if fields.get("archived") is None else bool(fields["archived"])

    if not archived and (new_bp != budget.percent_bp or was_archived):
        _check_sum(session, new_bp, exclude_id=budget.id)
    budget.percent_bp = new_bp
    budget.archived = archived
    session.flush()

    if archived and not was_archived:
        _drop_from_current_snapshot(session, budget, today)
    elif not archived and ("percent" in fields or was_archived):
        _set_current_snapshot(session, budget, today)
    session.flush()
    return budget


def remove(session: Session, budget: Budget) -> None:
    """B4: budgets with transactions can only be archived."""
    if session.scalar(select(exists().where(Transaction.budget_id == budget.id))):
        raise RuleViolation("B4", "Budget has transactions; archive it instead")
    if session.scalar(select(exists().where(RecurringRule.budget_id == budget.id))):
        raise Conflict("Budget is used by a recurring rule")
    session.execute(delete(PeriodBudget).where(PeriodBudget.budget_id == budget.id))
    session.delete(budget)
    session.flush()


def serialize(budget: Budget) -> dict[str, Any]:
    return {
        "id": budget.id,
        "name": budget.name,
        "percent": format_percent(budget.percent_bp),
        "sort_order": budget.sort_order,
        "archived": budget.archived,
        "created_at": iso_utc(budget.created_at),
    }


def serialize_list(session: Session) -> dict[str, Any]:
    allocated = _active_sum_bp(session)
    return {
        "items": [serialize(b) for b in ordered(session)],
        "allocated_percent": format_percent(allocated),
        "unallocated_percent": format_percent(FULL_PERCENT_BP - allocated),
    }

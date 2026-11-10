"""Read models: summary, history, breakdown, daily (§6.4). Aggregation runs in SQL."""

import datetime as dt
import itertools
from typing import Any

from sqlalchemy import ColumnElement, Date, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    EXPENSE,
    INCOME,
    POSITIVE,
    Budget,
    Category,
    Period,
    PeriodBudget,
    Transaction,
)
from app.money import FULL_PERCENT_BP, format_percent, percent_used, round_half_up_div, target_minor
from app.services import periods, settings

DEFAULT_PACE_DAYS = 30
PACE_PERIODS = 3


def _in_range(b: periods.Bounds) -> ColumnElement[bool]:
    condition = Transaction.date >= b.start
    if b.next_start is not None:
        condition = and_(condition, Transaction.date < b.next_start)
    return condition


def budget_status(direction: str, spent: int, target: int) -> str:
    """BD3: negative budgets are `ok` / `over`; positive ones `below` / `met`."""
    if direction == POSITIVE:
        return "met" if spent >= target else "below"
    return "over" if spent > target else "ok"


def _budget_rows(
    session: Session,
    period_ids: list[int],
    income: dict[int, int],
    spent: dict[tuple[int, int], int],
) -> dict[int, list[dict[str, Any]]]:
    """Per period: snapshot budgets (B3) plus budgets with expenses but no snapshot row."""
    snapshot = {
        (r.period_id, r.budget_id): (r.percent_bp, r.direction)
        for r in session.execute(
            select(
                PeriodBudget.period_id,
                PeriodBudget.budget_id,
                PeriodBudget.percent_bp,
                PeriodBudget.direction,
            ).where(PeriodBudget.period_id.in_(period_ids))
        )
    }
    keys = set(snapshot) | set(spent)
    budget_ids = {budget_id for _, budget_id in keys}
    by_id = {b.id: b for b in session.scalars(select(Budget).where(Budget.id.in_(budget_ids)))}
    result: dict[int, list[dict[str, Any]]] = {pid: [] for pid in period_ids}
    for period_id, budget_id in keys:
        budget = by_id[budget_id]
        # No snapshot row (expenses on a budget outside the snapshot): 0 %, current direction.
        bp, direction = snapshot.get((period_id, budget_id), (0, budget.direction))
        target = target_minor(income.get(period_id, 0), bp)  # B2
        used = spent.get((period_id, budget_id), 0)
        status = budget_status(direction, used, target)
        result[period_id].append(
            {
                "budget_id": budget_id,
                "name": budget.name,
                "archived": budget.archived,
                "sort_order": budget.sort_order,
                "percent": format_percent(bp),
                "percent_bp": bp,
                "target_minor": target,
                "spent_minor": used,
                "remaining_minor": target - used,  # B5
                "percent_used": percent_used(used, target),  # B5
                "over_target": used > target,  # BD5: unchanged for every direction
                "direction": direction,
                "status": status,
                "on_track": status in ("ok", "met"),
            }
        )
    for rows in result.values():
        rows.sort(key=lambda r: (r["sort_order"], r["name"]))
    return result


def summary(session: Session, period: Period, today: dt.date) -> dict[str, Any]:
    b = periods.bounds(session, period)
    totals = dict(
        session.execute(
            select(Transaction.kind, func.sum(Transaction.amount_minor))
            .where(_in_range(b))
            .group_by(Transaction.kind)
        ).all()
    )
    income = int(totals.get(INCOME, 0))
    expenses = int(totals.get(EXPENSE, 0))
    spent = {
        (period.id, int(budget_id)): int(amount)
        for budget_id, amount in session.execute(
            select(Transaction.budget_id, func.sum(Transaction.amount_minor))
            .where(_in_range(b), Transaction.kind == EXPENSE)
            .group_by(Transaction.budget_id)
        ).all()
        if budget_id is not None  # B6: always set on expenses
    }
    rows = _budget_rows(session, [period.id], {period.id: income}, spent)[period.id]
    allocated_bp = sum(r["percent_bp"] for r in rows)
    allocated_minor = sum(r["target_minor"] for r in rows)
    current_settings = settings.get(session)
    return {
        "period": periods.serialize(period, b, today),
        **settings.serialize(current_settings),
        "income_minor": income,
        "expenses_minor": expenses,
        "balance_minor": income - expenses,
        "unallocated": {
            "percent": format_percent(FULL_PERCENT_BP - allocated_bp),
            "amount_minor": income - allocated_minor,
        },
        "budgets": [_public(r) for r in rows],
    }


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in ("percent_bp", "sort_order")}


def history(session: Session, limit: int, today: dt.date) -> dict[str, Any]:
    """Last `limit` periods, oldest first."""
    ranked = select(
        Period.id,
        Period.start_date,
        func.lead(Period.start_date, type_=Date)
        .over(order_by=Period.start_date)
        .label("next_start"),
    ).cte("ranked")
    recent = list(
        session.execute(
            select(ranked.c.id, ranked.c.start_date, ranked.c.next_start)
            .order_by(ranked.c.start_date.desc())
            .limit(limit)
        )
    )
    recent.reverse()
    period_ids = [r.id for r in recent]
    in_period = and_(
        Transaction.date >= ranked.c.start_date,
        or_(ranked.c.next_start.is_(None), Transaction.date < ranked.c.next_start),
    )
    aggregates = session.execute(
        select(
            ranked.c.id,
            Transaction.kind,
            Transaction.budget_id,
            func.sum(Transaction.amount_minor),
        )
        .join(ranked, in_period)
        .where(ranked.c.id.in_(period_ids))
        .group_by(ranked.c.id, Transaction.kind, Transaction.budget_id)
    ).all()
    income: dict[int, int] = {}
    expenses: dict[int, int] = {}
    spent: dict[tuple[int, int], int] = {}
    for period_id, kind, budget_id, amount in aggregates:
        if kind == INCOME:
            income[period_id] = income.get(period_id, 0) + int(amount)
        else:
            expenses[period_id] = expenses.get(period_id, 0) + int(amount)
            if budget_id is not None:  # B6: always set on expenses
                spent[(period_id, int(budget_id))] = int(amount)
    budget_rows = _budget_rows(session, period_ids, income, spent)
    by_id = {p.id: p for p in session.scalars(select(Period).where(Period.id.in_(period_ids)))}
    items = []
    for r in recent:
        b = periods.Bounds(r.start_date, r.next_start)
        items.append(
            {
                "period": periods.serialize(by_id[r.id], b, today),
                "income_minor": income.get(r.id, 0),
                "expenses_minor": expenses.get(r.id, 0),
                "budgets": [
                    {
                        "budget_id": row["budget_id"],
                        "name": row["name"],
                        "target_minor": row["target_minor"],
                        "spent_minor": row["spent_minor"],
                        "direction": row["direction"],
                        "status": row["status"],
                    }
                    for row in budget_rows[r.id]
                ],
            }
        )
    return {"items": items}


def breakdown(
    session: Session, period: Period, budget_id: int | None, today: dt.date
) -> dict[str, Any]:
    """Expenses by category for a period, optionally for one budget."""
    b = periods.bounds(session, period)
    query = (
        select(Category.id, Category.name, Category.icon, func.sum(Transaction.amount_minor))
        .join(Category, Category.id == Transaction.category_id)
        .where(_in_range(b), Transaction.kind == EXPENSE)
        .group_by(Category.id, Category.name, Category.icon)
        .order_by(func.sum(Transaction.amount_minor).desc(), Category.name)
    )
    if budget_id is not None:
        query = query.where(Transaction.budget_id == budget_id)
    rows = [
        {"category_id": cid, "name": name, "icon": icon, "amount_minor": int(amount)}
        for cid, name, icon, amount in session.execute(query).all()
    ]
    return {
        "period": periods.serialize(period, b, today),
        "budget_id": budget_id,
        "total_minor": sum(r["amount_minor"] for r in rows),
        "categories": rows,
    }


def _pace_length_days(session: Session, period: Period) -> int:
    """§8: average length of the last 3 periods closed before `period` (fallback 30)."""
    earlier = list(
        session.scalars(
            select(Period.start_date)
            .where(Period.start_date <= period.start_date)
            .order_by(Period.start_date.desc())
            .limit(PACE_PERIODS + 1)
        )
    )
    earlier.reverse()
    lengths = [(later - start).days for start, later in itertools.pairwise(earlier)]
    if not lengths:
        return DEFAULT_PACE_DAYS
    return round_half_up_div(sum(lengths), len(lengths))


def daily(session: Session, period: Period, today: dt.date) -> dict[str, Any]:
    """Expenses per day with a running total, every day from start to end (or today)."""
    b = periods.bounds(session, period)
    per_day = dict(
        session.execute(
            select(Transaction.date, func.sum(Transaction.amount_minor))
            .where(_in_range(b), Transaction.kind == EXPENSE)
            .group_by(Transaction.date)
        ).all()
    )
    last = b.end if b.end is not None else max([today, *per_day.keys()])
    days = []
    cumulative = 0
    day = b.start
    while day <= last:
        spent = int(per_day.get(day, 0))
        cumulative += spent
        days.append({"date": day.isoformat(), "spent_minor": spent, "cumulative_minor": cumulative})
        day += dt.timedelta(days=1)
    return {
        "period": periods.serialize(period, b, today),
        "pace_length_days": _pace_length_days(session, period),
        "days": days,
    }

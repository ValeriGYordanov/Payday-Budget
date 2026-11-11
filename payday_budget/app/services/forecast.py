"""Forecast for the current period (v1.3, F1-F9). Computed on request; nothing is stored.

Money is integer minor units. Each projected amount is one division, rounded half up once.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app import recurrence
from app.errors import NotFound
from app.models import (
    EXPENSE,
    INCOME,
    POSITIVE,
    RECORDED,
    Budget,
    Category,
    Period,
    RecurringRule,
    Reminder,
    ReminderOccurrence,
    Transaction,
)
from app.money import parse_percent, round_half_up_div, target_minor
from app.services import periods, reports, settings

BASIS_PERIODS = 3  # D2, as the pace card


@dataclass
class Item:
    """A known item (F2): expected after today and before the next payday, or already due."""

    date: dt.date
    name: str
    kind: str
    amount_minor: int | None
    budget_id: int | None
    source: str  # "recurring" | "reminder"
    due: bool  # an open reminder occurrence
    estimated: bool = False  # F3: the amount is the reminder's last recorded one


def _expected_payday(session: Session, period: Period, today: dt.date) -> tuple[dt.date, bool]:
    """F1: start + L (the pace card's average length); overdue → tomorrow."""
    expected = period.start_date + dt.timedelta(days=reports.pace_length_days(session, period))
    if expected <= today:
        return today + dt.timedelta(days=1), True
    return expected, False


def _is_flexible() -> Any:
    """Expenses not created by a recurring rule or recorded from a reminder."""
    from_reminder = select(ReminderOccurrence.transaction_id).where(
        ReminderOccurrence.transaction_id.is_not(None)
    )
    return and_(
        Transaction.kind == EXPENSE,
        Transaction.recurring_rule_id.is_(None),
        Transaction.id.not_in(from_reminder),
    )


def _flexible_projection(
    session: Session, period: Period, today: dt.date, days_left: int
) -> tuple[dict[int | None, int], int, int]:
    """F4: per budget, projected flexible spending for `days_left` days.

    Returns ({budget_id: minor}, basis periods, basis days)."""
    closed = list(
        session.scalars(
            select(Period.start_date)
            .where(Period.start_date <= period.start_date)
            .order_by(Period.start_date.desc())
            .limit(BASIS_PERIODS + 1)
        )
    )
    closed.reverse()  # oldest first; the last one is the current period's start
    if len(closed) >= 2:
        start, end, basis_periods = closed[0], closed[-1], len(closed) - 1
    else:
        # P1: no closed period yet: this period's completed days.
        start, end, basis_periods = period.start_date, today, 0
    basis_days = (end - start).days
    if days_left == 0 or basis_days <= 0:
        return {}, basis_periods, max(basis_days, 0)
    totals = session.execute(
        select(Transaction.budget_id, func.sum(Transaction.amount_minor))
        .where(_is_flexible(), Transaction.date >= start, Transaction.date < end)
        .group_by(Transaction.budget_id)
    ).all()
    projection = {
        budget_id: round_half_up_div(int(total) * days_left, basis_days)
        for budget_id, total in totals
    }
    return projection, basis_periods, basis_days


def _last_recorded_amount(session: Session, reminder_id: int) -> int | None:
    """F3: the amount of the last transaction recorded from this reminder."""
    return session.scalar(
        select(Transaction.amount_minor)
        .join(ReminderOccurrence, ReminderOccurrence.transaction_id == Transaction.id)
        .where(ReminderOccurrence.reminder_id == reminder_id, ReminderOccurrence.status == RECORDED)
        .order_by(ReminderOccurrence.due_date.desc(), ReminderOccurrence.id.desc())
        .limit(1)
    )


def _known_items(session: Session, today: dt.date, payday: dt.date) -> list[Item]:
    """F2: recurring occurrences and reminder due dates with today < date < payday, plus
    open reminder occurrences (already due, not yet recorded)."""
    first, last = today + dt.timedelta(days=1), payday - dt.timedelta(days=1)
    items: list[Item] = []
    category_names: dict[int, str] = {
        cid: name for cid, name in session.execute(select(Category.id, Category.name))
    }
    for rule in session.scalars(select(RecurringRule).where(RecurringRule.active.is_(True))):
        end = last if rule.end_date is None else min(last, rule.end_date)
        name = rule.description or category_names.get(rule.category_id, "")
        for day in recurrence.occurrences(
            rule.frequency, rule.interval, rule.anchor_date, first, end
        ):
            items.append(
                Item(day, name, rule.kind, rule.amount_minor, rule.budget_id, "recurring", False)
            )
    reminders = {r.id: r for r in session.scalars(select(Reminder))}
    amounts: dict[int, int | None] = {}

    def amount(reminder: Reminder) -> tuple[int | None, bool]:
        """The reminder's amount, else its last recorded one (estimated)."""
        if reminder.amount_minor is not None:
            return reminder.amount_minor, False
        if reminder.id not in amounts:
            amounts[reminder.id] = _last_recorded_amount(session, reminder.id)
        return amounts[reminder.id], amounts[reminder.id] is not None

    def budget(reminder: Reminder) -> int | None:
        return None if reminder.kind == INCOME else reminder.budget_id

    for occurrence in session.scalars(
        select(ReminderOccurrence).where(ReminderOccurrence.status == "open")
    ):
        reminder = reminders[occurrence.reminder_id]
        value, estimated = amount(reminder)
        items.append(
            Item(
                occurrence.due_date,
                reminder.name,
                reminder.kind,
                value,
                budget(reminder),
                "reminder",
                True,
                estimated,
            )
        )
    for reminder in reminders.values():
        if not reminder.active:
            continue
        end = last if reminder.end_date is None else min(last, reminder.end_date)
        value, estimated = amount(reminder)
        for day in recurrence.occurrences(
            reminder.frequency, reminder.interval, reminder.anchor_date, first, end
        ):
            items.append(
                Item(
                    day,
                    reminder.name,
                    reminder.kind,
                    value,
                    budget(reminder),
                    "reminder",
                    False,
                    estimated,
                )
            )
    items.sort(key=lambda i: (not i.due, i.date, i.name))
    return items


def forecast(session: Session, today: dt.date) -> dict[str, Any]:
    period = periods.current(session, today)
    if period is None:
        raise NotFound("Current period", field="period")
    summary = reports.summary(session, period, today)
    payday, overdue = _expected_payday(session, period, today)
    days_left = (payday - today).days - 1  # F1: days after today and before the payday
    flexible, basis_periods, basis_days = _flexible_projection(session, period, today, days_left)
    items = _known_items(session, today, payday)

    known_income = sum(i.amount_minor or 0 for i in items if i.kind == INCOME)
    known_expenses = sum(i.amount_minor or 0 for i in items if i.kind == EXPENSE)
    flexible_total = sum(flexible.values())
    income_projected = summary["income_minor"] + known_income  # F5
    expenses_projected = summary["expenses_minor"] + known_expenses + flexible_total  # F6

    budgets = []
    still_needed = 0
    for row in summary["budgets"]:
        budget_id = row["budget_id"]
        known = sum(
            i.amount_minor or 0 for i in items if i.kind == EXPENSE and i.budget_id == budget_id
        )
        target = target_minor(income_projected, parse_percent(row["percent"]) or 0)  # F7
        projected_spent = row["spent_minor"] + known + flexible.get(budget_id, 0)
        if row["direction"] == POSITIVE:  # F8: savings are set aside first
            still_needed += max(0, target - row["spent_minor"] - known)
        budgets.append(
            {
                "budget_id": budget_id,
                "name": row["name"],
                "direction": row["direction"],
                "target_minor": target,
                "spent_minor": row["spent_minor"],
                "known_minor": known,
                "flexible_minor": flexible.get(budget_id, 0),
                "projected_spent_minor": projected_spent,
                "projected_status": reports.budget_status(
                    row["direction"], projected_spent, target
                ),
            }
        )
    available = income_projected - summary["expenses_minor"] - known_expenses - still_needed
    budget_names: dict[int, str] = {
        bid: name for bid, name in session.execute(select(Budget.id, Budget.name))
    }
    return {
        "period": summary["period"],
        **settings.serialize(settings.get(session)),
        "expected_payday": payday.isoformat(),
        "overdue": overdue,
        "days_left": days_left,
        "basis": {"periods": basis_periods, "days": basis_days},
        "income": {
            "so_far_minor": summary["income_minor"],
            "known_minor": known_income,
            "projected_minor": income_projected,
        },
        "expenses": {
            "so_far_minor": summary["expenses_minor"],
            "known_minor": known_expenses,
            "flexible_minor": flexible_total,
            "projected_minor": expenses_projected,
        },
        "balance_projected_minor": income_projected - expenses_projected,
        "safe_per_day_minor": round_half_up_div(max(0, available), max(days_left, 1)),  # F8
        "budgets": budgets,
        "upcoming": [  # F9
            {
                "date": i.date.isoformat(),
                "name": i.name,
                "kind": i.kind,
                "amount_minor": i.amount_minor,
                "budget_id": i.budget_id,
                "budget_name": budget_names.get(i.budget_id) if i.budget_id else None,
                "source": i.source,
                "due": i.due,
                "estimated": i.estimated,
            }
            for i in items
        ],
    }

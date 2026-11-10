"""Periods (§5.1). A period's range is always derived from start dates (P1)."""

import bisect
import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.errors import InvalidInput, NotFound, RuleViolation
from app.models import Budget, Period, PeriodBudget, Transaction, iso_utc
from app.money import format_percent
from app.users import Actor

# English month names (P4); `calendar.month_name` is locale-dependent.
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class Bounds:
    """Half-open date range `[start, next_start)`; `next_start` is None for the latest period."""

    start: dt.date
    next_start: dt.date | None

    @property
    def end(self) -> dt.date | None:
        return None if self.next_start is None else self.next_start - dt.timedelta(days=1)


def ordered(session: Session) -> list[Period]:
    return list(session.scalars(select(Period).order_by(Period.start_date)))


def get(session: Session, period_id: int) -> Period:
    period = session.get(Period, period_id)
    if period is None:
        raise NotFound("Period")
    return period


def current(session: Session, today: dt.date) -> Period | None:
    """Period with the greatest start_date <= today."""
    return session.scalars(
        select(Period).where(Period.start_date <= today).order_by(Period.start_date.desc()).limit(1)
    ).first()


def resolve(session: Session, ref: str, today: dt.date) -> Period:
    """`ref` is `current` or a period id."""
    if ref == "current":
        period = current(session, today)
        if period is None:
            raise NotFound("Current period", field="period")
        return period
    if not ref.isdigit():
        raise InvalidInput("period must be 'current' or a period id", field="period")
    return get(session, int(ref))


def bounds(session: Session, period: Period) -> Bounds:
    next_start = session.scalar(
        select(func.min(Period.start_date)).where(Period.start_date > period.start_date)
    )
    return Bounds(period.start_date, next_start)


def period_id_for(periods: list[Period], day: dt.date) -> int | None:
    """P1 lookup in a list of periods ordered by start_date."""
    starts = [p.start_date for p in periods]
    index = bisect.bisect_right(starts, day) - 1
    return periods[index].id if index >= 0 else None


def earliest_start(session: Session) -> dt.date | None:
    return session.scalar(select(func.min(Period.start_date)))


def days_elapsed(b: Bounds, today: dt.date) -> int:
    last = today if b.end is None else min(today, b.end)
    return max((last - b.start).days + 1, 0)


def default_name(session: Session, start_date: dt.date) -> str:
    """P4: `<Month> <YYYY>`, with ` (2)`, ` (3)`... on collision."""
    base = f"{MONTHS[start_date.month - 1]} {start_date.year}"
    taken = set(session.scalars(select(Period.name).where(Period.name.startswith(base))))
    if base not in taken:
        return base
    n = 2
    while f"{base} ({n})" in taken:
        n += 1
    return f"{base} ({n})"


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise InvalidInput("name must not be empty", field="name")
    return cleaned


def _check_start_date(
    session: Session, start_date: dt.date, today: dt.date, exclude_id: int | None = None
) -> None:
    """P2: unique, not in the future."""
    if start_date > today:
        raise RuleViolation("P2", "A period cannot start in the future", field="start_date")
    query = select(Period.id).where(Period.start_date == start_date)
    if exclude_id is not None:
        query = query.where(Period.id != exclude_id)
    if session.scalar(query) is not None:
        raise RuleViolation("P2", "A period already starts on this date", field="start_date")


def _snapshot_source(session: Session, start_date: dt.date) -> list[tuple[int, int, str]]:
    """B3 / BD2: (budget_id, percent_bp, direction) rows for a new period on `start_date`."""
    previous = session.scalars(
        select(Period).where(Period.start_date < start_date).order_by(Period.start_date.desc())
    ).first()
    following = session.scalars(
        select(Period).where(Period.start_date > start_date).order_by(Period.start_date)
    ).first()
    # Inserted between two periods: copy the period it splits. Before the earliest
    # period: copy the earliest period's snapshot. Otherwise: current defaults.
    source = previous if previous is not None and following is not None else following
    if source is not None:
        return [(pb.budget_id, pb.percent_bp, pb.direction) for pb in source.budgets]
    return [
        (b.id, b.percent_bp, b.direction)
        for b in session.scalars(select(Budget).where(Budget.archived.is_(False)))
    ]


def create(
    session: Session,
    *,
    start_date: dt.date | None,
    name: str | None,
    actor: Actor,
    today: dt.date,
) -> Period:
    """P3: periods are only created on request; start defaults to today."""
    start = start_date or today
    _check_start_date(session, start, today)
    period = Period(
        start_date=start,
        name=_clean_name(name) if name is not None else default_name(session, start),
        created_by_id=actor.id,
        created_by_name=actor.name,
    )
    period.budgets = [
        PeriodBudget(budget_id=budget_id, percent_bp=bp, direction=direction)
        for budget_id, bp, direction in _snapshot_source(session, start)
    ]
    session.add(period)
    session.flush()
    return period


def _check_no_orphans(session: Session, earliest: dt.date, code: str) -> None:
    """P6: no transaction may be dated before the earliest period."""
    if session.scalar(select(exists().where(Transaction.date < earliest))):
        raise RuleViolation(code, "Transactions would end up before the first period")


def update(
    session: Session,
    period: Period,
    *,
    fields: dict[str, Any],
    today: dt.date,
) -> Period:
    if "name" in fields:
        if fields["name"] is None:
            raise InvalidInput("name must not be empty", field="name")
        period.name = _clean_name(fields["name"])
    if "start_date" in fields:
        new_start: dt.date | None = fields["start_date"]
        if new_start is None:
            raise InvalidInput("start_date is required", field="start_date")
        if new_start != period.start_date:
            _check_start_date(session, new_start, today, exclude_id=period.id)
            period.start_date = new_start
            session.flush()
            earliest = earliest_start(session)
            assert earliest is not None
            _check_no_orphans(session, earliest, "P6")
    session.flush()
    return period


def remove(session: Session, period: Period) -> None:
    """P5: transactions merge into the previous period (implicit via P1)."""
    others = [p for p in ordered(session) if p.id != period.id]
    if not others:
        raise RuleViolation("P5", "The only period cannot be deleted")
    _check_no_orphans(session, others[0].start_date, "P5")
    session.execute(delete(PeriodBudget).where(PeriodBudget.period_id == period.id))
    session.delete(period)
    session.flush()


def serialize(period: Period, b: Bounds, today: dt.date) -> dict[str, Any]:
    return {
        "id": period.id,
        "name": period.name,
        "start_date": period.start_date.isoformat(),
        "end_date": b.end.isoformat() if b.end else None,
        "is_current": b.start <= today and (b.next_start is None or today < b.next_start),
        "days_elapsed": days_elapsed(b, today),
        "created_by_id": period.created_by_id,
        "created_by_name": period.created_by_name,
        "created_at": iso_utc(period.created_at),
    }


def serialize_all(session: Session, today: dt.date) -> list[dict[str, Any]]:
    periods = ordered(session)
    result = []
    for i, period in enumerate(periods):
        next_start = periods[i + 1].start_date if i + 1 < len(periods) else None
        result.append(serialize(period, Bounds(period.start_date, next_start), today))
    result.reverse()
    return result


def serialize_detail(session: Session, period: Period, today: dt.date) -> dict[str, Any]:
    data = serialize(period, bounds(session, period), today)
    rows = session.execute(
        select(
            PeriodBudget.budget_id,
            PeriodBudget.percent_bp,
            PeriodBudget.direction,
            Budget.name,
            Budget.archived,
        )
        .join(Budget, Budget.id == PeriodBudget.budget_id)
        .where(PeriodBudget.period_id == period.id)
        .order_by(Budget.sort_order, Budget.name)
    )
    data["budgets"] = [
        {
            "budget_id": r.budget_id,
            "name": r.name,
            "archived": r.archived,
            "percent": format_percent(r.percent_bp),
            "direction": r.direction,  # BD2: snapshot
        }
        for r in rows
    ]
    return data

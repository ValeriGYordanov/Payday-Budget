"""Reminders (v1.2 §4): repeat like recurring rules (R1) but never create a transaction.

Each due date opens an occurrence; the user records a transaction from the pre-filled
data, or dismisses it. The pre-fill always comes from the reminder as it is now (§10).
"""

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app import recurrence
from app.errors import InvalidInput, NotFound, RuleViolation
from app.models import (
    DISMISSED,
    INCOME,
    KINDS,
    NAME_MAX,
    OPEN,
    RECORDED,
    Budget,
    Category,
    Reminder,
    ReminderOccurrence,
    Tag,
    iso_utc,
    utcnow,
)
from app.services import periods, tags, transactions
from app.users import Actor

STATUSES = (OPEN, RECORDED, DISMISSED)

_FIELDS = (
    "name",
    "kind",
    "amount_minor",
    "category_id",
    "budget_id",
    "description",
    "tags",
    "frequency",
    "interval",
    "anchor_date",
    "end_date",
    "active",
)


def get(session: Session, reminder_id: int) -> Reminder:
    reminder = session.get(Reminder, reminder_id)
    if reminder is None:
        raise NotFound("Reminder")
    return reminder


def listing(session: Session) -> list[Reminder]:
    return list(session.scalars(select(Reminder).order_by(Reminder.name, Reminder.id)))


def _apply(session: Session, reminder: Reminder, values: dict[str, Any], *, is_new: bool) -> None:
    """Validate the merged state and write it. Pre-filled fields are all optional (RM3)."""
    name = (values.get("name") or "").strip()
    if not name:
        raise RuleViolation("RM3", "name is required", field="name")
    if len(name) > NAME_MAX:
        raise InvalidInput(f"name must be at most {NAME_MAX} characters", field="name")
    kind = values.get("kind")
    if kind is None:
        raise RuleViolation("RM3", "kind is required", field="kind")
    if kind not in KINDS:
        raise InvalidInput("kind must be income or expense", field="kind")

    amount = values.get("amount_minor")
    if amount is not None:
        amount = transactions.check_amount(amount)
    category_id = values.get("category_id")
    if category_id is not None:
        transactions.check_category(
            session, category_id, kind, changed=is_new or category_id != reminder.category_id
        )
    budget_id = values.get("budget_id")
    if budget_id is not None:
        if kind == INCOME:
            raise RuleViolation("B6", "Incomes must not have a budget", field="budget_id")
        transactions.check_budget(
            session, budget_id, kind, changed=is_new or budget_id != reminder.budget_id
        )

    # RM1: the schedule follows R1.
    frequency = values.get("frequency")
    if frequency is None or values.get("anchor_date") is None:
        field = "frequency" if frequency is None else "anchor_date"
        raise RuleViolation("RM1", f"{field} is required", field=field)
    if frequency not in recurrence.FREQUENCIES:
        raise RuleViolation("RM1", "frequency must be weekly, monthly or yearly", field="frequency")
    interval = values.get("interval")
    interval = 1 if interval is None else interval
    if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
        raise RuleViolation("RM1", "interval must be an integer >= 1", field="interval")
    anchor: dt.date = values["anchor_date"]
    end: dt.date | None = values.get("end_date")
    if end is not None and end < anchor:
        raise RuleViolation("RM1", "end_date must not be before anchor_date", field="end_date")

    description = values.get("description")
    if description is not None:
        description = description.strip() or None

    reminder.name = name
    reminder.kind = kind
    reminder.amount_minor = amount
    reminder.category_id = category_id
    reminder.budget_id = budget_id
    reminder.description = description
    reminder.frequency = frequency
    reminder.interval = interval
    reminder.anchor_date = anchor
    reminder.end_date = end
    if "tags" in values:
        reminder.tag_ids = [t.id for t in tags.by_names(session, values["tags"] or [])]
    active = values.get("active")
    reminder.active = True if active is None else bool(active)


def create(session: Session, *, values: dict[str, Any], today: dt.date) -> Reminder:
    reminder = Reminder(tag_ids=[])
    _apply(session, reminder, {k: values.get(k) for k in _FIELDS}, is_new=True)
    session.add(reminder)
    session.flush()
    open_due(session, reminder, today, latest_only=True)  # D11
    return reminder


def update(
    session: Session, reminder: Reminder, *, fields: dict[str, Any], today: dt.date
) -> Reminder:
    """RM5: schedule changes apply to due dates from now on; open occurrences stay."""
    was_active = reminder.active
    values: dict[str, Any] = {
        "name": reminder.name,
        "kind": reminder.kind,
        "amount_minor": reminder.amount_minor,
        "category_id": reminder.category_id,
        "budget_id": reminder.budget_id,
        "description": reminder.description,
        "frequency": reminder.frequency,
        "interval": reminder.interval,
        "anchor_date": reminder.anchor_date,
        "end_date": reminder.end_date,
        "active": reminder.active,
    }
    values.update({k: v for k, v in fields.items() if k in _FIELDS})
    if values["kind"] == INCOME and "budget_id" not in fields:
        values["budget_id"] = None  # B6: switching to income drops the budget
    _apply(session, reminder, values, is_new=False)
    if reminder.active and not was_active:
        # Resuming does not open the paused time (as with recurring rules).
        yesterday = today - dt.timedelta(days=1)
        if reminder.last_opened_date is None or reminder.last_opened_date < yesterday:
            reminder.last_opened_date = yesterday
    session.flush()
    open_due(session, reminder, today)
    return reminder


def remove(session: Session, reminder: Reminder) -> None:
    """RM5: its occurrences go too (FK cascade); recorded transactions stay."""
    session.delete(reminder)
    session.flush()
    session.expire_all()


def open_due(
    session: Session, reminder: Reminder, today: dt.date, *, latest_only: bool = False
) -> int:
    """RM2: open an occurrence for each due date from `last_opened_date + 1` (or the
    anchor) to today. Idempotent via UNIQUE (reminder_id, due_date). Returns the count.

    `latest_only` (a new reminder, D11): only the latest of those dates. Dates before the
    first period are skipped (D12): they could only be ignored (P6).
    """
    if not reminder.active:
        return 0
    start = (
        reminder.last_opened_date + dt.timedelta(days=1)
        if reminder.last_opened_date is not None
        else reminder.anchor_date
    )
    last = today if reminder.end_date is None else min(today, reminder.end_date)
    opened = 0
    if start <= last:
        earliest = periods.earliest_start(session)
        days = [
            day
            for day in recurrence.occurrences(
                reminder.frequency, reminder.interval, reminder.anchor_date, start, last
            )
            if earliest is not None and day >= earliest
        ]
        for day in days[-1:] if latest_only else days:
            statement = (
                sqlite_insert(ReminderOccurrence)
                .values(reminder_id=reminder.id, due_date=day, status=OPEN)
                .on_conflict_do_nothing(index_elements=["reminder_id", "due_date"])
                .returning(ReminderOccurrence.id)
            )
            if session.scalar(statement) is not None:
                opened += 1
    if reminder.last_opened_date is None or reminder.last_opened_date < today:
        reminder.last_opened_date = today
    session.flush()
    return opened


def open_all(session: Session, today: dt.date) -> int:
    opened = 0
    for reminder in session.scalars(select(Reminder).where(Reminder.active.is_(True))):
        opened += open_due(session, reminder, today)
    return opened


# --- occurrences --------------------------------------------------------------


def get_occurrence(session: Session, occurrence_id: int) -> ReminderOccurrence:
    occurrence = session.get(ReminderOccurrence, occurrence_id)
    if occurrence is None:
        raise NotFound("Reminder occurrence")
    return occurrence


def occurrences(session: Session, status: str | None) -> list[ReminderOccurrence]:
    query = select(ReminderOccurrence).order_by(ReminderOccurrence.due_date, ReminderOccurrence.id)
    if status is not None:
        if status not in STATUSES:
            raise InvalidInput("status must be open, recorded or dismissed", field="status")
        query = query.where(ReminderOccurrence.status == status)
    return list(session.scalars(query))


def prefill(session: Session, reminder: Reminder, due_date: dt.date) -> dict[str, Any]:
    """Transaction fields from the reminder as it is now. RM6: archived categories and
    budgets are left out (they can't be chosen for a new transaction)."""
    category = (
        session.get(Category, reminder.category_id) if reminder.category_id is not None else None
    )
    budget = session.get(Budget, reminder.budget_id) if reminder.budget_id is not None else None
    if category is not None and (category.archived or category.kind != reminder.kind):
        category = None
    if budget is not None and (budget.archived or reminder.kind == INCOME):
        budget = None
    tag_names = sorted(session.scalars(select(Tag.name).where(Tag.id.in_(reminder.tag_ids or []))))
    return {
        "kind": reminder.kind,
        "amount_minor": reminder.amount_minor,
        "category_id": category.id if category else None,
        "category_name": category.name if category else None,
        "budget_id": budget.id if budget else None,
        "budget_name": budget.name if budget else None,
        "date": due_date.isoformat(),
        "description": reminder.description,
        "tags": tag_names,
    }


def _check_open(occurrence: ReminderOccurrence) -> None:
    if occurrence.status != OPEN:
        raise RuleViolation("RM4", f"This reminder was already {occurrence.status}")


def record(
    session: Session,
    occurrence: ReminderOccurrence,
    *,
    fields: dict[str, Any],
    actor: Actor,
    today: dt.date,
) -> int:
    """RM3: record a transaction (T1-T4 apply); fields not given come from the pre-fill.
    Returns the new transaction id."""
    _check_open(occurrence)
    reminder = get(session, occurrence.reminder_id)
    base = prefill(session, reminder, occurrence.due_date)
    values = {
        "kind": base["kind"],
        "amount_minor": base["amount_minor"],
        "category_id": base["category_id"],
        "budget_id": base["budget_id"],
        "date": occurrence.due_date,
        "description": base["description"],
        "tags": base["tags"],
    }
    values.update(fields)
    transaction = transactions.create(session, values=values, actor=actor, today=today)
    occurrence.status = RECORDED
    occurrence.transaction_id = transaction.id
    occurrence.closed_at = utcnow()
    session.flush()
    return transaction.id


def dismiss(session: Session, occurrence: ReminderOccurrence) -> ReminderOccurrence:
    """RM4: ignored; never reopens."""
    _check_open(occurrence)
    occurrence.status = DISMISSED
    occurrence.closed_at = utcnow()
    session.flush()
    return occurrence


def mark_notified(session: Session, occurrence: ReminderOccurrence) -> ReminderOccurrence:
    """RM7: the integration has notified this occurrence (once)."""
    if occurrence.notified_at is None:
        occurrence.notified_at = utcnow()
        session.flush()
    return occurrence


# --- serialization ------------------------------------------------------------


def serialize(session: Session, reminder: Reminder) -> dict[str, Any]:
    category = (
        session.get(Category, reminder.category_id) if reminder.category_id is not None else None
    )
    budget = session.get(Budget, reminder.budget_id) if reminder.budget_id is not None else None
    tag_names = sorted(session.scalars(select(Tag.name).where(Tag.id.in_(reminder.tag_ids or []))))
    return {
        "id": reminder.id,
        "name": reminder.name,
        "kind": reminder.kind,
        "amount_minor": reminder.amount_minor,
        "category_id": reminder.category_id,
        "category_name": category.name if category else None,
        "budget_id": reminder.budget_id,
        "budget_name": budget.name if budget else None,
        "description": reminder.description,
        "tags": tag_names,
        "frequency": reminder.frequency,
        "interval": reminder.interval,
        "anchor_date": reminder.anchor_date.isoformat(),
        "end_date": reminder.end_date.isoformat() if reminder.end_date else None,
        "active": reminder.active,
        "last_opened_date": reminder.last_opened_date.isoformat()
        if reminder.last_opened_date
        else None,
    }


def serialize_occurrence(session: Session, occurrence: ReminderOccurrence) -> dict[str, Any]:
    reminder = get(session, occurrence.reminder_id)
    return {
        "id": occurrence.id,
        "reminder_id": reminder.id,
        "name": reminder.name,
        "due_date": occurrence.due_date.isoformat(),
        "status": occurrence.status,
        "transaction_id": occurrence.transaction_id,
        "notified_at": iso_utc(occurrence.notified_at) if occurrence.notified_at else None,
        "closed_at": iso_utc(occurrence.closed_at) if occurrence.closed_at else None,
        "prefill": prefill(session, reminder, occurrence.due_date),
    }

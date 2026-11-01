"""Recurring rules and transaction generation (§5.5)."""

import datetime as dt
import logging
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app import recurrence
from app.errors import ApiError, InvalidInput, NotFound, RuleViolation
from app.models import KINDS, Budget, Category, RecurringRule, Tag, Transaction, TransactionTag
from app.services import periods, tags, transactions

_LOGGER = logging.getLogger(__name__)

_FIELDS = (
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


def get(session: Session, rule_id: int) -> RecurringRule:
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise NotFound("Recurring rule")
    return rule


def listing(session: Session) -> list[RecurringRule]:
    return list(session.scalars(select(RecurringRule).order_by(RecurringRule.id)))


def _apply(session: Session, rule: RecurringRule, values: dict[str, Any], *, is_new: bool) -> None:
    """Validate the merged state (T1, T2, B4, B6, C2, R1) and write it."""
    for name in ("kind", "amount_minor", "category_id"):
        if values.get(name) is None:
            raise RuleViolation("T2", f"{name} is required", field=name)
    for name in ("frequency", "anchor_date"):
        if values.get(name) is None:
            raise RuleViolation("R1", f"{name} is required", field=name)
    kind = values["kind"]
    if kind not in KINDS:
        raise InvalidInput("kind must be income or expense", field="kind")
    amount = transactions.check_amount(values["amount_minor"])
    category = transactions.check_category(
        session,
        values["category_id"],
        kind,
        changed=is_new or values["category_id"] != rule.category_id,
    )
    budget = transactions.check_budget(
        session,
        values.get("budget_id"),
        kind,
        changed=is_new or values.get("budget_id") != rule.budget_id,
    )

    frequency = values["frequency"]
    if frequency not in recurrence.FREQUENCIES:
        raise RuleViolation("R1", "frequency must be weekly, monthly or yearly", field="frequency")
    interval = values.get("interval")
    interval = 1 if interval is None else interval
    if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
        raise RuleViolation("R1", "interval must be an integer >= 1", field="interval")
    anchor: dt.date = values["anchor_date"]
    end: dt.date | None = values.get("end_date")
    if end is not None and end < anchor:
        raise RuleViolation("R1", "end_date must not be before anchor_date", field="end_date")

    description = values.get("description")
    if description is not None:
        description = description.strip() or None

    rule.kind = kind
    rule.amount_minor = amount
    rule.category_id = category.id
    rule.budget_id = budget.id if budget else None
    rule.description = description
    rule.frequency = frequency
    rule.interval = interval
    rule.anchor_date = anchor
    rule.end_date = end
    if "tags" in values:
        rule.tag_ids = [t.id for t in tags.by_names(session, values["tags"] or [])]
    active = values.get("active")
    rule.active = True if active is None else bool(active)


def create(session: Session, *, values: dict[str, Any], today: dt.date) -> RecurringRule:
    rule = RecurringRule(tag_ids=[])
    _apply(session, rule, {k: values.get(k) for k in _FIELDS}, is_new=True)
    session.add(rule)
    session.flush()
    generate(session, rule, today)
    return rule


def update(
    session: Session, rule: RecurringRule, *, fields: dict[str, Any], today: dt.date
) -> RecurringRule:
    """R3: already generated transactions are not changed."""
    was_active = rule.active
    values: dict[str, Any] = {
        "kind": rule.kind,
        "amount_minor": rule.amount_minor,
        "category_id": rule.category_id,
        "budget_id": rule.budget_id,
        "description": rule.description,
        "frequency": rule.frequency,
        "interval": rule.interval,
        "anchor_date": rule.anchor_date,
        "end_date": rule.end_date,
        "active": rule.active,
    }
    values.update({k: v for k, v in fields.items() if k in _FIELDS})
    _apply(session, rule, values, is_new=False)
    if rule.active and not was_active:
        # Resuming does not backfill the paused time.
        yesterday = today - dt.timedelta(days=1)
        if rule.last_generated_date is None or rule.last_generated_date < yesterday:
            rule.last_generated_date = yesterday
    session.flush()
    generate(session, rule, today)
    return rule


def remove(session: Session, rule: RecurringRule) -> None:
    """Generated transactions are kept; their `recurring_rule_id` becomes NULL (FK)."""
    session.delete(rule)
    session.flush()
    session.expire_all()


def _skip_reason(session: Session, rule: RecurringRule) -> str | None:
    try:
        transactions.check_category(session, rule.category_id, rule.kind, changed=True)
        transactions.check_budget(session, rule.budget_id, rule.kind, changed=True)
    except ApiError as err:
        return f"{err.code}: {err.message}"
    return None


def generate(session: Session, rule: RecurringRule, today: dt.date) -> int:
    """R2: generate occurrences from `last_generated_date + 1` (or the anchor) to today.

    Idempotent via UNIQUE (recurring_rule_id, occurrence_date). Returns the number created.
    """
    if not rule.active:
        return 0
    start = (
        rule.last_generated_date + dt.timedelta(days=1)
        if rule.last_generated_date is not None
        else rule.anchor_date
    )
    last = today if rule.end_date is None else min(today, rule.end_date)  # R4
    created = 0
    if start <= last:
        earliest = periods.earliest_start(session)
        skip_reason = _skip_reason(session, rule)
        tag_ids = list(
            session.scalars(select(Tag.id).where(Tag.id.in_(rule.tag_ids or [])).order_by(Tag.id))
        )
        for day in recurrence.occurrences(
            rule.frequency, rule.interval, rule.anchor_date, start, last
        ):
            if earliest is None or day < earliest:
                _LOGGER.warning(
                    "Recurring rule %s: skipped %s, before the first period (R5)", rule.id, day
                )
                continue
            if skip_reason is not None:
                _LOGGER.warning("Recurring rule %s: skipped %s (%s)", rule.id, day, skip_reason)
                continue
            if _insert_occurrence(session, rule, day, tag_ids):
                created += 1
    if rule.last_generated_date is None or rule.last_generated_date < today:
        rule.last_generated_date = today
    session.flush()
    return created


def _insert_occurrence(
    session: Session, rule: RecurringRule, day: dt.date, tag_ids: list[int]
) -> bool:
    statement = (
        sqlite_insert(Transaction)
        .values(
            kind=rule.kind,
            amount_minor=rule.amount_minor,
            date=day,
            category_id=rule.category_id,
            budget_id=rule.budget_id,
            description=rule.description,
            recurring_rule_id=rule.id,
            occurrence_date=day,
        )
        .on_conflict_do_nothing(index_elements=["recurring_rule_id", "occurrence_date"])
        .returning(Transaction.id)
    )
    transaction_id = session.scalar(statement)
    if transaction_id is None:
        return False
    if tag_ids:
        session.execute(
            insert(TransactionTag),
            [{"transaction_id": transaction_id, "tag_id": tag_id} for tag_id in tag_ids],
        )
    return True


def generate_all(session: Session, today: dt.date) -> int:
    created = 0
    for rule in session.scalars(select(RecurringRule).where(RecurringRule.active.is_(True))):
        created += generate(session, rule, today)
    return created


def serialize(session: Session, rule: RecurringRule) -> dict[str, Any]:
    category = session.get(Category, rule.category_id)
    budget = session.get(Budget, rule.budget_id) if rule.budget_id is not None else None
    tag_names = sorted(session.scalars(select(Tag.name).where(Tag.id.in_(rule.tag_ids or []))))
    return {
        "id": rule.id,
        "kind": rule.kind,
        "amount_minor": rule.amount_minor,
        "category_id": rule.category_id,
        "category_name": category.name if category else None,
        "budget_id": rule.budget_id,
        "budget_name": budget.name if budget else None,
        "description": rule.description,
        "tags": tag_names,
        "frequency": rule.frequency,
        "interval": rule.interval,
        "anchor_date": rule.anchor_date.isoformat(),
        "end_date": rule.end_date.isoformat() if rule.end_date else None,
        "active": rule.active,
        "last_generated_date": rule.last_generated_date.isoformat()
        if rule.last_generated_date
        else None,
    }

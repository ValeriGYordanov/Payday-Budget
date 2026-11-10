"""SQLAlchemy models (§4).

Money is integer minor units. Percents are integer hundredths (`*_bp`).
A transaction never stores its period (P1); periods are derived from dates.
"""

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

INCOME = "income"
EXPENSE = "expense"
KINDS = (INCOME, EXPENSE)

# v1.2 BD1: negative = spend at most the target; positive = reach at least the target.
NEGATIVE = "negative"
POSITIVE = "positive"
DIRECTIONS = (NEGATIVE, POSITIVE)

OPEN = "open"
RECORDED = "recorded"
DISMISSED = "dismissed"

DESCRIPTION_MAX = 500
NAME_MAX = 100


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def iso_utc(value: dt.datetime) -> str:
    """ISO 8601 with offset; SQLite returns stored UTC timestamps as naive."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.isoformat()


class Base(DeclarativeBase):
    pass


class Settings(Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False)


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_date: Mapped[dt.date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    created_by_id: Mapped[str | None] = mapped_column(String(64))
    created_by_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    budgets: Mapped[list["PeriodBudget"]] = relationship(
        back_populates="period", cascade="all, delete-orphan"
    )


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("percent_bp BETWEEN 0 AND 10000", name="percent_range"),
        CheckConstraint("direction IN ('negative', 'positive')", name="direction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX), unique=True)
    percent_bp: Mapped[int] = mapped_column(Integer)
    direction: Mapped[str] = mapped_column(String(8), default=NEGATIVE, server_default=NEGATIVE)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PeriodBudget(Base):
    __tablename__ = "period_budgets"
    __table_args__ = (
        CheckConstraint("percent_bp BETWEEN 0 AND 10000", name="percent_range"),
        CheckConstraint("direction IN ('negative', 'positive')", name="direction"),
    )

    period_id: Mapped[int] = mapped_column(
        ForeignKey("periods.id", ondelete="CASCADE"), primary_key=True
    )
    budget_id: Mapped[int] = mapped_column(
        ForeignKey("budgets.id", ondelete="CASCADE"), primary_key=True
    )
    percent_bp: Mapped[int] = mapped_column(Integer)
    direction: Mapped[str] = mapped_column(String(8), default=NEGATIVE, server_default=NEGATIVE)

    period: Mapped[Period] = relationship(back_populates="budgets")
    budget: Mapped[Budget] = relationship()


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("name", "kind"),
        CheckConstraint("kind IN ('income', 'expense')", name="kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    kind: Mapped[str] = mapped_column(String(7))
    icon: Mapped[str] = mapped_column(String(64))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX), unique=True)


class TransactionTag(Base):
    __tablename__ = "transaction_tags"

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class RecurringRule(Base):
    __tablename__ = "recurring_rules"
    __table_args__ = (
        CheckConstraint("kind IN ('income', 'expense')", name="kind"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint("frequency IN ('weekly', 'monthly', 'yearly')", name="frequency"),
        CheckConstraint('"interval" >= 1', name="interval_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(7))
    amount_minor: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    budget_id: Mapped[int | None] = mapped_column(ForeignKey("budgets.id"))
    description: Mapped[str | None] = mapped_column(String(DESCRIPTION_MAX))
    tag_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    frequency: Mapped[str] = mapped_column(String(7))
    interval: Mapped[int] = mapped_column(Integer, default=1)
    anchor_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_generated_date: Mapped[dt.date | None] = mapped_column(Date)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("kind IN ('income', 'expense')", name="kind"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_budget_id_date", "budget_id", "date"),
        Index("ix_transactions_category_id_date", "category_id", "date"),
        Index(
            "ux_transactions_recurring_occurrence",
            "recurring_rule_id",
            "occurrence_date",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(7))
    amount_minor: Mapped[int] = mapped_column(Integer)
    date: Mapped[dt.date] = mapped_column(Date)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    budget_id: Mapped[int | None] = mapped_column(ForeignKey("budgets.id"))
    description: Mapped[str | None] = mapped_column(String(DESCRIPTION_MAX))
    recurring_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_rules.id", ondelete="SET NULL")
    )
    occurrence_date: Mapped[dt.date | None] = mapped_column(Date)
    created_by_id: Mapped[str | None] = mapped_column(String(64))
    created_by_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    category: Mapped[Category] = relationship(lazy="joined")
    budget: Mapped[Budget | None] = relationship(lazy="joined")
    tags: Mapped[list[Tag]] = relationship(
        secondary="transaction_tags", lazy="selectin", order_by=Tag.name
    )


class Reminder(Base):
    """v1.2 §4: repeats like a recurring rule (R1) but never creates a transaction."""

    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint("kind IN ('income', 'expense')", name="kind"),
        CheckConstraint("amount_minor IS NULL OR amount_minor > 0", name="amount_positive"),
        CheckConstraint("frequency IN ('weekly', 'monthly', 'yearly')", name="frequency"),
        CheckConstraint('"interval" >= 1', name="interval_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    kind: Mapped[str] = mapped_column(String(7))
    amount_minor: Mapped[int | None] = mapped_column(Integer)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    budget_id: Mapped[int | None] = mapped_column(ForeignKey("budgets.id"))
    description: Mapped[str | None] = mapped_column(String(DESCRIPTION_MAX))
    tag_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    frequency: Mapped[str] = mapped_column(String(7))
    interval: Mapped[int] = mapped_column(Integer, default=1)
    anchor_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_opened_date: Mapped[dt.date | None] = mapped_column(Date)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReminderOccurrence(Base):
    __tablename__ = "reminder_occurrences"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'recorded', 'dismissed')", name="status"),
        UniqueConstraint("reminder_id", "due_date", name="ux_reminder_occurrences_due"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reminder_id: Mapped[int] = mapped_column(ForeignKey("reminders.id", ondelete="CASCADE"))
    due_date: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(9), default=OPEN)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    notified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

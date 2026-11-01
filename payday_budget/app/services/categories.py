"""Categories (§5.3)."""

import re
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.errors import Conflict, InvalidInput, NotFound, RuleViolation
from app.models import EXPENSE, INCOME, Category, RecurringRule, Transaction

DEFAULT_ICON = "mdi:tag"
_ICON_RE = re.compile(r"^mdi:[a-z0-9]+(-[a-z0-9]+)*$")

# C3 first-run seed: (name, kind, icon).
SEED = (
    ("Salary", INCOME, "mdi:cash"),
    ("Other income", INCOME, "mdi:cash-plus"),
    ("Housing", EXPENSE, "mdi:home"),
    ("Food", EXPENSE, "mdi:food"),
    ("Transport", EXPENSE, "mdi:car"),
    ("Health", EXPENSE, "mdi:medical-bag"),
    ("Utilities", EXPENSE, "mdi:flash"),
    ("Entertainment", EXPENSE, "mdi:movie-open"),
    ("Shopping", EXPENSE, "mdi:shopping"),
    ("Savings transfer", EXPENSE, "mdi:piggy-bank"),
    ("Other", EXPENSE, "mdi:dots-horizontal"),
)


def get(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise NotFound("Category")
    return category


def _has_transactions(session: Session, category: Category) -> bool:
    return bool(session.scalar(select(exists().where(Transaction.category_id == category.id))))


def _clean_name(session: Session, name: str, kind: str, exclude_id: int | None = None) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise InvalidInput("name must not be empty", field="name")
    query = select(Category.id).where(Category.name == cleaned, Category.kind == kind)
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    if session.scalar(query) is not None:
        raise Conflict("A category with this name and kind already exists", field="name")
    return cleaned


def _check_icon(icon: str) -> str:
    if not _ICON_RE.match(icon):
        raise InvalidInput("icon must be an mdi:* icon name", field="icon")
    return icon


def seed(session: Session) -> None:
    """C3: insert the default categories that don't exist yet."""
    existing = set(session.execute(select(Category.name, Category.kind)).all())
    for name, kind, icon in SEED:
        if (name, kind) not in existing:
            session.add(Category(name=name, kind=kind, icon=icon))
    session.flush()


def listing(session: Session, kind: str | None, archived: bool | None) -> list[Category]:
    query = select(Category).order_by(Category.kind, Category.name)
    if kind is not None:
        query = query.where(Category.kind == kind)
    if archived is not None:
        query = query.where(Category.archived.is_(archived))
    return list(session.scalars(query))


def create(session: Session, *, name: str, kind: str, icon: str) -> Category:
    category = Category(name=_clean_name(session, name, kind), kind=kind, icon=_check_icon(icon))
    session.add(category)
    session.flush()
    return category


def update(session: Session, category: Category, *, fields: dict[str, Any]) -> Category:
    kind = category.kind
    if fields.get("kind") is not None and fields["kind"] != category.kind:
        # C1 / T2: a transaction's category must have the transaction's kind.
        if _has_transactions(session, category):
            raise RuleViolation(
                "C1", "Category has transactions; its kind cannot change", field="kind"
            )
        kind = fields["kind"]
    name = category.name
    if "name" in fields:
        if fields["name"] is None:
            raise InvalidInput("name must not be empty", field="name")
        name = fields["name"]
    if (name, kind) != (category.name, category.kind):
        category.name = _clean_name(session, name, kind, exclude_id=category.id)
        category.kind = kind
    if fields.get("icon") is not None:
        category.icon = _check_icon(fields["icon"])
    if fields.get("archived") is not None:
        category.archived = bool(fields["archived"])
    session.flush()
    return category


def remove(session: Session, category: Category) -> None:
    """C2: categories with transactions can only be archived."""
    if _has_transactions(session, category):
        raise RuleViolation("C2", "Category has transactions; archive it instead")
    if session.scalar(select(exists().where(RecurringRule.category_id == category.id))):
        raise Conflict("Category is used by a recurring rule")
    session.delete(category)
    session.flush()


def serialize(category: Category) -> dict[str, Any]:
    return {
        "id": category.id,
        "name": category.name,
        "kind": category.kind,
        "icon": category.icon,
        "archived": category.archived,
    }

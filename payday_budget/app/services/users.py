"""Known HA users, derived from `created_by` on transactions and periods (T3)."""

from typing import Any

from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app.models import Period, Transaction


def listing(session: Session) -> list[dict[str, Any]]:
    people = union_all(
        select(Transaction.created_by_id.label("id"), Transaction.created_by_name.label("name")),
        select(Period.created_by_id.label("id"), Period.created_by_name.label("name")),
    ).subquery()
    rows = session.execute(
        select(people.c.id, func.max(people.c.name))
        .where(people.c.id.is_not(None))
        .group_by(people.c.id)
        .order_by(func.max(people.c.name), people.c.id)
    )
    return [{"id": user_id, "name": name} for user_id, name in rows]

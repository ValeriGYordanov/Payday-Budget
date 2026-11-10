"""First-run setup: currency, first period, budgets (§6.6, P6, C3, K1)."""

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from app.errors import Conflict
from app.models import NEGATIVE, Settings
from app.services import budgets, categories, periods, settings
from app.users import Actor


def run(
    session: Session,
    *,
    currency: str,
    first_period: dict[str, Any],
    budget_specs: list[dict[str, Any]],
    actor: Actor,
    today: dt.date,
) -> Settings:
    current = settings.get(session)
    if current.setup_completed:
        raise Conflict("Setup has already been completed")
    current.currency = settings.check_currency(currency)
    # Budgets first so the first period's snapshot (B3) includes them.
    for spec in budget_specs:
        budgets.create(
            session,
            name=spec["name"],
            percent=spec["percent"],
            direction=spec.get("direction") or NEGATIVE,
            sort_order=spec.get("sort_order") or 0,
            today=today,
        )
    periods.create(
        session,
        start_date=first_period["start_date"],
        name=first_period.get("name"),
        actor=actor,
        today=today,
    )
    categories.seed(session)
    current.setup_completed = True
    session.flush()
    return current

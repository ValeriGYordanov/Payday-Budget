"""Request bodies. Fields left out of a PATCH body are unchanged (`model_fields_set`)."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.models import DESCRIPTION_MAX, NAME_MAX

Kind = Literal["income", "expense"]
Direction = Literal["negative", "positive"]
# Percent as a decimal string ("50.25") or a whole number; floats are rejected.
Percent = StrictStr | StrictInt
Name = Annotated[str, Field(min_length=1, max_length=NAME_MAX)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def given(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class PeriodCreate(Body):
    start_date: dt.date | None = None
    name: str | None = Field(default=None, max_length=NAME_MAX)


class PeriodUpdate(Body):
    start_date: dt.date | None = None
    name: str | None = Field(default=None, max_length=NAME_MAX)


class BudgetCreate(Body):
    name: Name
    percent: Percent
    direction: Direction = "negative"
    sort_order: int = 0


class BudgetUpdate(Body):
    name: str | None = Field(default=None, max_length=NAME_MAX)
    percent: Percent | None = None
    direction: Direction | None = None
    sort_order: int | None = None
    archived: bool | None = None


class CategoryCreate(Body):
    name: Name
    kind: Kind
    icon: str = "mdi:tag"


class CategoryUpdate(Body):
    name: str | None = Field(default=None, max_length=NAME_MAX)
    kind: Kind | None = None
    icon: str | None = None
    archived: bool | None = None


class TagBody(Body):
    name: Name


class TransactionBody(Body):
    """Used for create and update; T2 required fields are checked by the service."""

    kind: Kind | None = None
    amount_minor: StrictInt | None = None
    category_id: int | None = None
    budget_id: int | None = None
    date: dt.date | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    tags: list[str] | None = None


class RecurringBody(Body):
    """Used for create and update; required fields are checked by the service."""

    kind: Kind | None = None
    amount_minor: StrictInt | None = None
    category_id: int | None = None
    budget_id: int | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    tags: list[str] | None = None
    frequency: str | None = None
    interval: StrictInt | None = None
    anchor_date: dt.date | None = None
    end_date: dt.date | None = None
    active: bool | None = None


class ReminderBody(Body):
    """v1.2 §4: used for create and update; required fields are checked by the service."""

    name: str | None = Field(default=None, max_length=NAME_MAX)
    kind: Kind | None = None
    amount_minor: StrictInt | None = None
    category_id: int | None = None
    budget_id: int | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    tags: list[str] | None = None
    frequency: str | None = None
    interval: StrictInt | None = None
    anchor_date: dt.date | None = None
    end_date: dt.date | None = None
    active: bool | None = None


class SettingsUpdate(Body):
    currency: str
    confirm: bool = False


class SetupPeriod(Body):
    start_date: dt.date
    name: str | None = Field(default=None, max_length=NAME_MAX)


class SetupBudget(Body):
    name: Name
    percent: Percent
    direction: Direction = "negative"
    sort_order: int = 0


class SetupRequest(Body):
    currency: str = "EUR"
    first_period: SetupPeriod
    budgets: list[SetupBudget] = []

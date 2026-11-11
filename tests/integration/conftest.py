"""Fixtures: a fake add-on behind PaydayBudgetClient.request (no network)."""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.payday_budget.api import Actor, ApiError, CannotConnect, PaydayBudgetClient
from custom_components.payday_budget.const import CONF_SLUG, CONF_TOKEN, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


PERIOD_CURRENT = {
    "id": 2,
    "name": "November 2026",
    "start_date": "2026-11-01",
    "end_date": None,
    "is_current": True,
    "days_elapsed": 1,
    "created_by_id": None,
    "created_by_name": None,
    "created_at": "2026-11-01T10:00:00+00:00",
}
PERIOD_PREVIOUS = {
    **PERIOD_CURRENT,
    "id": 1,
    "name": "October 2026",
    "start_date": "2026-10-01",
    "end_date": "2026-10-31",
    "is_current": False,
    "days_elapsed": 31,
}


def budget_row(
    budget_id: int, name: str, target: int, spent: int, used: str | None
) -> dict[str, Any]:
    return {
        "budget_id": budget_id,
        "name": name,
        "archived": False,
        "percent": "50.00",
        "target_minor": target,
        "spent_minor": spent,
        "remaining_minor": target - spent,
        "percent_used": used,
        "over_target": spent > target,
        "direction": "negative",
        "status": "over" if spent > target else "ok",
        "on_track": spent <= target,
    }


def category(
    category_id: int, name: str, kind: str, icon: str, *, archived: bool = False, count: int = 0
) -> dict[str, Any]:
    return {
        "id": category_id,
        "name": name,
        "kind": kind,
        "icon": icon,
        "archived": archived,
        "transaction_count": count,
    }


def transaction(
    transaction_id: int,
    date: str,
    kind: str,
    amount_minor: int,
    category_id: int,
    category_name: str,
    budget_id: int | None,
    budget_name: str | None,
    *,
    tags: list[str] | None = None,
    rule: int | None = None,
) -> dict[str, Any]:
    """A transaction as the add-on's API returns it."""
    return {
        "id": transaction_id,
        "kind": kind,
        "amount_minor": amount_minor,
        "date": date,
        "period_id": 2,
        "category_id": category_id,
        "category_name": category_name,
        "budget_id": budget_id,
        "budget_name": budget_name,
        "description": None if rule else "Lidl",
        "tags": tags or [],
        "recurring_rule_id": rule,
        "occurrence_date": date if rule else None,
        "created_by_id": None if rule else "user-1",
        "created_by_name": None if rule else "Valeri",
        "created_at": "",
        "updated_at": "",
    }


def occurrence(
    occurrence_id: int,
    name: str,
    due_date: str,
    *,
    amount_minor: int | None = None,
    notified: bool = False,
) -> dict[str, Any]:
    """An open reminder occurrence as the add-on's API returns it."""
    return {
        "id": occurrence_id,
        "reminder_id": 50 + occurrence_id,
        "name": name,
        "due_date": due_date,
        "status": "open",
        "transaction_id": None,
        "notified_at": "2026-11-01T00:05:00+00:00" if notified else None,
        "closed_at": None,
        "prefill": {
            "kind": "expense",
            "amount_minor": amount_minor,
            "category_id": 11,
            "category_name": "Food",
            "budget_id": 1,
            "budget_name": "Needs",
            "date": due_date,
            "description": None,
            "tags": [],
        },
    }


class FakeAddon:
    """In-memory stand-in for the add-on REST API (§6.4)."""

    def __init__(self) -> None:
        self.settings = {"currency": "EUR", "minor_unit": 2, "setup_completed": True}
        self.budgets = [
            {
                "id": 1,
                "name": "Needs",
                "percent": "50.00",
                "direction": "negative",
                "sort_order": 0,
                "archived": False,
                "created_at": "",
            },
            {
                "id": 2,
                "name": "Fun",
                "percent": "30.00",
                "direction": "negative",
                "sort_order": 1,
                "archived": False,
                "created_at": "",
            },
        ]
        # The add-on's order: kind (expense first), then name.
        self.categories = [
            category(11, "Food", "expense", "mdi:food", count=3),
            category(10, "Salary", "income", "mdi:cash", count=1),
        ]
        self.tags = [{"id": 30, "name": "groceries"}]
        # GET /transactions: these newest first; `total` of the current period.
        self.listing = [
            transaction(
                8, "2026-11-02", "expense", 4550, 11, "Food", 1, "Needs", tags=["groceries"]
            ),
            transaction(7, "2026-11-01", "income", 300000, 10, "Salary", None, None, rule=5),
        ]
        self.current_total = 2
        self.occurrences: list[dict[str, Any]] = []  # open reminder occurrences
        self.forecast: dict[str, Any] = {
            "period": PERIOD_CURRENT,
            **self.settings,
            "expected_payday": "2026-12-01",
            "overdue": False,
            "days_left": 28,
            "basis": {"periods": 2, "days": 60},
            "income": {"so_far_minor": 300000, "known_minor": 15000, "projected_minor": 315000},
            "expenses": {
                "so_far_minor": 154550,
                "known_minor": 4000,
                "flexible_minor": 2800,
                "projected_minor": 161350,
            },
            "balance_projected_minor": 153650,
            "safe_per_day_minor": 5393,
            "budgets": [
                {
                    "budget_id": 1,
                    "name": "Needs",
                    "direction": "negative",
                    "target_minor": 157500,
                    "spent_minor": 4550,
                    "known_minor": 4000,
                    "flexible_minor": 2800,
                    "projected_spent_minor": 11350,
                    "projected_status": "ok",
                }
            ],
            "series": [
                {"date": "2026-11-01", "balance_minor": 145450, "projected": False, "items": 0}
            ],
            "upcoming": [
                {
                    "date": "2026-11-05",
                    "name": "Netflix",
                    "kind": "expense",
                    "amount_minor": 1599,
                    "budget_id": 2,
                    "budget_name": "Fun",
                    "source": "recurring",
                    "due": False,
                    "estimated": False,
                },
                {
                    "date": "2026-11-20",
                    "name": "Electricity",
                    "kind": "expense",
                    "amount_minor": None,
                    "budget_id": 1,
                    "budget_name": "Needs",
                    "source": "reminder",
                    "due": False,
                    "estimated": False,
                },
            ],
        }
        self.periods = [PERIOD_CURRENT, PERIOD_PREVIOUS]  # newest first, like the API
        self.summary: dict[str, Any] | None = {
            "period": PERIOD_CURRENT,
            **self.settings,
            "income_minor": 300000,
            "expenses_minor": 154550,
            "balance_minor": 145450,
            "unallocated": {"percent": "20.00", "amount_minor": 60000},
            "budgets": [
                budget_row(1, "Needs", 150000, 4550, "3.03"),
                budget_row(2, "Fun", 0, 150000, None),
            ],
        }
        self.history = [
            {
                "period": PERIOD_PREVIOUS,
                "income_minor": 250000,
                "expenses_minor": 100000,
                "budgets": [
                    {"budget_id": 1, "name": "Needs", "target_minor": 125000, "spent_minor": 100000}
                ],
            }
        ]
        self.transactions: dict[int, dict[str, Any]] = {
            7: {"id": 7, "kind": "expense", "budget_id": 1, "category_id": 11}
        }
        self.calls: list[dict[str, Any]] = []
        self.unreachable = False
        self.errors: dict[tuple[str, str], Exception] = {}

    def handle(
        self, method: str, path: str, params: dict[str, Any] | None, json: Any, actor: Actor | None
    ) -> Any:
        self.calls.append(
            {"method": method, "path": path, "params": params or {}, "json": json, "actor": actor}
        )
        if self.unreachable:
            raise CannotConnect("down")
        if (method, path) in self.errors:
            raise self.errors[(method, path)]
        params = params or {}
        if method == "GET":
            if path == "settings":
                return copy.deepcopy(self.settings)
            if path == "budgets":
                return {"items": copy.deepcopy(self.budgets)}
            if path == "categories":
                kind = params.get("kind")
                return {
                    "items": [
                        copy.deepcopy(c) for c in self.categories if kind in (None, c["kind"])
                    ]
                }
            if path == "reminders/occurrences":
                assert params.get("status") == "open"
                return {"items": copy.deepcopy(self.occurrences)}
            if path.startswith("reminders/occurrences/"):
                found = next(o for o in self.occurrences if o["id"] == int(path.split("/")[2]))
                return copy.deepcopy(found)
            if path == "forecast":
                if self.summary is None:
                    raise ApiError(404, "not_found", "Current period not found", "period")
                return copy.deepcopy(self.forecast)
            if path == "tags":
                return {"items": copy.deepcopy(self.tags)}
            if path == "transactions":
                if params.get("period") == "current" and self.summary is None:
                    raise ApiError(404, "not_found", "Current period not found", "period")
                limit, offset = int(params.get("limit", 50)), int(params.get("offset", 0))
                total = self.current_total if params.get("period") == "current" else None
                return {
                    "items": copy.deepcopy(self.listing[offset : offset + limit]),
                    "total": len(self.listing) if total is None else total,
                    "limit": limit,
                    "offset": offset,
                }
            if path == "periods":
                return {"items": copy.deepcopy(self.periods)}
            if path == "periods/history":
                return {"items": copy.deepcopy(self.history)}
            if path == "summary":
                if self.summary is None:
                    raise ApiError(404, "not_found", "Current period not found", "period")
                return {**copy.deepcopy(self.summary), "requested": params.get("period")}
            if path in ("breakdown", "daily"):
                return {"path": path, "params": params}
            if path.startswith("transactions/"):
                return copy.deepcopy(self.transactions[int(path.split("/")[1])])
        if method == "POST" and path == "transactions":
            return {"id": 99, **json}
        if method == "PATCH" and path.startswith("transactions/"):
            return {"id": int(path.split("/")[1]), **json}
        if method == "DELETE":
            if path.startswith("categories/"):
                self.categories = [c for c in self.categories if c["id"] != int(path.split("/")[1])]
            return None
        if method == "POST" and path.startswith("reminders/occurrences/"):
            _, _, occurrence_id, action = path.split("/")
            found = next(o for o in self.occurrences if o["id"] == int(occurrence_id))
            if action == "notified":
                found["notified_at"] = "2026-11-02T10:00:00+00:00"
                return copy.deepcopy(found)
            self.occurrences.remove(found)  # record / dismiss close it
            return {"id": 120} if action == "record" else {**found, "status": "dismissed"}
        if method == "POST" and path == "categories":
            self.categories.append(category(40, json["name"], json["kind"], json["icon"]))
            return copy.deepcopy(self.categories[-1])
        if method == "PATCH" and path.startswith("categories/"):
            found = next(c for c in self.categories if c["id"] == int(path.split("/")[1]))
            found.update(json)
            return copy.deepcopy(found)
        if method == "POST" and path == "periods":
            return {"id": 3, "name": json.get("name", "December 2026")}
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def addon() -> Generator[FakeAddon]:
    fake = FakeAddon()

    async def request(
        self: PaydayBudgetClient,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        actor: Actor | None = None,
    ) -> Any:
        return fake.handle(method, path, params, json, actor)

    async def events(self: PaydayBudgetClient) -> AsyncIterator[str]:
        raise CannotConnect("no stream in unit tests")
        yield ""  # pragma: no cover

    with (
        patch.object(PaydayBudgetClient, "request", request),
        patch.object(PaydayBudgetClient, "events", events),
    ):
        yield fake


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Payday Budget",
        data={
            CONF_HOST: "local-payday-budget",
            CONF_PORT: 8099,
            CONF_TOKEN: "tok",
            CONF_SLUG: "local_payday_budget",
        },
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture
async def loaded(hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon) -> MockConfigEntry:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry

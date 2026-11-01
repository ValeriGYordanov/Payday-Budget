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
                "sort_order": 0,
                "archived": False,
                "created_at": "",
            },
            {
                "id": 2,
                "name": "Fun",
                "percent": "30.00",
                "sort_order": 1,
                "archived": False,
                "created_at": "",
            },
        ]
        self.categories = [
            {"id": 10, "name": "Salary", "kind": "income", "icon": "mdi:cash", "archived": False},
            {"id": 11, "name": "Food", "kind": "expense", "icon": "mdi:food", "archived": False},
        ]
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
                return {"items": [c for c in self.categories if kind in (None, c["kind"])]}
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
            return None
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

"""Fixtures: a fresh migrated SQLite DB per test and a controllable "today"."""

import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import SUPERVISOR_IP
from app.main import create_app
from app.scheduler import run_once

TODAY = dt.date(2026, 11, 1)


class Clock:
    def __init__(self) -> None:
        self.today = TODAY


class Api:
    """Thin JSON helper around TestClient."""

    def __init__(self, client: TestClient, clock: Clock) -> None:
        self.client = client
        self.clock = clock

    def request(self, method: str, url: str, expect: int | None = None, **kwargs: Any) -> Any:
        response = self.client.request(method, f"/api/v1{url}", **kwargs)
        if expect is not None:
            assert response.status_code == expect, response.text
        return response.json() if response.content else None

    def get(self, url: str, expect: int = 200, **kw: Any) -> Any:
        return self.request("GET", url, expect, **kw)

    def post(self, url: str, json: Any, expect: int = 201, **kw: Any) -> Any:
        return self.request("POST", url, expect, json=json, **kw)

    def patch(self, url: str, json: Any, expect: int = 200, **kw: Any) -> Any:
        return self.request("PATCH", url, expect, json=json, **kw)

    def delete(self, url: str, expect: int = 204, **kw: Any) -> Any:
        return self.request("DELETE", url, expect, **kw)

    def error(self, method: str, url: str, code: str, status: int = 422, **kw: Any) -> Any:
        body = self.request(method, url, status, **kw)
        assert body["code"] == code, body
        return body

    # --- domain helpers -----------------------------------------------------

    def setup(
        self,
        start: str = "2026-10-25",
        budgets: list[dict[str, Any]] | None = None,
        currency: str = "EUR",
    ) -> Any:
        if budgets is None:
            budgets = [
                {"name": "Needs", "percent": "50"},
                {"name": "Wants", "percent": "30"},
                {"name": "Savings", "percent": "20"},
            ]
        return self.post(
            "/setup",
            {"currency": currency, "first_period": {"start_date": start}, "budgets": budgets},
        )

    def category_id(self, name: str, kind: str = "expense") -> int:
        items = self.get(f"/categories?kind={kind}")["items"]
        return int(next(c["id"] for c in items if c["name"] == name))

    def budget_id(self, name: str) -> int:
        return int(next(b["id"] for b in self.get("/budgets")["items"] if b["name"] == name))

    def period_id(self, start: str) -> int:
        return int(next(p["id"] for p in self.get("/periods")["items"] if p["start_date"] == start))

    def expense(
        self,
        amount: int,
        day: str,
        budget: str = "Needs",
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> Any:
        body = {
            "kind": "expense",
            "amount_minor": amount,
            "category_id": self.category_id(extra.pop("category", "Food")),
            "budget_id": self.budget_id(budget),
            "date": day,
            **extra,
        }
        return self.post("/transactions", body, headers=headers)

    def income(
        self, amount: int, day: str, headers: dict[str, str] | None = None, **extra: Any
    ) -> Any:
        body = {
            "kind": "income",
            "amount_minor": amount,
            "category_id": self.category_id(extra.pop("category", "Salary"), "income"),
            "date": day,
            **extra,
        }
        return self.post("/transactions", body, headers=headers)

    def new_period(self, start: str | None = None, **extra: Any) -> Any:
        body: dict[str, Any] = dict(extra)
        if start is not None:
            body["start_date"] = start
        return self.post("/periods", body)

    def rule(self, expect: int = 201, **fields: Any) -> Any:
        """Create a recurring rule; defaults to a weekly Needs/Food expense of 1000."""
        body: dict[str, Any] = {
            "kind": "expense",
            "amount_minor": 1000,
            "category_id": self.category_id("Food"),
            "budget_id": self.budget_id("Needs"),
            "frequency": "weekly",
            "anchor_date": "2026-10-25",
            **fields,
        }
        return self.request("POST", "/recurring", expect, json=body)

    def run_scheduler(self) -> int:
        app: Any = self.client.app
        return run_once(app.state.session_factory, lambda: self.clock.today)

    def generated(self, rule_id: int) -> list[str]:
        items = self.get("/transactions?limit=500")["items"]
        return sorted(t["date"] for t in items if t["recurring_rule_id"] == rule_id)

    def summary(self, period: str | int = "current") -> Any:
        return self.get(f"/summary?period={period}")

    def budget_row(self, summary: Any, name: str) -> Any:
        return next(b for b in summary["budgets"] if b["name"] == name)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def db_path(data_dir: Path) -> str:
    return str(data_dir / "payday_budget.db")


@pytest.fixture
def clock() -> Clock:
    return Clock()


def ingress_client(app: FastAPI) -> TestClient:
    """A client whose requests arrive from the Supervisor, as Ingress requests do."""
    return TestClient(app, client=(SUPERVISOR_IP, 50000))


def make_app(data_dir: Path, clock: Clock) -> FastAPI:
    return create_app(data_dir, today=lambda: clock.today, announce=lambda _token: None)


@pytest.fixture
def api(data_dir: Path, clock: Clock) -> Iterator[Api]:
    app = make_app(data_dir, clock)
    with ingress_client(app) as client:
        yield Api(client, clock)
    app.state.engine.dispose()


@pytest.fixture
def ready(api: Api) -> Api:
    """Setup done: EUR, first period 2026-10-25, Needs 50 / Wants 30 / Savings 20."""
    api.setup()
    return api

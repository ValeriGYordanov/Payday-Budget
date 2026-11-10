"""End to end: the integration against the real add-on backend over HTTP and SSE.

The add-on runs as a subprocess from its own environment (`.venv`, Python 3.12):
Home Assistant pins a different SQLAlchemy, so the two cannot share one venv.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.payday_budget.const import CONF_TOKEN, DOMAIN

ROOT = Path(__file__).resolve().parents[2]
ADDON_PYTHON = ROOT / ".venv" / "bin" / "python"

pytestmark = pytest.mark.skipif(not ADDON_PYTHON.exists(), reason="add-on venv (.venv) missing")


class RealAddon:
    def __init__(self, base: str, token: str) -> None:
        self.base = base
        self.token = token

    def call(self, method: str, path: str, body: Any = None) -> Any:
        request = urllib.request.Request(
            f"{self.base}/api/v1/{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read()
        return json.loads(payload) if payload else None


@pytest.fixture
def real_addon(tmp_path: Path, socket_enabled: None) -> Generator[RealAddon]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "PAYDAY_BUDGET_DATA": str(tmp_path), "TZ": "UTC"}
    env.pop("SUPERVISOR_TOKEN", None)
    process = subprocess.Popen(
        [
            str(ADDON_PYTHON),
            "-m",
            "uvicorn",
            "--factory",
            "app.main:create_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT / "payday_budget",
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 20
    while True:
        try:
            urllib.request.urlopen(f"{base}/api/v1/setup", timeout=1)
        except urllib.error.HTTPError as err:
            if err.code == 401:  # up, and requiring auth (§6.2)
                break
        except OSError:
            pass
        assert time.monotonic() < deadline, "add-on did not start"
        assert process.poll() is None, "add-on exited"
        time.sleep(0.1)
    addon = RealAddon(base, (tmp_path / "token").read_text().strip())
    addon.call(
        "POST",
        "setup",
        {
            "currency": "EUR",
            "first_period": {"start_date": dt.datetime.now(dt.UTC).date().isoformat()},
            "budgets": [{"name": "Needs", "percent": "60"}, {"name": "Savings", "percent": "20"}],
        },
    )
    yield addon
    process.terminate()
    process.wait(10)


async def _wait_for(hass: HomeAssistant, check: Callable[[], bool], timeout: float = 8) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "timed out waiting for state"
        await asyncio.sleep(0.05)
        await hass.async_block_till_done()


async def test_end_to_end(
    hass: HomeAssistant, real_addon: RealAddon, hass_ws_client: WebSocketGenerator
) -> None:
    host, port = real_addon.base.removeprefix("http://").split(":")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: int(port), CONF_TOKEN: real_addon.token},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    def state(entity_id: str) -> str | None:
        current = hass.states.get(entity_id)
        return current.state if current else None

    assert state("sensor.payday_budget_income") == "0.00"
    assert state("sensor.payday_budget_needs_target") == "0.00"
    assert state("sensor.payday_budget_unallocated") == "0.00"
    assert hass.states.get("sensor.payday_budget_unallocated").attributes["percent"] == "20.00"

    # §7.1: a write made elsewhere (e.g. the add-on UI) reaches HA through SSE `changed`.
    categories = real_addon.call("GET", "categories?kind=income")["items"]
    salary = next(c["id"] for c in categories if c["name"] == "Salary")
    await hass.async_add_executor_job(
        real_addon.call,
        "POST",
        "transactions",
        {"kind": "income", "amount_minor": 100000, "category_id": salary},
    )
    await _wait_for(hass, lambda: state("sensor.payday_budget_income") == "1000.00")
    assert state("sensor.payday_budget_needs_target") == "600.00"

    # §7.3 action through the real API, category and budget by name.
    response = await hass.services.async_call(
        DOMAIN,
        "add_transaction",
        {"kind": "expense", "amount": "25.50", "category": "Food", "budget": "Needs"},
        blocking=True,
        return_response=True,
    )
    transaction = real_addon.call("GET", f"transactions/{response['id']}")
    assert transaction["amount_minor"] == 2550
    await _wait_for(hass, lambda: state("sensor.payday_budget_needs_spent") == "25.50", timeout=15)
    assert state("binary_sensor.payday_budget_needs_over_target") == "off"

    # Rule violations from the add-on surface with their rule ID.
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_transaction",
            {
                "kind": "expense",
                "amount": 1,
                "category": "Food",
                "budget": "Needs",
                "date": "2000-01-01",
            },
            blocking=True,
        )
    assert err.value.translation_placeholders["code"] == "P6"
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.payday_budget_start_new_period"}, blocking=True
        )
    assert err.value.translation_placeholders["code"] == "P2"  # a period already starts today

    summary = await hass.services.async_call(
        DOMAIN, "get_summary", {}, blocking=True, return_response=True
    )
    assert (summary["income"], summary["expenses"], summary["balance"]) == (
        "1000.00",
        "25.50",
        "974.50",
    )

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "payday_budget/daily"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["days"][-1]["cumulative_minor"] == 2550

    # B4: archiving a budget removes its entities (§7.1).
    savings = next(
        b["id"] for b in real_addon.call("GET", "budgets")["items"] if b["name"] == "Savings"
    )
    await hass.async_add_executor_job(
        real_addon.call, "PATCH", f"budgets/{savings}", {"archived": True}
    )
    await _wait_for(hass, lambda: state("sensor.payday_budget_savings_target") is None, timeout=15)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_end_to_end_transactions_and_categories(
    hass: HomeAssistant, real_addon: RealAddon
) -> None:
    """v1.1: the new sensors and actions against the real add-on."""
    host, port = real_addon.base.removeprefix("http://").split(":")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: int(port), CONF_TOKEN: real_addon.token},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Back-to-back actions here; HA's 10 s refresh cooldown would only slow the test down.
    entry.runtime_data.coordinator._debounced_refresh.cooldown = 0.1

    def attr(entity_id: str, name: str) -> Any:
        current = hass.states.get(entity_id)
        return current.attributes.get(name) if current else None

    def state(entity_id: str) -> str | None:
        current = hass.states.get(entity_id)
        return current.state if current else None

    async def call(service: str, data: dict[str, Any], response: bool = False) -> Any:
        return await hass.services.async_call(
            DOMAIN, service, data, blocking=True, return_response=response
        )

    def category(name: str) -> dict[str, Any] | None:
        items = attr("sensor.payday_budget_categories", "categories") or []
        return next((c for c in items if c["name"] == name), None)

    assert state("sensor.payday_budget_recent_transactions") == "0"
    assert state("sensor.payday_budget_budgets") == "2"
    assert attr("sensor.payday_budget_budgets", "budgets")[0] == {
        "id": 1,
        "name": "Needs",
        "percent": "60.00",
        "archived": False,
        "sort_order": 0,
    }

    await call("add_transaction", {"kind": "income", "amount": "1000", "category": "Salary"})
    await call(
        "add_transaction",
        {
            "kind": "expense",
            "amount": "25.50",
            "category": "food",
            "budget": "needs",
            "description": "Lidl",
            "tags": ["groceries"],
        },
    )
    await _wait_for(
        hass, lambda: state("sensor.payday_budget_recent_transactions") == "2", timeout=15
    )
    newest = attr("sensor.payday_budget_recent_transactions", "transactions")[0]
    assert {k: newest[k] for k in ("kind", "amount", "currency", "category", "budget", "tags")} == {
        "kind": "expense",
        "amount": "25.50",
        "currency": "EUR",
        "category": "Food",
        "budget": "Needs",
        "tags": ["groceries"],
    }
    assert category("Food")["transaction_count"] == 1

    listed = await call(
        "list_transactions",
        {
            "period": "current",
            "kind": "expense",
            "category": "FOOD",
            "tag": "groceries",
            "search": "lid",
        },
        response=True,
    )
    assert (listed["total"], listed["limit"], listed["offset"]) == (1, 100, 0)
    assert listed["items"] == [newest]
    assert (await call("list_transactions", {"limit": 1}, response=True))["total"] == 2
    with pytest.raises(ServiceValidationError) as err:
        await call("list_transactions", {"period": "previous"}, response=True)
    assert err.value.translation_key == "no_previous_period"

    added = await call("add_category", {"name": "Pets", "kind": "expense"}, response=True)
    await _wait_for(hass, lambda: category("Pets") is not None, timeout=15)
    assert category("Pets")["icon"] == "mdi:tag"
    await call("update_category", {"category": "pets", "name": "Animals", "icon": "mdi:dog"})
    await _wait_for(hass, lambda: category("Animals") is not None, timeout=15)
    assert category("Animals")["id"] == added["id"]
    count = int(state("sensor.payday_budget_categories") or 0)
    await call("update_category", {"category": "Animals", "archived": True})
    await _wait_for(
        hass, lambda: state("sensor.payday_budget_categories") == str(count - 1), timeout=15
    )
    assert category("Animals")["archived"] is True

    with pytest.raises(ServiceValidationError) as err:
        await call("delete_category", {"category": "Food"})
    assert err.value.translation_placeholders["code"] == "C2"
    with pytest.raises(ServiceValidationError) as err:
        await call("update_category", {"category": "Food", "kind": "income"})
    assert err.value.translation_placeholders["code"] == "C1"
    with pytest.raises(ServiceValidationError) as err:
        await call("add_category", {"name": "Food", "kind": "expense"})
    assert err.value.translation_placeholders["code"] == "conflict"

    await call("delete_category", {"category": "Animals"})
    await _wait_for(hass, lambda: category("Animals") is None, timeout=15)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

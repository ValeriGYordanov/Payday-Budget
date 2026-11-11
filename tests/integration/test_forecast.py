"""v1.3 §6: forecast sensors, the get_forecast action and the WebSocket command."""

from typing import Any

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.payday_budget.const import DOMAIN
from tests.integration.conftest import FakeAddon


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_forecast_sensors(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    balance = hass.states.get("sensor.payday_budget_projected_balance")
    assert (balance.state, balance.attributes["unit_of_measurement"]) == ("1536.50", "EUR")
    assert balance.attributes["device_class"] == "monetary"
    assert "state_class" not in balance.attributes
    assert (balance.attributes["projected_income"], balance.attributes["projected_expenses"]) == (
        "3150.00",
        "1613.50",
    )
    assert balance.attributes["overdue"] is False
    assert hass.states.get("sensor.payday_budget_safe_per_day").state == "53.93"
    payday = hass.states.get("sensor.payday_budget_expected_payday")
    assert (payday.state, payday.attributes["device_class"], payday.attributes["days_left"]) == (
        "2026-12-01",
        "date",
        28,
    )


async def test_upcoming_sensor(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    state = hass.states.get("sensor.payday_budget_upcoming")
    assert state.state == "2"
    assert state.attributes["items"] == [
        {
            "date": "2026-11-05",
            "name": "Netflix",
            "kind": "expense",
            "amount": "15.99",
            "budget_id": 2,
            "budget_name": "Fun",
            "source": "recurring",
            "due": False,
            "estimated": False,
            "currency": "EUR",
        },
        {
            "date": "2026-11-20",
            "name": "Electricity",
            "kind": "expense",
            "amount": None,
            "budget_id": 1,
            "budget_name": "Needs",
            "source": "reminder",
            "due": False,
            "estimated": False,
            "currency": "EUR",
        },
    ]
    sensor = hass.data["sensor"].get_entity("sensor.payday_budget_upcoming")
    assert "items" in sensor._unrecorded_attributes


async def test_budget_projected_sensor(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    needs = hass.states.get("sensor.payday_budget_needs_projected")
    assert needs.state == "113.50"
    assert (needs.attributes["projected_status"], needs.attributes["target"]) == ("ok", "1575.00")
    # A budget the forecast doesn't list (here Fun) has no projection.
    assert hass.states.get("sensor.payday_budget_fun_projected").state == STATE_UNKNOWN


async def test_forecast_unknown_without_a_current_period(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.summary = None
    await _refresh(hass, loaded)
    for entity_id in (
        "sensor.payday_budget_projected_balance",
        "sensor.payday_budget_safe_per_day",
        "sensor.payday_budget_expected_payday",
        "sensor.payday_budget_upcoming",
    ):
        assert hass.states.get(entity_id).state == STATE_UNKNOWN, entity_id


async def test_get_forecast_action_money_as_decimal_strings(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    response: Any = await hass.services.async_call(
        DOMAIN, "get_forecast", {}, blocking=True, return_response=True
    )
    assert response["balance_projected"] == "1536.50"
    assert response["safe_per_day"] == "53.93"
    assert response["income"] == {"so_far": "3000.00", "known": "150.00", "projected": "3150.00"}
    assert response["budgets"][0]["projected_spent"] == "113.50"
    assert response["upcoming"][1]["amount"] is None
    assert response["series"][0]["balance"] == "1454.50"
    assert response["expected_payday"] == "2026-12-01"
    assert "balance_projected_minor" not in response


async def test_forecast_websocket_command(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_ws_client: WebSocketGenerator
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "payday_budget/forecast"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["balance_projected_minor"] == 153650  # minor units, as the charts expect

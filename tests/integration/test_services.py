"""§7.3 actions, the §7.2 button, and §7.4 WebSocket commands."""

from typing import Any

import pytest
from homeassistant.auth.models import User
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.payday_budget.api import ApiError
from custom_components.payday_budget.const import DOMAIN
from tests.integration.conftest import FakeAddon


async def _call(hass: HomeAssistant, service: str, data: dict[str, Any], **kw: Any) -> Any:
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, **kw)


def _last(addon: FakeAddon, method: str, path: str) -> dict[str, Any]:
    return [c for c in addon.calls if c["method"] == method and c["path"] == path][-1]


async def test_add_transaction_by_names(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon, hass_admin_user: User
) -> None:
    response = await _call(
        hass,
        "add_transaction",
        {
            "kind": "expense",
            "amount": 12.5,
            "category": "food",
            "budget": "NEEDS",
            "date": "2026-11-01",
            "tags": ["a", "b"],
            "description": "Lidl",
        },
        return_response=True,
        context=Context(user_id=hass_admin_user.id),
    )
    assert response == {"id": 99}
    call = _last(addon, "POST", "transactions")
    assert call["json"] == {
        "kind": "expense",
        "amount_minor": 1250,
        "category_id": 11,
        "budget_id": 1,
        "date": "2026-11-01",
        "description": "Lidl",
        "tags": ["a", "b"],
    }
    # T3: the acting HA user is passed to the add-on.
    assert call["actor"].user_id == hass_admin_user.id
    assert call["actor"].name == hass_admin_user.name


async def test_add_transaction_by_ids_and_string_amount(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    await _call(hass, "add_transaction", {"kind": "income", "amount": "3000", "category": 10})
    call = _last(addon, "POST", "transactions")
    assert call["json"] == {
        "kind": "income",
        "amount_minor": 300000,
        "category_id": 10,
        "budget_id": None,
    }
    assert call["actor"].user_id is None  # automations have no user


@pytest.mark.parametrize("amount", ["12.345", 0, "-1", "abc", 0.1 + 0.2, True])
async def test_T1_invalid_amount(
    hass: HomeAssistant, loaded: MockConfigEntry, amount: object
) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "add_transaction",
            {"kind": "expense", "amount": amount, "category": "Food", "budget": "Needs"},
        )
    assert err.value.translation_key == "invalid_amount"


async def test_unknown_category_or_budget(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "add_transaction", {"kind": "income", "amount": 1, "category": "Food"})
    assert err.value.translation_key == "unknown_category"  # Food is an expense category
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "add_transaction",
            {"kind": "expense", "amount": 1, "category": "Food", "budget": "Nope"},
        )
    assert err.value.translation_key == "unknown_budget"


async def test_rule_violation_raises_with_rule_id(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.errors[("POST", "transactions")] = ApiError(
        422, "P6", "Transactions before the first period are not allowed", "date"
    )
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "add_transaction",
            {"kind": "expense", "amount": 1, "category": "Food", "budget": "Needs"},
        )
    assert err.value.translation_key == "rule_violation"
    assert err.value.translation_placeholders == {
        "code": "P6",
        "message": "Transactions before the first period are not allowed",
    }


async def test_addon_unreachable_raises(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.unreachable = True
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "delete_transaction", {"id": 7})
    assert err.value.translation_key == "cannot_connect"


async def test_update_transaction(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    await _call(hass, "update_transaction", {"id": 7, "amount": "5.10", "category": "Food"})
    assert _last(addon, "PATCH", "transactions/7")["json"] == {
        "amount_minor": 510,
        "category_id": 11,
    }
    # Switching to income resolves the category in the new kind and clears the budget (B6).
    await _call(hass, "update_transaction", {"id": 7, "kind": "income", "category": "Salary"})
    assert _last(addon, "PATCH", "transactions/7")["json"] == {
        "kind": "income",
        "category_id": 10,
        "budget_id": None,
    }
    await _call(hass, "update_transaction", {"id": 7, "description": ""})
    assert _last(addon, "PATCH", "transactions/7")["json"] == {"description": None}


async def test_delete_transaction(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    await _call(hass, "delete_transaction", {"id": 7})
    assert _last(addon, "DELETE", "transactions/7")


async def test_P3_start_period_action(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    response = await _call(
        hass, "start_period", {"date": "2026-11-25", "name": "Bonus"}, return_response=True
    )
    assert response == {"id": 3, "name": "Bonus"}
    assert _last(addon, "POST", "periods")["json"] == {"start_date": "2026-11-25", "name": "Bonus"}


async def test_P3_button_starts_period_today(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon, hass_admin_user: User
) -> None:
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.payday_budget_start_new_period"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    call = _last(addon, "POST", "periods")
    assert call["json"] == {}  # the add-on defaults the start date to today
    assert call["actor"].user_id == hass_admin_user.id


async def test_P2_button_rule_violation(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.errors[("POST", "periods")] = ApiError(
        422, "P2", "A period already starts on this date", "start_date"
    )
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.payday_budget_start_new_period"}, blocking=True
        )
    assert err.value.translation_placeholders["code"] == "P2"


async def test_get_summary_money_as_decimal_strings(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    response = await _call(hass, "get_summary", {}, return_response=True)
    assert response["income"] == "3000.00"
    assert response["balance"] == "1454.50"
    assert response["unallocated"] == {"percent": "20.00", "amount": "600.00"}
    needs = response["budgets"][0]
    assert (needs["target"], needs["spent"], needs["remaining"], needs["percent_used"]) == (
        "1500.00",
        "45.50",
        "1454.50",
        "3.03",
    )
    assert response["period"]["name"] == "November 2026"


async def test_get_summary_previous_period(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    await _call(hass, "get_summary", {"period": "previous"}, return_response=True)
    assert _last(addon, "GET", "summary")["params"] == {"period": "1"}
    addon.periods = addon.periods[:1]
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "get_summary", {"period": "previous"}, return_response=True)
    assert err.value.translation_key == "no_previous_period"


async def test_websocket_commands(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    addon: FakeAddon,
    hass_ws_client: WebSocketGenerator,
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "payday_budget/summary"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["income_minor"] == 300000  # the add-on's JSON, unchanged

    await client.send_json_auto_id({"type": "payday_budget/history", "limit": 6})
    msg = await client.receive_json()
    assert msg["result"]["items"][0]["period"]["name"] == "October 2026"
    assert _last(addon, "GET", "periods/history")["params"] == {"limit": 6}

    await client.send_json_auto_id(
        {"type": "payday_budget/breakdown", "period": "previous", "budget": "Needs"}
    )
    msg = await client.receive_json()
    assert msg["result"] == {"path": "breakdown", "params": {"period": "1", "budget": 1}}

    await client.send_json_auto_id({"type": "payday_budget/daily", "period": 2})
    msg = await client.receive_json()
    assert msg["result"]["params"] == {"period": "2"}

    addon.errors[("GET", "daily")] = ApiError(404, "not_found", "Period not found")
    await client.send_json_auto_id({"type": "payday_budget/daily", "period": 5})
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"

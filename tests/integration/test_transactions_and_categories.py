"""v1.1: recent transactions, categories and budgets sensors; list and category actions."""

from typing import Any

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.payday_budget.api import ApiError
from custom_components.payday_budget.const import DOMAIN
from tests.integration.conftest import FakeAddon, category, transaction

RECENT = "sensor.payday_budget_recent_transactions"
CATEGORIES = "sensor.payday_budget_categories"
BUDGETS = "sensor.payday_budget_budgets"


async def _call(hass: HomeAssistant, service: str, data: dict[str, Any], **kw: Any) -> Any:
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, **kw)


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


def _calls(addon: FakeAddon, method: str, path: str) -> list[dict[str, Any]]:
    return [c for c in addon.calls if c["method"] == method and c["path"] == path]


def _entity(hass: HomeAssistant, entity_id: str) -> Any:
    return hass.data["sensor"].get_entity(entity_id)


# --- recent transactions (§4.1) ---------------------------------------------


async def test_RT1_recent_transactions_newest_first_at_most_ten(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.listing = [
        transaction(i, f"2026-11-{30 - i:02d}", "expense", 100, 11, "Food", 1, "Needs")
        for i in range(1, 16)
    ]
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    newest = [c for c in _calls(addon, "GET", "transactions") if "period" not in c["params"]]
    assert newest[-1]["params"] == {"limit": 10}
    items = hass.states.get(RECENT).attributes["transactions"]
    assert [t["id"] for t in items] == list(range(1, 11))  # the add-on's order: newest first
    assert "transactions" in _entity(hass, RECENT)._unrecorded_attributes


async def test_RT2_recent_amounts_are_exact_decimal_strings(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    items = hass.states.get(RECENT).attributes["transactions"]
    assert items[0] == {
        "id": 8,
        "date": "2026-11-02",
        "kind": "expense",
        "amount": "45.50",
        "currency": "EUR",
        "category": "Food",
        "category_id": 11,
        "budget": "Needs",
        "budget_id": 1,
        "description": "Lidl",
        "tags": ["groceries"],
        "created_by": "Valeri",
        "recurring": False,
    }
    assert (items[1]["amount"], items[1]["created_by"], items[1]["recurring"]) == (
        "3000.00",
        None,
        True,
    )
    addon.settings = {**addon.settings, "currency": "JPY", "minor_unit": 0}
    addon.listing = [transaction(9, "2026-11-02", "expense", 1500, 11, "Food", 1, "Needs")]
    await _refresh(hass, loaded)
    item = hass.states.get(RECENT).attributes["transactions"][0]
    assert (item["amount"], item["currency"]) == ("1500", "JPY")


async def test_RT3_state_is_current_period_count(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    assert hass.states.get(RECENT).state == "2"
    current = [c for c in _calls(addon, "GET", "transactions") if "period" in c["params"]]
    assert current[-1]["params"] == {"period": "current", "limit": 1}
    addon.current_total = 5
    await _refresh(hass, loaded)
    assert hass.states.get(RECENT).state == "5"
    addon.summary = None  # no current period
    await _refresh(hass, loaded)
    state = hass.states.get(RECENT)
    assert state.state == STATE_UNKNOWN
    assert len(state.attributes["transactions"]) == 2


# --- categories (§4.2) and budgets (§4.5) sensors ---------------------------


async def test_CM3_categories_sensor_keeps_archived_categories(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.categories.insert(1, category(12, "Old", "expense", "mdi:tag", archived=True, count=4))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(CATEGORIES)
    assert state.state == "2"  # non-archived only
    assert state.attributes["categories"] == [
        {
            "id": 11,
            "name": "Food",
            "kind": "expense",
            "icon": "mdi:food",
            "archived": False,
            "transaction_count": 3,
        },
        {
            "id": 12,
            "name": "Old",
            "kind": "expense",
            "icon": "mdi:tag",
            "archived": True,
            "transaction_count": 4,
        },
        {
            "id": 10,
            "name": "Salary",
            "kind": "income",
            "icon": "mdi:cash",
            "archived": False,
            "transaction_count": 1,
        },
    ]
    assert "categories" in _entity(hass, CATEGORIES)._unrecorded_attributes
    # Archived categories stay selectable for filtering.
    await _call(hass, "list_transactions", {"category": "old"}, return_response=True)
    assert _calls(addon, "GET", "transactions")[-1]["params"]["category"] == 12


async def test_BS1_budgets_sensor(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.budgets.append(
        {
            "id": 3,
            "name": "Old",
            "percent": "0.00",
            "sort_order": 2,
            "archived": True,
            "created_at": "",
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(BUDGETS)
    assert state.state == "2"
    assert state.attributes["budgets"] == [
        {"id": 1, "name": "Needs", "percent": "50.00", "archived": False, "sort_order": 0},
        {"id": 2, "name": "Fun", "percent": "30.00", "archived": False, "sort_order": 1},
        {"id": 3, "name": "Old", "percent": "0.00", "archived": True, "sort_order": 2},
    ]
    assert "budgets" in _entity(hass, BUDGETS)._unrecorded_attributes
    # No extra request: the sensor reuses the coordinator's budgets list.
    assert len(_calls(addon, "GET", "budgets")) == 1


async def test_new_sensors_on_the_device(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    for entity_id in (RECENT, CATEGORIES, BUDGETS):
        entity = _entity(hass, entity_id)
        assert entity.device_info["identifiers"] == {(DOMAIN, loaded.entry_id)}


# --- list_transactions (§4.3) -----------------------------------------------


async def test_TL1_list_transactions_passes_filters(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    response = await _call(
        hass,
        "list_transactions",
        {
            "period": "current",
            "date_from": "2026-11-01",
            "date_to": "2026-11-30",
            "kind": "expense",
            "category": "FOOD",
            "budget": "needs",
            "tag": "Groceries",
            "user": "user-1",
            "search": "lidl",
            "limit": 1,
            "offset": 1,
        },
        return_response=True,
    )
    assert _calls(addon, "GET", "transactions")[-1]["params"] == {
        "period": "current",
        "date_from": "2026-11-01",
        "date_to": "2026-11-30",
        "kind": "expense",
        "category": 11,
        "budget": 1,
        "tag": 30,
        "user": "user-1",
        "q": "lidl",
        "limit": 1,
        "offset": 1,
    }
    assert (response["total"], response["limit"], response["offset"]) == (2, 1, 1)
    assert response["items"] == hass.states.get(RECENT).attributes["transactions"][1:]


async def test_TL1_list_transactions_defaults(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    response = await _call(hass, "list_transactions", {}, return_response=True)
    assert _calls(addon, "GET", "transactions")[-1]["params"] == {"limit": 100, "offset": 0}
    assert [t["id"] for t in response["items"]] == [8, 7]
    for bad in ({"limit": 0}, {"limit": 501}, {"offset": -1}):
        with pytest.raises(Exception, match="value must be"):
            await _call(hass, "list_transactions", bad, return_response=True)


async def test_TL2_previous_period(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    await _call(hass, "list_transactions", {"period": "previous"}, return_response=True)
    assert _calls(addon, "GET", "transactions")[-1]["params"]["period"] == "1"
    addon.periods = addon.periods[:1]
    before = len(_calls(addon, "GET", "transactions"))
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "list_transactions", {"period": "previous"}, return_response=True)
    assert err.value.translation_key == "no_previous_period"
    assert len(_calls(addon, "GET", "transactions")) == before


async def test_TL3_name_in_both_kinds_needs_kind(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.categories.append(category(13, "Food", "income", "mdi:food"))
    before = len(_calls(addon, "GET", "transactions"))
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "list_transactions", {"category": "food"}, return_response=True)
    assert err.value.translation_key == "ambiguous_category"
    assert len(_calls(addon, "GET", "transactions")) == before  # nothing is called
    await _call(
        hass, "list_transactions", {"category": "food", "kind": "income"}, return_response=True
    )
    assert _calls(addon, "GET", "transactions")[-1]["params"]["category"] == 13
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "list_transactions", {"tag": "nope"}, return_response=True)
    assert err.value.translation_key == "unknown_tag"


async def test_TL3_D9_case_clash_within_a_kind_is_an_error(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.categories.append(category(12, "food", "expense", "mdi:food"))
    addon.budgets.append({**addon.budgets[0], "id": 3, "name": "NEEDS"})
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "add_transaction",
            {"kind": "expense", "amount": 1, "category": "Food", "budget": 1},
        )
    assert err.value.translation_key == "ambiguous_category"
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "add_transaction",
            {"kind": "expense", "amount": 1, "category": 11, "budget": "needs"},
        )
    assert err.value.translation_key == "ambiguous_budget"
    assert not _calls(addon, "POST", "transactions")
    # Ids stay unambiguous.
    await _call(
        hass, "add_transaction", {"kind": "expense", "amount": 1, "category": 12, "budget": 3}
    )
    assert _calls(addon, "POST", "transactions")[-1]["json"]["category_id"] == 12


# --- category actions (§4.4) ------------------------------------------------


async def test_CM1_add_category_refreshes_the_sensor(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    response = await _call(
        hass, "add_category", {"name": "Pets", "kind": "expense"}, return_response=True
    )
    assert response == {"id": 40}
    assert _calls(addon, "POST", "categories")[-1]["json"] == {
        "name": "Pets",
        "kind": "expense",
        "icon": "mdi:tag",
    }
    await hass.async_block_till_done()
    state = hass.states.get(CATEGORIES)
    assert state.state == "3"
    assert state.attributes["categories"][-1]["name"] == "Pets"


async def test_CM1_update_category_by_name(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    response = await _call(
        hass,
        "update_category",
        {"category": "food", "name": "Groceries", "icon": "mdi:cart", "archived": True},
        return_response=True,
    )
    assert response == {"id": 11}
    assert _calls(addon, "PATCH", "categories/11")[-1]["json"] == {
        "name": "Groceries",
        "icon": "mdi:cart",
        "archived": True,
    }
    await hass.async_block_till_done()
    assert hass.states.get(CATEGORIES).state == "1"


async def test_CM1_delete_category(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    await _call(hass, "delete_category", {"category": "Salary"})
    assert _calls(addon, "DELETE", "categories/10")
    await hass.async_block_till_done()
    assert [c["name"] for c in hass.states.get(CATEGORIES).attributes["categories"]] == ["Food"]


async def test_D8_update_category_kind(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.categories.append(category(13, "Other", "expense", "mdi:tag"))
    addon.categories.append(category(14, "Other", "income", "mdi:tag"))

    async def update(data: dict[str, Any]) -> dict[str, Any]:
        await _call(hass, "update_category", data, return_response=True)
        return [c for c in addon.calls if c["method"] == "PATCH"][-1]  # not the refresh's GETs

    # By name, existing in that kind: selects it, no kind change.
    call = await update({"category": "other", "kind": "income", "icon": "mdi:cash"})
    assert (call["path"], call["json"]) == ("categories/14", {"icon": "mdi:cash"})
    # By name, only in the other kind: changes the kind.
    call = await update({"category": "Food", "kind": "income"})
    assert (call["path"], call["json"]) == ("categories/11", {"kind": "income"})
    # By id: kind changes.
    call = await update({"category": 10, "kind": "expense"})
    assert (call["path"], call["json"]) == ("categories/10", {"kind": "expense"})
    # By name in both kinds without kind: ambiguous, nothing is called.
    before = len(addon.calls)
    with pytest.raises(ServiceValidationError) as err:
        await update({"category": "Other", "icon": "mdi:cash"})
    assert err.value.translation_key == "ambiguous_category"
    assert not [c for c in addon.calls[before:] if c["method"] != "GET"]
    with pytest.raises(ServiceValidationError) as err:
        await update({"category": "nope"})
    assert err.value.translation_key == "unknown_category_any"


async def test_delete_category_disambiguates_with_kind(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.categories.append(category(13, "Other", "expense", "mdi:tag"))
    addon.categories.append(category(14, "Other", "income", "mdi:tag"))
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "delete_category", {"category": "other"})
    assert err.value.translation_key == "ambiguous_category"
    assert not _calls(addon, "DELETE", "categories/13")
    await _call(hass, "delete_category", {"category": "other", "kind": "income"})
    assert _calls(addon, "DELETE", "categories/14")


@pytest.mark.parametrize(
    ("method", "path", "service", "data", "code"),
    [
        ("PATCH", "categories/11", "update_category", {"category": 11, "kind": "income"}, "C1"),
        ("DELETE", "categories/11", "delete_category", {"category": "Food"}, "C2"),
        ("POST", "categories", "add_category", {"name": "Food", "kind": "expense"}, "conflict"),
    ],
)
async def test_CM2_rule_violations_carry_the_rule_id(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    addon: FakeAddon,
    method: str,
    path: str,
    service: str,
    data: dict[str, Any],
    code: str,
) -> None:
    addon.errors[(method, path)] = ApiError(422, code, "Not allowed")
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, service, data)
    assert err.value.translation_key == "rule_violation"
    assert err.value.translation_placeholders == {"code": code, "message": "Not allowed"}

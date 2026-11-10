"""§7.2 entities, §7.1 availability and dynamic budget entities."""

from decimal import Decimal

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.payday_budget.api import InvalidAuth
from custom_components.payday_budget.const import DOMAIN
from tests.integration.conftest import FakeAddon


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_period_and_total_sensors(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    period = hass.states.get("sensor.payday_budget_period")
    assert period.state == "November 2026"
    assert period.attributes["start_date"] == "2026-11-01"
    assert period.attributes["days_elapsed"] == 1
    assert period.attributes["period_id"] == 2
    start = hass.states.get("sensor.payday_budget_period_start")
    assert (start.state, start.attributes["device_class"]) == ("2026-11-01", "date")
    for entity_id, value in (
        ("sensor.payday_budget_income", "3000.00"),
        ("sensor.payday_budget_expenses", "1545.50"),
        ("sensor.payday_budget_balance", "1454.50"),
        ("sensor.payday_budget_unallocated", "600.00"),
    ):
        state = hass.states.get(entity_id)
        assert state.state == value, entity_id
        assert state.attributes["device_class"] == "monetary"
        assert state.attributes["unit_of_measurement"] == "EUR"
        assert "state_class" not in state.attributes  # §7.2: no long-term statistics
    assert hass.states.get("sensor.payday_budget_unallocated").attributes["percent"] == "20.00"


async def test_budget_entities(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert hass.states.get("sensor.payday_budget_needs_target").state == "1500.00"
    assert hass.states.get("sensor.payday_budget_needs_spent").state == "45.50"
    assert hass.states.get("sensor.payday_budget_needs_remaining").state == "1454.50"
    used = hass.states.get("sensor.payday_budget_needs_used")
    assert (used.state, used.attributes["unit_of_measurement"]) == ("3.03", "%")
    assert used.attributes["state_class"] == "measurement"
    assert hass.states.get("binary_sensor.payday_budget_needs_over_target").state == STATE_OFF
    assert hass.states.get("binary_sensor.payday_budget_fun_over_target").state == STATE_ON
    assert hass.states.get("sensor.payday_budget_fun_remaining").state == "-1500.00"


async def test_B5_used_unavailable_when_target_is_zero(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    assert hass.states.get("sensor.payday_budget_fun_used").state == STATE_UNAVAILABLE


async def test_history_sensor(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    state = hass.states.get("sensor.payday_budget_history")
    assert state.state == "2"
    assert state.attributes["history"] == [
        {
            "name": "October 2026",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "income": "2500.00",
            "expenses": "1000.00",
            "budgets": {"Needs": {"target": "1250.00", "spent": "1000.00"}},
        }
    ]
    sensor = hass.data["sensor"].get_entity("sensor.payday_budget_history")
    assert "history" in sensor._unrecorded_attributes


async def test_single_device(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), loaded.entry_id)
    assert len(devices) == 1
    assert devices[0].name == "Payday Budget"
    assert devices[0].configuration_url == "homeassistant://hassio/ingress/local_payday_budget"


async def test_budget_entities_follow_budgets(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    registry = er.async_get(hass)
    addon.budgets[1]["archived"] = True
    addon.budgets.append(
        {
            "id": 3,
            "name": "Gifts",
            "percent": "5.00",
            "sort_order": 2,
            "archived": False,
            "created_at": "",
        }
    )
    await _refresh(hass, loaded)
    assert registry.async_get("sensor.payday_budget_fun_target") is None
    assert registry.async_get("binary_sensor.payday_budget_fun_over_target") is None
    assert registry.async_get("binary_sensor.payday_budget_fun_on_track") is None
    assert hass.states.get("sensor.payday_budget_fun_target") is None
    assert hass.states.get("sensor.payday_budget_gifts_target") is not None
    # Unarchive: the entities come back with the same IDs.
    addon.budgets[1]["archived"] = False
    await _refresh(hass, loaded)
    assert registry.async_get("sensor.payday_budget_fun_target") is not None


async def test_budget_rename_keeps_entity_id(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.budgets[0]["name"] = "Essentials"
    await _refresh(hass, loaded)
    state = hass.states.get("sensor.payday_budget_needs_target")
    assert state.attributes["friendly_name"] == "Payday Budget Essentials target"


async def test_entities_unavailable_when_addon_unreachable(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.unreachable = True
    await _refresh(hass, loaded)
    assert hass.states.get("sensor.payday_budget_income").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.payday_budget_needs_target").state == STATE_UNAVAILABLE
    addon.unreachable = False
    await _refresh(hass, loaded)
    assert hass.states.get("sensor.payday_budget_income").state == "3000.00"


async def test_no_current_period_before_setup(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.summary = None
    addon.budgets = []
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.payday_budget_period").state == STATE_UNKNOWN
    assert hass.states.get("sensor.payday_budget_income").state == STATE_UNKNOWN
    assert [s.entity_id for s in hass.states.async_all() if "_target" in s.entity_id] == []


async def test_currency_relabel_changes_unit(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.settings["currency"] = "USD"
    await _refresh(hass, loaded)
    assert hass.states.get("sensor.payday_budget_income").attributes["unit_of_measurement"] == "USD"


async def test_rejected_token_starts_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.errors[("GET", "settings")] = InvalidAuth()
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_monetary_value_is_exact_decimal(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    sensor = hass.data["sensor"].get_entity("sensor.payday_budget_needs_spent")
    assert sensor.native_value == Decimal("45.50")
    assert isinstance(sensor.native_value, Decimal)


async def test_unload(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(loaded.entry_id)
    assert loaded.state is ConfigEntryState.NOT_LOADED


async def test_BD3_on_track_sensor_and_direction_attributes(
    hass: HomeAssistant, loaded: MockConfigEntry, addon: FakeAddon
) -> None:
    needs = hass.states.get("binary_sensor.payday_budget_needs_on_track")
    assert (needs.state, needs.attributes["direction"], needs.attributes["status"]) == (
        STATE_ON,
        "negative",
        "ok",
    )
    fun = hass.states.get("binary_sensor.payday_budget_fun_on_track")
    assert (fun.state, fun.attributes["status"]) == (STATE_OFF, "over")
    target = hass.states.get("sensor.payday_budget_needs_target")
    assert target.attributes["direction"] == "negative"
    assert "direction" not in hass.states.get("sensor.payday_budget_needs_spent").attributes
    # A positive budget below its target: not on track, while over_target stays off.
    assert addon.summary is not None
    addon.summary["budgets"][0].update(direction="positive", status="below", on_track=False)
    await _refresh(hass, loaded)
    needs = hass.states.get("binary_sensor.payday_budget_needs_on_track")
    assert (needs.state, needs.attributes["status"]) == (STATE_OFF, "below")
    assert hass.states.get("binary_sensor.payday_budget_needs_over_target").state == STATE_OFF
    assert (
        hass.states.get("sensor.payday_budget_needs_target").attributes["direction"] == "positive"
    )

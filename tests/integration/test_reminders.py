"""v1.2 §4.4-§4.5: reminders sensor, notifications, options flow and actions."""

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.payday_budget.api import ApiError
from custom_components.payday_budget.const import CONF_NOTIFY_SERVICES, DOMAIN
from tests.integration.conftest import FakeAddon, occurrence

SENSOR = "sensor.payday_budget_reminders"


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


def _calls(addon: FakeAddon, method: str, path: str) -> list[dict[str, Any]]:
    return [c for c in addon.calls if c["method"] == method and c["path"] == path]


def _notifications(hass: HomeAssistant) -> dict[str, Any]:
    from homeassistant.components.persistent_notification import _async_get_or_create_notifications

    return dict(_async_get_or_create_notifications(hass))


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry, *, notify: list[str] | None = None
) -> MockConfigEntry:
    if notify is not None:
        hass.config_entries.async_update_entry(entry, options={CONF_NOTIFY_SERVICES: notify})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --- sensor --------------------------------------------------------------------


async def test_reminders_sensor(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.occurrences = [
        occurrence(1, "Electricity", "2026-11-02"),
        occurrence(2, "Credit card", "2026-11-10", amount_minor=25000, notified=True),
    ]
    await _setup(hass, entry)
    state = hass.states.get(SENSOR)
    assert state.state == "2"
    assert state.attributes["reminders"] == [
        {
            "id": 1,
            "reminder_id": 51,
            "name": "Electricity",
            "due_date": "2026-11-02",
            "kind": "expense",
            "amount": None,
            "currency": "EUR",
            "category": "Food",
            "budget": "Needs",
            "description": None,
        },
        {
            "id": 2,
            "reminder_id": 52,
            "name": "Credit card",
            "due_date": "2026-11-10",
            "kind": "expense",
            "amount": "250.00",
            "currency": "EUR",
            "category": "Food",
            "budget": "Needs",
            "description": None,
        },
    ]
    assert "reminders" in hass.data["sensor"].get_entity(SENSOR)._unrecorded_attributes


# --- notifications (RM7) ---------------------------------------------------------


async def test_RM7_new_occurrence_is_notified_once(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    pushes = async_mock_service(hass, "notify", "mobile_app_fold")
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "slug": "44f738b7_payday_budget"}
    )
    addon.occurrences = [occurrence(1, "Electricity", "2026-11-02")]
    await _setup(hass, entry, notify=["mobile_app_fold"])

    note = _notifications(hass)["payday_budget_reminder_1"]
    assert note["title"] == "Payday Budget: Electricity"
    assert "Due 2026-11-02. Enter the amount." in note["message"]
    assert "(/app/44f738b7_payday_budget)" in note["message"]
    assert len(pushes) == 1
    push: ServiceCall = pushes[0]
    assert push.data["title"] == "Payday Budget: Electricity"
    assert push.data["data"] == {
        "url": "/app/44f738b7_payday_budget",
        "clickAction": "/app/44f738b7_payday_budget",
    }
    assert len(_calls(addon, "POST", "reminders/occurrences/1/notified")) == 1

    await _refresh(hass, entry)  # the add-on now reports notified_at: no second push
    await _refresh(hass, entry)
    assert len(pushes) == 1
    assert len(_calls(addon, "POST", "reminders/occurrences/1/notified")) == 1


async def test_RM7_already_notified_occurrence_is_not_pushed_again(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    """After an HA restart: the persistent notification is shown again, without a push."""
    pushes = async_mock_service(hass, "notify", "mobile_app_fold")
    addon.occurrences = [
        occurrence(2, "Credit card", "2026-11-10", amount_minor=25000, notified=True)
    ]
    await _setup(hass, entry, notify=["mobile_app_fold"])
    note = _notifications(hass)["payday_budget_reminder_2"]
    assert "Due 2026-11-10. 250.00 EUR." in note["message"]
    assert pushes == []
    assert _calls(addon, "POST", "reminders/occurrences/2/notified") == []


async def test_RM7_closing_removes_the_persistent_notification(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.occurrences = [occurrence(1, "Electricity", "2026-11-02")]
    await _setup(hass, entry)
    assert "payday_budget_reminder_1" in _notifications(hass)
    addon.occurrences = []  # recorded or ignored elsewhere (e.g. in the app)
    await _refresh(hass, entry)
    assert "payday_budget_reminder_1" not in _notifications(hass)


async def test_RM7_without_notify_services_only_the_persistent_notification(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.occurrences = [occurrence(1, "Electricity", "2026-11-02")]
    await _setup(hass, entry)
    assert "payday_budget_reminder_1" in _notifications(hass)
    assert len(_calls(addon, "POST", "reminders/occurrences/1/notified")) == 1


async def test_RM7_missing_notify_service_is_skipped(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    pushes = async_mock_service(hass, "notify", "mobile_app_fold")
    addon.occurrences = [occurrence(1, "Electricity", "2026-11-02")]
    with patch("custom_components.payday_budget.notifications._LOGGER") as logger:
        await _setup(hass, entry, notify=["mobile_app_old_phone", "mobile_app_fold"])
    assert len(pushes) == 1
    logger.warning.assert_called_once_with(
        "Notify service notify.%s not found; skipped", "mobile_app_old_phone"
    )


async def test_RM7_without_a_slug_the_notification_has_no_link(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    """Manual setup (no discovery): no add-on slug, so no link to the app panel."""
    hass.config_entries.async_update_entry(
        entry, data={k: v for k, v in entry.data.items() if k != "slug"}
    )
    addon.occurrences = [occurrence(1, "Electricity", "2026-11-02")]
    await _setup(hass, entry)
    assert "/app/" not in _notifications(hass)["payday_budget_reminder_1"]["message"]


async def test_unload_dismisses_reminder_notifications(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.occurrences = [occurrence(1, "Electricity", "2026-11-02")]
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert "payday_budget_reminder_1" not in _notifications(hass)


# --- options flow (§4.5) -----------------------------------------------------------


async def test_options_flow_lists_notify_services(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    async_mock_service(hass, "notify", "mobile_app_fold")
    async_mock_service(hass, "notify", "persistent_notification")
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    selector = result["data_schema"].schema[CONF_NOTIFY_SERVICES]
    assert selector.config["options"] == ["mobile_app_fold"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NOTIFY_SERVICES: ["mobile_app_fold"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_NOTIFY_SERVICES: ["mobile_app_fold"]}


# --- actions (§4.4) -------------------------------------------------------------------


async def test_RM3_record_reminder_action(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.occurrences = [occurrence(1, "Electricity", "2026-11-02")]
    await _setup(hass, entry)
    response = await hass.services.async_call(
        DOMAIN,
        "record_reminder",
        {"occurrence": 1, "amount": "83.12", "budget": "fun"},
        blocking=True,
        return_response=True,
    )
    assert response == {"transaction_id": 120}
    assert _calls(addon, "POST", "reminders/occurrences/1/record")[-1]["json"] == {
        "amount_minor": 8312,
        "budget_id": 2,
    }
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "0"
    assert "payday_budget_reminder_1" not in _notifications(hass)


async def test_RM4_dismiss_reminder_action_and_closed_error(
    hass: HomeAssistant, entry: MockConfigEntry, addon: FakeAddon
) -> None:
    addon.occurrences = [occurrence(1, "Electricity", "2026-11-02")]
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "dismiss_reminder", {"occurrence": 1}, blocking=True)
    assert _calls(addon, "POST", "reminders/occurrences/1/dismiss")
    addon.occurrences = [occurrence(3, "Water", "2026-11-05")]
    addon.errors[("POST", "reminders/occurrences/3/dismiss")] = ApiError(
        422, "RM4", "This reminder was already recorded"
    )
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "dismiss_reminder", {"occurrence": 3}, blocking=True)
    assert err.value.translation_placeholders["code"] == "RM4"

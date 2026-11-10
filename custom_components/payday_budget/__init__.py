"""Payday Budget integration: entities, actions and WebSocket API for the add-on (§7)."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import PaydayBudgetClient
from .const import CONF_TOKEN, DOMAIN
from .coordinator import PaydayBudgetConfigEntry, PaydayBudgetCoordinator, PaydayBudgetRuntime
from .frontend import async_register_cards
from .notifications import ReminderNotifier
from .services import async_register_services
from .websocket import async_register_websocket_commands

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_services(hass)
    async_register_websocket_commands(hass)
    await async_register_cards(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PaydayBudgetConfigEntry) -> bool:
    client = PaydayBudgetClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_TOKEN],
    )
    coordinator = PaydayBudgetCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = PaydayBudgetRuntime(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # v1.2 §4.4: reminder notifications follow every refresh.
    notifier = ReminderNotifier(hass, entry)
    entry.async_on_unload(coordinator.async_add_listener(notifier.schedule))
    entry.async_on_unload(notifier.dismiss_all)
    notifier.schedule()
    # §7.1: refresh on every SSE `changed`; cancelled automatically on unload.
    entry.async_create_background_task(hass, coordinator.listen(), f"{DOMAIN}_events")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PaydayBudgetConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

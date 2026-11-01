"""Button (§7.2): start a new period dated today (P3)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import PaydayBudgetError
from .coordinator import PaydayBudgetConfigEntry, PaydayBudgetCoordinator
from .entity import PaydayBudgetEntity
from .helpers import actor_for, raise_for

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PaydayBudgetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([StartPeriodButton(entry.runtime_data.coordinator)])


class StartPeriodButton(PaydayBudgetEntity, ButtonEntity):
    _attr_translation_key = "start_new_period"

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "start_new_period")

    async def async_press(self) -> None:
        actor = await actor_for(self.hass, self._context)
        try:
            await self.coordinator.client.request("POST", "periods", json={}, actor=actor)
        except PaydayBudgetError as err:
            raise_for(err)
        await self.coordinator.async_request_refresh()

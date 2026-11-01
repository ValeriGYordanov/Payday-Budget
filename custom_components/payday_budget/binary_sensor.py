"""Binary sensors (§7.2): `<budget>_over_target`, on when spent > target."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PaydayBudgetConfigEntry, PaydayBudgetCoordinator
from .entity import BudgetEntity, track_budget_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PaydayBudgetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def over_target(coord: PaydayBudgetCoordinator, budget_id: int) -> list[Entity]:
        return [OverTargetSensor(coord, budget_id)]

    track_budget_entities(hass, entry, async_add_entities, over_target, "binary_sensor")


class OverTargetSensor(BudgetEntity, BinarySensorEntity):
    def __init__(self, coordinator: PaydayBudgetCoordinator, budget_id: int) -> None:
        super().__init__(coordinator, budget_id, "over_target")

    @property
    def is_on(self) -> bool | None:
        row = self.row
        return bool(row["over_target"]) if row else None

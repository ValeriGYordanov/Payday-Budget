"""Base entity and the dynamic per-budget entity manager (§7.1, §7.2)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SLUG, DOMAIN, NAME
from .coordinator import PaydayBudgetConfigEntry, PaydayBudgetCoordinator


class PaydayBudgetEntity(CoordinatorEntity[PaydayBudgetCoordinator]):
    """Single device "Payday Budget"; entity IDs come from device + entity name."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PaydayBudgetCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        slug = entry.data.get(CONF_SLUG)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer=NAME,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"homeassistant://hassio/ingress/{slug}" if slug else None,
        )


class BudgetEntity(PaydayBudgetEntity):
    """An entity for one budget; keyed by budget ID so renames keep the entity ID."""

    def __init__(self, coordinator: PaydayBudgetCoordinator, budget_id: int, kind: str) -> None:
        super().__init__(coordinator, f"budget_{budget_id}_{kind}")
        self.budget_id = budget_id
        self._attr_translation_key = f"budget_{kind}"

    def _budget_name(self) -> str:
        budget = next((b for b in self.coordinator.data.budgets if b["id"] == self.budget_id), None)
        return str(budget["name"]) if budget else str(self.budget_id)

    @property
    def name(self) -> str:
        """Translated template (e.g. "{budget} target") with the budget's current name.

        A plain property rather than translation placeholders: Entity.name is cached,
        and a renamed budget must rename its entities (the entity ID stays).
        """
        template = None
        if self.platform_data is not None and (key := self._name_translation_key):
            template = self.platform_data.platform_translations.get(key)
        return (template or "{budget}").format(budget=self._budget_name())

    @property
    def row(self) -> dict[str, Any] | None:
        """This budget's line in the current period summary."""
        return self.coordinator.data.budget_row(self.budget_id)


def track_budget_entities(
    hass: HomeAssistant,
    entry: PaydayBudgetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[PaydayBudgetCoordinator, int], list[Entity]],
    domain: str,
) -> None:
    """Add entities for new active budgets; remove them when a budget is archived or deleted."""
    coordinator = entry.runtime_data.coordinator
    known: set[int] = set()

    @callback
    def sync() -> None:
        active = {int(b["id"]) for b in coordinator.data.active_budgets()}
        new = active - known
        if new:
            async_add_entities(
                [entity for budget_id in sorted(new) for entity in factory(coordinator, budget_id)]
            )
            known.update(new)
        gone = known - active
        if gone:
            registry = er.async_get(hass)
            prefixes = tuple(f"{entry.entry_id}_budget_{budget_id}_" for budget_id in gone)
            for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
                if reg_entry.domain == domain and reg_entry.unique_id.startswith(prefixes):
                    registry.async_remove(reg_entry.entity_id)
            known.difference_update(gone)

    sync()
    entry.async_on_unload(coordinator.async_add_listener(sync))

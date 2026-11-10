"""Sensors (§7.2). Monetary sensors: device_class monetary, unit = currency, no state_class."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PaydayBudgetConfigEntry, PaydayBudgetCoordinator
from .entity import BudgetEntity, PaydayBudgetEntity, track_budget_entities
from .helpers import reminder_item, transaction_item
from .money import to_decimal, to_str

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PaydayBudgetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            PeriodSensor(coordinator),
            PeriodStartSensor(coordinator),
            TotalSensor(coordinator, "income", "income_minor"),
            TotalSensor(coordinator, "expenses", "expenses_minor"),
            TotalSensor(coordinator, "balance", "balance_minor"),
            UnallocatedSensor(coordinator),
            HistorySensor(coordinator),
            RecentTransactionsSensor(coordinator),
            CategoriesSensor(coordinator),
            BudgetsSensor(coordinator),
            RemindersSensor(coordinator),
        ]
    )

    def budget_sensors(coord: PaydayBudgetCoordinator, budget_id: int) -> list[Entity]:
        return [
            BudgetAmountSensor(coord, budget_id, "target", "target_minor"),
            BudgetAmountSensor(coord, budget_id, "spent", "spent_minor"),
            BudgetAmountSensor(coord, budget_id, "remaining", "remaining_minor"),
            BudgetUsedSensor(coord, budget_id),
        ]

    track_budget_entities(hass, entry, async_add_entities, budget_sensors, "sensor")


class PeriodSensor(PaydayBudgetEntity, SensorEntity):
    _attr_translation_key = "period"

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "period")

    @property
    def native_value(self) -> str | None:
        summary = self.coordinator.data.summary
        return str(summary["period"]["name"]) if summary else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        summary = self.coordinator.data.summary
        if summary is None:
            return None
        period = summary["period"]
        return {
            "start_date": period["start_date"],
            "days_elapsed": period["days_elapsed"],
            "period_id": period["id"],
        }


class PeriodStartSensor(PaydayBudgetEntity, SensorEntity):
    _attr_translation_key = "period_start"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "period_start")

    @property
    def native_value(self) -> dt.date | None:
        summary = self.coordinator.data.summary
        return dt.date.fromisoformat(summary["period"]["start_date"]) if summary else None


class MoneySensor(PaydayBudgetEntity, SensorEntity):
    """Exact Decimal state in major units; unit follows the install currency (K2)."""

    _attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_unit_of_measurement(self) -> str:
        return self.coordinator.data.currency

    @property
    def suggested_display_precision(self) -> int:
        return self.coordinator.data.minor_unit

    def money(self, minor: int | None) -> Decimal | None:
        return None if minor is None else to_decimal(minor, self.coordinator.data.minor_unit)


class TotalSensor(MoneySensor):
    def __init__(self, coordinator: PaydayBudgetCoordinator, key: str, field: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._field = field

    @property
    def native_value(self) -> Decimal | None:
        summary = self.coordinator.data.summary
        return self.money(summary[self._field]) if summary else None


class UnallocatedSensor(MoneySensor):
    _attr_translation_key = "unallocated"

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "unallocated")

    @property
    def native_value(self) -> Decimal | None:
        summary = self.coordinator.data.summary
        return self.money(summary["unallocated"]["amount_minor"]) if summary else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        summary = self.coordinator.data.summary
        return {"percent": summary["unallocated"]["percent"]} if summary else None


class HistorySensor(PaydayBudgetEntity, SensorEntity):
    """State: number of periods. `history` (last 12) is not recorded."""

    _attr_translation_key = "history"
    _unrecorded_attributes = frozenset({"history"})

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "history")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.period_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        unit = self.coordinator.data.minor_unit
        return {
            "history": [
                {
                    "name": item["period"]["name"],
                    "start_date": item["period"]["start_date"],
                    "end_date": item["period"]["end_date"],
                    "income": to_str(item["income_minor"], unit),
                    "expenses": to_str(item["expenses_minor"], unit),
                    "budgets": {
                        b["name"]: {
                            "target": to_str(b["target_minor"], unit),
                            "spent": to_str(b["spent_minor"], unit),
                        }
                        for b in item["budgets"]
                    },
                }
                for item in self.coordinator.data.history
            ]
        }


class RecentTransactionsSensor(PaydayBudgetEntity, SensorEntity):
    """v1.1 §4.1. State: transactions in the current period (RT3). Newest N not recorded."""

    _attr_translation_key = "recent_transactions"
    _unrecorded_attributes = frozenset({"transactions"})

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "recent_transactions")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.current_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "transactions": [
                transaction_item(t, data.currency, data.minor_unit) for t in data.recent
            ]
        }


class CategoriesSensor(PaydayBudgetEntity, SensorEntity):
    """v1.1 §4.2. State: non-archived categories; all of them in the app's order (D10)."""

    _attr_translation_key = "categories"
    _unrecorded_attributes = frozenset({"categories"})

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "categories")

    @property
    def native_value(self) -> int:
        return sum(1 for c in self.coordinator.data.categories if not c["archived"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        fields = ("id", "name", "kind", "icon", "archived", "transaction_count")
        return {"categories": [{f: c[f] for f in fields} for c in self.coordinator.data.categories]}


class BudgetsSensor(PaydayBudgetEntity, SensorEntity):
    """v1.1 §4.5 (BS1). State: non-archived budgets; all of them in the app's order."""

    _attr_translation_key = "budgets"
    _unrecorded_attributes = frozenset({"budgets"})

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "budgets")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.active_budgets())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        fields = ("id", "name", "percent", "direction", "archived", "sort_order")
        return {"budgets": [{f: b[f] for f in fields} for b in self.coordinator.data.budgets]}


class RemindersSensor(PaydayBudgetEntity, SensorEntity):
    """v1.2 §4.4. State: open reminder occurrences; `reminders` lists them (unrecorded)."""

    _attr_translation_key = "reminders"
    _unrecorded_attributes = frozenset({"reminders"})

    def __init__(self, coordinator: PaydayBudgetCoordinator) -> None:
        super().__init__(coordinator, "reminders")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.reminders)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "reminders": [reminder_item(o, data.currency, data.minor_unit) for o in data.reminders]
        }


class BudgetAmountSensor(BudgetEntity, MoneySensor):
    def __init__(
        self, coordinator: PaydayBudgetCoordinator, budget_id: int, kind: str, field: str
    ) -> None:
        super().__init__(coordinator, budget_id, kind)
        self._field = field

    @property
    def native_value(self) -> Decimal | None:
        row = self.row
        return self.money(row[self._field]) if row else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """v1.2 §3.4: the target carries the budget's direction."""
        row = self.row
        if self._field != "target_minor" or row is None:
            return None
        return {"direction": row["direction"]}


class BudgetUsedSensor(BudgetEntity, SensorEntity):
    """percent_used; unavailable when the target is 0 (B5)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: PaydayBudgetCoordinator, budget_id: int) -> None:
        super().__init__(coordinator, budget_id, "used")

    @property
    def available(self) -> bool:
        row = self.row
        return super().available and (row is None or row["percent_used"] is not None)

    @property
    def native_value(self) -> Decimal | None:
        row = self.row
        if row is None or row["percent_used"] is None:
            return None
        return Decimal(row["percent_used"])

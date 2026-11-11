"""Data coordinator (§7.1): loads on start, refreshes on SSE `changed`, polls every 5 min."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, CannotConnect, InvalidAuth, PaydayBudgetClient
from .const import DOMAIN, HISTORY_LIMIT, RECENT_LIMIT, SCAN_INTERVAL, SSE_BACKOFF_MAX_SECONDS

_LOGGER = logging.getLogger(__name__)

type PaydayBudgetConfigEntry = ConfigEntry[PaydayBudgetRuntime]


@dataclass
class PaydayBudgetData:
    settings: dict[str, Any]
    summary: dict[str, Any] | None  # None before the first period exists
    budgets: list[dict[str, Any]]
    period_count: int
    history: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    recent: list[dict[str, Any]]  # newest RECENT_LIMIT transactions, any period
    current_count: int | None  # transactions in the current period; None without one
    reminders: list[dict[str, Any]]  # open reminder occurrences (v1.2 §4.4)
    forecast: dict[str, Any] | None  # v1.3; None without a current period

    @property
    def currency(self) -> str:
        return str(self.settings["currency"])

    @property
    def minor_unit(self) -> int:
        return int(self.settings["minor_unit"])

    def active_budgets(self) -> list[dict[str, Any]]:
        return [b for b in self.budgets if not b["archived"]]

    def budget_row(self, budget_id: int) -> dict[str, Any] | None:
        if self.summary is None:
            return None
        return next((r for r in self.summary["budgets"] if r["budget_id"] == budget_id), None)


@dataclass
class PaydayBudgetRuntime:
    client: PaydayBudgetClient
    coordinator: PaydayBudgetCoordinator


class PaydayBudgetCoordinator(DataUpdateCoordinator[PaydayBudgetData]):
    config_entry: PaydayBudgetConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: PaydayBudgetConfigEntry, client: PaydayBudgetClient
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.client = client

    async def _async_update_data(self) -> PaydayBudgetData:
        try:
            (
                settings,
                budgets,
                periods,
                history,
                categories,
                recent,
                reminders,
            ) = await asyncio.gather(
                self.client.get("settings"),
                self.client.get("budgets"),
                self.client.get("periods"),
                self.client.get("periods/history", limit=HISTORY_LIMIT),
                self.client.get("categories"),
                self.client.get("transactions", limit=RECENT_LIMIT),
                self.client.get("reminders/occurrences", status="open"),
            )
            try:
                summary, current, forecast = await asyncio.gather(
                    self.client.get("summary", period="current"),
                    self.client.get("transactions", period="current", limit=1),
                    self.client.get("forecast"),
                )
            except ApiError as err:
                if err.status != 404:
                    raise
                summary = current = forecast = None
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("The add-on rejected the token") from err
        except (CannotConnect, ApiError) as err:
            raise UpdateFailed(f"Payday Budget add-on unavailable: {err}") from err
        return PaydayBudgetData(
            settings=settings,
            summary=summary,
            budgets=budgets["items"],
            period_count=len(periods["items"]),
            history=history["items"],
            categories=categories["items"],
            recent=recent["items"],
            current_count=None if current is None else int(current["total"]),
            reminders=reminders["items"],
            forecast=forecast,
        )

    async def listen(self) -> None:
        """Keep the SSE stream open; refresh on `changed`; reconnect with backoff."""
        backoff = 1
        while True:
            try:
                async for event in self.client.events():
                    backoff = 1
                    if event == "changed":
                        await self.async_request_refresh()
            except InvalidAuth:
                _LOGGER.debug("Event stream rejected the token")
            except CannotConnect as err:
                _LOGGER.debug("Event stream disconnected: %s", err)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, SSE_BACKOFF_MAX_SECONDS)

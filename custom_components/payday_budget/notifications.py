"""Reminder notifications (v1.2 §4.4, RM7).

Every open occurrence has a persistent notification while it is open (HA does not keep
them across restarts, so they are shown again then). Each occurrence is pushed once, through
the notify services chosen in the options, and then marked notified in the add-on.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .api import PaydayBudgetError
from .const import CONF_NOTIFY_SERVICES, CONF_SLUG, NAME
from .coordinator import PaydayBudgetConfigEntry
from .money import to_str

_LOGGER = logging.getLogger(__name__)

NOTIFY_DOMAIN = "notify"


def notification_id(occurrence_id: int) -> str:
    return f"payday_budget_reminder_{occurrence_id}"


class ReminderNotifier:
    def __init__(self, hass: HomeAssistant, entry: PaydayBudgetConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._shown: set[int] = set()
        self._pushed: set[int] = set()  # pushed this run, in case marking notified failed
        self._lock = asyncio.Lock()

    @callback
    def schedule(self) -> None:
        """Coordinator listener: process the latest open occurrences."""
        self.entry.async_create_background_task(
            self.hass, self.async_process(), "payday_budget_reminder_notifications"
        )

    def _link(self) -> str | None:
        slug = self.entry.data.get(CONF_SLUG)
        return f"/app/{slug}" if slug else None

    def _text(self, occurrence: dict[str, Any]) -> tuple[str, str]:
        data = self.entry.runtime_data.coordinator.data
        amount = occurrence["prefill"]["amount_minor"]
        detail = (
            f"{to_str(amount, data.minor_unit)} {data.currency}"
            if amount is not None
            else "Enter the amount"
        )
        return f"{NAME}: {occurrence['name']}", f"Due {occurrence['due_date']}. {detail}."

    async def async_process(self) -> None:
        async with self._lock:
            runtime = self.entry.runtime_data
            occurrences = {o["id"]: o for o in runtime.coordinator.data.reminders}
            for closed in self._shown - occurrences.keys():
                persistent_notification.async_dismiss(self.hass, notification_id(closed))
            self._shown &= occurrences.keys()
            link = self._link()
            for occurrence_id, occurrence in occurrences.items():
                title, message = self._text(occurrence)
                if occurrence_id not in self._shown:
                    body = f"{message}\n\n[Open {NAME}]({link})" if link else message
                    persistent_notification.async_create(
                        self.hass, body, title=title, notification_id=notification_id(occurrence_id)
                    )
                    self._shown.add(occurrence_id)
                if occurrence["notified_at"] is None and occurrence_id not in self._pushed:
                    await self._push(title, message, link)
                    self._pushed.add(occurrence_id)
                    try:
                        await runtime.client.request(
                            "POST", f"reminders/occurrences/{occurrence_id}/notified", json={}
                        )
                    except PaydayBudgetError as err:
                        _LOGGER.warning(
                            "Could not mark reminder %s notified: %s", occurrence_id, err
                        )

    async def _push(self, title: str, message: str, link: str | None) -> None:
        data: dict[str, Any] = {"title": title, "message": message}
        if link:
            data["data"] = {"url": link, "clickAction": link}  # iOS / Android companion app
        for service in self.entry.options.get(CONF_NOTIFY_SERVICES, []):
            if not self.hass.services.has_service(NOTIFY_DOMAIN, service):
                _LOGGER.warning("Notify service notify.%s not found; skipped", service)
                continue
            try:
                await self.hass.services.async_call(NOTIFY_DOMAIN, service, data, blocking=True)
            except HomeAssistantError as err:
                _LOGGER.warning("Reminder push via notify.%s failed: %s", service, err)

    @callback
    def dismiss_all(self) -> None:
        for occurrence_id in self._shown:
            persistent_notification.async_dismiss(self.hass, notification_id(occurrence_id))
        self._shown.clear()

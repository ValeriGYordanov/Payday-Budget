"""WebSocket commands for the cards (§7.4), proxied to the add-on API.

Responses are the add-on's JSON unchanged (integer minor units), as the charts expect.
"""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import ApiError, PaydayBudgetError
from .const import DOMAIN, HISTORY_LIMIT
from .coordinator import PaydayBudgetConfigEntry
from .helpers import resolve_budget, resolve_period

PERIOD = probatio.Any(int, str)


def _entry(hass: HomeAssistant) -> PaydayBudgetConfigEntry | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0] if entries else None


async def _proxy(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    path: str,
    params: dict[str, Any],
) -> None:
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Payday Budget is not set up")
        return
    client = entry.runtime_data.client
    try:
        if "period" in params:
            params["period"] = await resolve_period(client, params["period"])
        if params.get("budget") is not None:
            params["budget"] = await resolve_budget(client, params["budget"])
        result = await client.get(path, **params)
    except ApiError as err:
        connection.send_error(msg["id"], err.code, err.message)
        return
    except (PaydayBudgetError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "unavailable", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/summary",
        probatio.Optional("period", default="current"): PERIOD,
    }
)
@websocket_api.async_response
async def ws_summary(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    await _proxy(hass, connection, msg, "summary", {"period": msg["period"]})


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/history",
        probatio.Optional("limit", default=HISTORY_LIMIT): probatio.All(
            int, probatio.Range(min=1, max=120)
        ),
    }
)
@websocket_api.async_response
async def ws_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    await _proxy(hass, connection, msg, "periods/history", {"limit": msg["limit"]})


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/breakdown",
        probatio.Optional("period", default="current"): PERIOD,
        probatio.Optional("budget"): probatio.Any(None, int, str),
    }
)
@websocket_api.async_response
async def ws_breakdown(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    await _proxy(
        hass, connection, msg, "breakdown", {"period": msg["period"], "budget": msg.get("budget")}
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/daily",
        probatio.Optional("period", default="current"): PERIOD,
    }
)
@websocket_api.async_response
async def ws_daily(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    await _proxy(hass, connection, msg, "daily", {"period": msg["period"]})


@websocket_api.websocket_command({probatio.Required("type"): f"{DOMAIN}/forecast"})
@websocket_api.async_response
async def ws_forecast(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """v1.3: the current period's forecast for the cards."""
    await _proxy(hass, connection, msg, "forecast", {})


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    for command in (ws_summary, ws_history, ws_breakdown, ws_daily, ws_forecast):
        websocket_api.async_register_command(hass, command)

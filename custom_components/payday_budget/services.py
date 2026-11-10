"""Actions (§7.3). Amounts are major units; category / budget accept a name or an id."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import PaydayBudgetClient, PaydayBudgetError
from .const import DOMAIN
from .coordinator import PaydayBudgetConfigEntry
from .helpers import (
    actor_for,
    find_category,
    raise_for,
    resolve_budget,
    resolve_category,
    resolve_category_for_update,
    resolve_period,
    resolve_tag,
    transaction_item,
)
from .money import parse_amount, to_str

KINDS = probatio.In(["income", "expense"])
AMOUNT = probatio.Any(int, float, cv.string)  # converted exactly by money.parse_amount
ID_OR_NAME = probatio.Any(int, cv.string)
OPTIONAL_FIELDS: dict[Any, Any] = {
    probatio.Optional("budget"): probatio.Any(None, ID_OR_NAME),
    probatio.Optional("date"): cv.date,
    probatio.Optional("description"): probatio.Any(
        None, probatio.All(cv.string, probatio.Length(max=500))
    ),
    probatio.Optional("tags"): probatio.All(cv.ensure_list, [cv.string]),
}

ADD_SCHEMA = probatio.Schema(
    {
        probatio.Required("kind"): KINDS,
        probatio.Required("amount"): AMOUNT,
        probatio.Required("category"): ID_OR_NAME,
        **OPTIONAL_FIELDS,
    }
)
UPDATE_SCHEMA = probatio.Schema(
    {
        probatio.Required("id"): probatio.Coerce(int),
        probatio.Optional("kind"): KINDS,
        probatio.Optional("amount"): AMOUNT,
        probatio.Optional("category"): ID_OR_NAME,
        **OPTIONAL_FIELDS,
    }
)
DELETE_SCHEMA = probatio.Schema({probatio.Required("id"): probatio.Coerce(int)})
START_PERIOD_SCHEMA = probatio.Schema(
    {
        probatio.Optional("date"): cv.date,
        probatio.Optional("name"): probatio.All(cv.string, probatio.Length(max=100)),
    }
)
SUMMARY_SCHEMA = probatio.Schema({probatio.Optional("period", default="current"): cv.string})
LIST_SCHEMA = probatio.Schema(
    {
        probatio.Optional("period"): cv.string,
        probatio.Optional("date_from"): cv.date,
        probatio.Optional("date_to"): cv.date,
        probatio.Optional("kind"): KINDS,
        probatio.Optional("category"): ID_OR_NAME,
        probatio.Optional("budget"): ID_OR_NAME,
        probatio.Optional("tag"): ID_OR_NAME,
        probatio.Optional("user"): cv.string,
        probatio.Optional("search"): cv.string,
        probatio.Optional("limit", default=100): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1, max=500)
        ),
        probatio.Optional("offset", default=0): probatio.All(
            probatio.Coerce(int), probatio.Range(min=0)
        ),
    }
)
CATEGORY_NAME = probatio.All(cv.string, probatio.Length(min=1, max=100))
ADD_CATEGORY_SCHEMA = probatio.Schema(
    {
        probatio.Required("name"): CATEGORY_NAME,
        probatio.Required("kind"): KINDS,
        probatio.Optional("icon", default="mdi:tag"): cv.string,
    }
)
UPDATE_CATEGORY_SCHEMA = probatio.Schema(
    {
        probatio.Required("category"): ID_OR_NAME,
        probatio.Optional("kind"): KINDS,
        probatio.Optional("name"): CATEGORY_NAME,
        probatio.Optional("icon"): cv.string,
        probatio.Optional("archived"): cv.boolean,
    }
)
DELETE_CATEGORY_SCHEMA = probatio.Schema(
    {probatio.Required("category"): ID_OR_NAME, probatio.Optional("kind"): KINDS}
)


def _entry(hass: HomeAssistant) -> PaydayBudgetConfigEntry:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries or entries[0].state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    entry: PaydayBudgetConfigEntry = entries[0]
    return entry


def _amount_minor(hass_entry: PaydayBudgetConfigEntry, value: object) -> int:
    minor_unit = hass_entry.runtime_data.coordinator.data.minor_unit
    minor = parse_amount(value, minor_unit)
    if minor is None or minor <= 0:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_amount",
            translation_placeholders={"amount": str(value), "digits": str(minor_unit)},
        )
    return minor


async def _body(
    client: PaydayBudgetClient,
    entry: PaydayBudgetConfigEntry,
    data: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    """Translate action fields into the add-on's transaction body."""
    body: dict[str, Any] = {}
    if "kind" in data:
        body["kind"] = data["kind"]
    if "amount" in data:
        body["amount_minor"] = _amount_minor(entry, data["amount"])
    if "category" in data:
        body["category_id"] = await resolve_category(client, data["category"], kind)
    if "budget" in data:
        body["budget_id"] = (
            None if data["budget"] in (None, "") else await resolve_budget(client, data["budget"])
        )
    elif data.get("kind") == "income":
        body["budget_id"] = None  # B6: incomes have no budget
    if "date" in data:
        body["date"] = data["date"].isoformat()
    if "description" in data:
        body["description"] = data["description"] or None
    if "tags" in data:
        body["tags"] = data["tags"]
    return body


async def _add(call: ServiceCall) -> ServiceResponse:
    entry = _entry(call.hass)
    client = entry.runtime_data.client
    try:
        body = await _body(client, entry, dict(call.data), call.data["kind"])
        result = await client.request(
            "POST", "transactions", json=body, actor=await actor_for(call.hass, call.context)
        )
    except PaydayBudgetError as err:
        raise_for(err)
    await entry.runtime_data.coordinator.async_request_refresh()
    return {"id": result["id"]}


async def _update(call: ServiceCall) -> ServiceResponse:
    entry = _entry(call.hass)
    client = entry.runtime_data.client
    try:
        current = await client.get(f"transactions/{call.data['id']}")
        kind = call.data.get("kind", current["kind"])
        body = await _body(client, entry, dict(call.data), kind)
        result = await client.request(
            "PATCH",
            f"transactions/{call.data['id']}",
            json=body,
            actor=await actor_for(call.hass, call.context),
        )
    except PaydayBudgetError as err:
        raise_for(err)
    await entry.runtime_data.coordinator.async_request_refresh()
    return {"id": result["id"]}


async def _delete(call: ServiceCall) -> None:
    entry = _entry(call.hass)
    try:
        await entry.runtime_data.client.request("DELETE", f"transactions/{call.data['id']}")
    except PaydayBudgetError as err:
        raise_for(err)
    await entry.runtime_data.coordinator.async_request_refresh()


async def _start_period(call: ServiceCall) -> ServiceResponse:
    entry = _entry(call.hass)
    body: dict[str, Any] = {}
    if "date" in call.data:
        body["start_date"] = call.data["date"].isoformat()
    if "name" in call.data:
        body["name"] = call.data["name"]
    try:
        result = await entry.runtime_data.client.request(
            "POST", "periods", json=body, actor=await actor_for(call.hass, call.context)
        )
    except PaydayBudgetError as err:
        raise_for(err)
    await entry.runtime_data.coordinator.async_request_refresh()
    return {"id": result["id"], "name": result["name"]}


def summary_response(summary: dict[str, Any]) -> dict[str, Any]:
    """The add-on summary with money as exact decimal strings (HA JSON has no Decimal)."""
    unit = int(summary["minor_unit"])

    def money(minor: int) -> str:
        return to_str(minor, unit)

    return {
        "period": summary["period"],
        "currency": summary["currency"],
        "income": money(summary["income_minor"]),
        "expenses": money(summary["expenses_minor"]),
        "balance": money(summary["balance_minor"]),
        "unallocated": {
            "percent": summary["unallocated"]["percent"],
            "amount": money(summary["unallocated"]["amount_minor"]),
        },
        "budgets": [
            {
                "budget_id": b["budget_id"],
                "name": b["name"],
                "archived": b["archived"],
                "percent": b["percent"],
                "target": money(b["target_minor"]),
                "spent": money(b["spent_minor"]),
                "remaining": money(b["remaining_minor"]),
                "percent_used": b["percent_used"],
                "over_target": b["over_target"],
                "direction": b["direction"],
                "status": b["status"],
                "on_track": b["on_track"],
            }
            for b in summary["budgets"]
        ],
    }


async def _get_summary(call: ServiceCall) -> ServiceResponse:
    entry = _entry(call.hass)
    client = entry.runtime_data.client
    try:
        period = await resolve_period(client, call.data["period"])
        summary = await client.get("summary", period=period)
    except PaydayBudgetError as err:
        raise_for(err)
    return summary_response(summary)


async def _list_transactions(call: ServiceCall) -> ServiceResponse:
    """v1.1 §4.3 (TL1): each filter maps to the add-on's filter of the same meaning."""
    entry = _entry(call.hass)
    client = entry.runtime_data.client
    data = call.data
    params: dict[str, Any] = {"limit": data["limit"], "offset": data["offset"]}
    try:
        if "period" in data:
            params["period"] = await resolve_period(client, data["period"])
        for field in ("date_from", "date_to"):
            if field in data:
                params[field] = data[field].isoformat()
        if "kind" in data:
            params["kind"] = data["kind"]
        if "category" in data:
            params["category"] = await resolve_category(client, data["category"], data.get("kind"))
        if "budget" in data:
            params["budget"] = await resolve_budget(client, data["budget"])
        if "tag" in data:
            params["tag"] = await resolve_tag(client, data["tag"])
        if "user" in data:
            params["user"] = data["user"]
        if "search" in data:
            params["q"] = data["search"]
        result = await client.get("transactions", **params)
    except PaydayBudgetError as err:
        raise_for(err)
    coordinator_data = entry.runtime_data.coordinator.data
    return {
        "total": result["total"],
        "limit": result["limit"],
        "offset": result["offset"],
        "items": [
            transaction_item(t, coordinator_data.currency, coordinator_data.minor_unit)
            for t in result["items"]
        ],
    }


async def _add_category(call: ServiceCall) -> ServiceResponse:
    entry = _entry(call.hass)
    body = {"name": call.data["name"], "kind": call.data["kind"], "icon": call.data["icon"]}
    try:
        result = await entry.runtime_data.client.request("POST", "categories", json=body)
    except PaydayBudgetError as err:
        raise_for(err)
    await entry.runtime_data.coordinator.async_request_refresh()
    return {"id": result["id"]}


async def _update_category(call: ServiceCall) -> ServiceResponse:
    entry = _entry(call.hass)
    client = entry.runtime_data.client
    try:
        category, kind_changes = await resolve_category_for_update(
            client, call.data["category"], call.data.get("kind")
        )
        body = {f: call.data[f] for f in ("name", "icon", "archived") if f in call.data}
        if kind_changes:
            body["kind"] = call.data["kind"]
        result = await client.request("PATCH", f"categories/{category['id']}", json=body)
    except PaydayBudgetError as err:
        raise_for(err)
    await entry.runtime_data.coordinator.async_request_refresh()
    return {"id": result["id"]}


async def _delete_category(call: ServiceCall) -> None:
    entry = _entry(call.hass)
    client = entry.runtime_data.client
    try:
        category = await find_category(client, call.data["category"], call.data.get("kind"))
        await client.request("DELETE", f"categories/{category['id']}")
    except PaydayBudgetError as err:
        raise_for(err)
    await entry.runtime_data.coordinator.async_request_refresh()


def async_register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN, "add_transaction", _add, ADD_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, "update_transaction", _update, UPDATE_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(DOMAIN, "delete_transaction", _delete, DELETE_SCHEMA)
    hass.services.async_register(
        DOMAIN, "start_period", _start_period, START_PERIOD_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, "get_summary", _get_summary, SUMMARY_SCHEMA, SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, "list_transactions", _list_transactions, LIST_SCHEMA, SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, "add_category", _add_category, ADD_CATEGORY_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN,
        "update_category",
        _update_category,
        UPDATE_CATEGORY_SCHEMA,
        SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "delete_category", _delete_category, DELETE_CATEGORY_SCHEMA
    )

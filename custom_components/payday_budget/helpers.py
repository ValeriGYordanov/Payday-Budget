"""Shared helpers for actions, the button and WebSocket commands."""

from __future__ import annotations

from typing import Any, NoReturn

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .api import Actor, ApiError, CannotConnect, InvalidAuth, PaydayBudgetClient
from .const import DOMAIN


async def actor_for(hass: HomeAssistant, context: Context | None) -> Actor:
    """T3: the HA user behind a call; automations have none."""
    user_id = context.user_id if context else None
    if not user_id:
        return Actor(None, None)
    user = await hass.auth.async_get_user(user_id)
    return Actor(user_id, user.name if user else None)


def raise_for(err: Exception) -> NoReturn:
    """Map add-on errors to HA errors; rule violations carry the rule ID (§7.3)."""
    if isinstance(err, ApiError):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="rule_violation",
            translation_placeholders={"code": err.code, "message": err.message},
        ) from err
    if isinstance(err, InvalidAuth):
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="invalid_auth") from err
    if isinstance(err, CannotConnect):
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    raise err


async def resolve_period(client: PaydayBudgetClient, ref: str | int | None) -> str:
    """`current` / `previous` / id -> the add-on's `current` or an id (previous: before current)."""
    if ref is None or ref == "current":
        return "current"
    if ref == "previous":
        periods: list[dict[str, Any]] = (await client.get("periods"))["items"]  # newest first
        index = next((i for i, p in enumerate(periods) if p["is_current"]), None)
        if index is None or index + 1 >= len(periods):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_previous_period"
            )
        return str(periods[index + 1]["id"])
    text = str(ref).strip()
    if not text.isdigit():
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_period",
            translation_placeholders={"period": text},
        )
    return text


def _match(items: list[dict[str, Any]], ref: str | int) -> dict[str, Any] | None:
    """Ints are IDs; text matches a name (case-insensitive), then a numeric ID."""
    if isinstance(ref, int) and not isinstance(ref, bool):
        return next((i for i in items if i["id"] == ref), None)
    text = str(ref).strip()
    folded = text.casefold()
    found = next((i for i in items if str(i["name"]).casefold() == folded), None)
    if found is None and text.isdigit():
        found = next((i for i in items if i["id"] == int(text)), None)
    return found


async def resolve_category(client: PaydayBudgetClient, ref: str | int, kind: str) -> int:
    items = (await client.get("categories", kind=kind))["items"]
    found = _match(items, ref)
    if found is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_category",
            translation_placeholders={"category": str(ref), "kind": kind},
        )
    return int(found["id"])


async def resolve_budget(client: PaydayBudgetClient, ref: str | int) -> int:
    items = (await client.get("budgets"))["items"]
    found = _match(items, ref)
    if found is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_budget",
            translation_placeholders={"budget": str(ref)},
        )
    return int(found["id"])

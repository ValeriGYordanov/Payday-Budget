"""Shared helpers for actions, the button and WebSocket commands."""

from __future__ import annotations

from typing import Any, NoReturn

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .api import Actor, ApiError, CannotConnect, InvalidAuth, PaydayBudgetClient
from .const import DOMAIN
from .money import to_str


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


def _matches(items: list[dict[str, Any]], ref: str | int) -> list[dict[str, Any]]:
    """Ints are IDs; text matches names (case-insensitive), else a numeric ID."""
    if isinstance(ref, int) and not isinstance(ref, bool):
        return [i for i in items if i["id"] == ref]
    text = str(ref).strip()
    folded = text.casefold()
    found = [i for i in items if str(i["name"]).casefold() == folded]
    if not found and text.isdigit():
        found = [i for i in items if i["id"] == int(text)]
    return found


def _unknown_category(ref: str | int, kind: str | None) -> ServiceValidationError:
    if kind is None:
        return ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_category_any",
            translation_placeholders={"category": str(ref)},
        )
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_category",
        translation_placeholders={"category": str(ref), "kind": kind},
    )


def _ambiguous(key: str, ref: str | int) -> ServiceValidationError:
    """D9 / TL3: more than one match -> error; nothing is called."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=f"ambiguous_{key}",
        translation_placeholders={key: str(ref)},
    )


async def find_category(
    client: PaydayBudgetClient, ref: str | int, kind: str | None
) -> dict[str, Any]:
    """A category by name or id, within `kind` when given (archived ones included)."""
    params = {} if kind is None else {"kind": kind}
    found = _matches((await client.get("categories", **params))["items"], ref)
    if not found:
        raise _unknown_category(ref, kind)
    if len(found) > 1:
        raise _ambiguous("category", ref)
    return found[0]


async def resolve_category(client: PaydayBudgetClient, ref: str | int, kind: str | None) -> int:
    return int((await find_category(client, ref, kind))["id"])


async def resolve_category_for_update(
    client: PaydayBudgetClient, ref: str | int, kind: str | None
) -> tuple[dict[str, Any], bool]:
    """D8: the category to update, and whether `kind` asks for a kind change.

    By id, `kind` changes the kind. By name, a match in `kind` selects that
    category (no change); a name only in the other kind is changed to `kind`.
    """
    items: list[dict[str, Any]] = (await client.get("categories"))["items"]
    found = _matches(items, ref)
    if kind is not None and len(found) > 1:
        found = [c for c in found if c["kind"] == kind] or found
    if not found:
        raise _unknown_category(ref, None)
    if len(found) > 1:
        raise _ambiguous("category", ref)
    category = found[0]
    return category, kind is not None and kind != category["kind"]


async def resolve_budget(client: PaydayBudgetClient, ref: str | int) -> int:
    found = _matches((await client.get("budgets"))["items"], ref)
    if not found:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_budget",
            translation_placeholders={"budget": str(ref)},
        )
    if len(found) > 1:
        raise _ambiguous("budget", ref)
    return int(found[0]["id"])


async def resolve_tag(client: PaydayBudgetClient, ref: str | int) -> int:
    found = _matches((await client.get("tags"))["items"], ref)
    if not found:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_tag",
            translation_placeholders={"tag": str(ref)},
        )
    if len(found) > 1:
        raise _ambiguous("tag", ref)
    return int(found[0]["id"])


def transaction_item(transaction: dict[str, Any], currency: str, minor_unit: int) -> dict[str, Any]:
    """A transaction in the v1.1 §4.1 shape; money as an exact decimal string (RT2)."""
    return {
        "id": transaction["id"],
        "date": transaction["date"],
        "kind": transaction["kind"],
        "amount": to_str(transaction["amount_minor"], minor_unit),
        "currency": currency,
        "category": transaction["category_name"],
        "category_id": transaction["category_id"],
        "budget": transaction["budget_name"],
        "budget_id": transaction["budget_id"],
        "description": transaction["description"],
        "tags": transaction["tags"],
        "created_by": transaction["created_by_name"],
        "recurring": transaction["recurring_rule_id"] is not None,
    }

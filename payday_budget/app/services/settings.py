"""Install settings and currency (§5.6)."""

from typing import Any

from sqlalchemy.orm import Session

from app import currency
from app.errors import RuleViolation
from app.models import Settings


def get(session: Session) -> Settings:
    settings = session.get(Settings, 1)
    assert settings is not None, "settings row is created by the initial migration"
    return settings


def check_currency(code: str) -> str:
    """K1: one ISO 4217 currency per install."""
    normalized = code.strip().upper()
    if currency.exponent(normalized) is None:
        raise RuleViolation("K1", f"{code!r} is not an ISO 4217 currency code", field="currency")
    return normalized


def change_currency(session: Session, code: str, *, confirm: bool) -> Settings:
    """K2: relabel only, same exponent only, explicit confirmation required."""
    settings = get(session)
    new_code = check_currency(code)
    if new_code == settings.currency:
        return settings
    if currency.exponent(new_code) != currency.exponent(settings.currency):
        raise RuleViolation(
            "K2",
            f"{new_code} has a different minor-unit exponent than {settings.currency}",
            field="currency",
        )
    if not confirm:
        raise RuleViolation(
            "K2", "Changing the currency relabels all amounts; set confirm to true", field="confirm"
        )
    settings.currency = new_code
    session.flush()
    return settings


def serialize(settings: Settings) -> dict[str, Any]:
    return {
        "currency": settings.currency,
        "minor_unit": currency.exponent(settings.currency),
        "setup_completed": settings.setup_completed,
    }

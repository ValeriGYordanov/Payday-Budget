"""Money conversions. Integer minor units on the wire; exact Decimal in HA. No floats."""

import re
from decimal import Decimal

_AMOUNT_RE = re.compile(r"^\d+(?:\.(\d+))?$")


def to_decimal(minor: int, minor_unit: int) -> Decimal:
    """1250 (2) -> Decimal('12.50')."""
    return Decimal(minor).scaleb(-minor_unit).quantize(Decimal(1).scaleb(-minor_unit))


def to_str(minor: int, minor_unit: int) -> str:
    """Exact decimal string for attributes and responses (HA's JSON has no Decimal)."""
    return str(to_decimal(minor, minor_unit))


def parse_amount(value: object, minor_unit: int) -> int | None:
    """Major units (number or string) -> minor units; None if invalid or too precise."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        # repr gives the shortest exact round-trip text, e.g. 12.5 -> "12.5".
        text = repr(value)
    elif isinstance(value, (int, str, Decimal)):
        text = str(value).strip()
    else:
        return None
    match = _AMOUNT_RE.match(text)
    if not match:
        return None
    if len(match.group(1) or "") > minor_unit:
        return None
    return int(Decimal(text).scaleb(minor_unit))

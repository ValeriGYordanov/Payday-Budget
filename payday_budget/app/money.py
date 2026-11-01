"""Integer money and percent arithmetic. No floats.

Percents are stored as integer hundredths ("basis points": 5025 == 50.25 %).
"""

import re
from decimal import ROUND_HALF_UP, Decimal

PERCENT_SCALE = 100
FULL_PERCENT_BP = 100 * PERCENT_SCALE
_PERCENT_RE = re.compile(r"^\d{1,3}(\.\d{1,2})?$")


def parse_percent(value: str | int) -> int | None:
    """Return basis points, or None if `value` is not 0-100 with <= 2 decimals."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        bp = value * PERCENT_SCALE
    else:
        text = value.strip()
        if not _PERCENT_RE.match(text):
            return None
        bp = int(Decimal(text) * PERCENT_SCALE)
    if not 0 <= bp <= FULL_PERCENT_BP:
        return None
    return bp


def format_percent(bp: int) -> str:
    sign = "-" if bp < 0 else ""
    whole, frac = divmod(abs(bp), PERCENT_SCALE)
    return f"{sign}{whole}.{frac:02d}"


def round_half_up_div(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero."""
    q, r = divmod(abs(numerator), denominator)
    if r * 2 >= denominator:
        q += 1
    return q if numerator >= 0 else -q


def target_minor(income_minor: int, percent_bp: int) -> int:
    """B2: income x percent / 100, rounded half-up to a whole minor unit."""
    return round_half_up_div(income_minor * percent_bp, FULL_PERCENT_BP)


def percent_used(spent_minor: int, target: int) -> str | None:
    """B5: spent / target x 100 with 2 decimals; None when target is 0."""
    if target == 0:
        return None
    value = (Decimal(spent_minor) * 100 / Decimal(target)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"{value:.2f}"

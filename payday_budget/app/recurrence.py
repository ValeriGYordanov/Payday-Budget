"""Occurrence dates of recurring rules (R1). Pure date maths, no DB."""

import calendar
import datetime as dt
from collections.abc import Iterator

WEEKLY = "weekly"
MONTHLY = "monthly"
YEARLY = "yearly"
FREQUENCIES = (WEEKLY, MONTHLY, YEARLY)


def _clamped(year: int, month: int, day: int) -> dt.date:
    """`day` in that month, or the month's last day if it doesn't exist."""
    return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def nth(frequency: str, interval: int, anchor: dt.date, n: int) -> dt.date:
    """The n-th occurrence (n >= 0), always computed from the anchor (no drift)."""
    if frequency == WEEKLY:
        return anchor + dt.timedelta(weeks=n * interval)
    if frequency == MONTHLY:
        months = anchor.month - 1 + n * interval
        return _clamped(anchor.year + months // 12, months % 12 + 1, anchor.day)
    if frequency == YEARLY:
        return _clamped(anchor.year + n * interval, anchor.month, anchor.day)
    raise ValueError(f"unknown frequency {frequency!r}")


def _first_index(frequency: str, interval: int, anchor: dt.date, start: dt.date) -> int:
    """An index n whose occurrence is at or before the first one on or after `start`."""
    if start <= anchor:
        return 0
    if frequency == WEEKLY:
        return (start - anchor).days // (7 * interval)
    if frequency == MONTHLY:
        months = (start.year - anchor.year) * 12 + start.month - anchor.month
        return max(months // interval - 1, 0)
    return max((start.year - anchor.year) // interval - 1, 0)


def occurrences(
    frequency: str,
    interval: int,
    anchor: dt.date,
    start: dt.date,
    end: dt.date,
) -> Iterator[dt.date]:
    """Occurrence dates within `[start, end]`, both inclusive, in order."""
    n = _first_index(frequency, interval, anchor, start)
    while True:
        day = nth(frequency, interval, anchor, n)
        if day > end:
            return
        if day >= start:
            yield day
        n += 1

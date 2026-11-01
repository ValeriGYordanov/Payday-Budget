"""R1 occurrence maths."""

import datetime as dt
import random

import pytest

from app.recurrence import nth, occurrences

D = dt.date


def _all(frequency: str, interval: int, anchor: D, start: D, end: D) -> list[D]:
    return list(occurrences(frequency, interval, anchor, start, end))


def test_R1_weekly_with_interval() -> None:
    assert _all("weekly", 2, D(2026, 1, 5), D(2026, 1, 1), D(2026, 2, 2)) == [
        D(2026, 1, 5),
        D(2026, 1, 19),
        D(2026, 2, 2),
    ]


def test_R1_monthly_missing_day_uses_last_day_without_drift() -> None:
    assert _all("monthly", 1, D(2026, 1, 31), D(2026, 1, 1), D(2026, 5, 31)) == [
        D(2026, 1, 31),
        D(2026, 2, 28),
        D(2026, 3, 31),
        D(2026, 4, 30),
        D(2026, 5, 31),
    ]
    assert nth("monthly", 1, D(2028, 1, 30), 1) == D(2028, 2, 29)


def test_R1_monthly_with_interval_crosses_years() -> None:
    assert _all("monthly", 3, D(2026, 11, 30), D(2026, 11, 1), D(2027, 8, 30)) == [
        D(2026, 11, 30),
        D(2027, 2, 28),
        D(2027, 5, 30),
        D(2027, 8, 30),
    ]


def test_R1_yearly_leap_day_falls_back_to_feb_28() -> None:
    assert _all("yearly", 1, D(2024, 2, 29), D(2024, 1, 1), D(2028, 12, 31)) == [
        D(2024, 2, 29),
        D(2025, 2, 28),
        D(2026, 2, 28),
        D(2027, 2, 28),
        D(2028, 2, 29),
    ]


def test_R1_yearly_with_interval() -> None:
    assert _all("yearly", 2, D(2026, 6, 1), D(2026, 1, 1), D(2031, 1, 1)) == [
        D(2026, 6, 1),
        D(2028, 6, 1),
        D(2030, 6, 1),
    ]


def test_R1_window_bounds_are_inclusive() -> None:
    anchor = D(2026, 1, 1)
    assert _all("weekly", 1, anchor, D(2026, 1, 8), D(2026, 1, 15)) == [
        D(2026, 1, 8),
        D(2026, 1, 15),
    ]
    assert _all("weekly", 1, anchor, D(2026, 1, 9), D(2026, 1, 14)) == []
    assert _all("weekly", 1, anchor, D(2025, 1, 1), D(2025, 12, 31)) == []


@pytest.mark.parametrize("frequency", ["weekly", "monthly", "yearly"])
def test_R1_windowed_occurrences_match_brute_force(frequency: str) -> None:
    rng = random.Random(frequency)
    for _ in range(300):
        anchor = D(2000, 1, 1) + dt.timedelta(days=rng.randrange(365 * 20))
        interval = rng.randint(1, 5)
        start = anchor + dt.timedelta(days=rng.randrange(-100, 365 * 8))
        end = start + dt.timedelta(days=rng.randrange(0, 900))
        expected = []
        n = 0
        while (day := nth(frequency, interval, anchor, n)) <= end:
            if day >= start:
                expected.append(day)
            n += 1
        assert _all(frequency, interval, anchor, start, end) == expected

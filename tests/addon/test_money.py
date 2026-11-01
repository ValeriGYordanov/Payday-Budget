"""Integer money and percent helpers."""

import pytest

from app.money import format_percent, parse_percent, percent_used, round_half_up_div, target_minor


@pytest.mark.parametrize(
    ("value", "bp"),
    [("0", 0), ("100", 10000), ("50.25", 5025), ("7.5", 750), (" 33.33 ", 3333), (20, 2000)],
)
def test_B1_parse_percent_valid(value: str | int, bp: int) -> None:
    assert parse_percent(value) == bp


@pytest.mark.parametrize("value", ["100.01", "-0.01", "1.234", "", "1,5", "+5", 101, -1, True])
def test_B1_parse_percent_invalid(value: str | int) -> None:
    assert parse_percent(value) is None


def test_B1_format_percent() -> None:
    assert [format_percent(v) for v in (0, 5, 5025, 10000, -150)] == [
        "0.00",
        "0.05",
        "50.25",
        "100.00",
        "-1.50",
    ]


def test_B2_round_half_up() -> None:
    assert [round_half_up_div(n, 10) for n in (4, 5, 15, 25, -5, -4)] == [0, 1, 2, 3, -1, 0]
    assert target_minor(1001, 5000) == 501
    assert target_minor(999, 3333) == 333  # 332.9667
    assert target_minor(0, 5000) == 0


def test_B5_percent_used() -> None:
    assert percent_used(0, 0) is None
    assert percent_used(1, 3) == "33.33"
    assert percent_used(2, 3) == "66.67"
    assert percent_used(150, 100) == "150.00"

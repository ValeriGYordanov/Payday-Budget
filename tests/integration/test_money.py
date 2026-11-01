"""Integer minor units <-> exact Decimal; no floats in results."""

from decimal import Decimal

import pytest

from custom_components.payday_budget.money import parse_amount, to_decimal, to_str


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (12.5, 2, 1250),
        ("12.50", 2, 1250),
        (3000, 2, 300000),
        ("0.01", 2, 1),
        (1500, 0, 1500),
        ("1.234", 3, 1234),
        (Decimal("7.1"), 2, 710),
    ],
)
def test_T1_parse_amount(value: object, unit: int, expected: int) -> None:
    assert parse_amount(value, unit) == expected


@pytest.mark.parametrize(
    "value", ["12.345", "1,5", "-1", "1e3", 0.1 + 0.2, 1e20, True, None, "", "1.5x"]
)
def test_T1_parse_amount_rejects(value: object) -> None:
    assert parse_amount(value, 2) is None


def test_to_decimal_and_str() -> None:
    assert to_decimal(4550, 2) == Decimal("45.50")
    assert str(to_decimal(-5, 2)) == "-0.05"
    assert to_str(0, 2) == "0.00"
    assert to_str(1500, 0) == "1500"
    assert to_str(1, 3) == "0.001"

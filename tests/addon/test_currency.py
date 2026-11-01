"""§5.6 Currency."""

import pytest

from app import currency
from tests.addon.conftest import Api


def test_K1_default_currency_is_eur(api: Api) -> None:
    assert api.get("/settings") == {"currency": "EUR", "minor_unit": 2, "setup_completed": False}
    api.post("/setup", {"first_period": {"start_date": "2026-10-25"}})
    assert api.get("/settings")["currency"] == "EUR"


def test_K1_currency_chosen_in_setup(api: Api) -> None:
    api.setup(currency="jpy")
    assert api.get("/settings") == {"currency": "JPY", "minor_unit": 0, "setup_completed": True}


@pytest.mark.parametrize("code", ["XXX", "EURO", "", "BGN"])
def test_K1_currency_must_be_iso_4217(api: Api, code: str) -> None:
    body = {"currency": code, "first_period": {"start_date": "2026-10-25"}}
    api.error("POST", "/setup", "K1", json=body)
    api.error("PATCH", "/settings", "K1", json={"currency": code, "confirm": True})


def test_K2_exponent_follows_currency() -> None:
    assert (currency.exponent("EUR"), currency.exponent("JPY"), currency.exponent("KWD")) == (
        2,
        0,
        3,
    )
    assert currency.exponent("CLF") == 4


def test_K2_change_requires_same_exponent(ready: Api) -> None:
    ready.error("PATCH", "/settings", "K2", json={"currency": "JPY", "confirm": True})
    ready.error("PATCH", "/settings", "K2", json={"currency": "KWD", "confirm": True})
    assert ready.get("/settings")["currency"] == "EUR"


def test_K2_change_requires_confirmation(ready: Api) -> None:
    body = ready.error("PATCH", "/settings", "K2", json={"currency": "USD"})
    assert body["field"] == "confirm"
    assert ready.get("/settings")["currency"] == "EUR"


def test_K2_change_relabels_without_conversion(ready: Api) -> None:
    ready.income(123456, "2026-10-26")
    assert ready.patch("/settings", {"currency": "usd", "confirm": True})["currency"] == "USD"
    summary = ready.summary()
    assert (summary["currency"], summary["income_minor"]) == ("USD", 123456)


def test_K2_same_currency_is_a_no_op(ready: Api) -> None:
    assert ready.patch("/settings", {"currency": "EUR"})["currency"] == "EUR"

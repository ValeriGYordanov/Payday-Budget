"""§5.1 Periods."""

import datetime as dt

import pytest

from app import clock as clock_module
from tests.addon.conftest import Api


def test_P1_transaction_belongs_to_period_with_greatest_start_on_or_before_its_date(
    ready: Api,
) -> None:
    ready.clock.today = dt.date(2026, 12, 1)
    ready.new_period("2026-11-25")
    first, second = ready.period_id("2026-10-25"), ready.period_id("2026-11-25")
    before = ready.expense(100, "2026-11-24")
    on_start = ready.expense(200, "2026-11-25")
    assert before["period_id"] == first
    assert on_start["period_id"] == second
    assert ready.summary(first)["expenses_minor"] == 100
    assert ready.summary(second)["expenses_minor"] == 200


def test_P1_period_is_never_stored_on_transaction(api: Api) -> None:
    from app.models import Transaction

    assert "period_id" not in Transaction.__table__.columns


def test_P1_period_end_is_day_before_next_start_and_latest_is_open_ended(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 12, 1)
    ready.new_period("2026-11-25")
    latest, first = ready.get("/periods")["items"]
    assert first["end_date"] == "2026-11-24"
    assert latest["end_date"] is None
    assert latest["is_current"] and not first["is_current"]


def test_P2_future_start_date_is_rejected(ready: Api) -> None:
    ready.error("POST", "/periods", "P2", json={"start_date": "2026-11-02"})
    pid = ready.period_id("2026-10-25")
    ready.error("PATCH", f"/periods/{pid}", "P2", json={"start_date": "2026-11-02"})


def test_P2_start_date_is_unique(ready: Api) -> None:
    ready.error("POST", "/periods", "P2", json={"start_date": "2026-10-25"})
    second = ready.new_period("2026-10-30")
    ready.error("PATCH", f"/periods/{second['id']}", "P2", json={"start_date": "2026-10-25"})


def test_P3_no_automatic_period_start(ready: Api) -> None:
    ready.clock.today = dt.date(2027, 3, 1)
    assert len(ready.get("/periods")["items"]) == 1
    assert ready.summary()["period"]["start_date"] == "2026-10-25"


def test_P3_manual_start_defaults_to_today(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 11, 25)
    period = ready.new_period()
    assert period["start_date"] == "2026-11-25"
    assert ready.summary()["period"]["id"] == period["id"]


def test_P4_default_name_is_english_month_and_year(ready: Api) -> None:
    assert ready.get("/periods")["items"][0]["name"] == "October 2026"


def test_P4_name_collision_appends_counter(ready: Api) -> None:
    second = ready.new_period("2026-10-28")
    third = ready.new_period("2026-10-30")
    assert second["name"] == "October 2026 (2)"
    assert third["name"] == "October 2026 (3)"


def test_P4_period_is_renamable_and_explicit_name_is_kept(ready: Api) -> None:
    pid = ready.period_id("2026-10-25")
    assert ready.patch(f"/periods/{pid}", {"name": "Payday Oct"})["name"] == "Payday Oct"
    assert ready.new_period("2026-10-30", name="Bonus")["name"] == "Bonus"
    ready.error("PATCH", f"/periods/{pid}", "validation_error", json={"name": "  "})


def test_P4_editing_start_date_does_not_rename(ready: Api) -> None:
    pid = ready.period_id("2026-10-25")
    assert ready.patch(f"/periods/{pid}", {"start_date": "2026-09-25"})["name"] == "October 2026"


def test_P5_start_date_is_editable(ready: Api) -> None:
    pid = ready.period_id("2026-10-25")
    assert ready.patch(f"/periods/{pid}", {"start_date": "2026-10-20"})["start_date"] == (
        "2026-10-20"
    )


def test_P5_editing_start_past_a_neighbour_resorts_periods(ready: Api) -> None:
    second = ready.new_period("2026-10-28")
    ready.patch(f"/periods/{second['id']}", {"start_date": "2026-10-20"})
    starts = [p["start_date"] for p in ready.get("/periods")["items"]]
    assert starts == ["2026-10-25", "2026-10-20"]


def test_P5_delete_merges_transactions_into_previous_period(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 12, 1)
    second = ready.new_period("2026-11-25")
    ready.expense(100, "2026-11-01")
    ready.expense(250, "2026-11-26")
    ready.delete(f"/periods/{second['id']}")
    summary = ready.summary()
    assert summary["period"]["start_date"] == "2026-10-25"
    assert summary["expenses_minor"] == 350


def test_P5_delete_earliest_rejected_if_transactions_would_precede_first_period(
    ready: Api,
) -> None:
    ready.new_period("2026-10-28")
    first = ready.period_id("2026-10-25")
    ready.expense(100, "2026-10-26")
    ready.error("DELETE", f"/periods/{first}", "P5")


def test_P5_delete_earliest_allowed_without_orphaned_transactions(ready: Api) -> None:
    ready.new_period("2026-10-28")
    ready.expense(100, "2026-10-29")
    ready.delete(f"/periods/{ready.period_id('2026-10-25')}")
    assert [p["start_date"] for p in ready.get("/periods")["items"]] == ["2026-10-28"]


def test_P5_deleting_the_only_period_is_rejected(ready: Api) -> None:
    ready.error("DELETE", f"/periods/{ready.period_id('2026-10-25')}", "P5")


def test_P6_transaction_before_earliest_period_is_rejected(ready: Api) -> None:
    body = {
        "kind": "expense",
        "amount_minor": 100,
        "category_id": ready.category_id("Food"),
        "budget_id": ready.budget_id("Needs"),
        "date": "2026-10-24",
    }
    ready.error("POST", "/transactions", "P6", json=body)
    tx = ready.expense(100, "2026-10-25")
    ready.error("PATCH", f"/transactions/{tx['id']}", "P6", json={"date": "2026-10-01"})


def test_P6_transactions_rejected_when_no_period_exists(api: Api) -> None:
    category = api.post("/categories", {"name": "Pay", "kind": "income"})
    body = {"kind": "income", "amount_minor": 100, "category_id": category["id"]}
    api.error("POST", "/transactions", "P6", json=body)


def test_P6_moving_earliest_start_after_transactions_is_rejected(ready: Api) -> None:
    ready.expense(100, "2026-10-26")
    pid = ready.period_id("2026-10-25")
    ready.error("PATCH", f"/periods/{pid}", "P6", json={"start_date": "2026-10-27"})
    assert ready.get(f"/periods/{pid}")["start_date"] == "2026-10-25"


def test_P6_setup_requires_first_period(api: Api) -> None:
    body = api.error("POST", "/setup", "validation_error", json={"currency": "EUR"})
    assert body["field"] == "first_period"
    assert api.get("/setup") == {"setup_completed": False}


def test_P7_income_dated_before_new_period_belongs_to_previous(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 11, 25)
    ready.income(300000, "2026-11-24")  # salary arrived the day before the button press
    ready.new_period()
    previous = ready.period_id("2026-10-25")
    assert ready.summary(previous)["income_minor"] == 300000
    assert ready.summary()["income_minor"] == 0


def test_P8_changing_transaction_date_rebuckets(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 12, 1)
    second = ready.new_period("2026-11-25")
    tx = ready.expense(100, "2026-11-01")
    assert ready.summary()["expenses_minor"] == 0
    moved = ready.patch(f"/transactions/{tx['id']}", {"date": "2026-11-26"})
    assert moved["period_id"] == second["id"]
    assert ready.summary()["expenses_minor"] == 100


def test_P8_changing_period_start_rebuckets(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 12, 1)
    second = ready.new_period("2026-11-25")
    ready.expense(100, "2026-11-20")
    ready.patch(f"/periods/{second['id']}", {"start_date": "2026-11-15"})
    assert ready.summary()["expenses_minor"] == 100
    assert ready.summary(ready.period_id("2026-10-25"))["expenses_minor"] == 0


def test_P9_today_uses_tz_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from zoneinfo import ZoneInfo

    for tz in ("Pacific/Kiritimati", "Pacific/Pago_Pago", "Europe/Sofia"):
        monkeypatch.setenv("TZ", tz)
        assert clock_module.today() == dt.datetime.now(ZoneInfo(tz)).date()


def test_P9_unknown_or_missing_tz_falls_back_to_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Not/AZone")
    assert clock_module.local_zone().key == "UTC"
    monkeypatch.delenv("TZ")
    assert clock_module.local_zone().key == "UTC"


def test_P9_dates_have_no_time_of_day(ready: Api) -> None:
    tx = ready.expense(100, "2026-10-26")
    assert tx["date"] == "2026-10-26"
    ready.error(
        "PATCH", f"/transactions/{tx['id']}", "validation_error", json={"date": "2026-10-26T10:00"}
    )

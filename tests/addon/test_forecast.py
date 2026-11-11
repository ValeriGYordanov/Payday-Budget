"""v1.3 Forecasting (SPEC-1.3 F1-F9, P1-P6)."""

import datetime as dt
from typing import Any

from tests.addon.conftest import Api


def _three_periods(api: Api) -> None:
    """Closed periods 09-01..09-30 and 10-01..10-30 (30 days each); current from 10-31.

    Today is 2026-11-01, so the expected payday is 10-31 + 30 = 11-30 and 28 days are left
    (11-02 .. 11-29). Flexible spending in the closed periods: Needs 6000, Wants 1800 over
    60 days, i.e. 100 and 30 a day.
    """
    api.setup(start="2026-09-01")
    api.income(100000, "2026-09-01")
    api.expense(3000, "2026-09-10", budget="Needs")
    api.expense(1800, "2026-10-05", budget="Wants")
    api.expense(3000, "2026-10-10", budget="Needs")
    api.new_period("2026-10-01")
    api.new_period("2026-10-31")
    api.income(200000, "2026-10-31")
    api.expense(5000, "2026-11-01", budget="Needs")


def _forecast(api: Api, expect: int = 200) -> Any:
    return api.get("/forecast", expect=expect)


def _budget(result: Any, name: str) -> Any:
    return next(b for b in result["budgets"] if b["name"] == name)


def _reminder(api: Api, **fields: Any) -> Any:
    body = {"name": "Ток", "kind": "expense", "frequency": "monthly", **fields}
    return api.post("/reminders", body)


def test_F1_expected_payday_from_the_last_three_periods(api: Api) -> None:
    _three_periods(api)
    result = _forecast(api)
    assert (result["expected_payday"], result["days_left"], result["overdue"]) == (
        "2026-11-30",
        28,
        False,
    )


def test_F1_fallback_and_overdue(ready: Api) -> None:
    result = _forecast(ready)  # no closed period: 10-25 + 30
    assert (result["expected_payday"], result["days_left"]) == ("2026-11-24", 22)
    ready.clock.today = dt.date(2026, 12, 5)
    result = _forecast(ready)
    assert (result["expected_payday"], result["days_left"], result["overdue"]) == (
        "2026-12-06",
        0,
        True,
    )
    assert result["expenses"]["flexible_minor"] == 0


def test_F1_no_current_period(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 10, 1)  # before the first period
    ready.error("GET", "/forecast", "not_found", status=404)


def test_F4_flexible_spending_from_the_closed_periods(api: Api) -> None:
    _three_periods(api)
    result = _forecast(api)
    assert result["basis"] == {"periods": 2, "days": 60}
    assert (
        _budget(result, "Needs")["flexible_minor"],
        _budget(result, "Wants")["flexible_minor"],
    ) == (
        2800,
        840,
    )
    assert result["expenses"]["flexible_minor"] == 3640


def test_F4_recurring_and_reminder_transactions_are_not_flexible(api: Api) -> None:
    _three_periods(api)
    api.rule(anchor_date="2026-09-15", end_date="2026-10-20")  # generated in the closed periods
    _reminder(api, anchor_date="2026-09-20")  # opens 2026-10-20 only (D11)
    occurrence = api.get("/reminders/occurrences?status=open")["items"][0]
    api.post(
        f"/reminders/occurrences/{occurrence['id']}/record",
        {
            "amount_minor": 99999,
            "budget_id": api.budget_id("Needs"),
            "category_id": api.category_id("Utilities"),
        },
    )
    assert _budget(_forecast(api), "Needs")["flexible_minor"] == 2800  # unchanged


def test_F4_P1_first_period_uses_its_completed_days(ready: Api) -> None:
    ready.expense(700, "2026-10-26", budget="Needs")  # 7 completed days: 10-25 .. 10-31
    ready.expense(9999, "2026-11-01", budget="Needs")  # today: actual, not part of the pace
    result = _forecast(ready)
    assert result["basis"] == {"periods": 0, "days": 7}
    assert _budget(result, "Needs")["flexible_minor"] == 2200  # 100 a day x 22 days left
    ready.clock.today = dt.date(2026, 10, 25)  # the period's first day
    assert _forecast(ready)["expenses"]["flexible_minor"] == 0


def test_F2_known_items_before_the_payday(api: Api) -> None:
    _three_periods(api)
    api.rule(anchor_date="2026-11-05")  # weekly 1000, Needs: 11-05, 12, 19, 26
    api.rule(anchor_date="2026-11-30")  # on the payday itself: not counted
    result = _forecast(api)
    recurring = [i["date"] for i in result["upcoming"] if i["source"] == "recurring"]
    assert recurring == ["2026-11-05", "2026-11-12", "2026-11-19", "2026-11-26"]
    assert result["expenses"]["known_minor"] == 4000
    assert _budget(result, "Needs")["known_minor"] == 4000


def test_F3_P5_reminder_amounts(api: Api) -> None:
    _three_periods(api)
    _reminder(api, anchor_date="2026-11-15")  # no amount, no history: listed, not counted
    weekly = _reminder(api, name="Вода", frequency="weekly", anchor_date="2026-10-31")
    opened = [
        o
        for o in api.get("/reminders/occurrences?status=open")["items"]
        if o["reminder_id"] == weekly["id"]
    ]
    api.post(
        f"/reminders/occurrences/{opened[0]['id']}/record",
        {
            "amount_minor": 2500,
            "category_id": api.category_id("Utilities"),
            "budget_id": api.budget_id("Needs"),
        },
    )
    result = _forecast(api)
    tok = [i for i in result["upcoming"] if i["name"] == "Ток"]
    assert [(i["date"], i["amount_minor"]) for i in tok] == [("2026-11-15", None)]
    assert tok[0]["estimated"] is False
    assert all(i["estimated"] for i in result["upcoming"] if i["name"] == "Вода")  # D6
    voda = [(i["date"], i["amount_minor"]) for i in result["upcoming"] if i["name"] == "Вода"]
    assert voda == [
        ("2026-11-07", 2500),
        ("2026-11-14", 2500),
        ("2026-11-21", 2500),
        ("2026-11-28", 2500),
    ]
    assert result["expenses"]["known_minor"] == 10000


def test_F2_open_reminder_occurrences_count_as_due(api: Api) -> None:
    _three_periods(api)
    _reminder(api, name="Наем", amount_minor=40000, anchor_date="2026-10-31")  # due, open
    result = _forecast(api)
    due = [i for i in result["upcoming"] if i["due"]]
    assert [(i["date"], i["name"], i["amount_minor"]) for i in due] == [
        ("2026-10-31", "Наем", 40000)
    ]
    assert result["upcoming"][0]["due"] is True  # due ones first
    assert result["upcoming"][0]["estimated"] is False  # the reminder's own amount
    assert result["expenses"]["known_minor"] == 40000


def test_F5_F6_projected_income_expenses_and_balance(api: Api) -> None:
    _three_periods(api)
    api.rule(anchor_date="2026-11-05")  # 4 x 1000
    api.rule(  # P6: income inside the window counts; the 11-30 one would start a new period
        kind="income",
        amount_minor=15000,
        category_id=api.category_id("Other income", "income"),
        budget_id=None,
        frequency="monthly",
        anchor_date="2026-11-15",
    )
    result = _forecast(api)
    assert result["income"] == {
        "so_far_minor": 200000,
        "known_minor": 15000,
        "projected_minor": 215000,
    }
    assert result["expenses"] == {
        "so_far_minor": 5000,
        "known_minor": 4000,
        "flexible_minor": 3640,
        "projected_minor": 12640,
    }
    assert result["balance_projected_minor"] == 215000 - 12640


def test_F7_per_budget_outlook(api: Api) -> None:
    _three_periods(api)
    api.patch(f"/budgets/{api.budget_id('Savings')}", {"direction": "positive"})
    api.rule(anchor_date="2026-11-05")
    result = _forecast(api)
    needs = _budget(result, "Needs")
    assert {
        k: needs[k]
        for k in (
            "target_minor",
            "spent_minor",
            "known_minor",
            "flexible_minor",
            "projected_spent_minor",
            "projected_status",
        )
    } == {
        "target_minor": 100000,
        "spent_minor": 5000,
        "known_minor": 4000,
        "flexible_minor": 2800,
        "projected_spent_minor": 11800,
        "projected_status": "ok",
    }
    savings = _budget(result, "Savings")
    assert (savings["direction"], savings["target_minor"], savings["projected_status"]) == (
        "positive",
        40000,
        "below",
    )
    api.expense(95000, "2026-11-01", budget="Needs")  # now over its limit
    assert _budget(_forecast(api), "Needs")["projected_status"] == "over"


def test_F8_P2_safe_per_day_sets_savings_aside(api: Api) -> None:
    _three_periods(api)
    api.rule(anchor_date="2026-11-05")
    assert _forecast(api)["safe_per_day_minor"] == round((200000 - 5000 - 4000) / 28)  # 6821
    api.patch(f"/budgets/{api.budget_id('Savings')}", {"direction": "positive"})
    # Savings still needs its 40000 target: (200000 - 5000 - 4000 - 40000) / 28 = 5392.86
    assert _forecast(api)["safe_per_day_minor"] == 5393
    api.expense(300000, "2026-11-01", budget="Needs")
    assert _forecast(api)["safe_per_day_minor"] == 0  # never negative


def test_F9_upcoming_fields(api: Api) -> None:
    _three_periods(api)
    api.rule(anchor_date="2026-11-05", description="Фитнес")
    item = _forecast(api)["upcoming"][0]
    assert item == {
        "date": "2026-11-05",
        "name": "Фитнес",
        "kind": "expense",
        "amount_minor": 1000,
        "budget_id": api.budget_id("Needs"),
        "budget_name": "Needs",
        "source": "recurring",
        "due": False,
        "estimated": False,
    }


def test_series_runs_from_the_period_start_to_the_day_before_payday(api: Api) -> None:
    """§7 chart data: actual balance to today, then projected; it ends at the projection."""
    _three_periods(api)
    api.rule(anchor_date="2026-11-05")
    result = _forecast(api)
    series = result["series"]
    assert [p["date"] for p in series[:2]] == ["2026-10-31", "2026-11-01"]
    assert [p["balance_minor"] for p in series[:2]] == [200000, 195000]
    assert not series[1]["projected"] and series[2]["projected"]
    assert series[-1]["date"] == "2026-11-29"
    assert len(series) == 2 + result["days_left"]
    assert series[-1]["balance_minor"] == result["balance_projected_minor"]
    on_fifth = next(p for p in series if p["date"] == "2026-11-05")
    assert on_fifth["items"] == 1

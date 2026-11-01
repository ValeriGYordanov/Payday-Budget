"""§5.2 Budgets."""

import datetime as dt

import pytest

from tests.addon.conftest import Api


def _snapshot(api: Api, period_id: int) -> dict[str, str]:
    return {b["name"]: b["percent"] for b in api.get(f"/periods/{period_id}")["budgets"]}


@pytest.mark.parametrize("percent", ["100.01", "-1", "50.255", "abc", 101, "1e2"])
def test_B1_percent_must_be_0_to_100_with_2_decimals(ready: Api, percent: object) -> None:
    ready.error("POST", "/budgets", "B1", json={"name": "X", "percent": percent})


def test_B1_float_percent_is_rejected_as_validation_error(api: Api) -> None:
    api.error("POST", "/budgets", "validation_error", json={"name": "X", "percent": 12.5})


def test_B1_sum_of_active_budgets_must_not_exceed_100(api: Api) -> None:
    api.post("/budgets", {"name": "A", "percent": "33.33"})
    api.post("/budgets", {"name": "B", "percent": "33.33"})
    api.post("/budgets", {"name": "C", "percent": "33.34"})
    listing = api.get("/budgets")
    assert listing["allocated_percent"] == "100.00"
    assert listing["unallocated_percent"] == "0.00"
    api.error("POST", "/budgets", "B1", json={"name": "D", "percent": "0.01"})
    a = api.budget_id("A")
    api.error("PATCH", f"/budgets/{a}", "B1", json={"percent": "33.34"})


def test_B1_archived_budgets_do_not_count_and_unarchive_rechecks(ready: Api) -> None:
    wants = ready.budget_id("Wants")
    ready.patch(f"/budgets/{wants}", {"archived": True})
    ready.post("/budgets", {"name": "Fun", "percent": "30"})
    ready.error("PATCH", f"/budgets/{wants}", "B1", json={"archived": False})


def test_B1_unallocated_may_be_positive(ready: Api) -> None:
    ready.patch(f"/budgets/{ready.budget_id('Wants')}", {"percent": "10.5"})
    assert ready.get("/budgets")["unallocated_percent"] == "19.50"
    ready.income(100000, "2026-10-26")
    unallocated = ready.summary()["unallocated"]
    assert unallocated == {"percent": "19.50", "amount_minor": 19500}


def test_B2_target_is_income_times_percent_rounded_half_up(ready: Api) -> None:
    ready.income(1001, "2026-10-26")  # 50% = 500.5 -> 501; 30% = 300.3 -> 300; 20% = 200.2
    summary = ready.summary()
    assert ready.budget_row(summary, "Needs")["target_minor"] == 501
    assert ready.budget_row(summary, "Wants")["target_minor"] == 300
    assert ready.budget_row(summary, "Savings")["target_minor"] == 200
    assert summary["unallocated"]["amount_minor"] == 1001 - 501 - 300 - 200


def test_B3_new_period_snapshots_active_budget_percents(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 11, 25)
    ready.patch(f"/budgets/{ready.budget_id('Wants')}", {"archived": True})
    period = ready.new_period()
    assert _snapshot(ready, period["id"]) == {"Needs": "50.00", "Savings": "20.00"}


def test_B3_editing_percent_updates_default_and_current_but_not_past(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 11, 25)
    current = ready.new_period()
    past = ready.period_id("2026-10-25")
    ready.patch(f"/budgets/{ready.budget_id('Needs')}", {"percent": "40"})
    assert _snapshot(ready, current["id"])["Needs"] == "40.00"
    assert _snapshot(ready, past)["Needs"] == "50.00"
    assert ready.get(f"/budgets/{ready.budget_id('Needs')}")["percent"] == "40.00"


def test_B3_backdated_period_between_two_copies_the_split_period(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 12, 1)
    ready.new_period("2026-11-25")
    first = ready.period_id("2026-10-25")
    ready.patch(f"/budgets/{ready.budget_id('Needs')}", {"percent": "45"})  # current only
    inserted = ready.new_period("2026-11-10")
    assert _snapshot(ready, inserted["id"]) == _snapshot(ready, first)
    assert _snapshot(ready, inserted["id"])["Needs"] == "50.00"


def test_B3_backdated_period_before_earliest_copies_earliest(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 12, 1)
    second = ready.new_period("2026-11-25")
    ready.patch(f"/budgets/{ready.budget_id('Needs')}", {"percent": "45"})
    earliest = ready.period_id("2026-10-25")
    inserted = ready.new_period("2026-09-25")
    assert _snapshot(ready, inserted["id"]) == _snapshot(ready, earliest)
    assert _snapshot(ready, second["id"])["Needs"] == "45.00"


def test_B3_new_budget_joins_current_snapshot_only(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 11, 25)
    past = ready.period_id("2026-10-25")
    current = ready.new_period()
    ready.patch(f"/budgets/{ready.budget_id('Wants')}", {"percent": "20"})
    ready.post("/budgets", {"name": "Gifts", "percent": "10"})
    assert _snapshot(ready, current["id"])["Gifts"] == "10.00"
    assert "Gifts" not in _snapshot(ready, past)


def test_B4_budget_with_transactions_can_only_be_archived(ready: Api) -> None:
    ready.expense(100, "2026-10-26", budget="Wants")
    wants = ready.budget_id("Wants")
    ready.error("DELETE", f"/budgets/{wants}", "B4")
    assert ready.patch(f"/budgets/{wants}", {"archived": True})["archived"] is True


def test_B4_budget_without_transactions_can_be_deleted_with_its_snapshots(ready: Api) -> None:
    wants = ready.budget_id("Wants")
    ready.delete(f"/budgets/{wants}")
    ready.get(f"/budgets/{wants}", expect=404)
    assert "Wants" not in _snapshot(ready, ready.period_id("2026-10-25"))


def test_B4_archived_budget_cannot_be_chosen_for_new_transactions(ready: Api) -> None:
    tx = ready.expense(100, "2026-10-26", budget="Wants")
    wants = ready.budget_id("Wants")
    ready.patch(f"/budgets/{wants}", {"archived": True})
    body = {
        "kind": "expense",
        "amount_minor": 1,
        "category_id": ready.category_id("Food"),
        "budget_id": wants,
        "date": "2026-10-26",
    }
    ready.error("POST", "/transactions", "B4", json=body)
    # An existing transaction may keep its archived budget, but can't switch to one.
    ready.patch(f"/transactions/{tx['id']}", {"amount_minor": 200})
    other = ready.expense(100, "2026-10-26", budget="Needs")
    ready.error("PATCH", f"/transactions/{other['id']}", "B4", json={"budget_id": wants})


def test_B4_archived_budget_still_appears_in_past_periods(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 11, 25)
    ready.expense(100, "2026-10-26", budget="Wants")
    past = ready.period_id("2026-10-25")
    ready.new_period()
    ready.patch(f"/budgets/{ready.budget_id('Wants')}", {"archived": True})
    row = ready.budget_row(ready.summary(past), "Wants")
    assert row["archived"] is True
    assert row["spent_minor"] == 100
    ready.clock.today = dt.date(2026, 12, 25)
    assert "Wants" not in _snapshot(ready, ready.new_period()["id"])


def test_B4_archiving_keeps_current_snapshot_row_only_if_it_has_expenses(ready: Api) -> None:
    current = ready.period_id("2026-10-25")
    ready.expense(100, "2026-10-26", budget="Wants")
    ready.patch(f"/budgets/{ready.budget_id('Wants')}", {"archived": True})
    ready.patch(f"/budgets/{ready.budget_id('Savings')}", {"archived": True})
    snapshot = _snapshot(ready, current)
    assert "Wants" in snapshot
    assert "Savings" not in snapshot


def test_B4_unarchive_returns_budget_to_current_snapshot(ready: Api) -> None:
    savings = ready.budget_id("Savings")
    ready.patch(f"/budgets/{savings}", {"archived": True})
    ready.patch(f"/budgets/{savings}", {"archived": False})
    assert _snapshot(ready, ready.period_id("2026-10-25"))["Savings"] == "20.00"


def test_B5_spent_remaining_and_percent_used(ready: Api) -> None:
    ready.income(100000, "2026-10-26")
    ready.expense(20000, "2026-10-27", budget="Needs")
    ready.expense(5000, "2026-10-28", budget="Needs")
    ready.expense(31000, "2026-10-28", budget="Wants")
    ready.income(500, "2026-10-29")  # incomes never count as spent
    summary = ready.summary()
    needs = ready.budget_row(summary, "Needs")
    wants = ready.budget_row(summary, "Wants")
    assert (needs["target_minor"], needs["spent_minor"], needs["remaining_minor"]) == (
        50250,
        25000,
        25250,
    )
    assert needs["percent_used"] == "49.75"
    assert wants["remaining_minor"] == 30150 - 31000
    assert wants["over_target"] is True
    assert summary["income_minor"] == 100500
    assert summary["expenses_minor"] == 56000
    assert summary["balance_minor"] == 100500 - 56000


def test_B5_percent_used_unavailable_when_target_is_zero(ready: Api) -> None:
    ready.expense(100, "2026-10-26")
    row = ready.budget_row(ready.summary(), "Needs")
    assert row["target_minor"] == 0
    assert row["percent_used"] is None


def test_B5_budget_missing_from_past_snapshot_shows_zero_target(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 11, 25)
    past = ready.period_id("2026-10-25")
    ready.new_period()
    ready.patch(f"/budgets/{ready.budget_id('Wants')}", {"percent": "20"})
    ready.post("/budgets", {"name": "Gifts", "percent": "10"})
    ready.income(1000, "2026-10-26")
    ready.expense(70, "2026-10-26", budget="Gifts")
    row = ready.budget_row(ready.summary(past), "Gifts")
    assert (row["percent"], row["target_minor"], row["spent_minor"]) == ("0.00", 0, 70)
    assert row["percent_used"] is None


def test_B6_expense_requires_budget(ready: Api) -> None:
    body = {
        "kind": "expense",
        "amount_minor": 100,
        "category_id": ready.category_id("Food"),
        "date": "2026-10-26",
    }
    ready.error("POST", "/transactions", "B6", json=body)


def test_B6_income_must_not_have_budget(ready: Api) -> None:
    body = {
        "kind": "income",
        "amount_minor": 100,
        "category_id": ready.category_id("Salary", "income"),
        "budget_id": ready.budget_id("Needs"),
        "date": "2026-10-26",
    }
    ready.error("POST", "/transactions", "B6", json=body)
    tx = ready.income(100, "2026-10-26")
    ready.error(
        "PATCH", f"/transactions/{tx['id']}", "B6", json={"budget_id": ready.budget_id("Needs")}
    )


def test_B7_savings_is_an_ordinary_budget(ready: Api) -> None:
    ready.income(100000, "2026-10-26")
    ready.expense(20000, "2026-10-27", budget="Savings", category="Savings transfer")
    summary = ready.summary()
    savings = ready.budget_row(summary, "Savings")
    assert (savings["target_minor"], savings["spent_minor"]) == (20000, 20000)
    assert summary["expenses_minor"] == 20000

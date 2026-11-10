"""Read endpoints: summary, history, breakdown, daily (§6.4, §8)."""

import datetime as dt

from tests.addon.conftest import Api


def test_summary_shape(ready: Api) -> None:
    ready.income(200000, "2026-10-25")
    ready.expense(5000, "2026-10-26")
    summary = ready.summary()
    assert summary["period"]["name"] == "October 2026"
    assert summary["period"]["days_elapsed"] == 8  # 2026-10-25 .. 2026-11-01
    assert (summary["currency"], summary["minor_unit"]) == ("EUR", 2)
    assert [b["name"] for b in summary["budgets"]] == ["Needs", "Savings", "Wants"]
    assert set(summary["budgets"][0]) == {
        "budget_id",
        "name",
        "archived",
        "percent",
        "target_minor",
        "spent_minor",
        "remaining_minor",
        "percent_used",
        "over_target",
        "direction",
        "status",
        "on_track",
    }


def test_summary_unknown_period(ready: Api) -> None:
    ready.error("GET", "/summary?period=999", "not_found", status=404)
    ready.error("GET", "/summary?period=previous", "validation_error")


def test_summary_without_periods(api: Api) -> None:
    api.error("GET", "/summary", "not_found", status=404)


def test_history_lists_last_n_periods_oldest_first(ready: Api) -> None:
    ready.clock.today = dt.date(2027, 1, 31)
    ready.new_period("2026-11-25")
    ready.new_period("2026-12-25")
    ready.income(1000, "2026-10-25")
    ready.expense(100, "2026-11-01", budget="Needs")
    ready.income(2000, "2026-11-25")
    ready.expense(300, "2026-12-01", budget="Wants")
    ready.expense(50, "2026-12-30", budget="Savings")
    items = ready.get("/periods/history?limit=2")["items"]
    assert [i["period"]["start_date"] for i in items] == ["2026-11-25", "2026-12-25"]
    nov = items[0]
    assert (nov["income_minor"], nov["expenses_minor"]) == (2000, 300)
    wants = next(b for b in nov["budgets"] if b["name"] == "Wants")
    assert (wants["target_minor"], wants["spent_minor"]) == (600, 300)
    all_items = ready.get("/periods/history")["items"]
    assert len(all_items) == 3
    assert all_items[0]["expenses_minor"] == 100


def test_breakdown_by_category_with_budget_filter(ready: Api) -> None:
    ready.expense(500, "2026-10-26", budget="Needs", category="Food")
    ready.expense(300, "2026-10-27", budget="Wants", category="Food")
    ready.expense(900, "2026-10-27", budget="Needs", category="Housing")
    ready.income(9999, "2026-10-27")
    result = ready.get("/breakdown")
    assert result["total_minor"] == 1700
    assert [(c["name"], c["amount_minor"]) for c in result["categories"]] == [
        ("Housing", 900),
        ("Food", 800),
    ]
    needs = ready.get(f"/breakdown?budget={ready.budget_id('Needs')}")
    assert [(c["name"], c["amount_minor"]) for c in needs["categories"]] == [
        ("Housing", 900),
        ("Food", 500),
    ]


def test_daily_cumulative_spend_and_pace_length(ready: Api) -> None:
    ready.expense(100, "2026-10-25")
    ready.expense(50, "2026-10-27")
    ready.expense(25, "2026-10-27")
    ready.income(9999, "2026-10-26")
    daily = ready.get("/daily")
    assert daily["pace_length_days"] == 30  # no closed periods yet
    days = daily["days"]
    assert [d["date"] for d in days][0::7] == ["2026-10-25", "2026-11-01"]
    assert len(days) == 8
    assert [d["cumulative_minor"] for d in days[:4]] == [100, 100, 175, 175]
    assert days[2]["spent_minor"] == 75


def test_daily_pace_length_is_average_of_last_three_closed_periods(ready: Api) -> None:
    ready.clock.today = dt.date(2027, 3, 1)
    for start in ("2026-11-24", "2026-12-26", "2027-01-25", "2027-02-25"):
        ready.new_period(start)
    # Closed lengths before the current period: 32, 30, 31 (the oldest, 30, is ignored).
    assert ready.get("/daily")["pace_length_days"] == 31  # (32 + 30 + 31) / 3 = 31
    first_closed = ready.period_id("2026-11-24")
    assert ready.get(f"/daily?period={first_closed}")["pace_length_days"] == 30
    closed = ready.get(f"/daily?period={first_closed}")["days"]
    assert (closed[0]["date"], closed[-1]["date"], len(closed)) == ("2026-11-24", "2026-12-25", 32)

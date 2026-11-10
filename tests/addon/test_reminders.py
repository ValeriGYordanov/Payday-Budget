"""v1.2 §4 Reminders (SPEC-1.2 RM1-RM7)."""

import datetime as dt
from typing import Any

from tests.addon.conftest import Api


def _reminder(api: Api, expect: int = 201, **fields: Any) -> Any:
    """A monthly electricity reminder; amount left for the user by default."""
    body: dict[str, Any] = {
        "name": "Electricity",
        "kind": "expense",
        "category_id": api.category_id("Utilities"),
        "budget_id": api.budget_id("Needs"),
        "frequency": "monthly",
        "anchor_date": "2026-10-28",
        **fields,
    }
    return api.request("POST", "/reminders", expect, json=body)


def _open(api: Api) -> list[dict[str, Any]]:
    return list(api.get("/reminders/occurrences?status=open")["items"])


def _two_weekly(api: Api) -> Any:
    """A weekly reminder with two open occurrences: 2026-11-01 (created) and 2026-11-08."""
    reminder = _reminder(api, amount_minor=5000, frequency="weekly", anchor_date="2026-10-25")
    api.clock.today = dt.date(2026, 11, 8)
    api.run_scheduler()
    return reminder


def test_RM1_due_dates_follow_r1_with_month_end_clamping(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 10, 31)
    _reminder(ready, anchor_date="2026-10-31")
    ready.clock.today = dt.date(2027, 3, 1)
    ready.run_scheduler()
    assert [o["due_date"] for o in _open(ready)] == [
        "2026-10-31",
        "2026-11-30",
        "2026-12-31",
        "2027-01-31",
        "2027-02-28",
    ]


def test_RM1_schedule_is_validated(ready: Api) -> None:
    _reminder(ready, 422, frequency="daily")
    _reminder(ready, 422, interval=0)
    _reminder(ready, 422, end_date="2026-10-01")
    body = _reminder(ready, 422, anchor_date=None)
    assert body["code"] == "RM1"


def test_RM2_new_reminder_opens_only_its_latest_due_date(ready: Api) -> None:
    """D11: a first date in the past doesn't flood the user with old reminders."""
    reminder = _reminder(ready, frequency="weekly", anchor_date="2026-10-25")
    assert [o["due_date"] for o in _open(ready)] == ["2026-11-01"]  # not 2026-10-25
    assert ready.get(f"/reminders/{reminder['id']}")["last_opened_date"] == "2026-11-01"
    future = _reminder(ready, name="Insurance", anchor_date="2026-12-01")
    assert all(o["reminder_id"] != future["id"] for o in _open(ready))  # never future


def test_RM2_due_dates_before_the_first_period_are_skipped(ready: Api) -> None:
    """D12: they could only be ignored (P6). The first period starts 2026-10-25."""
    ready.clock.today = dt.date(2026, 10, 20)
    _reminder(ready, frequency="weekly", anchor_date="2026-10-13")
    assert _open(ready) == []
    ready.clock.today = dt.date(2026, 11, 3)
    ready.run_scheduler()
    assert [o["due_date"] for o in _open(ready)] == ["2026-10-27", "2026-11-03"]


def test_RM2_scheduler_catches_up_and_is_idempotent(ready: Api) -> None:
    reminder = _reminder(ready)
    assert len(_open(ready)) == 1  # 2026-10-28
    ready.clock.today = dt.date(2027, 1, 5)  # add-on was off: catch up
    ready.run_scheduler()
    ready.run_scheduler()
    dates = [o["due_date"] for o in _open(ready)]
    assert dates == ["2026-10-28", "2026-11-28", "2026-12-28"]
    assert ready.get(f"/reminders/{reminder['id']}")["last_opened_date"] == "2027-01-05"


def test_RM2_end_date_and_resume_without_backfill(ready: Api) -> None:
    reminder = _reminder(ready, frequency="weekly", anchor_date="2026-10-26")
    ready.patch(f"/reminders/{reminder['id']}", {"active": False})
    ready.clock.today = dt.date(2026, 11, 20)
    ready.run_scheduler()
    assert [o["due_date"] for o in _open(ready)] == ["2026-10-26"]  # paused: nothing new
    ready.patch(f"/reminders/{reminder['id']}", {"active": True, "end_date": "2026-11-30"})
    ready.clock.today = dt.date(2026, 12, 20)
    ready.run_scheduler()
    assert [o["due_date"] for o in _open(ready)] == ["2026-10-26", "2026-11-23", "2026-11-30"]


def test_RM3_name_and_kind_required_prefill_optional(ready: Api) -> None:
    assert _reminder(ready, 422, name=" ")["code"] == "RM3"
    assert _reminder(ready, 422, kind=None)["code"] == "RM3"
    bare = _reminder(ready, category_id=None, budget_id=None)
    assert (bare["amount_minor"], bare["category_id"], bare["budget_id"]) == (None, None, None)
    _reminder(ready, 422, kind="income", category_id=ready.category_id("Salary", "income"))


def test_RM3_record_uses_prefill_and_due_date(ready: Api) -> None:
    _reminder(ready, description="EVN", tags=["bills"])
    occurrence = _open(ready)[0]
    assert occurrence["prefill"]["amount_minor"] is None
    ready.error(
        "POST", f"/reminders/occurrences/{occurrence['id']}/record", "T2", json={}
    )  # amount missing: T1-T4 apply
    transaction = ready.post(
        f"/reminders/occurrences/{occurrence['id']}/record", {"amount_minor": 8312}
    )
    assert (transaction["amount_minor"], transaction["date"]) == (8312, "2026-10-28")
    assert (transaction["category_name"], transaction["budget_name"]) == ("Utilities", "Needs")
    assert (transaction["description"], transaction["tags"]) == ("EVN", ["bills"])
    closed = ready.get(f"/reminders/occurrences/{occurrence['id']}")
    assert (closed["status"], closed["transaction_id"]) == ("recorded", transaction["id"])
    assert closed["closed_at"] is not None
    assert _open(ready) == []


def test_RM3_record_fields_override_prefill(ready: Api) -> None:
    _reminder(ready, amount_minor=5000)
    occurrence = _open(ready)[0]
    transaction = ready.post(
        f"/reminders/occurrences/{occurrence['id']}/record",
        {"amount_minor": 6100, "date": "2026-10-30", "budget_id": ready.budget_id("Wants")},
    )
    assert (transaction["amount_minor"], transaction["date"], transaction["budget_name"]) == (
        6100,
        "2026-10-30",
        "Wants",
    )


def test_RM4_dismissed_and_recorded_never_reopen(ready: Api) -> None:
    _two_weekly(ready)
    first, second = _open(ready)
    assert (
        ready.post(f"/reminders/occurrences/{first['id']}/dismiss", {}, expect=200)["status"]
        == "dismissed"
    )
    transaction = ready.post(f"/reminders/occurrences/{second['id']}/record", {})
    ready.error("POST", f"/reminders/occurrences/{first['id']}/record", "RM4", json={})
    ready.error("POST", f"/reminders/occurrences/{second['id']}/dismiss", "RM4", json={})
    ready.delete(f"/transactions/{transaction['id']}")
    ready.run_scheduler()
    assert _open(ready) == []
    assert ready.get(f"/reminders/occurrences/{second['id']}")["status"] == "recorded"


def test_RM5_edits_show_in_open_occurrences_and_schedule_applies_onward(ready: Api) -> None:
    reminder = _reminder(ready)
    occurrence = _open(ready)[0]
    ready.patch(f"/reminders/{reminder['id']}", {"amount_minor": 7000, "anchor_date": "2026-10-05"})
    reopened = ready.get(f"/reminders/occurrences/{occurrence['id']}")
    assert (reopened["status"], reopened["prefill"]["amount_minor"]) == ("open", 7000)
    ready.clock.today = dt.date(2026, 11, 10)
    ready.run_scheduler()
    assert [o["due_date"] for o in _open(ready)] == ["2026-10-28", "2026-11-05"]


def test_RM5_deleting_a_reminder_keeps_recorded_transactions(ready: Api) -> None:
    reminder = _two_weekly(ready)
    first, second = _open(ready)
    transaction = ready.post(f"/reminders/occurrences/{first['id']}/record", {})
    ready.delete(f"/reminders/{reminder['id']}")
    ready.get(f"/reminders/occurrences/{second['id']}", expect=404)
    assert ready.get(f"/transactions/{transaction['id']}")["amount_minor"] == 5000


def test_RM6_archived_category_and_budget_are_not_prefilled(ready: Api) -> None:
    _reminder(ready)
    ready.patch(f"/categories/{ready.category_id('Utilities')}", {"archived": True})
    ready.patch(f"/budgets/{ready.budget_id('Needs')}", {"archived": True})
    prefill = _open(ready)[0]["prefill"]
    assert (prefill["category_id"], prefill["budget_id"]) == (None, None)
    reminder = ready.get("/reminders")["items"][0]
    assert reminder["category_name"] == "Utilities"  # the reminder itself keeps them


def test_RM7_notified_once(ready: Api) -> None:
    _reminder(ready)
    occurrence = _open(ready)[0]
    assert occurrence["notified_at"] is None
    first = ready.post(f"/reminders/occurrences/{occurrence['id']}/notified", {}, expect=200)
    second = ready.post(f"/reminders/occurrences/{occurrence['id']}/notified", {}, expect=200)
    assert first["notified_at"] is not None
    assert second["notified_at"] == first["notified_at"]


def test_reminder_occurrence_listing_filters(ready: Api) -> None:
    _two_weekly(ready)
    first, _second = _open(ready)
    ready.post(f"/reminders/occurrences/{first['id']}/dismiss", {}, expect=200)
    assert len(ready.get("/reminders/occurrences")["items"]) == 2
    assert len(ready.get("/reminders/occurrences?status=dismissed")["items"]) == 1
    ready.error("GET", "/reminders/occurrences?status=closed", "validation_error")

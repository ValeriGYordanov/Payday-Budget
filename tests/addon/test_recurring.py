"""§5.5 Recurring rules and generation (R1-R5)."""

import datetime as dt
import logging
from pathlib import Path

import pytest

from app.main import create_app
from tests.addon.conftest import Api, Clock, ingress_client, make_app

# The `ready` fixture: first period 2026-10-25, today 2026-11-01.


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"frequency": "daily"}, "frequency"),
        ({"frequency": None}, "frequency"),
        ({"interval": 0}, "interval"),
        ({"anchor_date": None}, "anchor_date"),
        ({"end_date": "2026-10-24"}, "end_date"),
    ],
)
def test_R1_rule_validation(ready: Api, fields: dict[str, object], field: str) -> None:
    body = ready.rule(expect=422, **fields)
    assert (body["code"], body["field"]) == ("R1", field)


def test_R1_rule_crud(ready: Api) -> None:
    rule = ready.rule(frequency="monthly", interval=2, description=" Rent ", tags=["home"])
    assert rule["interval"] == 2
    assert (rule["description"], rule["tags"], rule["active"]) == ("Rent", ["home"], True)
    assert ready.get(f"/recurring/{rule['id']}") == rule
    assert ready.get("/recurring")["items"] == [rule]
    updated = ready.patch(f"/recurring/{rule['id']}", {"amount_minor": 5, "frequency": "yearly"})
    assert (updated["amount_minor"], updated["frequency"]) == (5, "yearly")
    ready.delete(f"/recurring/{rule['id']}")
    ready.get(f"/recurring/{rule['id']}", expect=404)


def test_T1_recurring_amount_must_be_positive(ready: Api) -> None:
    assert ready.rule(expect=422, amount_minor=0)["code"] == "T1"


def test_T2_recurring_category_must_match_kind(ready: Api) -> None:
    salary = ready.category_id("Salary", "income")
    assert ready.rule(expect=422, category_id=salary)["code"] == "T2"
    assert ready.rule(expect=422, kind=None)["code"] == "T2"


def test_B6_recurring_budget_rules(ready: Api) -> None:
    assert ready.rule(expect=422, budget_id=None)["code"] == "B6"
    salary = ready.category_id("Salary", "income")
    assert ready.rule(expect=422, kind="income", category_id=salary)["code"] == "B6"
    income = ready.rule(kind="income", category_id=salary, budget_id=None)
    assert income["budget_id"] is None


def test_B4_C2_recurring_rejects_archived_references(ready: Api) -> None:
    ready.patch(f"/budgets/{ready.budget_id('Wants')}", {"archived": True})
    assert ready.rule(expect=422, budget_id=ready.budget_id("Wants"))["code"] == "B4"
    ready.patch(f"/categories/{ready.category_id('Health')}", {"archived": True})
    assert ready.rule(expect=422, category_id=ready.category_id("Health"))["code"] == "C2"


def test_R2_new_rule_backfills_from_anchor_to_today(ready: Api) -> None:
    rule = ready.rule(anchor_date="2026-10-25")
    assert ready.generated(rule["id"]) == ["2026-10-25", "2026-11-01"]
    assert rule["last_generated_date"] == "2026-11-01"


def test_R2_scheduler_catches_up_on_start_after_downtime(
    ready: Api, data_dir: Path, clock: Clock
) -> None:
    rule = ready.rule(anchor_date="2026-10-25")
    clock.today = dt.date(2026, 11, 22)  # add-on was down for three weeks
    app = make_app(data_dir, clock)
    with ingress_client(app) as client:
        restarted = Api(client, clock)
        assert restarted.generated(rule["id"]) == [
            "2026-10-25",
            "2026-11-01",
            "2026-11-08",
            "2026-11-15",
            "2026-11-22",
        ]
        assert restarted.get(f"/recurring/{rule['id']}")["last_generated_date"] == "2026-11-22"
    app.state.engine.dispose()


def test_R2_generation_is_idempotent(ready: Api) -> None:
    from app.models import RecurringRule

    rule = ready.rule(anchor_date="2026-10-25")
    assert ready.run_scheduler() == 0
    # Even if last_generated_date is lost, the UNIQUE index prevents duplicates.
    factory = ready.client.app.state.session_factory  # type: ignore[attr-defined]
    with factory() as session:
        session.get(RecurringRule, rule["id"]).last_generated_date = None
        session.commit()
    assert ready.run_scheduler() == 0
    assert ready.generated(rule["id"]) == ["2026-10-25", "2026-11-01"]


def test_R2_monthly_rule_generates_each_day_of_catch_up(ready: Api) -> None:
    ready.clock.today = dt.date(2027, 3, 31)
    rule = ready.rule(frequency="monthly", anchor_date="2026-10-31")
    assert ready.generated(rule["id"]) == [
        "2026-10-31",
        "2026-11-30",
        "2026-12-31",
        "2027-01-31",
        "2027-02-28",
        "2027-03-31",
    ]


def test_R2_paused_rule_resumes_without_backfill(ready: Api) -> None:
    rule = ready.rule(anchor_date="2026-11-01")
    ready.patch(f"/recurring/{rule['id']}", {"active": False})
    ready.clock.today = dt.date(2026, 11, 22)
    assert ready.run_scheduler() == 0
    resumed = ready.patch(f"/recurring/{rule['id']}", {"active": True})
    assert ready.generated(rule["id"]) == ["2026-11-01", "2026-11-22"]
    assert resumed["last_generated_date"] == "2026-11-22"


def test_R2_inactive_rule_generates_nothing(ready: Api) -> None:
    rule = ready.rule(active=False)
    assert ready.generated(rule["id"]) == []
    assert rule["last_generated_date"] is None


def test_R3_generated_transactions_are_normal_transactions(ready: Api) -> None:
    rule = ready.rule(anchor_date="2026-11-01", tags=["auto"], description="Gym")
    (tx,) = ready.get("/transactions")["items"]
    assert tx["recurring_rule_id"] == rule["id"]
    assert tx["occurrence_date"] == "2026-11-01"
    assert (tx["kind"], tx["amount_minor"], tx["description"], tx["tags"]) == (
        "expense",
        1000,
        "Gym",
        ["auto"],
    )
    assert tx["created_by_id"] is None
    assert ready.budget_row(ready.summary(), "Needs")["spent_minor"] == 1000
    edited = ready.patch(f"/transactions/{tx['id']}", {"amount_minor": 1200})
    assert edited["amount_minor"] == 1200


def test_R3_editing_rule_does_not_change_generated(ready: Api) -> None:
    rule = ready.rule(anchor_date="2026-10-25")
    ready.patch(f"/recurring/{rule['id']}", {"amount_minor": 9999, "anchor_date": "2026-10-20"})
    amounts = {t["amount_minor"] for t in ready.get("/transactions")["items"]}
    assert amounts == {1000}
    ready.clock.today = dt.date(2026, 11, 3)
    ready.run_scheduler()  # new schedule: 2026-11-03 is the next occurrence
    assert ready.generated(rule["id"]) == ["2026-10-25", "2026-11-01", "2026-11-03"]


def test_R3_deleted_generated_transaction_is_not_regenerated(ready: Api) -> None:
    rule = ready.rule(anchor_date="2026-10-25")
    first = next(t for t in ready.get("/transactions")["items"] if t["date"] == "2026-10-25")
    ready.delete(f"/transactions/{first['id']}")
    ready.run_scheduler()
    ready.clock.today = dt.date(2026, 11, 8)
    ready.run_scheduler()
    assert ready.generated(rule["id"]) == ["2026-11-01", "2026-11-08"]


def test_R3_deleting_rule_keeps_generated_transactions(ready: Api) -> None:
    rule = ready.rule(anchor_date="2026-10-25")
    ready.delete(f"/recurring/{rule['id']}")
    items = ready.get("/transactions")["items"]
    assert len(items) == 2
    assert all(t["recurring_rule_id"] is None for t in items)


def test_R4_never_generates_future_transactions(ready: Api) -> None:
    future = ready.rule(anchor_date="2026-11-02")
    assert ready.generated(future["id"]) == []
    weekly = ready.rule(anchor_date="2026-10-31")
    assert ready.generated(weekly["id"]) == ["2026-10-31"]
    ready.clock.today = dt.date(2026, 11, 6)
    ready.run_scheduler()
    assert ready.generated(weekly["id"]) == ["2026-10-31"]
    assert ready.generated(future["id"]) == ["2026-11-02"]


def test_R4_end_date_is_inclusive(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 12, 31)
    rule = ready.rule(anchor_date="2026-10-25", end_date="2026-11-08")
    assert ready.generated(rule["id"]) == ["2026-10-25", "2026-11-01", "2026-11-08"]


def test_R5_occurrences_before_first_period_are_skipped_and_logged(
    ready: Api, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        rule = ready.rule(anchor_date="2026-10-11")
    assert ready.generated(rule["id"]) == ["2026-10-25", "2026-11-01"]
    skipped = [r.getMessage() for r in caplog.records if "R5" in r.getMessage()]
    assert len(skipped) == 2
    assert "2026-10-11" in skipped[0] and "2026-10-18" in skipped[1]
    # Skipped occurrences are not retried once an earlier period exists.
    ready.new_period("2026-10-01")
    ready.run_scheduler()
    assert ready.generated(rule["id"]) == ["2026-10-25", "2026-11-01"]


def test_R5_rule_with_no_periods_skips_everything(api: Api) -> None:
    category = api.post("/categories", {"name": "Pay", "kind": "income"})
    body = {
        "kind": "income",
        "amount_minor": 1,
        "category_id": category["id"],
        "frequency": "weekly",
        "anchor_date": "2026-10-25",
    }
    rule = api.post("/recurring", body)
    assert api.get("/transactions")["total"] == 0
    assert rule["last_generated_date"] == "2026-11-01"


def test_R2_archived_reference_skips_occurrence_and_logs(
    ready: Api, caplog: pytest.LogCaptureFixture
) -> None:
    rule = ready.rule(anchor_date="2026-11-01", budget_id=ready.budget_id("Wants"))
    ready.patch(f"/budgets/{ready.budget_id('Wants')}", {"archived": True})
    ready.clock.today = dt.date(2026, 11, 8)
    with caplog.at_level(logging.WARNING):
        assert ready.run_scheduler() == 0
    assert any("B4" in r.getMessage() for r in caplog.records)
    assert ready.generated(rule["id"]) == ["2026-11-01"]
    assert ready.get(f"/recurring/{rule['id']}")["last_generated_date"] == "2026-11-08"


def test_recurring_references_block_delete(ready: Api) -> None:
    ready.rule(anchor_date="2026-11-02", category_id=ready.category_id("Health"))
    ready.error("DELETE", f"/categories/{ready.category_id('Health')}", "conflict", status=409)
    ready.post("/budgets", {"name": "Gym", "percent": "0"})
    ready.rule(anchor_date="2026-11-02", budget_id=ready.budget_id("Gym"))
    ready.error("DELETE", f"/budgets/{ready.budget_id('Gym')}", "conflict", status=409)


def test_R2_startup_run_failure_does_not_block_start(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_today() -> dt.date:
        raise RuntimeError("boom")

    app = create_app(tmp_path, today=broken_today, announce=lambda _token: None)
    with caplog.at_level(logging.ERROR), ingress_client(app) as client:
        assert client.get("/api/v1/setup").status_code == 200
    assert any("scheduler run failed" in r.getMessage() for r in caplog.records)
    app.state.engine.dispose()

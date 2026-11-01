"""§5.4 Transactions, tags and the transactions list."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from tests.addon.conftest import Api


@pytest.mark.parametrize("amount", [0, -100])
def test_T1_amount_must_be_positive(ready: Api, amount: int) -> None:
    body = {
        "kind": "income",
        "amount_minor": amount,
        "category_id": ready.category_id("Salary", "income"),
    }
    ready.error("POST", "/transactions", "T1", json=body)
    tx = ready.income(100, "2026-10-26")
    ready.error("PATCH", f"/transactions/{tx['id']}", "T1", json={"amount_minor": amount})


@pytest.mark.parametrize("amount", [10.5, "100", True])
def test_T1_amount_must_be_an_integer_in_minor_units(ready: Api, amount: object) -> None:
    body = {"kind": "income", "amount_minor": amount, "category_id": 1}
    ready.error("POST", "/transactions", "validation_error", json=body)


def test_T1_sign_comes_from_kind(ready: Api) -> None:
    ready.income(1000, "2026-10-26")
    ready.expense(300, "2026-10-26")
    summary = ready.summary()
    assert (summary["income_minor"], summary["expenses_minor"]) == (1000, 300)
    assert summary["balance_minor"] == 700


@pytest.mark.parametrize("missing", ["kind", "amount_minor", "category_id"])
def test_T2_required_fields(ready: Api, missing: str) -> None:
    body = {
        "kind": "expense",
        "amount_minor": 100,
        "category_id": ready.category_id("Food"),
        "budget_id": ready.budget_id("Needs"),
    }
    del body[missing]
    assert ready.error("POST", "/transactions", "T2", json=body)["field"] == missing


def test_T2_date_defaults_to_today(ready: Api) -> None:
    body = {
        "kind": "income",
        "amount_minor": 100,
        "category_id": ready.category_id("Salary", "income"),
    }
    assert ready.post("/transactions", body)["date"] == ready.clock.today.isoformat()


def test_T2_category_must_match_kind(ready: Api) -> None:
    body = {
        "kind": "income",
        "amount_minor": 100,
        "category_id": ready.category_id("Food"),
        "date": "2026-10-26",
    }
    ready.error("POST", "/transactions", "T2", json=body)
    tx = ready.expense(100, "2026-10-26")
    salary = ready.category_id("Salary", "income")
    ready.error("PATCH", f"/transactions/{tx['id']}", "T2", json={"category_id": salary})


def test_T2_kind_change_needs_matching_category_and_budget(ready: Api) -> None:
    tx = ready.expense(100, "2026-10-26")
    salary = ready.category_id("Salary", "income")
    ready.error(
        "PATCH", f"/transactions/{tx['id']}", "B6", json={"kind": "income", "category_id": salary}
    )
    changed = ready.patch(
        f"/transactions/{tx['id']}", {"kind": "income", "category_id": salary, "budget_id": None}
    )
    assert (changed["kind"], changed["budget_id"]) == ("income", None)


def test_T2_optional_description_and_tags(ready: Api) -> None:
    tx = ready.expense(100, "2026-10-26", description="  Lidl  ", tags=["weekly", "food", "weekly"])
    assert tx["description"] == "Lidl"
    assert tx["tags"] == ["food", "weekly"]
    assert {t["name"] for t in ready.get("/tags")["items"]} == {"food", "weekly"}
    plain = ready.expense(100, "2026-10-26")
    assert (plain["description"], plain["tags"]) == (None, [])
    cleared = ready.patch(f"/transactions/{tx['id']}", {"description": None, "tags": []})
    assert (cleared["description"], cleared["tags"]) == (None, [])


def test_T2_description_max_500(ready: Api) -> None:
    ready.expense(100, "2026-10-26", description="x" * 500)
    body = {
        "kind": "income",
        "amount_minor": 1,
        "category_id": ready.category_id("Salary", "income"),
        "description": "x" * 501,
    }
    assert (
        ready.error("POST", "/transactions", "validation_error", json=body)["field"]
        == "description"
    )


def test_T3_created_by_from_ingress_headers(ready: Api) -> None:
    headers = {
        "X-Remote-User-Id": "u1",
        "X-Remote-User-Name": "valeri",
        "X-Remote-User-Display-Name": "Valeri",
    }
    tx = ready.expense(100, "2026-10-26", headers=headers)
    assert (tx["created_by_id"], tx["created_by_name"]) == ("u1", "Valeri")
    listed = ready.get("/transactions")["items"][0]
    assert listed["created_by_name"] == "Valeri"


def test_T3_created_by_from_acting_user_headers_on_token_requests(ready: Api) -> None:
    headers = {
        "Authorization": f"Bearer {ready.client.app.state.token}",  # type: ignore[attr-defined]
        "X-Acting-User-Id": "u2",
        "X-Acting-User-Name": "Wife",
        "X-Remote-User-Id": "x",
    }
    client = TestClient(ready.client.app)  # not from the Supervisor
    body = {
        "kind": "expense",
        "amount_minor": 100,
        "category_id": ready.category_id("Food"),
        "budget_id": ready.budget_id("Needs"),
        "date": "2026-10-26",
    }
    tx = client.post("/api/v1/transactions", json=body, headers=headers).json()
    assert (tx["created_by_id"], tx["created_by_name"]) == ("u2", "Wife")
    ready.clock.today = dt.date(2026, 11, 25)
    period = client.post("/api/v1/periods", json={}, headers=headers).json()
    assert (period["created_by_id"], period["created_by_name"]) == ("u2", "Wife")


def test_T3_ingress_ignores_acting_user_headers(ready: Api) -> None:
    headers = {"X-Acting-User-Id": "u2", "X-Remote-User-Id": "u1", "X-Remote-User-Name": "v"}
    tx = ready.expense(100, "2026-10-26", headers=headers)
    assert (tx["created_by_id"], tx["created_by_name"]) == ("u1", "v")


def test_T3_created_by_is_null_without_identity(ready: Api) -> None:
    tx = ready.expense(100, "2026-10-26")
    assert (tx["created_by_id"], tx["created_by_name"]) == (None, None)
    assert tx["created_at"].endswith("+00:00")


def test_T4_any_user_can_edit_and_delete_any_transaction_and_settings(ready: Api) -> None:
    tx = ready.expense(100, "2026-10-26", headers={"X-Remote-User-Id": "a"})
    other = {"X-Remote-User-Id": "b"}
    edited = ready.patch(f"/transactions/{tx['id']}", {"amount_minor": 250}, headers=other)
    assert edited["amount_minor"] == 250
    assert edited["created_by_id"] == "a"  # creator is kept
    ready.patch("/settings", {"currency": "USD", "confirm": True}, headers=other)
    ready.patch(f"/budgets/{ready.budget_id('Needs')}", {"percent": "45"}, headers=other)
    ready.delete(f"/transactions/{tx['id']}", headers=other)
    ready.get(f"/transactions/{tx['id']}", expect=404)


def test_tags_crud_and_delete_detaches_from_transactions(ready: Api) -> None:
    tag = ready.post("/tags", {"name": "trip"})
    ready.error("POST", "/tags", "conflict", status=409, json={"name": "trip"})
    tx = ready.expense(100, "2026-10-26", tags=["trip"])
    assert ready.patch(f"/tags/{tag['id']}", {"name": "holiday"})["name"] == "holiday"
    assert ready.get(f"/transactions/{tx['id']}")["tags"] == ["holiday"]
    ready.delete(f"/tags/{tag['id']}")
    assert ready.get(f"/transactions/{tx['id']}")["tags"] == []


def test_transaction_list_filters_and_pagination(ready: Api) -> None:
    ready.clock.today = dt.date(2026, 12, 1)
    second = ready.new_period("2026-11-25")
    ready.income(300000, "2026-10-25", description="Salary Oct")
    ready.expense(1000, "2026-10-26", budget="Needs", category="Food", tags=["weekly"])
    ready.expense(2000, "2026-11-10", budget="Wants", category="Shopping", description="50% off")
    ready.expense(
        3000, "2026-11-26", budget="Needs", category="Food", headers={"X-Remote-User-Id": "w"}
    )

    def ids(query: str) -> list[int]:
        return [t["amount_minor"] for t in ready.get(f"/transactions?{query}")["items"]]

    assert ids("") == [3000, 2000, 1000, 300000]  # newest first
    assert ids(f"period={second['id']}") == [3000]
    assert ids("period=current") == [3000]
    assert ids("date_from=2026-10-26&date_to=2026-11-10") == [2000, 1000]
    assert ids("kind=income") == [300000]
    assert ids(f"category={ready.category_id('Food')}") == [3000, 1000]
    assert ids(f"budget={ready.budget_id('Wants')}") == [2000]
    tag_id = ready.get("/tags")["items"][0]["id"]
    assert ids(f"tag={tag_id}") == [1000]
    assert ids("user=w") == [3000]
    assert ids("q=salary") == [300000]
    assert ids("q=50%25") == [2000]  # LIKE wildcards are escaped
    assert ids("q=5_") == []
    page = ready.get("/transactions?limit=2&offset=1")
    assert ([t["amount_minor"] for t in page["items"]], page["total"]) == ([2000, 1000], 4)
    ready.error("GET", "/transactions?period=foo", "validation_error")
    ready.error("GET", "/transactions?limit=0", "validation_error")


def test_transaction_references_must_exist(ready: Api) -> None:
    body = {"kind": "income", "amount_minor": 1, "category_id": 999}
    ready.error("POST", "/transactions", "not_found", status=404, json=body)
    ready.error("GET", "/transactions/999", "not_found", status=404)


def test_unknown_fields_are_rejected(ready: Api) -> None:
    body = {"kind": "income", "amount_minor": 1, "category_id": 1, "period_id": 1}
    assert (
        ready.error("POST", "/transactions", "validation_error", json=body)["field"] == "period_id"
    )

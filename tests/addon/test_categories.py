"""§5.3 Categories, and v1.1 A1/A2 (transaction counts)."""

from typing import Any

from sqlalchemy import event

from app.services.categories import SEED
from tests.addon.conftest import Api


def test_C1_category_has_kind_and_is_not_linked_to_budgets(ready: Api) -> None:
    first = ready.expense(100, "2026-10-26", budget="Needs", category="Food")
    second = ready.expense(100, "2026-10-26", budget="Wants", category="Food")
    assert first["category_id"] == second["category_id"]
    assert {first["budget_id"], second["budget_id"]} == {
        ready.budget_id("Needs"),
        ready.budget_id("Wants"),
    }
    assert "budget_id" not in ready.get(f"/categories/{first['category_id']}")


def test_C1_kind_cannot_change_when_category_has_transactions(ready: Api) -> None:
    ready.expense(100, "2026-10-26", category="Food")
    food = ready.category_id("Food")
    ready.error("PATCH", f"/categories/{food}", "C1", json={"kind": "income"})
    health = ready.category_id("Health")
    assert ready.patch(f"/categories/{health}", {"kind": "income"})["kind"] == "income"


def test_C1_name_is_unique_per_kind(ready: Api) -> None:
    ready.error(
        "POST", "/categories", "conflict", status=409, json={"name": "Food", "kind": "expense"}
    )
    assert ready.post("/categories", {"name": "Food", "kind": "income"})["kind"] == "income"


def test_C2_category_with_transactions_can_only_be_archived(ready: Api) -> None:
    ready.expense(100, "2026-10-26", category="Food")
    food = ready.category_id("Food")
    ready.error("DELETE", f"/categories/{food}", "C2")
    assert ready.patch(f"/categories/{food}", {"archived": True})["archived"] is True


def test_C2_category_without_transactions_can_be_deleted(ready: Api) -> None:
    health = ready.category_id("Health")
    ready.delete(f"/categories/{health}")
    ready.get(f"/categories/{health}", expect=404)


def test_C2_archived_category_cannot_be_chosen(ready: Api) -> None:
    tx = ready.expense(100, "2026-10-26", category="Food")
    food = ready.category_id("Food")
    ready.patch(f"/categories/{food}", {"archived": True})
    body = {
        "kind": "expense",
        "amount_minor": 1,
        "category_id": food,
        "budget_id": ready.budget_id("Needs"),
        "date": "2026-10-26",
    }
    ready.error("POST", "/transactions", "C2", json=body)
    ready.patch(f"/transactions/{tx['id']}", {"amount_minor": 5})  # may keep it
    other = ready.expense(100, "2026-10-26", category="Health")
    ready.error("PATCH", f"/transactions/{other['id']}", "C2", json={"category_id": food})


def test_C3_setup_seeds_default_categories(ready: Api) -> None:
    items = ready.get("/categories")["items"]
    assert {(c["name"], c["kind"]) for c in items} == {(n, k) for n, k, _ in SEED}
    assert {c["name"] for c in items if c["kind"] == "income"} == {"Salary", "Other income"}
    assert all(c["icon"].startswith("mdi:") for c in items)


def test_C3_seeded_categories_are_editable(ready: Api) -> None:
    food = ready.category_id("Food")
    updated = ready.patch(f"/categories/{food}", {"name": "Groceries", "icon": "mdi:cart"})
    assert (updated["name"], updated["icon"]) == ("Groceries", "mdi:cart")


def test_C3_category_icon_must_be_mdi(ready: Api) -> None:
    ready.error(
        "POST",
        "/categories",
        "validation_error",
        json={"name": "X", "kind": "expense", "icon": "fa:x"},
    )


def test_C3_category_list_filters(ready: Api) -> None:
    food = ready.category_id("Food")
    ready.patch(f"/categories/{food}", {"archived": True})
    archived = ready.get("/categories?archived=true")["items"]
    assert [c["name"] for c in archived] == ["Food"]
    assert all(c["kind"] == "income" for c in ready.get("/categories?kind=income")["items"])


def test_A1_category_list_carries_transaction_count_across_periods(ready: Api) -> None:
    ready.expense(100, "2026-10-26", category="Food")
    ready.income(5000, "2026-10-27")
    ready.new_period("2026-10-30")
    ready.expense(200, "2026-10-31", category="Food")
    ready.expense(300, "2026-10-31", category="Health")
    health = ready.category_id("Health")
    ready.patch(f"/categories/{health}", {"archived": True})

    counts = {
        (c["name"], c["kind"]): c["transaction_count"] for c in ready.get("/categories")["items"]
    }
    assert counts[("Food", "expense")] == 2  # any period
    assert counts[("Health", "expense")] == 1  # archived categories keep their count
    assert counts[("Salary", "income")] == 1
    assert counts[("Housing", "expense")] == 0
    income = ready.get("/categories?kind=income")["items"]
    assert [(c["name"], c["transaction_count"]) for c in income] == [
        ("Other income", 0),
        ("Salary", 1),
    ]
    archived = ready.get("/categories?archived=true")["items"]
    assert [(c["name"], c["transaction_count"]) for c in archived] == [("Health", 1)]


def test_A1_transaction_counts_come_from_one_query(ready: Api) -> None:
    for category in ("Food", "Health", "Transport"):
        ready.expense(100, "2026-10-26", category=category)
    app: Any = ready.client.app
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", record)
    try:
        items = ready.get("/categories")["items"]
    finally:
        event.remove(app.state.engine, "before_cursor_execute", record)
    assert len(items) == len(SEED)
    assert len([s for s in statements if "transactions" in s]) == 1


def test_A2_single_category_carries_transaction_count(ready: Api) -> None:
    tx = ready.expense(100, "2026-10-26", category="Food")
    ready.expense(100, "2026-10-27", category="Food")
    food = ready.category_id("Food")
    assert ready.get(f"/categories/{food}")["transaction_count"] == 2
    ready.delete(f"/transactions/{tx['id']}")
    assert ready.get(f"/categories/{food}")["transaction_count"] == 1
    # D11: every category response has the same shape.
    assert ready.patch(f"/categories/{food}", {"icon": "mdi:food-apple"})["transaction_count"] == 1
    created = ready.post("/categories", {"name": "Pets", "kind": "expense"})
    assert created["transaction_count"] == 0

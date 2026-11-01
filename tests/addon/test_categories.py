"""§5.3 Categories."""

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

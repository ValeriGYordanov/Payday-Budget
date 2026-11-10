"""v1.2 §6 Suggestions from history (SPEC-1.2 SG1-SG3, D15)."""

import datetime as dt
from typing import Any

from tests.addon.conftest import Api


def _suggest(api: Api, category: str, kind: str = "expense") -> Any:
    return api.get(f"/suggestions?category={api.category_id(category, kind)}")


def test_SG1_budget_used_most_with_the_category(ready: Api) -> None:
    ready.expense(100, "2026-10-26", budget="Needs", category="Food")
    ready.expense(100, "2026-10-27", budget="Wants", category="Food")
    ready.expense(100, "2026-10-28", budget="Wants", category="Food")
    ready.expense(100, "2026-10-28", budget="Needs", category="Health")
    assert _suggest(ready, "Food")["budget_name"] == "Wants"
    assert _suggest(ready, "Health")["budget_name"] == "Needs"
    assert _suggest(ready, "Transport") == {
        "budget_id": None,
        "budget_name": None,
        "descriptions": [],
    }


def test_SG1_ties_go_to_the_most_recent_use(ready: Api) -> None:
    ready.expense(100, "2026-10-26", budget="Wants", category="Food")
    ready.expense(100, "2026-10-29", budget="Needs", category="Food")
    assert _suggest(ready, "Food")["budget_name"] == "Needs"


def test_SG1_only_the_last_90_days_and_active_budgets(ready: Api) -> None:
    ready.expense(100, "2026-10-26", budget="Wants", category="Food")
    ready.expense(100, "2026-10-27", budget="Wants", category="Food")
    ready.clock.today = dt.date(2027, 2, 1)  # window starts 2026-11-03: 10-26/27 are out
    ready.expense(100, "2027-01-10", budget="Needs", category="Food")
    assert _suggest(ready, "Food")["budget_name"] == "Needs"
    ready.patch(f"/budgets/{ready.budget_id('Needs')}", {"archived": True})
    assert _suggest(ready, "Food")["budget_name"] is None  # Wants is outside the window


def test_SG2_previous_descriptions_most_recent_first_up_to_5(ready: Api) -> None:
    for day, text in [
        ("2026-10-25", "Metro"),
        ("2026-10-26", "Lidl"),
        ("2026-10-27", "Billa"),
        ("2026-10-28", "Kaufland"),
        ("2026-10-29", "Fantastico"),
        ("2026-10-30", "T-Market"),
        ("2026-10-31", "Lidl"),  # repeated: counts once, at its latest use
    ]:
        ready.expense(100, day, category="Food", description=text)
    ready.expense(100, "2026-10-31", category="Health", description="Pharmacy")
    assert _suggest(ready, "Food")["descriptions"] == [
        "Lidl",
        "T-Market",
        "Fantastico",
        "Kaufland",
        "Billa",
    ]


def test_SG3_suggestions_store_nothing(ready: Api) -> None:
    ready.expense(100, "2026-10-26", budget="Wants", category="Food", description="Lidl")
    before = ready.client.get("/api/v1/export").content
    _suggest(ready, "Food")
    after = ready.client.get("/api/v1/export").content
    import io
    import zipfile

    def tables(data: bytes) -> dict[str, bytes]:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {n: archive.read(n) for n in archive.namelist() if n.endswith(".csv")}

    assert tables(before) == tables(after)

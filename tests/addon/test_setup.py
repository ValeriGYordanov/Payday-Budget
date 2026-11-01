"""First-run setup endpoint (§6.6, P6, C3, K1)."""

from tests.addon.conftest import Api


def test_setup_creates_currency_budgets_first_period_and_seed(api: Api) -> None:
    assert api.get("/setup") == {"setup_completed": False}
    result = api.setup(currency="USD")
    assert result == {"currency": "USD", "minor_unit": 2, "setup_completed": True}
    assert api.get("/setup") == {"setup_completed": True}
    (period,) = api.get("/periods")["items"]
    assert (period["start_date"], period["name"]) == ("2026-10-25", "October 2026")
    snapshot = {b["name"]: b["percent"] for b in api.get(f"/periods/{period['id']}")["budgets"]}
    assert snapshot == {"Needs": "50.00", "Wants": "30.00", "Savings": "20.00"}
    assert len(api.get("/categories")["items"]) == 11


def test_setup_runs_only_once(ready: Api) -> None:
    body = {"first_period": {"start_date": "2026-10-26"}}
    ready.error("POST", "/setup", "conflict", status=409, json=body)


def test_setup_is_atomic(api: Api) -> None:
    budgets = [{"name": "A", "percent": "60"}, {"name": "B", "percent": "50"}]
    api.error(
        "POST",
        "/setup",
        "B1",
        json={"first_period": {"start_date": "2026-10-25"}, "budgets": budgets},
    )
    api.error("POST", "/setup", "P2", json={"first_period": {"start_date": "2026-11-02"}})
    assert api.get("/setup") == {"setup_completed": False}
    assert api.get("/budgets")["items"] == []
    assert api.get("/periods")["items"] == []
    assert api.get("/categories")["items"] == []


def test_setup_with_custom_period_name_and_no_budgets(api: Api) -> None:
    api.post("/setup", {"first_period": {"start_date": "2026-10-25", "name": "Start"}})
    assert api.summary()["period"]["name"] == "Start"
    assert api.summary()["unallocated"]["percent"] == "100.00"

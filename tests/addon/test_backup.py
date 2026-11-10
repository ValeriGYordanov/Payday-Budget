"""v1.2 §5 Export and import (SPEC-1.2 EX1-EX6, D13, D14)."""

import csv
import datetime as dt
import io
import json
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.addon.conftest import Api, Clock, ingress_client, make_app


def _export(api: Api) -> bytes:
    response = api.client.get("/api/v1/export")
    assert response.status_code == 200, response.text
    return response.content


def _import(api: Api, data: bytes, *, confirm: bool, expect: int = 200) -> Any:
    query = "?confirm=true" if confirm else ""
    return api.request(
        "POST",
        f"/import{query}",
        expect,
        content=data,
        headers={"Content-Type": "application/zip"},
    )


def _rows(data: bytes, table: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return list(csv.DictReader(io.StringIO(archive.read(f"{table}.csv").decode())))


def _edit(data: bytes, table: str, change: Callable[[list[dict[str, str]]], None]) -> bytes:
    """A copy of the backup with `change` applied to one CSV's rows."""
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with source, zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name == f"{table}.csv":
                reader = csv.DictReader(io.StringIO(content.decode()))
                rows = list(reader)
                change(rows)
                text = io.StringIO()
                writer = csv.DictWriter(text, fieldnames=list(reader.fieldnames or []))
                writer.writeheader()
                writer.writerows(rows)
                content = text.getvalue().encode()
            target.writestr(name, content)
    return out.getvalue()


def _populate(api: Api) -> None:
    """Setup plus a bit of everything: transactions, tags, a recurring rule, a reminder."""
    api.patch(f"/budgets/{api.budget_id('Savings')}", {"direction": "positive"})
    api.income(200000, "2026-10-25")
    api.expense(4550, "2026-10-26", category="Food", tags=["groceries", "lidl"])
    api.expense(1, "2026-10-27", budget="Savings", description='Quote "this", and, commas')
    api.rule(anchor_date="2026-10-26")
    api.post(
        "/reminders",
        {
            "name": "Electricity",
            "kind": "expense",
            "frequency": "monthly",
            "anchor_date": "2026-10-28",
        },
    )


@pytest.fixture
def other(tmp_path: Path, clock: Clock) -> Iterator[Api]:
    """A second, fresh install (setup not done) to restore into."""
    data_dir = tmp_path / "other"
    data_dir.mkdir()
    app = make_app(data_dir, clock)
    with ingress_client(app) as client:
        yield Api(client, clock)
    app.state.engine.dispose()


def test_EX1_export_contains_every_table_and_a_manifest(ready: Api) -> None:
    _populate(ready)
    response = ready.client.get("/api/v1/export")
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="payday-budget-2026-11-01.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    assert names == {
        "manifest.json",
        *(
            f"{t}.csv"
            for t in (
                "settings",
                "periods",
                "budgets",
                "period_budgets",
                "categories",
                "tags",
                "recurring_rules",
                "transactions",
                "transaction_tags",
                "reminders",
                "reminder_occurrences",
            )
        ),
    }
    app: Any = ready.client.app
    assert (manifest["format"], manifest["app_version"], manifest["currency"]) == (
        1,
        app.version,
        "EUR",
    )
    assert manifest["counts"]["transactions"] == len(_rows(response.content, "transactions"))
    budgets = {r["name"]: r for r in _rows(response.content, "budgets")}
    assert (budgets["Needs"]["percent"], budgets["Savings"]["direction"]) == ("50.00", "positive")
    amounts = {r["amount_minor"] for r in _rows(response.content, "transactions")}
    assert {"200000", "4550"} <= amounts  # integer minor units, no floats


def test_EX1_round_trip_restores_identical_data(ready: Api, other: Api) -> None:
    _populate(ready)
    data = _export(ready)
    result = _import(other, data, confirm=True)  # D13: onto a fresh install
    assert result["counts"]["transactions"]["file"] > 0
    assert other.get("/setup") == {"setup_completed": True}
    again = _export(other)
    for table in json.loads(zipfile.ZipFile(io.BytesIO(data)).read("manifest.json"))["counts"]:
        assert _rows(again, table) == _rows(data, table), table
    assert other.summary()["budgets"] == ready.summary()["budgets"]


def test_EX2_preview_changes_nothing_and_confirm_replaces(ready: Api, other: Api) -> None:
    _populate(ready)
    backup = _export(ready)
    other.setup(budgets=[{"name": "Only", "percent": "10"}])
    other.income(999, "2026-10-26")
    preview = _import(other, backup, confirm=False)
    assert preview["counts"]["budgets"] == {"file": 3, "current": 1}
    assert preview["counts"]["transactions"]["current"] == 1
    assert [b["name"] for b in other.get("/budgets")["items"]] == ["Only"]  # unchanged
    _import(other, backup, confirm=True)
    assert [b["name"] for b in other.get("/budgets")["items"]] == ["Needs", "Savings", "Wants"]
    assert all(t["amount_minor"] != 999 for t in other.get("/transactions")["items"])


def test_EX3_a_bad_file_leaves_the_data_unchanged(ready: Api) -> None:
    _populate(ready)
    before = _export(ready)

    def break_last(rows: list[dict[str, str]]) -> None:
        rows[-1]["category_id"] = "9999"

    _import(ready, _edit(before, "transactions", break_last), confirm=True, expect=422)
    after = _export(ready)
    for table in ("budgets", "transactions", "reminders"):
        assert _rows(after, table) == _rows(before, table)


@pytest.mark.parametrize(
    ("table", "change", "code", "where"),
    [
        ("budgets", lambda r: r[0].update(percent="99"), "B1", "budgets.csv"),
        ("budgets", lambda r: r[0].update(percent="12.345"), "B1", "budgets.csv row 2"),
        ("transactions", lambda r: r[0].update(date="2020-01-01"), "P6", "transactions.csv row 2"),
        ("transactions", lambda r: r[0].update(kind="expense"), "T2", "transactions.csv row 2"),
        ("transactions", lambda r: r[1].update(budget_id=""), "B6", "transactions.csv row 3"),
        ("periods", lambda r: r[0].update(start_date="2030-01-01"), "P2", "periods.csv row 2"),
        ("settings", lambda r: r[0].update(currency="XXX"), "K1", "settings.csv row 2"),
        ("reminders", lambda r: r[0].update(end_date="2020-01-01"), "RM1", "reminders.csv row 2"),
        (
            "recurring_rules",
            lambda r: r[0].update(end_date="2020-01-01"),
            "R1",
            "recurring_rules.csv row 2",
        ),
        (
            "transactions",
            lambda r: r[0].update(category_id="9999"),
            "validation_error",
            "transactions.csv row 2",
        ),
        (
            "budgets",
            lambda r: r[0].update(archived="maybe"),
            "validation_error",
            "budgets.csv row 2",
        ),
        (
            "budgets",
            lambda r: r[1].update(name=r[0]["name"]),
            "validation_error",
            "budgets.csv row 3",
        ),
        (
            "categories",
            lambda r: r[0].update(name="  "),
            "validation_error",
            "categories.csv row 2",
        ),
    ],
)
def test_EX4_first_error_names_file_row_and_rule(
    ready: Api, table: str, change: Callable[[list[dict[str, str]]], None], code: str, where: str
) -> None:
    _populate(ready)
    body = _import(ready, _edit(_export(ready), table, change), confirm=False, expect=422)
    assert body["code"] == code, body
    assert body["message"].startswith(where), body


def test_EX4_file_shape_is_checked(ready: Api) -> None:
    backup = _export(ready)
    assert _import(ready, b"not a zip", confirm=False, expect=422)["code"] == "validation_error"
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(backup)) as source, zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            if name != "tags.csv":
                target.writestr(name, source.read(name))
    body = _import(ready, out.getvalue(), confirm=False, expect=422)
    assert body["message"] == "tags.csv: missing from the backup"

    def drop_column(rows: list[dict[str, str]]) -> None:
        for row in rows:
            row.pop("icon")

    edited = _edit(backup, "categories", lambda rows: None)
    source = zipfile.ZipFile(io.BytesIO(edited))
    out = io.BytesIO()
    with source, zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name == "categories.csv":
                lines = content.decode().splitlines()
                content = "\n".join(
                    [lines[0] + ",extra"] + [line + ",x" for line in lines[1:]]
                ).encode()
            target.writestr(name, content)
    body = _import(ready, out.getvalue(), confirm=False, expect=422)
    assert body["message"].startswith("categories.csv row 1: columns do not match")


def test_EX5_newer_format_is_rejected(ready: Api) -> None:
    backup = _export(ready)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(backup)) as source, zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name == "manifest.json":
                content = json.dumps({**json.loads(content), "format": 2}).encode()
            target.writestr(name, content)
    assert _import(ready, out.getvalue(), confirm=False, expect=422)["code"] == "EX5"


def test_EX6_scheduler_catches_up_after_import(ready: Api, other: Api) -> None:
    _populate(ready)  # weekly rule from 2026-10-26, monthly reminder from 2026-10-28
    backup = _export(ready)
    other.clock.today = dt.date(2026, 12, 1)
    _import(other, backup, confirm=True)
    generated = other.generated(other.get("/recurring")["items"][0]["id"])
    assert generated[-1] == "2026-11-30"
    dues = [o["due_date"] for o in other.get("/reminders/occurrences?status=open")["items"]]
    assert dues == ["2026-10-28", "2026-11-28"]


def test_EX6_preview_does_not_run_the_scheduler(ready: Api, other: Api) -> None:
    _populate(ready)
    backup = _export(ready)
    other.clock.today = dt.date(2026, 11, 20)
    _import(other, backup, confirm=False)
    assert other.get("/setup") == {"setup_completed": False}

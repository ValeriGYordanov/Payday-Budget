"""Schema, migrations and storage (§4, §6.5)."""

import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from app.main import create_app
from app.models import Base
from tests.addon.conftest import Api


def test_migrations_match_models(api: Api, db_path: str) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    engine.dispose()


def test_migrations_are_idempotent_on_restart(api: Api, data_dir: Path) -> None:
    api.setup()
    create_app(data_dir).state.engine.dispose()
    assert api.get("/setup") == {"setup_completed": True}


def test_database_uses_wal(api: Api, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.close()


def test_required_indexes_exist(api: Api, db_path: str) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    indexes = {i["name"]: i for i in inspect(engine).get_indexes("transactions")}
    engine.dispose()
    assert indexes["ix_transactions_date"]["column_names"] == ["date"]
    assert indexes["ix_transactions_budget_id_date"]["column_names"] == ["budget_id", "date"]
    assert indexes["ix_transactions_category_id_date"]["column_names"] == ["category_id", "date"]
    unique = indexes["ux_transactions_recurring_occurrence"]
    assert unique["column_names"] == ["recurring_rule_id", "occurrence_date"]
    assert unique["unique"]


def test_money_columns_are_integers(api: Api, db_path: str) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    types = {
        (table, col["name"]): str(col["type"])
        for table in ("transactions", "recurring_rules", "budgets", "period_budgets")
        for col in insp.get_columns(table)
    }
    engine.dispose()
    assert types[("transactions", "amount_minor")] == "INTEGER"
    assert types[("recurring_rules", "amount_minor")] == "INTEGER"
    assert types[("budgets", "percent_bp")] == "INTEGER"
    assert types[("period_budgets", "percent_bp")] == "INTEGER"


def test_BD1_migration_makes_existing_budgets_negative(tmp_path: Path) -> None:
    from app import migrate
    from app.db import make_engine

    # The app's own engine: foreign keys on, as on HA Green.
    engine = make_engine(str(tmp_path / "old.db"))
    migrate.upgrade(engine, "0001")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO budgets (id, name, percent_bp, sort_order, archived, created_at)"
            " VALUES (1, 'Needs', 5000, 0, 0, '2026-11-01 00:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO periods (id, start_date, name, created_at)"
            " VALUES (1, '2026-11-01', 'November 2026', '2026-11-01 00:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO period_budgets (period_id, budget_id, percent_bp) VALUES (1, 1, 5000)"
        )
        conn.exec_driver_sql(
            "INSERT INTO categories (id, name, kind, icon, archived)"
            " VALUES (1, 'Food', 'expense', 'mdi:food', 0)"
        )
        conn.exec_driver_sql(
            "INSERT INTO transactions (id, kind, amount_minor, date, category_id, budget_id,"
            " created_at, updated_at) VALUES (1, 'expense', 100, '2026-11-02', 1, 1,"
            " '2026-11-02 00:00:00', '2026-11-02 00:00:00')"
        )
    migrate.upgrade(engine)
    with engine.begin() as conn:
        assert conn.exec_driver_sql("SELECT direction FROM budgets").scalar() == "negative"
        assert conn.exec_driver_sql("SELECT direction FROM period_budgets").scalar() == "negative"
        assert conn.exec_driver_sql("SELECT count(*) FROM transactions").scalar() == 1
        # The CHECK holds on migrated databases too.
        with pytest.raises(IntegrityError), conn.begin_nested():
            conn.exec_driver_sql("UPDATE budgets SET direction = 'sideways'")
    engine.dispose()


def test_failed_migration_leaves_no_partial_changes(tmp_path: Path) -> None:
    """A migration that fails partway rolls back completely (DDL included)."""
    from app import migrate
    from app.db import make_engine

    engine = make_engine(str(tmp_path / "old.db"))
    migrate.upgrade(engine, "0001")
    with engine.begin() as conn:
        # 0002 creates `reminders` first, then fails on this existing table.
        conn.exec_driver_sql("CREATE TABLE reminder_occurrences (id INTEGER PRIMARY KEY)")
    with pytest.raises(Exception, match="already exists"):
        migrate.upgrade(engine)
    tables = set(inspect(engine).get_table_names())
    assert "reminders" not in tables
    assert "direction" not in {c["name"] for c in inspect(engine).get_columns("budgets")}
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0001"
    engine.dispose()

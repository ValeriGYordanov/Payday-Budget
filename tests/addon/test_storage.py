"""Schema, migrations and storage (§4, §6.5)."""

import sqlite3
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

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

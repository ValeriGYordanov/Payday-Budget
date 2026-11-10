"""Apply Alembic migrations on start (§6.5)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    """All or nothing: every pending migration runs in one SQLite transaction.

    Python's sqlite3 driver commits DDL (CREATE/ALTER) immediately, so a migration that
    failed halfway used to leave a half-migrated database. With the driver's own
    transaction handling off (AUTOCOMMIT), an explicit BEGIN covers DDL too, and any
    error rolls everything back.
    """
    cfg = alembic_config()
    with engine.connect() as base:
        connection = base.execution_options(isolation_level="AUTOCOMMIT")
        connection.exec_driver_sql("BEGIN")
        try:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, revision)
        except BaseException:
            connection.exec_driver_sql("ROLLBACK")
            raise
        connection.exec_driver_sql("COMMIT")

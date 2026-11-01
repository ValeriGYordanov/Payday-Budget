"""Runtime configuration: data directory, add-on options, logging."""

import json
import logging
import os
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = "/data"
PORT = 8099  # Ingress and integration share this internal port (no host port).
DISCOVERY_SERVICE = "payday_budget"

# Add-on `log_level` option -> Python logging level.
LOG_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


def data_dir() -> Path:
    return Path(os.environ.get("PAYDAY_BUDGET_DATA", DEFAULT_DATA_DIR))


def db_path(base: Path) -> Path:
    return base / "payday_budget.db"


def load_options(base: Path) -> dict[str, Any]:
    """`/data/options.json`, written by the Supervisor; empty outside the add-on."""
    try:
        options = json.loads((base / "options.json").read_text())
    except FileNotFoundError:
        return {}
    return options if isinstance(options, dict) else {}


def configure_logging(log_level: object) -> int:
    level = LOG_LEVELS.get(str(log_level).lower(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return level

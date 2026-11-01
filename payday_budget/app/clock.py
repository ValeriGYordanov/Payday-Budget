"""Local "today" in HA's timezone (P9)."""

import logging
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_LOGGER = logging.getLogger(__name__)


def local_zone() -> ZoneInfo:
    name = os.environ.get("TZ") or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        _LOGGER.warning("Unknown TZ %r, falling back to UTC", name)
        return ZoneInfo("UTC")


def today() -> date:
    return datetime.now(local_zone()).date()

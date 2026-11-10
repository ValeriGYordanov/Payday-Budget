"""Constants for the Payday Budget integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "payday_budget"
NAME: Final = "Payday Budget"

CONF_TOKEN: Final = "token"
CONF_SLUG: Final = "slug"
# v1.2 §4.5 option: notify services (e.g. "mobile_app_pixel") that get reminder pushes.
CONF_NOTIFY_SERVICES: Final = "notify_services"
DEFAULT_PORT: Final = 8099

# §7.1: fallback polling; SSE `changed` events refresh sooner.
SCAN_INTERVAL: Final = timedelta(minutes=5)
SSE_BACKOFF_MAX_SECONDS: Final = 60
SSE_READ_TIMEOUT_SECONDS: Final = 90  # the add-on sends a keepalive every 25 s

HISTORY_LIMIT: Final = 12
RECENT_LIMIT: Final = 10  # v1.1 §9 D1: newest N transactions in the sensor

"""Supervisor discovery (§6.3): announce `{host, port, token}` to Home Assistant."""

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from app.config import DISCOVERY_SERVICE

_LOGGER = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"
RETRIES = 3
BACKOFF_SECONDS = 2.0


def send(
    token: str,
    port: int,
    *,
    supervisor_url: str = SUPERVISOR_URL,
    supervisor_token: str | None = None,
    host: str | None = None,
    retries: int = RETRIES,
    backoff: float = BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> str | None:
    """POST /discovery. Returns the message uuid, or None if skipped or failed."""
    supervisor_token = supervisor_token or os.environ.get("SUPERVISOR_TOKEN")
    if not supervisor_token:
        _LOGGER.info("No SUPERVISOR_TOKEN; not running as an add-on, skipping discovery")
        return None
    # The container hostname is the add-on's DNS name on the Supervisor network.
    payload = {
        "service": DISCOVERY_SERVICE,
        "config": {"host": host or socket.gethostname(), "port": port, "token": token},
    }
    request = urllib.request.Request(
        f"{supervisor_url}/discovery",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {supervisor_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                uuid = json.loads(response.read())["data"]["uuid"]
            _LOGGER.info("Discovery sent to Home Assistant (uuid %s)", uuid)
            return str(uuid)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as err:
            detail = (
                err.read().decode(errors="replace")
                if isinstance(err, urllib.error.HTTPError)
                else err
            )
            if attempt == retries:
                _LOGGER.warning("Discovery failed after %d attempts: %s", attempt + 1, detail)
                return None
            delay = backoff * 2**attempt
            _LOGGER.info(
                "Discovery attempt %d failed (%s); retrying in %.0fs", attempt + 1, detail, delay
            )
            sleep(delay)
    return None

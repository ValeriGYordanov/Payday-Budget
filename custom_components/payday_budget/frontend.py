"""Serve and register the dashboard cards bundle (§7.1, §8). No separate frontend install."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

CARDS_FILE = Path(__file__).parent / "www" / "payday-budget-cards.js"
CARDS_URL = f"/{DOMAIN}/payday-budget-cards.js"


def _version() -> str:
    manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
    return str(manifest["version"])


async def async_register_cards(hass: HomeAssistant) -> None:
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARDS_URL, str(CARDS_FILE), cache_headers=True)]
    )
    # The version query makes browsers fetch the new bundle after an update.
    version = await hass.async_add_executor_job(_version)
    add_extra_js_url(hass, f"{CARDS_URL}?v={version}")

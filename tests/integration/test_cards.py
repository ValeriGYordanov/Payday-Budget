"""§7.1 / §8: the integration serves the cards bundle and loads it on every dashboard."""

import json
from pathlib import Path

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.payday_budget.const import DOMAIN
from custom_components.payday_budget.frontend import CARDS_FILE, CARDS_URL


async def test_cards_bundle_served_and_registered(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    version = json.loads((Path(CARDS_FILE).parent.parent / "manifest.json").read_text())["version"]
    assert f"{CARDS_URL}?v={version}" in hass.data[DATA_EXTRA_MODULE_URL].urls
    client = await hass_client()
    response = await client.get(CARDS_URL)
    assert response.status == 200
    body = await response.text()
    for card in ("progress", "periods", "category", "pace"):
        assert f"payday-budget-{card}-card" in body

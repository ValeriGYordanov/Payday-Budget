"""§7.1 config flow: Supervisor discovery (§6.3), manual step, re-authentication."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.payday_budget.api import CannotConnect, InvalidAuth
from custom_components.payday_budget.const import CONF_SLUG, CONF_TOKEN, DOMAIN

DISCOVERY = HassioServiceInfo(
    config={"host": "416b9a6e-payday-budget", "port": 8099, "token": "disc-token"},
    name="Payday Budget",
    slug="416b9a6e_payday_budget",
    uuid="1234",
)
VALIDATE = "custom_components.payday_budget.config_flow.PaydayBudgetClient.get"
SETUP = "custom_components.payday_budget.async_setup_entry"


async def test_manual_setup(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with patch(VALIDATE, AsyncMock(return_value={})), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "h", CONF_PORT: 8099, CONF_TOKEN: "t"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "h", CONF_PORT: 8099, CONF_TOKEN: "t"}
    assert result["result"].unique_id == DOMAIN


async def test_manual_setup_errors(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for error, key in ((CannotConnect("x"), "cannot_connect"), (InvalidAuth(), "invalid_auth")):
        with patch(VALIDATE, AsyncMock(side_effect=error)):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_HOST: "h", CONF_PORT: 8099, CONF_TOKEN: "t"}
            )
        assert result["errors"] == {"base": key}


async def test_only_one_entry(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")


async def test_hassio_discovery_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=DISCOVERY
    )
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "hassio_confirm")
    assert result["description_placeholders"] == {"addon": "Payday Budget"}
    with patch(VALIDATE, AsyncMock(return_value={})), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: "416b9a6e-payday-budget",
        CONF_PORT: 8099,
        CONF_TOKEN: "disc-token",
        CONF_SLUG: "416b9a6e_payday_budget",
    }


async def test_rediscovery_updates_token(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_HOST: "old", CONF_PORT: 8099, CONF_TOKEN: "old-token"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=DISCOVERY
    )
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")
    assert entry.data[CONF_TOKEN] == "disc-token"
    assert entry.data[CONF_HOST] == "416b9a6e-payday-budget"


async def test_reauth_updates_token(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={CONF_HOST: "h", CONF_PORT: 8099, CONF_TOKEN: "old"}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(VALIDATE, AsyncMock(side_effect=InvalidAuth())):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "bad"}
        )
    assert result["errors"] == {"base": "invalid_auth"}
    with patch(VALIDATE, AsyncMock(return_value={})), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "new"}
        )
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "reauth_successful")
    assert entry.data[CONF_TOKEN] == "new"

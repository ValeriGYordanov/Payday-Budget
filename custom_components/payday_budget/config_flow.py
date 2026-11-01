"""Config flow (§7.1): Supervisor discovery, manual setup, re-authentication.

One entry only, enforced with a fixed unique ID so that a re-discovery can still
update host, port and token (`single_config_entry` would abort it).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import CannotConnect, InvalidAuth, PaydayBudgetClient, PaydayBudgetError
from .const import CONF_SLUG, CONF_TOKEN, DEFAULT_PORT, DOMAIN, NAME


class PaydayBudgetConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}
        self._addon_name = NAME

    async def _validate(self, host: str, port: int, token: str) -> str | None:
        """Return an error key, or None if the add-on accepts the token."""
        client = PaydayBudgetClient(async_get_clientsession(self.hass), host, port, token)
        try:
            await client.get("settings")
        except InvalidAuth:
            return "invalid_auth"
        except CannotConnect:
            return "cannot_connect"
        except PaydayBudgetError:
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._validate(
                user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_TOKEN]
            )
            if error is None:
                return self.async_create_entry(title=NAME, data=user_input)
            errors["base"] = error
        schema = probatio.Schema(
            {
                probatio.Required(CONF_HOST): str,
                probatio.Required(CONF_PORT, default=DEFAULT_PORT): int,
                probatio.Required(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """§6.3: the add-on announces `{host, port, token}` on every start."""
        config = discovery_info.config
        self._discovered = {
            CONF_HOST: config[CONF_HOST],
            CONF_PORT: int(config[CONF_PORT]),
            CONF_TOKEN: config[CONF_TOKEN],
            CONF_SLUG: discovery_info.slug,
        }
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured(updates=self._discovered)
        self._addon_name = discovery_info.name
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            d = self._discovered
            error = await self._validate(d[CONF_HOST], d[CONF_PORT], d[CONF_TOKEN])
            if error is None:
                return self.async_create_entry(title=NAME, data=d)
            errors["base"] = error
        return self.async_show_form(
            step_id="hassio_confirm",
            description_placeholders={"addon": self._addon_name},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            error = await self._validate(
                entry.data[CONF_HOST], entry.data[CONF_PORT], user_input[CONF_TOKEN]
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema({probatio.Required(CONF_TOKEN): str}),
            errors=errors,
        )

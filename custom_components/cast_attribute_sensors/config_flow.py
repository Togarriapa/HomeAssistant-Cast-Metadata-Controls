"""Config flow for Cast Metadata & Controls."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import DOMAIN, NAME


class CastAttributeSensorsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cast Metadata & Controls."""

    VERSION = 3

    async def async_step_user(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

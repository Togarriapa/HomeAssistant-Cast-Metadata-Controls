"""Config and options flows."""

from __future__ import annotations

from typing import Any, override
from uuid import uuid4

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ENTITIES,
    CONF_GROUP_ID,
    CONF_GROUP_NAME,
    CONF_GROUPS,
    CONF_MEMBERS,
    DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    NAME,
)


class CastMetadataConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single hub entry."""

    VERSION = 7

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> GroupOptionsFlow:
        return GroupOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))


class GroupOptionsFlow(OptionsFlowWithReload):
    """Allow explicit grouping when integrations cannot be matched automatically."""

    def _groups(self) -> list[dict[str, Any]]:
        value = self.config_entry.options.get(CONF_GROUPS, [])
        return [dict(group) for group in value] if isinstance(value, list) else []

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = ["add_group"]
        if self._groups():
            options.extend(["remove_group", "clear_groups"])
        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_add_group(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_ids = user_input[CONF_ENTITIES]
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            registry = er.async_get(self.hass)
            member_ids: list[str] = []
            for entity_id in entity_ids:
                entry = registry.async_get(entity_id)
                if (
                    entry is not None
                    and entry.domain == MEDIA_PLAYER_DOMAIN
                    and entry.platform != DOMAIN
                ):
                    member_ids.append(entry.id)
            if len(set(member_ids)) < 2:
                errors[CONF_ENTITIES] = "two_entities_required"
            else:
                groups = self._groups()
                groups.append(
                    {
                        CONF_GROUP_ID: uuid4().hex,
                        CONF_GROUP_NAME: str(
                            user_input.get(CONF_GROUP_NAME, "")
                        ).strip(),
                        CONF_MEMBERS: list(dict.fromkeys(member_ids)),
                    }
                )
                return self.async_create_entry(data={CONF_GROUPS: groups})

        return self.async_show_form(
            step_id="add_group",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_GROUP_NAME): selector.TextSelector(),
                    vol.Required(CONF_ENTITIES): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=MEDIA_PLAYER_DOMAIN,
                            multiple=True,
                            reorder=True,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_group(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        groups = self._groups()
        if user_input is not None:
            group_id = user_input[CONF_GROUP_ID]
            return self.async_create_entry(
                data={
                    CONF_GROUPS: [
                        group for group in groups if group[CONF_GROUP_ID] != group_id
                    ]
                }
            )
        options = [
            selector.SelectOptionDict(
                value=group[CONF_GROUP_ID],
                label=group.get(CONF_GROUP_NAME)
                or f"Group {index + 1} ({len(group.get(CONF_MEMBERS, []))} entities)",
            )
            for index, group in enumerate(groups)
        ]
        return self.async_show_form(
            step_id="remove_group",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GROUP_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_clear_groups(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None and user_input.get("confirm"):
            return self.async_create_entry(data={CONF_GROUPS: []})
        return self.async_show_form(
            step_id="clear_groups",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        )

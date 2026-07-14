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
    CONF_GROUP_KEY,
    CONF_GROUP_NAME,
    CONF_GROUPS,
    CONF_MEMBERS,
    CONF_ROUTES,
    DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    NAME,
    ROUTE_KEYS,
)


class CastMetadataConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single hub entry."""

    VERSION = 8

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
    """Configure explicit grouping and per-capability routing."""

    _selected_group_key: str | None = None

    def _groups(self) -> list[dict[str, Any]]:
        value = self.config_entry.options.get(CONF_GROUPS, [])
        return [dict(group) for group in value] if isinstance(value, list) else []

    def _routes(self) -> dict[str, dict[str, str]]:
        value = self.config_entry.options.get(CONF_ROUTES, {})
        if not isinstance(value, dict):
            return {}
        return {
            str(key): dict(routes)
            for key, routes in value.items()
            if isinstance(routes, dict)
        }

    def _save(
        self,
        *,
        groups: list[dict[str, Any]] | None = None,
        routes: dict[str, dict[str, str]] | None = None,
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            data={
                CONF_GROUPS: self._groups() if groups is None else groups,
                CONF_ROUTES: self._routes() if routes is None else routes,
            }
        )

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = ["add_group", "configure_routes"]
        if self._groups():
            options.extend(["remove_group", "clear_groups"])
        if self._routes():
            options.append("clear_routes")
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
                return self._save(groups=groups)
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
            return self._save(
                groups=[group for group in groups if group[CONF_GROUP_ID] != group_id]
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
            return self._save(groups=[])
        return self.async_show_form(
            step_id="clear_groups",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        )

    async def async_step_configure_routes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        runtime = self.config_entry.runtime_data
        if user_input is not None:
            self._selected_group_key = str(user_input[CONF_GROUP_KEY])
            return await self.async_step_route_group()
        options = [
            selector.SelectOptionDict(value=group.key, label=group.name)
            for group in runtime.groups
        ]
        return self.async_show_form(
            step_id="configure_routes",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GROUP_KEY): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_route_group(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        runtime = self.config_entry.runtime_data
        group = runtime.group_by_key(self._selected_group_key or "")
        if group is None:
            return self.async_abort(reason="group_not_found")
        current = self._routes().get(group.key, {})
        source_options = [selector.SelectOptionDict(value="", label="Automatic")]
        for source_id in group.source_ids:
            entity_id = runtime.manager.get_entity_id(source_id)
            state = runtime.manager.get_state(source_id)
            if not entity_id:
                continue
            name = (
                str(state.attributes.get("friendly_name", "")).strip()
                if state is not None
                else ""
            )
            platform = runtime.manager.platform(source_id) or "unknown"
            source_options.append(
                selector.SelectOptionDict(
                    value=entity_id,
                    label=f"{name or entity_id} · {platform}",
                )
            )

        if user_input is not None:
            routes = self._routes()
            selected: dict[str, str] = {}
            for capability in ROUTE_KEYS:
                entity_id = str(user_input.get(capability, "")).strip()
                source_id = (
                    runtime.manager.source_id_for_entity(entity_id)
                    if entity_id
                    else None
                )
                if source_id in group.source_ids:
                    selected[capability] = source_id
            if selected:
                routes[group.key] = selected
            else:
                routes.pop(group.key, None)
            return self._save(routes=routes)

        schema: dict[Any, Any] = {}
        for capability in ROUTE_KEYS:
            source_id = current.get(capability)
            entity_id = runtime.manager.get_entity_id(source_id) if source_id else ""
            schema[vol.Optional(capability, default=entity_id or "")] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(options=source_options)
                )
            )
        return self.async_show_form(
            step_id="route_group",
            data_schema=vol.Schema(schema),
            description_placeholders={"name": group.name},
        )

    async def async_step_clear_routes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None and user_input.get("confirm"):
            return self._save(routes={})
        return self.async_show_form(
            step_id="clear_routes",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        )

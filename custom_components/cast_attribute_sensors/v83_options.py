"""V8.3 options for explicit physical-device entity inventories."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import voluptuous as vol
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    BUTTON_DOMAIN,
    CONF_COMMAND_MAPS,
    CONF_DEVICE_ENTITIES,
    CONF_ENTITIES,
    CONF_GROUP_NAME,
    CONF_GROUPS,
    CONF_PROVIDER_ROUTES,
    DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    REMOTE_DOMAIN,
    ROUTE_NAVIGATION,
    ROUTE_RESTART,
)
from .generic_capabilities import (
    COMMAND_LABELS,
    LOGICAL_COMMANDS,
    normalized_command_map,
)
from .merge_options import MANUAL_GROUP_PREFIX, merge_manual_group_configs

_AUTOMATIC = "__automatic__"
_SUPPORTED_DOMAINS = frozenset({MEDIA_PLAYER_DOMAIN, REMOTE_DOMAIN, BUTTON_DOMAIN})


def _mapping_option(self, key: str) -> dict[str, Any]:
    value = self.config_entry.options.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def _device_entities(self) -> dict[str, list[str]]:
    return {
        str(group_key): list(dict.fromkeys(str(item) for item in values if item))
        for group_key, values in self._mapping_option(CONF_DEVICE_ENTITIES).items()
        if isinstance(values, list)
    }


def _provider_routes(self) -> dict[str, dict[str, str]]:
    return {
        str(group_key): {
            str(capability): str(entity_id)
            for capability, entity_id in values.items()
            if entity_id
        }
        for group_key, values in self._mapping_option(CONF_PROVIDER_ROUTES).items()
        if isinstance(values, dict)
    }


def _command_maps(self) -> dict[str, dict[str, str]]:
    return {
        str(group_key): normalized_command_map(values)
        for group_key, values in self._mapping_option(CONF_COMMAND_MAPS).items()
        if isinstance(values, dict)
    }


def _candidate_entities(self, group) -> list[str]:
    runtime = self.config_entry.runtime_data
    registry = er.async_get(self.hass)
    source_entities = [
        runtime.manager.get_entity_id(source_id) for source_id in group.source_ids
    ]
    source_entries = [
        registry.async_get(entity_id)
        for entity_id in source_entities
        if entity_id is not None
    ]
    device_ids = {
        entry.device_id for entry in source_entries if entry and entry.device_id
    }
    config_entry_ids = {
        entry.config_entry_id
        for entry in source_entries
        if entry and entry.config_entry_id
    }
    candidates = list(source_entities)
    candidates.extend(self._device_entities().get(group.key, []))
    for entry in registry.entities.values():
        if (
            entry.domain not in _SUPPORTED_DOMAINS
            or entry.platform == DOMAIN
            or entry.disabled_by is not None
        ):
            continue
        if entry.domain == MEDIA_PLAYER_DOMAIN and (
            runtime.manager.source_id_for_entity(entry.entity_id) is None
        ):
            continue
        if (
            entry.device_id in device_ids
            or entry.config_entry_id in config_entry_ids
        ):
            candidates.append(entry.entity_id)
    return list(dict.fromkeys(str(item) for item in candidates if item))


def _remap_generic_mapping(
    mapping: dict[str, Any],
    old_keys: Iterable[str],
    new_key: str,
    *,
    merge_lists: bool,
) -> dict[str, Any]:
    ordered = list(dict.fromkeys(str(key) for key in old_keys if key))
    if new_key not in ordered:
        ordered.insert(0, new_key)
    result = dict(mapping)
    if merge_lists:
        merged: list[str] = []
        for key in ordered:
            values = result.get(key, [])
            if isinstance(values, list):
                merged.extend(str(item) for item in values if item)
        selected: Any = list(dict.fromkeys(merged))
    else:
        selected = next(
            (
                dict(result[key])
                for key in ordered
                if isinstance(result.get(key), dict) and result[key]
            ),
            None,
        )
    for key in ordered:
        result.pop(key, None)
    if selected:
        result[new_key] = selected
    return result


def _save_physical_device(
    self,
    *,
    current_group,
    selected_entities: list[str],
    name: str,
):
    runtime = self.config_entry.runtime_data
    registry = er.async_get(self.hass)
    member_ids = list(
        dict.fromkeys(
            source_id
            for entity_id in selected_entities
            if (entry := registry.async_get(entity_id)) is not None
            and entry.domain == MEDIA_PLAYER_DOMAIN
            and entry.platform != DOMAIN
            and (source_id := runtime.manager.source_id_for_entity(entity_id))
        )
    )
    if not member_ids:
        return None

    old_group_keys = {current_group.key}
    old_group_keys.update(
        group.key
        for source_id in member_ids
        if (group := runtime.group_for_source(source_id)) is not None
    )
    existing_manual_id = (
        current_group.key.removeprefix(MANUAL_GROUP_PREFIX)
        if current_group.key.startswith(MANUAL_GROUP_PREFIX)
        else None
    )
    groups, group_id = merge_manual_group_configs(
        self._groups(),
        member_ids=member_ids,
        name=name or current_group.name,
        group_id=existing_manual_id,
    )
    target_key = f"{MANUAL_GROUP_PREFIX}{group_id}"
    updates = self._remap_settings(old_group_keys, target_key)
    entities = updates.get(CONF_DEVICE_ENTITIES, self._device_entities())
    entities[target_key] = list(dict.fromkeys(selected_entities))
    updates[CONF_DEVICE_ENTITIES] = entities
    updates[CONF_GROUPS] = groups
    return self._save(**updates)


async def async_step_configure_device_entities(self, user_input=None):
    return await self._choose_group(
        "configure_device_entities", "device_entities_group", user_input
    )


async def async_step_device_entities_group(self, user_input=None):
    runtime = self.config_entry.runtime_data
    group = runtime.group_by_key(self._selected_group_key or "")
    if group is None:
        return self.async_abort(reason="group_not_found")
    errors: dict[str, str] = {}
    if user_input is not None:
        values = user_input[CONF_ENTITIES]
        selected = [values] if isinstance(values, str) else list(values)
        result = self._save_physical_device(
            current_group=group,
            selected_entities=selected,
            name=str(user_input.get(CONF_GROUP_NAME, "")).strip(),
        )
        if result is not None:
            return result
        errors[CONF_ENTITIES] = "media_player_required"

    return self.async_show_form(
        step_id="device_entities_group",
        data_schema=vol.Schema(
            {
                vol.Optional(
                    CONF_GROUP_NAME, default=group.name
                ): selector.TextSelector(),
                vol.Required(
                    CONF_ENTITIES,
                    default=self._candidate_entities(group),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True, reorder=True)
                ),
            }
        ),
        description_placeholders={"name": group.name},
        errors=errors,
    )


async def async_step_configure_entity_providers(self, user_input=None):
    return await self._choose_group(
        "configure_entity_providers", "entity_provider_group", user_input
    )


def _provider_options(self, group, domain: str) -> list[selector.SelectOptionDict]:
    registry = er.async_get(self.hass)
    runtime = self.config_entry.runtime_data
    options = [selector.SelectOptionDict(value=_AUTOMATIC, label="Automatic")]
    for entity_id in runtime.configured_device_entities(group):
        entry = registry.async_get(entity_id)
        if entry is None or entry.domain != domain or entry.disabled_by is not None:
            continue
        state = self.hass.states.get(entity_id)
        friendly = (
            str(state.attributes.get("friendly_name", "")).strip()
            if state is not None
            else ""
        )
        options.append(
            selector.SelectOptionDict(
                value=entity_id,
                label=f"{friendly or entity_id} · {entry.domain}/{entry.platform}",
            )
        )
    return options


async def async_step_entity_provider_group(self, user_input=None):
    runtime = self.config_entry.runtime_data
    group = runtime.group_by_key(self._selected_group_key or "")
    if group is None:
        return self.async_abort(reason="group_not_found")
    routes = self._provider_routes()
    current = routes.get(group.key, {})
    if user_input is not None:
        selected = {
            capability: str(user_input.get(capability, _AUTOMATIC)).strip()
            for capability in (ROUTE_NAVIGATION, ROUTE_RESTART)
        }
        selected = {
            capability: entity_id
            for capability, entity_id in selected.items()
            if entity_id != _AUTOMATIC
        }
        if selected:
            routes[group.key] = selected
        else:
            routes.pop(group.key, None)
        return self._save(**{CONF_PROVIDER_ROUTES: routes})

    return self.async_show_form(
        step_id="entity_provider_group",
        data_schema=vol.Schema(
            {
                vol.Optional(
                    ROUTE_NAVIGATION,
                    default=current.get(ROUTE_NAVIGATION, _AUTOMATIC),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._provider_options(group, REMOTE_DOMAIN)
                    )
                ),
                vol.Optional(
                    ROUTE_RESTART,
                    default=current.get(ROUTE_RESTART, _AUTOMATIC),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._provider_options(group, BUTTON_DOMAIN)
                    )
                ),
            }
        ),
        description_placeholders={"name": group.name},
    )


async def async_step_configure_remote_commands(self, user_input=None):
    return await self._choose_group(
        "configure_remote_commands", "remote_commands_group", user_input
    )


async def async_step_remote_commands_group(self, user_input=None):
    runtime = self.config_entry.runtime_data
    group = runtime.group_by_key(self._selected_group_key or "")
    if group is None:
        return self.async_abort(reason="group_not_found")
    maps = self._command_maps()
    current = maps.get(group.key, {})
    if user_input is not None:
        configured = normalized_command_map(dict(user_input))
        if configured:
            maps[group.key] = configured
        else:
            maps.pop(group.key, None)
        return self._save(**{CONF_COMMAND_MAPS: maps})

    schema = {
        vol.Required(
            command, default=current.get(command, command)
        ): selector.TextSelector()
        for command in LOGICAL_COMMANDS
    }
    return self.async_show_form(
        step_id="remote_commands_group",
        data_schema=vol.Schema(schema),
        description_placeholders={
            "name": group.name,
            "commands": ", ".join(
                f"{command} ({COMMAND_LABELS[command]})"
                for command in LOGICAL_COMMANDS
            ),
        },
    )


def install_v83_options(flow_class: type) -> None:
    """Extend V8 options with generic physical-device inventory configuration."""
    original_init = flow_class.async_step_init
    original_remap = flow_class._remap_settings
    original_remove = flow_class._remove_settings

    async def async_step_init(self, user_input=None):
        result = await original_init(self, user_input)
        menu = list(result.get("menu_options", []))
        additions = [
            "configure_device_entities",
            "configure_entity_providers",
            "configure_remote_commands",
        ]
        insert_at = (
            menu.index("configure_routes")
            if "configure_routes" in menu
            else len(menu)
        )
        for option in reversed(additions):
            if option not in menu:
                menu.insert(insert_at, option)
        result["menu_options"] = menu
        return result

    def _remap_settings(self, old_keys, new_key: str) -> dict[str, Any]:
        updates = original_remap(self, old_keys, new_key)
        updates[CONF_DEVICE_ENTITIES] = _remap_generic_mapping(
            self._device_entities(), old_keys, new_key, merge_lists=True
        )
        updates[CONF_PROVIDER_ROUTES] = _remap_generic_mapping(
            self._provider_routes(), old_keys, new_key, merge_lists=False
        )
        updates[CONF_COMMAND_MAPS] = _remap_generic_mapping(
            self._command_maps(), old_keys, new_key, merge_lists=False
        )
        return updates

    def _remove_settings(self, group_keys) -> dict[str, Any]:
        keys = [str(key) for key in group_keys]
        updates = original_remove(self, keys)
        for option_key, mapping in (
            (CONF_DEVICE_ENTITIES, self._device_entities()),
            (CONF_PROVIDER_ROUTES, self._provider_routes()),
            (CONF_COMMAND_MAPS, self._command_maps()),
        ):
            for key in keys:
                mapping.pop(key, None)
            updates[option_key] = mapping
        return updates

    flow_class._device_entities = _device_entities
    flow_class._provider_routes = _provider_routes
    flow_class._command_maps = _command_maps
    flow_class._candidate_entities = _candidate_entities
    flow_class._save_physical_device = _save_physical_device
    flow_class._provider_options = _provider_options
    flow_class.async_step_init = async_step_init
    flow_class.async_step_configure_device_entities = async_step_configure_device_entities
    flow_class.async_step_device_entities_group = async_step_device_entities_group
    flow_class.async_step_configure_entity_providers = async_step_configure_entity_providers
    flow_class.async_step_entity_provider_group = async_step_entity_provider_group
    flow_class.async_step_configure_remote_commands = async_step_configure_remote_commands
    flow_class.async_step_remote_commands_group = async_step_remote_commands_group
    flow_class._remap_settings = _remap_settings
    flow_class._remove_settings = _remove_settings

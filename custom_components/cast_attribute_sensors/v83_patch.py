"""V8.3 generic linked-entity inventory and capability routing."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    BUTTON_DOMAIN,
    CONF_COMMAND_MAPS,
    CONF_DEVICE_ENTITIES,
    CONF_PROVIDER_ROUTES,
    DOMAIN,
    REMOTE_DOMAIN,
    ROUTE_NAVIGATION,
    ROUTE_RESTART,
    TV_APP_PREFIX,
)
from .generic_capabilities import command_for, normalized_command_map, source_kind
from .media_player import SourceAction, UnifiedMediaController, _action_key
from .runtime import IntegrationRuntime
from .source_manager import SourceManager

_TOKEN = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
_STOP_TOKENS = frozenset(
    {
        "button",
        "controller",
        "device",
        "media",
        "player",
        "remote",
        "smart",
        "television",
    }
)
_INSTALLED = False


def _option_mapping(runtime: IntegrationRuntime, key: str) -> dict[str, Any]:
    value = runtime.entry.options.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def _configured_device_entities(
    self: IntegrationRuntime, group
) -> tuple[str, ...]:
    configured = _option_mapping(self, CONF_DEVICE_ENTITIES).get(group.key, [])
    values = configured if isinstance(configured, list) else []
    source_entities = [
        self.manager.get_entity_id(source_id) for source_id in group.source_ids
    ]
    return tuple(
        dict.fromkeys(
            str(entity_id)
            for entity_id in (*source_entities, *values)
            if entity_id
        )
    )


def _configured_provider_routes(
    self: IntegrationRuntime, group
) -> dict[str, str]:
    configured = _option_mapping(self, CONF_PROVIDER_ROUTES).get(group.key, {})
    if not isinstance(configured, dict):
        return {}
    return {
        str(capability): str(entity_id)
        for capability, entity_id in configured.items()
        if entity_id
    }


def _configured_command_map(
    self: IntegrationRuntime, group
) -> dict[str, str]:
    return normalized_command_map(
        _option_mapping(self, CONF_COMMAND_MAPS).get(group.key, {})
    )


def _set_group_configuration(
    self: SourceManager,
    source_ids: tuple[str, ...],
    *,
    entity_ids: tuple[str, ...],
    provider_routes: Mapping[str, str],
    command_map: Mapping[str, str],
) -> None:
    configurations = getattr(self, "_generic_group_configurations", None)
    if configurations is None:
        configurations = {}
        self._generic_group_configurations = configurations
    configurations[frozenset(source_ids)] = {
        "source_ids": tuple(source_ids),
        "entity_ids": tuple(dict.fromkeys(entity_ids)),
        "provider_routes": dict(provider_routes),
        "command_map": dict(command_map),
    }


def _group_configuration(
    self: SourceManager, source_ids: tuple[str, ...]
) -> dict[str, Any]:
    configurations = getattr(self, "_generic_group_configurations", {})
    exact = configurations.get(frozenset(source_ids))
    if isinstance(exact, dict):
        return exact
    requested = set(source_ids)
    matches = [
        config
        for key, config in configurations.items()
        if requested and requested.issubset(key)
    ]
    return matches[0] if len(matches) == 1 else {}


def _linked_entity_ids(
    self: SourceManager, source_ids: tuple[str, ...]
) -> tuple[str, ...]:
    configured = self.group_configuration(source_ids)
    values = configured.get("entity_ids", ())
    return tuple(str(item) for item in values if item)


def _source_facts(
    self: SourceManager, source_ids: tuple[str, ...]
) -> tuple[set[str], set[str], set[str], set[str]]:
    device_ids: set[str] = set()
    config_entry_ids: set[str] = set()
    area_ids: set[str] = set()
    labels: set[str] = set()
    for source_id in source_ids:
        source = self.get_source(source_id)
        if source is None:
            continue
        if source.device_id:
            device_ids.add(source.device_id)
        if source.config_entry_id:
            config_entry_ids.add(source.config_entry_id)
        state = self.get_state(source_id)
        if state is not None:
            name = state.attributes.get("friendly_name")
            if isinstance(name, str):
                labels.add(name.casefold())
    for device_id in device_ids:
        device = self.device_registry.async_get(device_id)
        if device is None:
            continue
        if device.area_id:
            area_ids.add(device.area_id)
        for value in (device.name, device.name_by_user, device.model):
            if isinstance(value, str):
                labels.add(value.casefold())
    return device_ids, config_entry_ids, area_ids, labels


def _label_tokens(values: set[str]) -> set[str]:
    return {
        token.casefold()
        for value in values
        for token in _TOKEN.findall(value)
        if token.casefold() not in _STOP_TOKENS and not token.isdecimal()
    }


def _entry_labels(self: SourceManager, entry: er.RegistryEntry) -> set[str]:
    values: set[str] = {entry.entity_id.casefold()}
    state = self.hass.states.get(entry.entity_id)
    if state is not None:
        name = state.attributes.get("friendly_name")
        if isinstance(name, str):
            values.add(name.casefold())
    device = (
        self.device_registry.async_get(entry.device_id)
        if entry.device_id is not None
        else None
    )
    if device is not None:
        for value in (device.name, device.name_by_user, device.model):
            if isinstance(value, str):
                values.add(value.casefold())
    return values


def _provider_entity_id(
    self: SourceManager,
    source_ids: tuple[str, ...],
    capability: str,
) -> str | None:
    configuration = self.group_configuration(source_ids)
    linked = set(self.linked_entity_ids(source_ids))
    routed = str(configuration.get("provider_routes", {}).get(capability, ""))
    if routed and routed in linked:
        entry = self.entity_registry.async_get(routed)
        if entry is not None and entry.disabled_by is None:
            return routed

    domains = {
        ROUTE_NAVIGATION: {REMOTE_DOMAIN},
        ROUTE_RESTART: {BUTTON_DOMAIN},
    }.get(capability, set())
    candidates = [
        entry
        for entity_id in linked
        if (entry := self.entity_registry.async_get(entity_id)) is not None
        and entry.domain in domains
        and entry.platform != DOMAIN
        and entry.disabled_by is None
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0].entity_id

    device_ids, config_entry_ids, area_ids, source_labels = self._source_facts(
        source_ids
    )
    source_tokens = _label_tokens(source_labels)
    scored: list[tuple[int, str]] = []
    for entry in candidates:
        score = 0
        if entry.device_id and entry.device_id in device_ids:
            score += 300
        if entry.config_entry_id and entry.config_entry_id in config_entry_ids:
            score += 240
        device = (
            self.device_registry.async_get(entry.device_id)
            if entry.device_id is not None
            else None
        )
        if device is not None and device.area_id in area_ids:
            score += 40
        state = self.hass.states.get(entry.entity_id)
        if state is not None and state.state != STATE_UNAVAILABLE:
            score += 20
        score += 10 * min(
            len(source_tokens & _label_tokens(self._entry_labels(entry))), 5
        )
        device_class = getattr(entry, "device_class", None) or getattr(
            entry, "original_device_class", None
        )
        if capability == ROUTE_RESTART and device_class == "restart":
            score += 100
        scored.append((score, entry.entity_id))

    scored.sort(key=lambda item: (-item[0], item[1]))
    if scored[0][0] > scored[1][0]:
        return scored[0][1]
    return None


def _remote_entity_id(
    self: SourceManager, source_ids: tuple[str, ...]
) -> str | None:
    configured = self.provider_entity_id(source_ids, ROUTE_NAVIGATION)
    if configured is not None:
        return configured
    return _remote_entity_id.original(self, source_ids)


async def _send_command(
    self: SourceManager, source_ids: tuple[str, ...], command: str
) -> None:
    entity_id = self.remote_entity_id(source_ids)
    if entity_id is None:
        raise HomeAssistantError(
            "No linked remote provider is available; configure the physical device entities"
        )
    configuration = self.group_configuration(source_ids)
    configured_map = normalized_command_map(configuration.get("command_map", {}))
    await self.hass.services.async_call(
        REMOTE_DOMAIN,
        "send_command",
        {
            ATTR_ENTITY_ID: entity_id,
            "command": command_for(configured_map, command),
        },
        blocking=True,
    )


def _restart_button_entity_id(
    self: SourceManager, source_ids: tuple[str, ...]
) -> str | None:
    configured = self.provider_entity_id(source_ids, ROUTE_RESTART)
    if configured is not None:
        return configured
    return _restart_button_entity_id.original(self, source_ids)


def _register_controller(
    self: IntegrationRuntime, entity_id: str, controller: Any
) -> None:
    _register_controller.original(self, entity_id, controller)
    group = controller.group
    self.manager.set_group_configuration(
        group.source_ids,
        entity_ids=self.configured_device_entities(group),
        provider_routes=self.configured_provider_routes(group),
        command_map=self.configured_command_map(group),
    )
    controller.async_write_ha_state()


def _extra_state_attributes(self: UnifiedMediaController) -> dict[str, Any]:
    attributes = dict(_extra_state_attributes.original.fget(self))
    linked = self.runtime.configured_device_entities(self.group)
    navigation = self.runtime.manager.remote_entity_id(self.group.source_ids)
    restart = self.runtime.manager.restart_button_entity_id(self.group.source_ids)
    attributes.update(
        {
            "linked_entities": list(linked),
            "remote_available": navigation is not None,
            "navigation_provider": navigation,
            "restart_provider": restart,
            "entity_provider_routes": self.runtime.configured_provider_routes(
                self.group
            ),
            "remote_command_map": self.runtime.configured_command_map(self.group),
        }
    )
    return attributes


def _normalized_action_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _raw_actions(self: UnifiedMediaController) -> list[SourceAction]:
    actions = list(_raw_actions.original(self))
    generic_source_ids = [
        source_id
        for source_id in self.group.source_ids
        if not (
            (source := self.runtime.manager.get_source(source_id)) is not None
            and source.is_cast
        )
    ]
    generic_id_set = set(generic_source_ids)
    actions = [
        action
        for action in actions
        if not (action.kind == "input" and action.source_id in generic_id_set)
    ]

    existing = {(action.kind, action.source_id, action.value) for action in actions}
    existing_app_names = {
        _normalized_action_name(action.default_name)
        for action in actions
        if action.kind in {"tv_app", "adb_app", "native_source"}
    }
    existing_input_names = {
        _normalized_action_name(action.default_name)
        for action in actions
        if action.kind == "input"
    }

    for source_id in generic_source_ids:
        for value in self.runtime.manager.sources(source_id):
            kind = source_kind(value)
            normalized_name = _normalized_action_name(value)
            identity = (kind, source_id, value)
            if identity in existing:
                continue
            if kind == "native_source" and normalized_name in existing_app_names:
                continue
            if kind == "input" and normalized_name in existing_input_names:
                continue
            key_value = value if kind == "input" else f"{source_id}:{value}"
            actions.append(
                SourceAction(
                    kind,
                    source_id,
                    value,
                    _action_key(kind, key_value),
                    value,
                )
            )
            existing.add(identity)
            if kind == "native_source":
                existing_app_names.add(normalized_name)
            else:
                existing_input_names.add(normalized_name)
    return actions


def _prefix(self: UnifiedMediaController, action: SourceAction) -> str:
    if action.kind == "native_source":
        return TV_APP_PREFIX
    return _prefix.original(self, action)


def _source(self: UnifiedMediaController) -> str | None:
    current = _source.original.fget(self)
    if current is not None:
        return current
    actions = self._source_actions()
    for source_id in self.group.source_ids:
        state = self.runtime.manager.get_state(source_id)
        selected = state.attributes.get("source") if state else None
        if not isinstance(selected, str):
            continue
        for option, action in actions.items():
            if (
                action.kind == "native_source"
                and action.source_id == source_id
                and action.value == selected
            ):
                return option
    return None


async def _async_select_source(
    self: UnifiedMediaController, source: str
) -> None:
    action = self._source_actions().get(source)
    if action is None or action.kind != "native_source":
        await _async_select_source.original(self, source)
        return
    await self._leave_cast_session()
    await self.runtime.manager.call_media_player(
        action.source_id,
        "select_source",
        {"source": action.value},
    )


def install_v83_patches() -> None:
    """Install generic V8.3 routing once, after the V8.1 runtime patches."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    IntegrationRuntime.configured_device_entities = _configured_device_entities
    IntegrationRuntime.configured_provider_routes = _configured_provider_routes
    IntegrationRuntime.configured_command_map = _configured_command_map

    SourceManager.set_group_configuration = _set_group_configuration
    SourceManager.group_configuration = _group_configuration
    SourceManager.linked_entity_ids = _linked_entity_ids
    SourceManager._source_facts = _source_facts
    SourceManager._entry_labels = _entry_labels
    SourceManager.provider_entity_id = _provider_entity_id
    _remote_entity_id.original = SourceManager.remote_entity_id
    SourceManager.remote_entity_id = _remote_entity_id
    SourceManager.send_command = _send_command
    _restart_button_entity_id.original = SourceManager.restart_button_entity_id
    SourceManager.restart_button_entity_id = _restart_button_entity_id

    _register_controller.original = IntegrationRuntime.register_controller
    IntegrationRuntime.register_controller = callback(_register_controller)

    _extra_state_attributes.original = UnifiedMediaController.extra_state_attributes
    UnifiedMediaController.extra_state_attributes = property(_extra_state_attributes)
    _raw_actions.original = UnifiedMediaController._raw_actions
    UnifiedMediaController._raw_actions = _raw_actions
    _prefix.original = UnifiedMediaController._prefix
    UnifiedMediaController._prefix = _prefix
    _source.original = UnifiedMediaController.source
    UnifiedMediaController.source = property(_source)
    _async_select_source.original = UnifiedMediaController.async_select_source
    UnifiedMediaController.async_select_source = _async_select_source

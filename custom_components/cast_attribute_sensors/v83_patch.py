"""V8.3 universal remote and native-source routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_REMOTE_CONTROLS,
    CONF_REMOTE_ENTITY,
    CONF_REMOTE_PROFILE,
    DOMAIN,
    REMOTE_DOMAIN,
    TV_APP_PREFIX,
)
from .grouping import normalized_device_name
from .media_player import SourceAction, UnifiedMediaController, _action_key
from .runtime import IntegrationRuntime
from .source_manager import SourceManager
from .universal_remote import (
    PROFILE_AUTO,
    PROFILE_BRAVIA,
    is_auto_supported_platform,
    native_source_kind,
    profile_for_platform,
    translate_command,
)

_NATIVE_SOURCE_PLATFORMS = frozenset({"braviatv", "sony_bravia"})
_TOKEN = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
_STOP_TOKENS = frozenset(
    {
        "android",
        "cast",
        "controller",
        "device",
        "google",
        "media",
        "player",
        "remote",
        "smart",
        "television",
    }
)
_INSTALLED = False


@dataclass(frozen=True, slots=True)
class RemoteTarget:
    """One remote entity selected for a physical controller."""

    entity_id: str
    platform: str
    profile: str
    score: int


def _labels(manager: SourceManager, entry: er.RegistryEntry) -> set[str]:
    state = manager.hass.states.get(entry.entity_id)
    device = (
        manager.device_registry.async_get(entry.device_id)
        if entry.device_id is not None
        else None
    )
    values = [
        state.attributes.get("friendly_name") if state else None,
        device.name if device else None,
        device.name_by_user if device else None,
        device.model if device else None,
        device.manufacturer if device else None,
    ]
    return {
        normalized
        for value in values
        if isinstance(value, str)
        and value.strip()
        and (normalized := normalized_device_name(value))
    }


def _tokens(labels: set[str]) -> set[str]:
    return {
        token
        for label in labels
        for token in _TOKEN.findall(label)
        if token not in _STOP_TOKENS and not token.isdecimal()
    }


def _source_facts(
    manager: SourceManager, source_ids: tuple[str, ...]
) -> tuple[set[str], set[str], set[tuple[str, str]], set[str], set[str], set[str]]:
    config_entry_ids: set[str] = set()
    device_ids: set[str] = set()
    connections: set[tuple[str, str]] = set()
    areas: set[str] = set()
    platforms: set[str] = set()
    labels: set[str] = set()

    for source_id in source_ids:
        source = manager.get_source(source_id)
        if source is None:
            continue
        if source.config_entry_id:
            config_entry_ids.add(source.config_entry_id)
        if source.device_id:
            device_ids.add(source.device_id)
        platforms.add(source.platform)
        entry = (
            manager.entity_registry.async_get(source.entity_id)
            if source.entity_id
            else None
        )
        if entry is not None:
            labels.update(_labels(manager, entry))
        state = manager.get_state(source_id)
        if state is not None:
            friendly_name = state.attributes.get("friendly_name")
            if isinstance(friendly_name, str) and friendly_name.strip():
                labels.add(normalized_device_name(friendly_name))

    for device_id in device_ids:
        device = manager.device_registry.async_get(device_id)
        if device is None:
            continue
        connections.update(device.connections)
        if device.area_id:
            areas.add(device.area_id)
        for value in (
            device.name,
            device.name_by_user,
            device.model,
            device.manufacturer,
        ):
            if isinstance(value, str) and value.strip():
                labels.add(normalized_device_name(value))

    labels.discard("")
    return config_entry_ids, device_ids, connections, areas, platforms, labels


def _score_remote(
    manager: SourceManager,
    entry: er.RegistryEntry,
    *,
    config_entry_ids: set[str],
    device_ids: set[str],
    connections: set[tuple[str, str]],
    areas: set[str],
    source_platforms: set[str],
    source_labels: set[str],
) -> int:
    score = 0
    if entry.device_id and entry.device_id in device_ids:
        score = max(score, 300)
    if entry.config_entry_id and entry.config_entry_id in config_entry_ids:
        score = max(score, 260)

    device = (
        manager.device_registry.async_get(entry.device_id)
        if entry.device_id is not None
        else None
    )
    if device is not None and connections & set(device.connections):
        score = max(score, 280)
    if device is not None and device.area_id and device.area_id in areas:
        score = max(score, 40)

    candidate_labels = _labels(manager, entry)
    if source_labels & candidate_labels:
        score = max(score, 220)
    shared_tokens = _tokens(source_labels) & _tokens(candidate_labels)
    if shared_tokens:
        score = max(score, 100 + min(len(shared_tokens), 5) * 20)

    platform = entry.platform.casefold()
    if platform in source_platforms:
        score += 80
    if platform in _NATIVE_SOURCE_PLATFORMS and (
        source_platforms & _NATIVE_SOURCE_PLATFORMS
        or any("bravia" in label or "sony" in label for label in source_labels)
    ):
        score += 80
    if platform == "androidtv_remote" and source_platforms & {
        "androidtv_remote",
        "androidtv",
        "cast",
    }:
        score += 40
    return score


def _manager_init(self: SourceManager, hass) -> None:
    _manager_init.original(self, hass)
    self._remote_overrides: dict[frozenset[str], dict[str, str]] = {}


def _set_remote_override(
    self: SourceManager,
    source_ids: tuple[str, ...],
    config: dict[str, str] | None,
) -> None:
    key = frozenset(source_ids)
    if config and config.get(CONF_REMOTE_ENTITY):
        self._remote_overrides[key] = dict(config)
    else:
        self._remote_overrides.pop(key, None)


def _remote_target(
    self: SourceManager, source_ids: tuple[str, ...]
) -> RemoteTarget | None:
    override = self._remote_overrides.get(frozenset(source_ids), {})
    override_entity = str(override.get(CONF_REMOTE_ENTITY, "")).strip()
    if override_entity:
        entry = self.entity_registry.async_get(override_entity)
        if entry is not None and entry.domain == REMOTE_DOMAIN:
            configured_profile = str(
                override.get(CONF_REMOTE_PROFILE, PROFILE_AUTO)
            ).strip()
            profile = (
                profile_for_platform(entry.platform)
                if configured_profile == PROFILE_AUTO
                else configured_profile
            )
            return RemoteTarget(entry.entity_id, entry.platform, profile, 1000)

    (
        config_entry_ids,
        device_ids,
        connections,
        areas,
        source_platforms,
        source_labels,
    ) = _source_facts(self, source_ids)

    candidates: list[RemoteTarget] = []
    for entry in self.entity_registry.entities.values():
        if (
            entry.domain != REMOTE_DOMAIN
            or entry.platform == DOMAIN
            or entry.disabled_by is not None
            or not is_auto_supported_platform(entry.platform)
        ):
            continue
        score = _score_remote(
            self,
            entry,
            config_entry_ids=config_entry_ids,
            device_ids=device_ids,
            connections=connections,
            areas=areas,
            source_platforms=source_platforms,
            source_labels=source_labels,
        )
        candidates.append(
            RemoteTarget(
                entry.entity_id,
                entry.platform,
                profile_for_platform(entry.platform),
                score,
            )
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item.score, item.entity_id))
    if len(candidates) == 1:
        return candidates[0]
    if candidates[0].score > candidates[1].score and candidates[0].score >= 40:
        return candidates[0]
    return None


def _remote_entity_id(
    self: SourceManager, source_ids: tuple[str, ...]
) -> str | None:
    target = self.remote_target(source_ids)
    return target.entity_id if target else None


def _remote_media_source_id(
    self: SourceManager, source_ids: tuple[str, ...]
) -> str | None:
    target = self.remote_target(source_ids)
    if target is None:
        return None
    remote_entry = self.entity_registry.async_get(target.entity_id)
    if remote_entry is None:
        return None

    desired_platforms = {
        "androidtv_remote": {"androidtv_remote"},
        "androidtv": {"androidtv"},
        PROFILE_BRAVIA: set(_NATIVE_SOURCE_PLATFORMS),
    }.get(target.profile, {target.platform})

    direct = [
        source_id
        for source_id in source_ids
        if self.platform(source_id) in desired_platforms
    ]
    if len(direct) == 1:
        return direct[0]

    scored: list[tuple[int, str]] = []
    for source in self._sources.values():
        if source.entity_id is None or source.platform not in desired_platforms:
            continue
        score = 0
        if remote_entry.device_id and source.device_id == remote_entry.device_id:
            score = 120
        if (
            remote_entry.config_entry_id
            and source.config_entry_id == remote_entry.config_entry_id
        ):
            score = max(score, 100)
        if score:
            scored.append((score, source.registry_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


async def _send_command(
    self: SourceManager, source_ids: tuple[str, ...], command: str
) -> None:
    target = self.remote_target(source_ids)
    if target is None:
        raise RuntimeError("No compatible TV remote entity is linked")
    await self.hass.services.async_call(
        REMOTE_DOMAIN,
        "send_command",
        {
            ATTR_ENTITY_ID: target.entity_id,
            "command": translate_command(target.profile, command),
        },
        blocking=True,
    )


def _remote_config(
    self: IntegrationRuntime, group
) -> dict[str, str]:
    configured = self._mapping_option(CONF_REMOTE_CONTROLS).get(group.key, {})
    if not isinstance(configured, dict):
        return {}
    return {
        CONF_REMOTE_ENTITY: str(configured.get(CONF_REMOTE_ENTITY, "")).strip(),
        CONF_REMOTE_PROFILE: str(
            configured.get(CONF_REMOTE_PROFILE, PROFILE_AUTO)
        ).strip(),
    }


def _register_controller(
    self: IntegrationRuntime, entity_id: str, controller: Any
) -> None:
    _register_controller.original(self, entity_id, controller)
    self.manager.set_remote_override(
        controller.group.source_ids,
        self.remote_config(controller.group),
    )


def _extra_state_attributes(self: UnifiedMediaController) -> dict[str, Any]:
    attributes = dict(_extra_state_attributes.original.fget(self))
    target = self.runtime.manager.remote_target(self.group.source_ids)
    attributes.update(
        {
            "remote_available": target is not None,
            "remote_entity_id": target.entity_id if target else None,
            "remote_platform": target.platform if target else None,
            "remote_profile": target.profile if target else None,
        }
    )
    return attributes


def _raw_actions(self: UnifiedMediaController) -> list[SourceAction]:
    actions = list(_raw_actions.original(self))
    native_ids = [
        source_id
        for source_id in self.group.source_ids
        if self.runtime.manager.platform(source_id) in _NATIVE_SOURCE_PLATFORMS
    ]
    companion = self.runtime.manager.remote_media_source_id(self.group.source_ids)
    if (
        companion is not None
        and self.runtime.manager.platform(companion) in _NATIVE_SOURCE_PLATFORMS
        and companion not in native_ids
    ):
        native_ids.append(companion)

    native_id_set = set(native_ids)
    actions = [
        action
        for action in actions
        if not (action.source_id in native_id_set and action.kind == "input")
    ]
    existing = {(action.kind, action.source_id, action.value) for action in actions}
    for source_id in native_ids:
        for value in self.runtime.manager.sources(source_id):
            kind = native_source_kind(value)
            identity = (kind, source_id, value)
            if identity in existing:
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
    return actions


def _prefix(self: UnifiedMediaController, action: SourceAction) -> str:
    if action.kind == "native_app":
        return TV_APP_PREFIX
    return _prefix.original(self, action)


def _source(self: UnifiedMediaController) -> str | None:
    active = _source.original.fget(self)
    if active is not None:
        return active
    actions = self._source_actions()
    for source_id in self.group.source_ids:
        state = self.runtime.manager.get_state(source_id)
        current = state.attributes.get("source") if state else None
        if not isinstance(current, str):
            continue
        for option, action in actions.items():
            if (
                action.kind == "native_app"
                and action.source_id == source_id
                and action.value == current
            ):
                return option
    return None


async def _async_select_source(
    self: UnifiedMediaController, source: str
) -> None:
    action = self._source_actions().get(source)
    if action is None or action.kind != "native_app":
        await _async_select_source.original(self, source)
        return
    await self._leave_cast_session()
    await self.runtime.manager.call_media_player(
        action.source_id,
        "select_source",
        {"source": action.value},
    )


def install_v83_patches() -> None:
    """Install universal remote support exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    _manager_init.original = SourceManager.__init__
    SourceManager.__init__ = _manager_init
    SourceManager.set_remote_override = _set_remote_override
    SourceManager.remote_target = _remote_target
    SourceManager.remote_entity_id = _remote_entity_id
    SourceManager.remote_media_source_id = _remote_media_source_id
    SourceManager.send_command = _send_command

    IntegrationRuntime.remote_config = _remote_config
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

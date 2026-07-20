"""V8.3.1 runtime corrections for generic providers and applications."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError

from .ad_skip import AdSkipManager
from .const import (
    ANDROID_TV_ADB_DOMAIN,
    ANDROID_TV_REMOTE_DOMAIN,
    BUTTON_DOMAIN,
    DOMAIN,
    REMOTE_DOMAIN,
    ROUTE_NAVIGATION,
    ROUTE_RESTART,
    ROUTE_TV_APPS,
    TV_APP_PREFIX,
)
from .media_player import (
    SourceAction,
    UnifiedMediaController,
    _action_key,
    _is_transient_app,
)
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


def _tokens(values: set[str]) -> set[str]:
    return {
        token.casefold()
        for value in values
        for token in _TOKEN.findall(value)
        if token.casefold() not in _STOP_TOKENS and not token.isdecimal()
    }


def _provider_entity_id(
    self: SourceManager,
    source_ids: tuple[str, ...],
    capability: str,
) -> str | None:
    """Use explicit v8.3 routing first, then safe Home Assistant evidence."""
    selected = _provider_entity_id.original(self, source_ids, capability)
    if selected is not None:
        return selected

    domains = {
        ROUTE_NAVIGATION: {REMOTE_DOMAIN},
        ROUTE_RESTART: {BUTTON_DOMAIN},
    }.get(capability, set())
    if not domains:
        return None

    device_ids, config_entry_ids, area_ids, source_labels = self._source_facts(
        source_ids
    )
    source_tokens = _tokens(source_labels)
    scored: list[tuple[int, str]] = []
    for entry in self.entity_registry.entities.values():
        if (
            entry.domain not in domains
            or entry.platform == DOMAIN
            or entry.disabled_by is not None
        ):
            continue
        score = 0
        if entry.device_id and entry.device_id in device_ids:
            score += 500
        if entry.config_entry_id and entry.config_entry_id in config_entry_ids:
            score += 300
        device = (
            self.device_registry.async_get(entry.device_id)
            if entry.device_id is not None
            else None
        )
        if device is not None and device.area_id in area_ids:
            score += 80
        state = self.hass.states.get(entry.entity_id)
        if state is not None and state.state != STATE_UNAVAILABLE:
            score += 20
        score += 10 * min(
            len(source_tokens & _tokens(self._entry_labels(entry))), 5
        )
        device_class = getattr(entry, "device_class", None) or getattr(
            entry, "original_device_class", None
        )
        if capability == ROUTE_RESTART and device_class == "restart":
            score += 120
        scored.append((score, entry.entity_id))

    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    if scored[0][0] > 0 and (
        len(scored) == 1 or scored[0][0] > scored[1][0]
    ):
        return scored[0][1]
    return scored[0][1] if len(scored) == 1 else None


def _native_app_source_id(
    self: SourceManager, source_ids: tuple[str, ...]
) -> str | None:
    """Return the best non-Cast provider for application operations."""
    legacy = _native_app_source_id.original(self, source_ids)
    if legacy is not None:
        return legacy

    candidates: list[tuple[int, str]] = []
    for source_id in source_ids:
        source = self.get_source(source_id)
        if source is None or source.is_cast or source.entity_id is None:
            continue
        score = 0
        if source.platform == ANDROID_TV_REMOTE_DOMAIN:
            score += 500
        selectable = self.sources(source_id)
        if selectable:
            score += 250
        if self.supports(source_id, MediaPlayerEntityFeature.PLAY_MEDIA):
            score += 200
        state = self.get_state(source_id)
        if state is not None and state.state != STATE_UNAVAILABLE:
            score += 50
            if state.attributes.get("app_id") or state.attributes.get("app_name"):
                score += 20
        candidates.append((score, source_id))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _tv_apps(self: SourceManager, source_id: str) -> dict[str, str]:
    """Expose learned/current apps for every configured non-Cast provider."""
    source = self.get_source(source_id)
    if source is None or source.is_cast:
        return {}
    apps = dict(_tv_apps.original(self, source_id))
    apps.update(self._learned_apps.get(source_id, {}))
    state = self.get_state(source_id)
    if state is not None:
        app_id = state.attributes.get("app_id")
        if isinstance(app_id, str) and app_id.strip():
            app_name = state.attributes.get("app_name")
            apps[app_id.strip()] = (
                app_name.strip()
                if isinstance(app_name, str) and app_name.strip()
                else app_id.strip()
            )
    return apps


async def _launch_tv_app(
    self: SourceManager, source_id: str, app_id: str
) -> None:
    """Launch through source selection, Android app launch, or PLAY_MEDIA."""
    source = self.get_source(source_id)
    if source is None or source.is_cast:
        raise HomeAssistantError("The selected application provider is unavailable")

    requested = app_id.strip()
    catalog = self.tv_apps(source_id)
    app_name = catalog.get(requested, requested)
    selectable = self.sources(source_id)
    match = next(
        (
            value
            for value in selectable
            if value.casefold() in {requested.casefold(), app_name.casefold()}
        ),
        None,
    )
    if match is not None:
        await self.call_media_player(
            source_id, "select_source", {"source": match}
        )
        return

    if source.platform == ANDROID_TV_REMOTE_DOMAIN:
        await _launch_tv_app.original(self, source_id, requested)
        return

    if self.supports(source_id, MediaPlayerEntityFeature.PLAY_MEDIA):
        await self.call_media_player(
            source_id,
            "play_media",
            {
                "media": {
                    "media_content_type": "app",
                    "media_content_id": requested,
                }
            },
        )
        return

    entity_id = self.get_entity_id(source_id) or source_id
    raise HomeAssistantError(
        f"{entity_id} exposes neither a matching selectable source nor "
        "PLAY_MEDIA application launch"
    )


def _raw_actions(self: UnifiedMediaController) -> list[SourceAction]:
    """Add launchable learned/current apps without duplicating selectable apps."""
    actions = list(_raw_actions.original(self))
    for source_id in self._source_ids(cast=False):
        source = self.runtime.manager.get_source(source_id)
        if source is None:
            continue
        selectable = {
            value.casefold().strip()
            for value in self.runtime.manager.sources(source_id)
        }
        can_launch = (
            source.platform == ANDROID_TV_REMOTE_DOMAIN
            or self.runtime.manager.supports(
                source_id, MediaPlayerEntityFeature.PLAY_MEDIA
            )
        )
        existing_values = {
            action.value.casefold()
            for action in actions
            if action.source_id == source_id and action.kind != "input"
        }
        existing_names = {
            action.default_name.casefold().strip()
            for action in actions
            if action.source_id == source_id and action.kind != "input"
        }
        for app_id, name in self.runtime.manager.tv_apps(source_id).items():
            normalized_id = app_id.casefold().strip()
            normalized_name = name.casefold().strip()
            selectable_match = (
                normalized_id in selectable or normalized_name in selectable
            )
            if (
                not normalized_id
                or not normalized_name
                or _is_transient_app(name)
                or normalized_id in existing_values
                or normalized_name in existing_names
                or (not selectable_match and not can_launch)
            ):
                continue
            actions.append(
                SourceAction(
                    "generic_app",
                    source_id,
                    app_id,
                    _action_key("generic_app", f"{source_id}:{app_id}"),
                    name,
                )
            )
            existing_values.add(normalized_id)
            existing_names.add(normalized_name)
    return actions


def _prefix(self: UnifiedMediaController, action: SourceAction) -> str:
    if action.kind == "generic_app":
        return TV_APP_PREFIX
    return _prefix.original(self, action)


def _source(self: UnifiedMediaController) -> str | None:
    current = _source.original.fget(self)
    if current is not None:
        return current
    actions = self._source_actions()
    for source_id in self._source_ids(cast=False):
        state = self.runtime.manager.get_state(source_id)
        if state is None:
            continue
        app_id = state.attributes.get("app_id")
        app_name = state.attributes.get("app_name")
        for option, action in actions.items():
            if action.kind != "generic_app" or action.source_id != source_id:
                continue
            if isinstance(app_id, str) and action.value == app_id:
                return option
            if (
                isinstance(app_name, str)
                and action.default_name.casefold() == app_name.casefold()
            ):
                return option
    return None


async def _async_select_source(
    self: UnifiedMediaController, source: str
) -> None:
    action = self._source_actions().get(source)
    if action is None or action.kind != "generic_app":
        await _async_select_source.original(self, source)
        return
    await self._leave_cast_session()
    await self.runtime.manager.launch_tv_app(action.source_id, action.value)


async def _async_launch_tv_app(
    self: UnifiedMediaController, app_id: str
) -> None:
    """Resolve a service request against the controller application catalog."""
    requested = app_id.strip().casefold()
    for option, action in self._source_actions().items():
        if action.kind not in {
            "tv_app",
            "adb_app",
            "native_source",
            "generic_app",
        }:
            continue
        if requested in {
            action.value.casefold(),
            self._display_name(action).casefold(),
        }:
            await self.async_select_source(option)
            return

    target = self.runtime.manager.android_tv_remote_source_id(
        self.group.source_ids
    )
    if target is None:
        raise HomeAssistantError("No native application provider is configured")
    await self._leave_cast_session()
    await self.runtime.manager.launch_tv_app(target, app_id)


def _register_tv_app(
    self: UnifiedMediaController, app_id: str, app_name: str
) -> None:
    """Register an app against the best native provider for this device."""
    target = self.runtime.manager.android_tv_remote_source_id(
        self.group.source_ids
    )
    if target is None:
        raise HomeAssistantError("No native application provider is configured")
    self.runtime.manager.register_app(target, app_id.strip(), app_name.strip())
    if self.entity_id:
        self.async_write_ha_state()


def _extra_state_attributes(self: UnifiedMediaController) -> dict[str, Any]:
    attributes = dict(_extra_state_attributes.original.fget(self))
    native_providers = [
        self.runtime.manager.get_entity_id(source_id)
        for source_id in self._category_ids(ROUTE_TV_APPS, cast=False)
    ]
    restart_provider = attributes.get("restart_provider")
    attributes.update(
        {
            "application_providers": [
                entity_id for entity_id in native_providers if entity_id
            ],
            "restart_available": restart_provider is not None,
            "runtime_release": "8.3.1",
        }
    )
    return attributes


async def _async_skip_now(
    self: AdSkipManager, group
) -> bool:
    """Keep conservative skipping but record an actionable failure reason."""
    youtube_sources = [
        source_id
        for source_id in group.source_ids
        if self._youtube_state(source_id) is not None
    ]
    if not youtube_sources:
        self._set_result(group.key, "youtube_not_detected")
        return False
    if await _async_skip_now.original(self, group):
        return True

    cast_sources = [
        source_id
        for source_id in youtube_sources
        if (
            (source := self.runtime.manager.get_source(source_id)) is not None
            and source.is_cast
        )
    ]
    adb_sources = [
        source_id
        for source_id in youtube_sources
        if (
            (source := self.runtime.manager.get_source(source_id)) is not None
            and source.platform == ANDROID_TV_ADB_DOMAIN
        )
    ]
    if adb_sources and not self.hass.services.has_service(
        ANDROID_TV_ADB_DOMAIN, "adb_command"
    ):
        result = "adb_service_unavailable"
    elif adb_sources:
        result = "skip_control_not_detected"
    elif cast_sources:
        result = "cast_skip_not_advertised"
    else:
        result = "no_safe_skip_method"
    self._set_result(group.key, result)
    return False


def install_v831_patches() -> None:
    """Install the v8.3.1 corrections exactly once after v8.3."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    _provider_entity_id.original = SourceManager.provider_entity_id
    SourceManager.provider_entity_id = _provider_entity_id
    _native_app_source_id.original = SourceManager.android_tv_remote_source_id
    SourceManager.android_tv_remote_source_id = _native_app_source_id
    _tv_apps.original = SourceManager.tv_apps
    SourceManager.tv_apps = _tv_apps
    _launch_tv_app.original = SourceManager.launch_tv_app
    SourceManager.launch_tv_app = _launch_tv_app

    _raw_actions.original = UnifiedMediaController._raw_actions
    UnifiedMediaController._raw_actions = _raw_actions
    _prefix.original = UnifiedMediaController._prefix
    UnifiedMediaController._prefix = _prefix
    _source.original = UnifiedMediaController.source
    UnifiedMediaController.source = property(_source)
    _async_select_source.original = UnifiedMediaController.async_select_source
    UnifiedMediaController.async_select_source = _async_select_source
    UnifiedMediaController.async_launch_tv_app = _async_launch_tv_app
    UnifiedMediaController.register_tv_app = _register_tv_app
    _extra_state_attributes.original = UnifiedMediaController.extra_state_attributes
    UnifiedMediaController.extra_state_attributes = property(_extra_state_attributes)

    _async_skip_now.original = AdSkipManager.async_skip_now
    AdSkipManager.async_skip_now = _async_skip_now

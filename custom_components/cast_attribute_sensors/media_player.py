"""One compact media-player controller per physical device."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ANDROID_TV_ADB_DOMAIN,
    ANDROID_TV_REMOTE_DOMAIN,
    BUTTON_DOMAIN,
    CAST_APP_PREFIX,
    CONF_ACTIVITY_MUTE,
    CONF_ACTIVITY_NAME,
    CONF_ACTIVITY_SOURCE,
    CONF_ACTIVITY_VOLUME,
    CONF_APP_CONFIRM_DELAY,
    CONF_BROADCAST_ADDRESS,
    CONF_BROADCAST_PORT,
    CONF_CAST_EXIT_DELAY,
    CONF_DISPLAY_NAME,
    CONF_FAVORITE,
    CONF_MAC,
    CONF_ORDER,
    CONF_POWER_DELAY,
    CONF_RESTART_DELAY,
    CONF_RETRY_DELAY,
    CONF_VISIBLE,
    INPUT_PREFIX,
    ROUTE_CAST_APPS,
    ROUTE_INPUTS,
    ROUTE_METADATA,
    ROUTE_NAVIGATION,
    ROUTE_PLAYBACK,
    ROUTE_POWER,
    ROUTE_RESTART,
    ROUTE_SEEK,
    ROUTE_TV_APPS,
    ROUTE_VOLUME,
    TRANSIENT_APP_MARKERS,
    TV_APP_PREFIX,
    UID_SEPARATOR,
    UID_VERSION,
    WAKE_ON_LAN_DOMAIN,
)
from .grouping import PhysicalGroup
from .runtime import IntegrationRuntime

_IMPLEMENTED_FEATURES = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.SEEK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.SHUFFLE_SET
    | MediaPlayerEntityFeature.REPEAT_SET
)


@dataclass(frozen=True, slots=True)
class SourceAction:
    """A selectable app or physical input."""

    kind: str
    source_id: str
    value: str
    key: str
    default_name: str


def _action_key(kind: str, value: str) -> str:
    return f"{kind}|{value}"


def _state_enum(value: str | None) -> MediaPlayerState | None:
    if value is None:
        return None
    try:
        return MediaPlayerState(value)
    except ValueError:
        return None


def _features(state: State | None) -> MediaPlayerEntityFeature:
    value = state.attributes.get("supported_features", 0) if state else 0
    return MediaPlayerEntityFeature(value if isinstance(value, int) else 0)


def _live_position(state: State | None) -> float | None:
    if state is None:
        return None
    position = state.attributes.get("media_position")
    if not isinstance(position, (int, float)):
        return None
    result = float(position)
    updated_at = state.attributes.get("media_position_updated_at")
    parsed: datetime | None = None
    if isinstance(updated_at, datetime):
        parsed = updated_at
    elif isinstance(updated_at, str):
        parsed = dt_util.parse_datetime(updated_at)
    if state.state == MediaPlayerState.PLAYING and parsed is not None:
        result += max(0.0, (dt_util.utcnow() - parsed).total_seconds())
    duration = state.attributes.get("media_duration")
    if isinstance(duration, (int, float)) and duration > 0:
        result = min(result, float(duration))
    return max(0.0, result)


def _is_transient_app(name: str) -> bool:
    normalized = name.casefold().strip()
    return any(marker in normalized for marker in TRANSIENT_APP_MARKERS)


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create controllers and hot-add newly discovered independent devices."""
    platform = DynamicControllerPlatform(entry.runtime_data, async_add_entities)
    platform.start()
    entry.async_on_unload(platform.stop)


class DynamicControllerPlatform:
    """Own controller entities for the lifetime of the config entry."""

    def __init__(self, runtime: IntegrationRuntime, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
        self.runtime = runtime
        self._async_add_entities = async_add_entities
        self._entities: dict[str, UnifiedMediaController] = {}
        self._unsubscribe = None

    @callback
    def start(self) -> None:
        self._add_groups(self.runtime.groups)
        self._unsubscribe = self.runtime.async_subscribe_group_additions(self._add_groups)

    @callback
    def stop(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _add_groups(self, groups: tuple[PhysicalGroup, ...]) -> None:
        entities: list[UnifiedMediaController] = []
        for group in groups:
            if group.key in self._entities:
                continue
            entity = UnifiedMediaController(self.runtime, group)
            self._entities[group.key] = entity
            entities.append(entity)
        if entities:
            self._async_add_entities(entities)


class UnifiedMediaController(MediaPlayerEntity):
    """Proxy the best capability from all representations of one physical device."""

    _attr_has_entity_name = True
    _attr_name = "Controller"
    _attr_should_poll = False

    def __init__(self, runtime: IntegrationRuntime, group: PhysicalGroup) -> None:
        self.runtime = runtime
        self.group = group
        self._attr_unique_id = UID_SEPARATOR.join((UID_VERSION, group.key, "media_player", "controller"))
        self._attr_device_info = runtime.device_info(group)
        if group.is_tv:
            self._attr_device_class = MediaPlayerDeviceClass.TV
        self._attr_icon = "mdi:television" if group.is_tv else "mdi:cast-connected"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        for source_id in self.group.source_ids:
            self.async_on_remove(self.runtime.manager.async_subscribe_source(source_id, self._async_source_updated))
        if self.entity_id:
            self.runtime.register_controller(self.entity_id, self)

    async def async_will_remove_from_hass(self) -> None:
        if self.entity_id:
            self.runtime.unregister_controller(self.entity_id)
        await super().async_will_remove_from_hass()

    @callback
    def _async_source_updated(self, source_id: str, old_state: State | None, new_state: State | None) -> None:
        if self.entity_id:
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return any(self.runtime.manager.available(source_id) for source_id in self.group.source_ids)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        health, details = self.runtime.health(self.group)
        actions = self._source_actions()
        favorites = [option for option, action in actions.items() if self._preference(action).get(CONF_FAVORITE) is True]
        activities = self.runtime.activities(self.group)
        return {
            "physical_device_id": self.group.key,
            "health": health,
            "source_entities": [self.runtime.manager.get_entity_id(source_id) for source_id in self.group.source_ids],
            "source_platforms": [self.runtime.manager.platform(source_id) for source_id in self.group.source_ids],
            "capability_routes": self.runtime.configured_routes().get(self.group.key, {}),
            "favorite_sources": favorites,
            "activity_names": [str(item.get(CONF_ACTIVITY_NAME, "")).strip() for item in activities if str(item.get(CONF_ACTIVITY_NAME, "")).strip()],
            "managed_apps": self.app_catalog(),
            "remote_available": self.runtime.manager.remote_entity_id(
                self.group.source_ids
            )
            is not None,
            **details,
        }

    def _source_ids(self, *, cast: bool | None = None) -> tuple[str, ...]:
        result: list[str] = []
        for source_id in self.group.source_ids:
            source = self.runtime.manager.get_source(source_id)
            if source is not None and (cast is None or source.is_cast is cast):
                result.append(source_id)
        return tuple(result)

    def _routed_source(self, capability: str) -> str | None:
        source_id = self.runtime.route_source(self.group, capability)
        return source_id if source_id and self.runtime.manager.available(source_id) else None

    def _active_cast_source(self) -> str | None:
        for source_id in self._source_ids(cast=True):
            state = self.runtime.manager.get_state(source_id)
            if state is None or state.state in {"off", "unavailable", "unknown"}:
                continue
            if state.state in {"playing", "paused", "buffering"} or state.attributes.get("media_title") is not None:
                return source_id
        return None

    def _primary_native_source(self) -> str | None:
        priorities = {ANDROID_TV_REMOTE_DOMAIN: 0, ANDROID_TV_ADB_DOMAIN: 2}
        candidates = sorted(
            self._source_ids(cast=False),
            key=lambda source_id: (priorities.get(self.runtime.manager.platform(source_id), 1), self.runtime.manager.get_entity_id(source_id) or source_id),
        )
        return next((source_id for source_id in candidates if self.runtime.manager.available(source_id)), candidates[0] if candidates else None)

    def _active_state(self) -> State | None:
        routed = self._routed_source(ROUTE_METADATA)
        if routed:
            return self.runtime.manager.get_state(routed)
        active_cast = self._active_cast_source()
        if active_cast:
            return self.runtime.manager.get_state(active_cast)
        primary = self._primary_native_source() or self.group.primary_source_id
        return self.runtime.manager.get_state(primary)

    def _target_for_feature(self, feature: MediaPlayerEntityFeature, capability: str, *, prefer_cast: bool = False) -> str | None:
        routed = self._routed_source(capability)
        if routed and self.runtime.manager.supports(routed, feature):
            return routed
        ordered: list[str] = []
        active_cast = self._active_cast_source()
        if prefer_cast and active_cast:
            ordered.append(active_cast)
        primary = self._primary_native_source()
        if primary:
            ordered.append(primary)
        ordered.extend(self.group.source_ids)
        if not prefer_cast and active_cast:
            ordered.append(active_cast)
        seen: set[str] = set()
        for source_id in ordered:
            if source_id in seen:
                continue
            seen.add(source_id)
            if self.runtime.manager.available(source_id) and self.runtime.manager.supports(source_id, feature):
                return source_id
        return None

    @property
    def state(self) -> MediaPlayerState | None:
        state = self._active_state()
        return _state_enum(state.state if state else None)

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        combined = MediaPlayerEntityFeature(0)
        for source_id in self.group.source_ids:
            combined |= _features(self.runtime.manager.get_state(source_id))
        result = combined & _IMPLEMENTED_FEATURES
        if self.source_list:
            result |= MediaPlayerEntityFeature.SELECT_SOURCE
        wol = self.runtime.wol_config(self.group)
        if wol.get(CONF_MAC):
            result |= MediaPlayerEntityFeature.TURN_ON
        return result

    @property
    def volume_level(self) -> float | None:
        source = self._routed_source(ROUTE_VOLUME)
        state = self.runtime.manager.get_state(source) if source else self._active_state()
        value = state.attributes.get("volume_level") if state else None
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def is_volume_muted(self) -> bool | None:
        source = self._routed_source(ROUTE_VOLUME)
        state = self.runtime.manager.get_state(source) if source else self._active_state()
        value = state.attributes.get("is_volume_muted") if state else None
        return value if isinstance(value, bool) else None

    @property
    def media_content_id(self) -> str | None:
        return self._string_attribute("media_content_id")

    @property
    def media_content_type(self) -> str | None:
        return self._string_attribute("media_content_type")

    @property
    def media_duration(self) -> float | None:
        state = self._active_state()
        value = state.attributes.get("media_duration") if state else None
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def media_position(self) -> float | None:
        return _live_position(self._active_state())

    @property
    def media_position_updated_at(self) -> datetime | None:
        state = self._active_state()
        value = state.attributes.get("media_position_updated_at") if state else None
        if isinstance(value, datetime):
            return value
        return dt_util.parse_datetime(value) if isinstance(value, str) else None

    @property
    def media_title(self) -> str | None:
        return self._string_attribute("media_title")

    @property
    def media_artist(self) -> str | None:
        return self._string_attribute("media_artist")

    @property
    def media_album_name(self) -> str | None:
        return self._string_attribute("media_album_name")

    @property
    def app_id(self) -> str | None:
        return self._string_attribute("app_id")

    @property
    def app_name(self) -> str | None:
        return self._string_attribute("app_name")

    @property
    def media_image_url(self) -> str | None:
        """Return artwork from the active source, with source-level fallbacks."""
        states = [self._active_state()]
        states.extend(
            self.runtime.manager.get_state(source_id)
            for source_id in self.group.source_ids
        )
        companion = self.runtime.manager.android_tv_remote_source_id(
            self.group.source_ids
        )
        if companion is not None:
            states.append(self.runtime.manager.get_state(companion))
        for state in states:
            if state is None:
                continue
            for attribute in ("entity_picture", "media_image_url"):
                value = state.attributes.get(attribute)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @property
    def shuffle(self) -> bool | None:
        state = self._active_state()
        value = state.attributes.get("shuffle") if state else None
        return value if isinstance(value, bool) else None

    @property
    def repeat(self) -> str | None:
        return self._string_attribute("repeat")

    def _string_attribute(self, name: str) -> str | None:
        state = self._active_state()
        value = state.attributes.get(name) if state else None
        return str(value) if value is not None else None

    def _category_ids(self, route: str, *, cast: bool | None) -> tuple[str, ...]:
        routed = self.runtime.route_source(self.group, route)
        if routed:
            source = self.runtime.manager.get_source(routed)
            if source is not None and (cast is None or source.is_cast is cast):
                return (routed,)
        return self._source_ids(cast=cast)

    def _raw_actions(self) -> list[SourceAction]:
        actions: list[SourceAction] = []
        native_names: set[str] = set()
        tv_app_sources = list(self._category_ids(ROUTE_TV_APPS, cast=False))
        companion = self.runtime.manager.android_tv_remote_source_id(
            self.group.source_ids
        )
        if companion is not None and companion not in tv_app_sources:
            tv_app_sources.append(companion)
        for source_id in tv_app_sources:
            if self.runtime.manager.platform(source_id) != ANDROID_TV_REMOTE_DOMAIN:
                continue
            for app_id, name in self.runtime.manager.tv_apps(source_id).items():
                if not _is_transient_app(name):
                    actions.append(SourceAction("tv_app", source_id, app_id, _action_key("tv_app", app_id), name))
                    native_names.add(name.casefold().strip())
        for source_id in tv_app_sources:
            if self.runtime.manager.platform(source_id) != ANDROID_TV_ADB_DOMAIN:
                continue
            for native_source in self.runtime.manager.sources(source_id):
                normalized = native_source.casefold().strip()
                if normalized and not _is_transient_app(native_source) and normalized not in native_names:
                    actions.append(SourceAction("adb_app", source_id, native_source, _action_key("adb_app", native_source), native_source))
        for source_id in self._category_ids(ROUTE_INPUTS, cast=False):
            if self.runtime.manager.platform(source_id) in {ANDROID_TV_REMOTE_DOMAIN, ANDROID_TV_ADB_DOMAIN}:
                continue
            for native_source in self.runtime.manager.sources(source_id):
                if native_source.strip() and not _is_transient_app(native_source):
                    actions.append(SourceAction("input", source_id, native_source, _action_key("input", native_source), native_source))
        cast_names: set[str] = set()
        for source_id in self._category_ids(ROUTE_CAST_APPS, cast=True):
            for app_id, name in self.runtime.manager.cast_apps(source_id).items():
                normalized = name.casefold().strip()
                if _is_transient_app(name) or normalized in cast_names:
                    continue
                cast_names.add(normalized)
                actions.append(SourceAction("cast_app", source_id, app_id, _action_key("cast_app", app_id), name))
        return actions

    def _preference(self, action: SourceAction) -> dict[str, Any]:
        return self.runtime.app_preferences(self.group).get(action.key, {})

    def _display_name(self, action: SourceAction) -> str:
        preference = self._preference(action)
        override = str(preference.get(CONF_DISPLAY_NAME, "")).strip()
        return override or action.default_name

    def _prefix(self, action: SourceAction) -> str:
        if action.kind in {"tv_app", "adb_app"}:
            return TV_APP_PREFIX
        if action.kind == "cast_app":
            return CAST_APP_PREFIX
        return INPUT_PREFIX

    def _source_actions(self) -> dict[str, SourceAction]:
        raw = [action for action in self._raw_actions() if action.kind == "input" or self._preference(action).get(CONF_VISIBLE, True) is not False]
        raw.sort(key=lambda action: (int(self._preference(action).get(CONF_ORDER, 1000)), self._display_name(action).casefold(), action.value))
        names = Counter((self._prefix(action), self._display_name(action)) for action in raw)
        result: dict[str, SourceAction] = {}
        for action in raw:
            display = self._display_name(action)
            option = f"{self._prefix(action)}{display}"
            if names[(self._prefix(action), display)] > 1 or option in result:
                option = f"{option} [{action.value}]"
            result[option] = action
        return result

    def app_catalog(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for action in self._raw_actions():
            if action.kind == "input":
                continue
            preference = self._preference(action)
            items.append({
                "key": action.key,
                "kind": action.kind,
                "name": self._display_name(action),
                "default_name": action.default_name,
                "value": action.value,
                "visible": preference.get(CONF_VISIBLE, True) is not False,
                "favorite": preference.get(CONF_FAVORITE) is True,
                "order": int(preference.get(CONF_ORDER, 1000)),
            })
        return sorted(items, key=lambda item: (item["order"], str(item["name"]).casefold(), str(item["key"])))

    def action_catalog(self) -> list[dict[str, str]]:
        return [{"key": action.key, "label": option, "kind": action.kind} for option, action in self._source_actions().items()]

    def source_option_for_key(self, key: str) -> str | None:
        return next((option for option, action in self._source_actions().items() if action.key == key), None)

    @property
    def source_list(self) -> list[str]:
        return list(self._source_actions())

    @property
    def source(self) -> str | None:
        actions = self._source_actions()
        active_cast = self._active_cast_source()
        if active_cast:
            state = self.runtime.manager.get_state(active_cast)
            app_id = state.attributes.get("app_id") if state else None
            if isinstance(app_id, str):
                for option, action in actions.items():
                    if action.kind == "cast_app" and action.source_id == active_cast and action.value == app_id:
                        return option
            app_name = state.attributes.get("app_name") if state else None
            if isinstance(app_name, str):
                for option, action in actions.items():
                    if (
                        action.kind == "cast_app"
                        and action.source_id == active_cast
                        and self._display_name(action).casefold() == app_name.casefold()
                    ):
                        return option
        native_source_ids = list(self._source_ids(cast=False))
        companion = self.runtime.manager.android_tv_remote_source_id(
            self.group.source_ids
        )
        if companion is not None and companion not in native_source_ids:
            native_source_ids.append(companion)
        for source_id in native_source_ids:
            state = self.runtime.manager.get_state(source_id)
            if state is None:
                continue
            app_id = state.attributes.get("app_id")
            current_source = state.attributes.get("source")
            for option, action in actions.items():
                if action.source_id != source_id:
                    continue
                if action.kind == "tv_app" and action.value == app_id:
                    return option
                if action.kind in {"adb_app", "input"} and action.value == current_source:
                    return option
        return None

    async def _leave_cast_session(self) -> None:
        source_ids = self.group.source_ids
        navigation = self.runtime.route_source(self.group, ROUTE_NAVIGATION)
        if navigation:
            source_ids = (navigation,)
        remote_available = self.runtime.manager.remote_entity_id(source_ids)
        if remote_available:
            await self.runtime.manager.send_command(source_ids, "HOME")
        for source_id in self._source_ids(cast=True):
            if self.runtime.manager.supports(source_id, MediaPlayerEntityFeature.STOP):
                await self.runtime.manager.call_media_player(source_id, "media_stop")
        if remote_available:
            await asyncio.sleep(self.runtime.command_delays(self.group)[CONF_CAST_EXIT_DELAY])

    async def async_select_source(self, source: str) -> None:
        action = self._source_actions()[source]
        delays = self.runtime.command_delays(self.group)
        if action.kind == "cast_app":
            if self.state == MediaPlayerState.OFF:
                await self.async_turn_on()
                await asyncio.sleep(delays[CONF_POWER_DELAY])
            await self.runtime.manager.launch_cast_app(action.source_id, action.value)
            return
        await self._leave_cast_session()
        if action.kind == "tv_app":
            await self.runtime.manager.launch_tv_app(action.source_id, action.value)
            await asyncio.sleep(delays[CONF_APP_CONFIRM_DELAY])
            state = self.runtime.manager.get_state(action.source_id)
            if state is not None and state.attributes.get("app_id") != action.value:
                await self.async_send_command("HOME")
                await asyncio.sleep(delays[CONF_RETRY_DELAY])
                await self.runtime.manager.launch_tv_app(action.source_id, action.value)
            return
        await self.runtime.manager.call_media_player(action.source_id, "select_source", {"source": action.value})

    async def async_run_activity(self, activity_name: str) -> None:
        activity = next((item for item in self.runtime.activities(self.group) if str(item.get(CONF_ACTIVITY_NAME, "")).casefold() == activity_name.casefold()), None)
        if activity is None:
            raise HomeAssistantError(f"Unknown activity: {activity_name}")
        await self.async_turn_on()
        source_key = str(activity.get(CONF_ACTIVITY_SOURCE, "")).strip()
        if source_key:
            await asyncio.sleep(self.runtime.command_delays(self.group)[CONF_POWER_DELAY])
            option = self.source_option_for_key(source_key)
            if option:
                await self.async_select_source(option)
        volume = activity.get(CONF_ACTIVITY_VOLUME)
        if isinstance(volume, (int, float)) and volume >= 0:
            await self.async_set_volume_level(max(0.0, min(float(volume) / 100.0, 1.0)))
        mute = activity.get(CONF_ACTIVITY_MUTE)
        if isinstance(mute, bool):
            await self.async_mute_volume(mute)

    async def _call_feature(self, feature: MediaPlayerEntityFeature, capability: str, service: str, data: dict[str, Any] | None = None, *, prefer_cast: bool = False) -> bool:
        target = self._target_for_feature(feature, capability, prefer_cast=prefer_cast)
        if target:
            await self.runtime.manager.call_media_player(target, service, data)
            return True
        return False

    async def async_turn_on(self) -> None:
        if await self._call_feature(MediaPlayerEntityFeature.TURN_ON, ROUTE_POWER, "turn_on"):
            return
        wol = self.runtime.wol_config(self.group)
        mac = str(wol.get(CONF_MAC, "")).strip()
        if not mac:
            return
        if not self.hass.services.has_service(WAKE_ON_LAN_DOMAIN, "send_magic_packet"):
            raise HomeAssistantError("Wake on LAN is configured but the integration is not loaded")
        data: dict[str, Any] = {"mac": mac}
        address = str(wol.get(CONF_BROADCAST_ADDRESS, "")).strip()
        if address:
            data[CONF_BROADCAST_ADDRESS] = address
        port = wol.get(CONF_BROADCAST_PORT)
        if isinstance(port, int) and port > 0:
            data[CONF_BROADCAST_PORT] = port
        await self.hass.services.async_call(WAKE_ON_LAN_DOMAIN, "send_magic_packet", data, blocking=True)

    async def async_turn_off(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.TURN_OFF, ROUTE_POWER, "turn_off")

    async def async_media_play(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.PLAY, ROUTE_PLAYBACK, "media_play", prefer_cast=True)

    async def async_media_pause(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.PAUSE, ROUTE_PLAYBACK, "media_pause", prefer_cast=True)

    async def async_media_play_pause(self) -> None:
        await (self.async_media_pause() if self.state == MediaPlayerState.PLAYING else self.async_media_play())

    async def async_media_stop(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.STOP, ROUTE_PLAYBACK, "media_stop", prefer_cast=True)

    async def async_media_previous_track(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.PREVIOUS_TRACK, ROUTE_PLAYBACK, "media_previous_track", prefer_cast=True)

    async def async_media_next_track(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.NEXT_TRACK, ROUTE_PLAYBACK, "media_next_track", prefer_cast=True)

    async def async_media_seek(self, position: float) -> None:
        await self._call_feature(MediaPlayerEntityFeature.SEEK, ROUTE_SEEK, "media_seek", {"seek_position": position}, prefer_cast=True)

    async def async_seek_relative(self, seconds: float) -> None:
        state = self._active_state()
        position = _live_position(state)
        if position is None:
            return
        target = max(0.0, position + seconds)
        duration = state.attributes.get("media_duration") if state else None
        if isinstance(duration, (int, float)) and duration > 0:
            target = min(target, float(duration))
        await self.async_media_seek(target)

    async def async_set_volume_level(self, volume: float) -> None:
        await self._call_feature(MediaPlayerEntityFeature.VOLUME_SET, ROUTE_VOLUME, "volume_set", {"volume_level": volume})

    async def async_mute_volume(self, mute: bool) -> None:
        await self._call_feature(MediaPlayerEntityFeature.VOLUME_MUTE, ROUTE_VOLUME, "volume_mute", {"is_volume_muted": mute})

    async def async_volume_up(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.VOLUME_STEP, ROUTE_VOLUME, "volume_up")

    async def async_volume_down(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.VOLUME_STEP, ROUTE_VOLUME, "volume_down")

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self._call_feature(MediaPlayerEntityFeature.SHUFFLE_SET, ROUTE_PLAYBACK, "shuffle_set", {"shuffle": shuffle}, prefer_cast=True)

    async def async_set_repeat(self, repeat: str) -> None:
        await self._call_feature(MediaPlayerEntityFeature.REPEAT_SET, ROUTE_PLAYBACK, "repeat_set", {"repeat": repeat}, prefer_cast=True)

    async def async_send_command(self, command: str) -> None:
        source_ids = self.group.source_ids
        routed = self.runtime.route_source(self.group, ROUTE_NAVIGATION)
        if routed:
            source_ids = (routed,)
        await self.runtime.manager.send_command(source_ids, command)

    async def async_restart(self) -> None:
        source_ids = self.group.source_ids
        routed = self.runtime.route_source(self.group, ROUTE_RESTART)
        if routed:
            source_ids = (routed,)
        restart_entity = self.runtime.manager.restart_button_entity_id(source_ids)
        if restart_entity:
            await self.hass.services.async_call(BUTTON_DOMAIN, "press", {ATTR_ENTITY_ID: restart_entity}, blocking=True)
            return
        off_target = self._target_for_feature(MediaPlayerEntityFeature.TURN_OFF, ROUTE_POWER)
        on_target = self._target_for_feature(MediaPlayerEntityFeature.TURN_ON, ROUTE_POWER)
        if off_target and on_target:
            await self.runtime.manager.call_media_player(off_target, "turn_off")
            await asyncio.sleep(self.runtime.command_delays(self.group)[CONF_RESTART_DELAY])
            await self.runtime.manager.call_media_player(on_target, "turn_on")
            return
        await self._leave_cast_session()
        if self.runtime.manager.remote_entity_id(source_ids):
            await self.runtime.manager.send_command(source_ids, "HOME")

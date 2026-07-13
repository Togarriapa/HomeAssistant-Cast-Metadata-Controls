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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ANDROID_TV_ADB_DOMAIN,
    ANDROID_TV_REMOTE_DOMAIN,
    BUTTON_DOMAIN,
    CAST_APP_PREFIX,
    INPUT_PREFIX,
    TRANSIENT_APP_MARKERS,
    TV_APP_PREFIX,
    UID_SEPARATOR,
    UID_VERSION,
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
    """Create one controller for every resolved physical group."""
    runtime: IntegrationRuntime = entry.runtime_data
    async_add_entities(
        [UnifiedMediaController(runtime, group) for group in runtime.groups]
    )


class UnifiedMediaController(MediaPlayerEntity):
    """Proxy the best capability from all representations of one physical device."""

    _attr_has_entity_name = True
    _attr_name = "Controller"
    _attr_should_poll = False

    def __init__(self, runtime: IntegrationRuntime, group: PhysicalGroup) -> None:
        self.runtime = runtime
        self.group = group
        self._attr_unique_id = UID_SEPARATOR.join(
            (UID_VERSION, group.key, "media_player", "controller")
        )
        self._attr_device_info = runtime.device_info(group)
        if group.is_tv:
            self._attr_device_class = MediaPlayerDeviceClass.TV
        self._attr_icon = "mdi:television" if group.is_tv else "mdi:cast-connected"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        for source_id in self.group.source_ids:
            self.async_on_remove(
                self.runtime.manager.async_subscribe_source(
                    source_id, self._async_source_updated
                )
            )
        if self.entity_id:
            self.runtime.register_controller(self.entity_id, self)

    async def async_will_remove_from_hass(self) -> None:
        if self.entity_id:
            self.runtime.unregister_controller(self.entity_id)
        await super().async_will_remove_from_hass()

    @callback
    def _async_source_updated(
        self, source_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        if self.entity_id:
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return any(
            self.runtime.manager.available(source_id)
            for source_id in self.group.source_ids
        )

    def _source_ids(self, *, cast: bool | None = None) -> tuple[str, ...]:
        result: list[str] = []
        for source_id in self.group.source_ids:
            source = self.runtime.manager.get_source(source_id)
            if source is None:
                continue
            if cast is None or source.is_cast is cast:
                result.append(source_id)
        return tuple(result)

    def _active_cast_source(self) -> str | None:
        for source_id in self._source_ids(cast=True):
            state = self.runtime.manager.get_state(source_id)
            if state is None or state.state in {"off", "unavailable", "unknown"}:
                continue
            if state.state in {"playing", "paused", "buffering"}:
                return source_id
            if state.attributes.get("media_title") is not None:
                return source_id
        return None

    def _primary_native_source(self) -> str | None:
        native_ids = self._source_ids(cast=False)
        priorities = {
            ANDROID_TV_REMOTE_DOMAIN: 0,
            ANDROID_TV_ADB_DOMAIN: 2,
        }
        candidates = sorted(
            native_ids,
            key=lambda source_id: (
                priorities.get(self.runtime.manager.platform(source_id), 1),
                self.runtime.manager.get_entity_id(source_id) or source_id,
            ),
        )
        return next(
            (
                source_id
                for source_id in candidates
                if self.runtime.manager.available(source_id)
            ),
            candidates[0] if candidates else None,
        )

    def _active_state(self) -> State | None:
        active_cast = self._active_cast_source()
        if active_cast:
            return self.runtime.manager.get_state(active_cast)
        primary = self._primary_native_source() or self.group.primary_source_id
        return self.runtime.manager.get_state(primary)

    def _target_for_feature(
        self, feature: MediaPlayerEntityFeature, *, prefer_cast: bool = False
    ) -> str | None:
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
            if self.runtime.manager.available(
                source_id
            ) and self.runtime.manager.supports(source_id, feature):
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
        return result

    @property
    def volume_level(self) -> float | None:
        state = self._active_state()
        value = state.attributes.get("volume_level") if state else None
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def is_volume_muted(self) -> bool | None:
        state = self._active_state()
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
        return self._string_attribute("entity_picture")

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

    def _source_actions(self) -> dict[str, SourceAction]:
        actions: dict[str, SourceAction] = {}
        native_names: set[str] = set()

        for source_id in self._source_ids(cast=False):
            if self.runtime.manager.platform(source_id) != ANDROID_TV_REMOTE_DOMAIN:
                continue
            apps = self.runtime.manager.tv_apps(source_id)
            counts = Counter(apps.values())
            for app_id, name in sorted(
                apps.items(), key=lambda item: item[1].casefold()
            ):
                if _is_transient_app(name):
                    continue
                option = f"{TV_APP_PREFIX}{name}"
                if counts[name] > 1 or option in actions:
                    option = f"{option} [{app_id}]"
                actions[option] = SourceAction("tv_app", source_id, app_id)
                native_names.add(name.casefold().strip())

        for source_id in self._source_ids(cast=False):
            platform = self.runtime.manager.platform(source_id)
            for native_source in self.runtime.manager.sources(source_id):
                normalized = native_source.casefold().strip()
                if not normalized or _is_transient_app(native_source):
                    continue
                if platform == ANDROID_TV_ADB_DOMAIN:
                    if normalized in native_names:
                        continue
                    actions.setdefault(
                        f"{TV_APP_PREFIX}{native_source}",
                        SourceAction("adb_app", source_id, native_source),
                    )
                elif platform != ANDROID_TV_REMOTE_DOMAIN:
                    actions.setdefault(
                        f"{INPUT_PREFIX}{native_source}",
                        SourceAction("input", source_id, native_source),
                    )

        for source_id in self._source_ids(cast=True):
            apps = self.runtime.manager.cast_apps(source_id)
            counts = Counter(apps.values())
            for app_id, name in sorted(
                apps.items(), key=lambda item: item[1].casefold()
            ):
                option = f"{CAST_APP_PREFIX}{name}"
                if counts[name] > 1 or option in actions:
                    option = f"{option} [{app_id}]"
                actions[option] = SourceAction("cast_app", source_id, app_id)

        return actions

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
                    if (
                        action.kind == "cast_app"
                        and action.source_id == active_cast
                        and action.value == app_id
                    ):
                        return option

        for source_id in self._source_ids(cast=False):
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
                if (
                    action.kind in {"adb_app", "input"}
                    and action.value == current_source
                ):
                    return option
        return None

    async def _leave_cast_session(self) -> None:
        remote_available = self.runtime.manager.remote_entity_id(self.group.source_ids)
        if remote_available:
            await self.runtime.manager.send_command(self.group.source_ids, "HOME")
        for source_id in self._source_ids(cast=True):
            if self.runtime.manager.supports(source_id, MediaPlayerEntityFeature.STOP):
                await self.runtime.manager.call_media_player(source_id, "media_stop")
        if remote_available:
            await asyncio.sleep(0.75)

    async def async_select_source(self, source: str) -> None:
        action = self._source_actions()[source]
        if action.kind == "cast_app":
            power_target = self._target_for_feature(MediaPlayerEntityFeature.TURN_ON)
            if power_target and self.state == MediaPlayerState.OFF:
                await self.runtime.manager.call_media_player(power_target, "turn_on")
                await asyncio.sleep(0.8)
            await self.runtime.manager.launch_cast_app(action.source_id, action.value)
            return

        await self._leave_cast_session()
        if action.kind == "tv_app":
            await self.runtime.manager.launch_tv_app(action.source_id, action.value)
            await asyncio.sleep(1.25)
            state = self.runtime.manager.get_state(action.source_id)
            if state is not None and state.attributes.get("app_id") != action.value:
                await self.runtime.manager.send_command(self.group.source_ids, "HOME")
                await asyncio.sleep(0.5)
                await self.runtime.manager.launch_tv_app(action.source_id, action.value)
            return
        await self.runtime.manager.call_media_player(
            action.source_id, "select_source", {"source": action.value}
        )

    async def _call_feature(
        self,
        feature: MediaPlayerEntityFeature,
        service: str,
        data: dict[str, Any] | None = None,
        *,
        prefer_cast: bool = False,
    ) -> None:
        target = self._target_for_feature(feature, prefer_cast=prefer_cast)
        if target:
            await self.runtime.manager.call_media_player(target, service, data)

    async def async_turn_on(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.TURN_ON, "turn_on")

    async def async_turn_off(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.TURN_OFF, "turn_off")

    async def async_media_play(self) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.PLAY, "media_play", prefer_cast=True
        )

    async def async_media_pause(self) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.PAUSE, "media_pause", prefer_cast=True
        )

    async def async_media_play_pause(self) -> None:
        if self.state == MediaPlayerState.PLAYING:
            await self.async_media_pause()
        else:
            await self.async_media_play()

    async def async_media_stop(self) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.STOP, "media_stop", prefer_cast=True
        )

    async def async_media_previous_track(self) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.PREVIOUS_TRACK,
            "media_previous_track",
            prefer_cast=True,
        )

    async def async_media_next_track(self) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.NEXT_TRACK, "media_next_track", prefer_cast=True
        )

    async def async_media_seek(self, position: float) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.SEEK,
            "media_seek",
            {"seek_position": position},
            prefer_cast=True,
        )

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
        await self._call_feature(
            MediaPlayerEntityFeature.VOLUME_SET,
            "volume_set",
            {"volume_level": volume},
        )

    async def async_mute_volume(self, mute: bool) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.VOLUME_MUTE,
            "volume_mute",
            {"is_volume_muted": mute},
        )

    async def async_volume_up(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.VOLUME_STEP, "volume_up")

    async def async_volume_down(self) -> None:
        await self._call_feature(MediaPlayerEntityFeature.VOLUME_STEP, "volume_down")

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.SHUFFLE_SET,
            "shuffle_set",
            {"shuffle": shuffle},
            prefer_cast=True,
        )

    async def async_set_repeat(self, repeat: str) -> None:
        await self._call_feature(
            MediaPlayerEntityFeature.REPEAT_SET,
            "repeat_set",
            {"repeat": repeat},
            prefer_cast=True,
        )

    async def async_send_command(self, command: str) -> None:
        await self.runtime.manager.send_command(self.group.source_ids, command)

    async def async_restart(self) -> None:
        restart_entity = self.runtime.manager.restart_button_entity_id(
            self.group.source_ids
        )
        if restart_entity:
            await self.hass.services.async_call(
                BUTTON_DOMAIN,
                "press",
                {ATTR_ENTITY_ID: restart_entity},
                blocking=True,
            )
            return

        off_target = self._target_for_feature(MediaPlayerEntityFeature.TURN_OFF)
        on_target = self._target_for_feature(MediaPlayerEntityFeature.TURN_ON)
        if off_target and on_target:
            await self.runtime.manager.call_media_player(off_target, "turn_off")
            await asyncio.sleep(2)
            await self.runtime.manager.call_media_player(on_target, "turn_on")
            return

        await self._leave_cast_session()
        if self.runtime.manager.remote_entity_id(self.group.source_ids):
            await self.runtime.manager.send_command(self.group.source_ids, "HOME")

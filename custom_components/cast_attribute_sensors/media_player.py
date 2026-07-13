"""Compact Cast and TV controller media-player entities."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
import re

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import State, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ANDROID_TV_ADB_DOMAIN,
    ANDROID_TV_REMOTE_DOMAIN,
    UID_SEPARATOR,
    UID_VERSION,
)
from .entity import CastLinkedEntity
from .manager import CastManager
from .tv_entity import TvLinkedEntity
from .tv_manager import TvManager

TV_APP_PREFIX = "TV App · "
CAST_APP_PREFIX = "Cast · "
INPUT_PREFIX = "Input · "
PROXIED_FEATURES = (
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
)
_GENERIC_NAMES = {"tv", "television", "androidtv", "googletv", "chromecast", "cast"}
_CAST_ONLY_SOURCE_MARKERS = ("ready to cast", "cast receiver", "chromecast built-in")


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one compact controller per physical TV or standalone Cast device."""
    cast_manager: CastManager = entry.runtime_data.manager
    tv_manager: TvManager = entry.runtime_data.tv_manager
    added_tv_sources: set[str] = set()
    added_cast_sources: set[str] = set()

    @callback
    def add_current_controllers(*_args) -> None:
        primary_tv_sources = _primary_tv_source_ids(tv_manager)
        entities: list[MediaPlayerEntity] = []

        for source_id in primary_tv_sources:
            if source_id in added_tv_sources:
                continue
            added_tv_sources.add(source_id)
            entities.append(TvControllerMediaPlayer(tv_manager, cast_manager, source_id))

        for cast_source_id in cast_manager.source_ids:
            if cast_source_id in added_cast_sources:
                continue
            if any(
                cast_source_id
                in _matching_cast_source_ids(cast_manager, tv_manager, tv_source_id)
                for tv_source_id in primary_tv_sources
            ):
                continue
            added_cast_sources.add(cast_source_id)
            entities.append(CastControllerMediaPlayer(cast_manager, cast_source_id))

        if entities:
            async_add_entities(entities)

    add_current_controllers()
    entry.async_on_unload(
        tv_manager.async_subscribe_source_added(add_current_controllers)
    )
    entry.async_on_unload(
        cast_manager.async_subscribe_source_added(add_current_controllers)
    )


def _registry_entry(manager, source_registry_id: str):
    entity_id = manager.get_source_entity_id(source_registry_id)
    return manager._entity_registry.async_get(entity_id) if entity_id else None


def _normalized_name(manager, source_registry_id: str) -> str:
    state = manager.get_source_state(source_registry_id)
    name = str(state.attributes.get("friendly_name", "")) if state else ""
    name = re.sub(
        r"\b(android tv remote|google tv remote|remote|controller|media player|adb)\b",
        " ",
        name,
        flags=re.IGNORECASE,
    )
    return "".join(character for character in name.casefold() if character.isalnum())


def _device_signature(manager, source_registry_id: str):
    registry_entry = _registry_entry(manager, source_registry_id)
    if registry_entry is None or registry_entry.device_id is None:
        return None, frozenset(), None
    device = dr.async_get(manager.hass).async_get(registry_entry.device_id)
    if device is None:
        return registry_entry.device_id, frozenset(), None
    return registry_entry.device_id, frozenset(device.connections), device.area_id


def _same_physical_device(
    first_manager,
    first_source_id: str,
    second_manager,
    second_source_id: str,
) -> bool:
    first_device_id, first_connections, first_area = _device_signature(
        first_manager, first_source_id
    )
    second_device_id, second_connections, second_area = _device_signature(
        second_manager, second_source_id
    )
    if first_device_id and first_device_id == second_device_id:
        return True
    if first_connections and second_connections and first_connections & second_connections:
        return True

    first_name = _normalized_name(first_manager, first_source_id)
    second_name = _normalized_name(second_manager, second_source_id)
    if (
        not first_name
        or first_name != second_name
        or first_name in _GENERIC_NAMES
        or (first_area and second_area and first_area != second_area)
    ):
        return False
    return True


def _tv_source_groups(manager: TvManager) -> list[list[str]]:
    groups: list[list[str]] = []
    for source_id in manager.source_ids:
        for group in groups:
            if any(
                _same_physical_device(manager, source_id, manager, member)
                for member in group
            ):
                group.append(source_id)
                break
        else:
            groups.append([source_id])
    return groups


def _source_priority(manager: TvManager, source_id: str) -> tuple[int, str]:
    platform = manager.get_source_platform(source_id)
    if platform == ANDROID_TV_REMOTE_DOMAIN:
        priority = 0
    elif platform == ANDROID_TV_ADB_DOMAIN:
        priority = 2
    else:
        priority = 1
    return priority, manager.get_source_entity_id(source_id) or source_id


def _primary_tv_source_ids(manager: TvManager) -> tuple[str, ...]:
    return tuple(
        min(group, key=lambda source_id: _source_priority(manager, source_id))
        for group in _tv_source_groups(manager)
    )


def _tv_group_source_ids(manager: TvManager, primary_source_id: str) -> tuple[str, ...]:
    for group in _tv_source_groups(manager):
        if primary_source_id in group:
            return tuple(group)
    return (primary_source_id,)


def _matching_cast_source_ids(
    cast_manager: CastManager,
    tv_manager: TvManager,
    primary_tv_source_id: str,
) -> tuple[str, ...]:
    tv_sources = _tv_group_source_ids(tv_manager, primary_tv_source_id)
    return tuple(
        cast_source_id
        for cast_source_id in cast_manager.source_ids
        if any(
            _same_physical_device(
                cast_manager, cast_source_id, tv_manager, tv_source_id
            )
            for tv_source_id in tv_sources
        )
    )


def _media_state(value: str | None) -> MediaPlayerState | None:
    if value is None:
        return None
    try:
        return MediaPlayerState(value)
    except ValueError:
        return None


def _supported_features(state: State | None) -> MediaPlayerEntityFeature:
    value = state.attributes.get("supported_features", 0) if state else 0
    native = MediaPlayerEntityFeature(value if isinstance(value, int) else 0)
    return native & PROXIED_FEATURES


def _live_position(state: State | None) -> float | None:
    """Return playback position corrected for elapsed time since its last update."""
    if state is None:
        return None
    position = state.attributes.get("media_position")
    if not isinstance(position, (int, float)):
        return None
    result = float(position)
    updated_at = state.attributes.get("media_position_updated_at")
    if state.state == MediaPlayerState.PLAYING and updated_at is not None:
        parsed: datetime | None
        if isinstance(updated_at, datetime):
            parsed = updated_at
        elif isinstance(updated_at, str):
            parsed = dt_util.parse_datetime(updated_at)
        else:
            parsed = None
        if parsed is not None:
            result += max(0.0, (dt_util.utcnow() - parsed).total_seconds())
    duration = state.attributes.get("media_duration")
    if isinstance(duration, (int, float)) and duration > 0:
        result = min(result, float(duration))
    return max(0.0, result)


class _MediaProperties:
    """Properties shared by compact proxy media players."""

    def _source_state(self) -> State | None:
        raise NotImplementedError

    @property
    def state(self) -> MediaPlayerState | None:
        state = self._source_state()
        return _media_state(state.state if state else None)

    @property
    def volume_level(self) -> float | None:
        state = self._source_state()
        value = state.attributes.get("volume_level") if state else None
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def is_volume_muted(self) -> bool | None:
        state = self._source_state()
        value = state.attributes.get("is_volume_muted") if state else None
        return value if isinstance(value, bool) else None

    @property
    def media_content_id(self) -> str | None:
        state = self._source_state()
        value = state.attributes.get("media_content_id") if state else None
        return str(value) if value is not None else None

    @property
    def media_content_type(self) -> str | None:
        state = self._source_state()
        value = state.attributes.get("media_content_type") if state else None
        return str(value) if value is not None else None

    @property
    def media_duration(self) -> float | None:
        state = self._source_state()
        value = state.attributes.get("media_duration") if state else None
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def media_position(self) -> float | None:
        return _live_position(self._source_state())

    @property
    def media_position_updated_at(self) -> datetime | None:
        state = self._source_state()
        value = state.attributes.get("media_position_updated_at") if state else None
        if isinstance(value, datetime):
            return value
        return dt_util.parse_datetime(value) if isinstance(value, str) else None

    @property
    def media_title(self) -> str | None:
        state = self._source_state()
        value = state.attributes.get("media_title") if state else None
        return str(value) if value is not None else None

    @property
    def media_artist(self) -> str | None:
        state = self._source_state()
        value = state.attributes.get("media_artist") if state else None
        return str(value) if value is not None else None

    @property
    def media_album_name(self) -> str | None:
        state = self._source_state()
        value = state.attributes.get("media_album_name") if state else None
        return str(value) if value is not None else None

    @property
    def app_id(self) -> str | None:
        state = self._source_state()
        value = state.attributes.get("app_id") if state else None
        return str(value) if value is not None else None

    @property
    def app_name(self) -> str | None:
        state = self._source_state()
        value = state.attributes.get("app_name") if state else None
        return str(value) if value is not None else None

    @property
    def media_image_url(self) -> str | None:
        state = self._source_state()
        value = state.attributes.get("entity_picture") if state else None
        return str(value) if value is not None else None


class CastControllerMediaPlayer(_MediaProperties, CastLinkedEntity, MediaPlayerEntity):
    """Single compact entity for a standalone native Cast source."""

    _attr_name = "Controller"
    _attr_icon = "mdi:cast-connected"

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "media_player", "controller")
        )
        super().__init__(manager, source_registry_id, unique_id)

    def _source_state(self) -> State | None:
        return self._manager.get_source_state(self._source_registry_id)

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = _supported_features(self._source_state())
        if self.source_list:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        return features

    def _app_maps(self) -> tuple[dict[str, str], dict[str, str]]:
        apps = self._manager.get_apps(self._source_registry_id)
        counts = Counter(apps.values())
        option_to_id: dict[str, str] = {}
        id_to_option: dict[str, str] = {}
        for app_id, name in sorted(apps.items(), key=lambda item: item[1].casefold()):
            option = name if counts[name] == 1 else f"{name} [{app_id}]"
            option_to_id[option] = app_id
            id_to_option[app_id] = option
        return option_to_id, id_to_option

    @property
    def source_list(self) -> list[str]:
        return list(self._app_maps()[0])

    @property
    def source(self) -> str | None:
        state = self._source_state()
        app_id = state.attributes.get("app_id") if state else None
        return self._app_maps()[1].get(app_id) if isinstance(app_id, str) else None

    async def async_select_source(self, source: str) -> None:
        await self._manager.async_launch_app(
            self._source_registry_id, self._app_maps()[0][source]
        )

    async def async_turn_on(self) -> None:
        await self._manager.async_call_media_player(self._source_registry_id, "turn_on")

    async def async_turn_off(self) -> None:
        await self._manager.async_call_media_player(self._source_registry_id, "turn_off")

    async def async_media_play(self) -> None:
        await self._manager.async_call_media_player(self._source_registry_id, "media_play")

    async def async_media_pause(self) -> None:
        await self._manager.async_call_media_player(self._source_registry_id, "media_pause")

    async def async_media_play_pause(self) -> None:
        service = "media_pause" if self.state == MediaPlayerState.PLAYING else "media_play"
        await self._manager.async_call_media_player(self._source_registry_id, service)

    async def async_media_stop(self) -> None:
        await self._manager.async_call_media_player(self._source_registry_id, "media_stop")

    async def async_media_previous_track(self) -> None:
        await self._manager.async_call_media_player(
            self._source_registry_id, "media_previous_track"
        )

    async def async_media_next_track(self) -> None:
        await self._manager.async_call_media_player(
            self._source_registry_id, "media_next_track"
        )

    async def async_media_seek(self, position: float) -> None:
        await self._manager.async_call_media_player(
            self._source_registry_id, "media_seek", {"seek_position": position}
        )

    async def async_set_volume_level(self, volume: float) -> None:
        await self._manager.async_call_media_player(
            self._source_registry_id, "volume_set", {"volume_level": volume}
        )

    async def async_mute_volume(self, mute: bool) -> None:
        await self._manager.async_call_media_player(
            self._source_registry_id, "volume_mute", {"is_volume_muted": mute}
        )

    async def async_volume_up(self) -> None:
        await self._manager.async_call_media_player(self._source_registry_id, "volume_up")

    async def async_volume_down(self) -> None:
        await self._manager.async_call_media_player(
            self._source_registry_id, "volume_down"
        )


class TvControllerMediaPlayer(_MediaProperties, TvLinkedEntity, MediaPlayerEntity):
    """One composite controller for all entities belonging to a physical TV."""

    _attr_name = "Controller"
    _attr_icon = "mdi:television"
    _attr_device_class = MediaPlayerDeviceClass.TV

    def __init__(
        self,
        manager: TvManager,
        cast_manager: CastManager,
        source_registry_id: str,
    ) -> None:
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "media_player", "tv_controller")
        )
        super().__init__(manager, source_registry_id, unique_id)
        self._cast_manager = cast_manager

    @property
    def _tv_source_ids(self) -> tuple[str, ...]:
        return _tv_group_source_ids(self._manager, self._source_registry_id)

    @property
    def _cast_source_ids(self) -> tuple[str, ...]:
        return _matching_cast_source_ids(
            self._cast_manager, self._manager, self._source_registry_id
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        for source_id in self._tv_source_ids:
            if source_id == self._source_registry_id:
                continue
            self.async_on_remove(
                self._manager.async_subscribe_source(source_id, self._async_related_event)
            )
        for source_id in self._cast_source_ids:
            self.async_on_remove(
                self._cast_manager.async_subscribe_source(
                    source_id, self._async_related_event
                )
            )

    @callback
    def _async_related_event(
        self, source_registry_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        if self.entity_id is not None:
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return any(
            self._manager.source_available(source_id)
            for source_id in self._tv_source_ids
        ) or any(
            self._cast_manager.source_available(source_id)
            for source_id in self._cast_source_ids
        )

    def _active_cast_source_id(self) -> str | None:
        for source_id in self._cast_source_ids:
            state = self._cast_manager.get_source_state(source_id)
            if state is None or state.state in {"off", "unavailable", "unknown"}:
                continue
            if state.attributes.get("app_id") or state.state in {"playing", "paused"}:
                return source_id
        return None

    def _primary_tv_state(self) -> State | None:
        for source_id in sorted(
            self._tv_source_ids, key=lambda item: _source_priority(self._manager, item)
        ):
            state = self._manager.get_source_state(source_id)
            if state is not None and state.state != "unavailable":
                return state
        return self._manager.get_source_state(self._source_registry_id)

    def _source_state(self) -> State | None:
        active_cast = self._active_cast_source_id()
        if active_cast is not None:
            cast_state = self._cast_manager.get_source_state(active_cast)
            if cast_state is not None and (
                cast_state.state in {"playing", "paused"}
                or cast_state.attributes.get("media_title") is not None
            ):
                return cast_state
        return self._primary_tv_state()

    def _tv_source_for_feature(
        self, feature: MediaPlayerEntityFeature
    ) -> str | None:
        for source_id in sorted(
            self._tv_source_ids, key=lambda item: _source_priority(self._manager, item)
        ):
            if self._manager.source_available(source_id) and self._manager.source_supports(
                source_id, feature
            ):
                return source_id
        return None

    def _playback_target(
        self, feature: MediaPlayerEntityFeature
    ) -> tuple[object, str] | None:
        active_cast = self._active_cast_source_id()
        if active_cast is not None and self._cast_manager.source_supports(
            active_cast, feature
        ):
            return self._cast_manager, active_cast
        tv_source = self._tv_source_for_feature(feature)
        return (self._manager, tv_source) if tv_source is not None else None

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = MediaPlayerEntityFeature(0)
        for source_id in self._tv_source_ids:
            features |= _supported_features(self._manager.get_source_state(source_id))
        active_cast = self._active_cast_source_id()
        if active_cast is not None:
            features |= _supported_features(
                self._cast_manager.get_source_state(active_cast)
            )
        if self.source_list:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        return features & (PROXIED_FEATURES | MediaPlayerEntityFeature.SELECT_SOURCE)

    def _remote_source_id(self) -> str | None:
        return next(
            (
                source_id
                for source_id in self._tv_source_ids
                if self._manager.get_source_platform(source_id)
                == ANDROID_TV_REMOTE_DOMAIN
            ),
            None,
        )

    def _source_actions(self) -> dict[str, tuple[str, str, str]]:
        """Return option -> (mechanism, source_registry_id, app/input value)."""
        result: dict[str, tuple[str, str, str]] = {}
        tv_app_names: set[str] = set()

        for source_id in self._tv_source_ids:
            if self._manager.get_source_platform(source_id) != ANDROID_TV_REMOTE_DOMAIN:
                continue
            for app_id, name in sorted(
                self._manager.get_apps(source_id).items(),
                key=lambda item: item[1].casefold(),
            ):
                option = f"{TV_APP_PREFIX}{name}"
                if option in result:
                    option = f"{option} [{app_id}]"
                result[option] = ("tv_app", source_id, app_id)
                tv_app_names.add(name.casefold())

        for source_id in self._tv_source_ids:
            platform = self._manager.get_source_platform(source_id)
            sources = self._manager.get_sources(source_id)
            if platform == ANDROID_TV_ADB_DOMAIN:
                for source in sources:
                    normalized = source.casefold().strip()
                    if (
                        not normalized
                        or normalized in tv_app_names
                        or any(marker in normalized for marker in _CAST_ONLY_SOURCE_MARKERS)
                    ):
                        continue
                    result.setdefault(
                        f"{TV_APP_PREFIX}{source}",
                        ("adb_app", source_id, source),
                    )
            elif platform != ANDROID_TV_REMOTE_DOMAIN:
                for source in sources:
                    result.setdefault(
                        f"{INPUT_PREFIX}{source}",
                        ("tv_input", source_id, source),
                    )

        for cast_source_id in self._cast_source_ids:
            for app_id, name in sorted(
                self._cast_manager.get_apps(cast_source_id).items(),
                key=lambda item: item[1].casefold(),
            ):
                option = f"{CAST_APP_PREFIX}{name}"
                if option in result:
                    option = f"{option} [{app_id}]"
                result[option] = ("cast_app", cast_source_id, app_id)

        return result

    @property
    def source_list(self) -> list[str]:
        return list(self._source_actions())

    @property
    def source(self) -> str | None:
        actions = self._source_actions()
        active_cast = self._active_cast_source_id()
        if active_cast is not None:
            state = self._cast_manager.get_source_state(active_cast)
            app_id = state.attributes.get("app_id") if state else None
            if isinstance(app_id, str):
                for option, (kind, source_id, value) in actions.items():
                    if kind == "cast_app" and source_id == active_cast and value == app_id:
                        return option

        for source_id in self._tv_source_ids:
            state = self._manager.get_source_state(source_id)
            if state is None:
                continue
            app_id = state.attributes.get("app_id")
            source = state.attributes.get("source")
            for option, (kind, action_source_id, value) in actions.items():
                if action_source_id != source_id:
                    continue
                if kind == "tv_app" and isinstance(app_id, str) and value == app_id:
                    return option
                if kind in {"adb_app", "tv_input"} and value == source:
                    return option
        return None

    async def _async_leave_cast_session(self) -> None:
        """Return the TV to Home before launching a local app or input."""
        remote_source = self._remote_source_id()
        if remote_source is not None:
            await self._manager.async_send_remote_command(remote_source, "HOME")
            await asyncio.sleep(0.35)
            return
        for cast_source_id in self._cast_source_ids:
            state = self._cast_manager.get_source_state(cast_source_id)
            if state is None or state.state in {"off", "unavailable", "unknown"}:
                continue
            if self._cast_manager.source_supports(
                cast_source_id, MediaPlayerEntityFeature.STOP
            ):
                await self._cast_manager.async_call_media_player(
                    cast_source_id, "media_stop"
                )

    async def async_select_source(self, source: str) -> None:
        kind, source_id, value = self._source_actions()[source]
        if kind == "cast_app":
            await self._cast_manager.async_launch_app(source_id, value)
            return

        await self._async_leave_cast_session()
        if kind == "tv_app":
            await self._manager.async_launch_app(source_id, value)
        else:
            await self._manager.async_call_media_player(
                source_id, "select_source", {"source": value}
            )

    async def async_turn_on(self) -> None:
        source_id = self._tv_source_for_feature(MediaPlayerEntityFeature.TURN_ON)
        if source_id is not None:
            await self._manager.async_call_media_player(source_id, "turn_on")

    async def async_turn_off(self) -> None:
        source_id = self._tv_source_for_feature(MediaPlayerEntityFeature.TURN_OFF)
        if source_id is not None:
            await self._manager.async_call_media_player(source_id, "turn_off")

    async def _async_playback_service(
        self, feature: MediaPlayerEntityFeature, service: str, data=None
    ) -> None:
        target = self._playback_target(feature)
        if target is None:
            return
        manager, source_id = target
        await manager.async_call_media_player(source_id, service, data)

    async def async_media_play(self) -> None:
        await self._async_playback_service(
            MediaPlayerEntityFeature.PLAY, "media_play"
        )

    async def async_media_pause(self) -> None:
        await self._async_playback_service(
            MediaPlayerEntityFeature.PAUSE, "media_pause"
        )

    async def async_media_play_pause(self) -> None:
        if self.state == MediaPlayerState.PLAYING:
            await self.async_media_pause()
        else:
            await self.async_media_play()

    async def async_media_stop(self) -> None:
        await self._async_playback_service(
            MediaPlayerEntityFeature.STOP, "media_stop"
        )

    async def async_media_previous_track(self) -> None:
        await self._async_playback_service(
            MediaPlayerEntityFeature.PREVIOUS_TRACK, "media_previous_track"
        )

    async def async_media_next_track(self) -> None:
        await self._async_playback_service(
            MediaPlayerEntityFeature.NEXT_TRACK, "media_next_track"
        )

    async def async_media_seek(self, position: float) -> None:
        await self._async_playback_service(
            MediaPlayerEntityFeature.SEEK,
            "media_seek",
            {"seek_position": position},
        )

    async def async_set_volume_level(self, volume: float) -> None:
        source_id = self._tv_source_for_feature(MediaPlayerEntityFeature.VOLUME_SET)
        if source_id is not None:
            await self._manager.async_call_media_player(
                source_id, "volume_set", {"volume_level": volume}
            )

    async def async_mute_volume(self, mute: bool) -> None:
        source_id = self._tv_source_for_feature(MediaPlayerEntityFeature.VOLUME_MUTE)
        if source_id is not None:
            await self._manager.async_call_media_player(
                source_id, "volume_mute", {"is_volume_muted": mute}
            )

    async def async_volume_up(self) -> None:
        source_id = self._tv_source_for_feature(MediaPlayerEntityFeature.VOLUME_STEP)
        if source_id is not None:
            await self._manager.async_call_media_player(source_id, "volume_up")

    async def async_volume_down(self) -> None:
        source_id = self._tv_source_for_feature(MediaPlayerEntityFeature.VOLUME_STEP)
        if source_id is not None:
            await self._manager.async_call_media_player(source_id, "volume_down")

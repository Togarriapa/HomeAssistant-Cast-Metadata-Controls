"""Compact Cast and TV controller media-player entities."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import ANDROID_TV_ADB_DOMAIN, UID_SEPARATOR, UID_VERSION
from .entity import CastLinkedEntity
from .manager import CastManager
from .platform import setup_source_entities
from .tv_entity import TvLinkedEntity
from .tv_manager import TvManager
from .tv_platform import setup_tv_entities

APP_PREFIX = "App · "
INPUT_PREFIX = "Input · "


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one compact controller entity per Cast and TV source."""
    cast_manager: CastManager = entry.runtime_data.manager
    tv_manager: TvManager = entry.runtime_data.tv_manager
    setup_source_entities(
        entry, cast_manager, async_add_entities, _make_cast_controller
    )
    setup_tv_entities(entry, tv_manager, async_add_entities, _make_tv_controller)


def _make_cast_controller(
    manager: CastManager, source_registry_id: str
) -> list[MediaPlayerEntity]:
    return [CastControllerMediaPlayer(manager, source_registry_id)]


def _make_tv_controller(
    manager: TvManager, source_registry_id: str
) -> list[MediaPlayerEntity]:
    return [TvControllerMediaPlayer(manager, source_registry_id)]


def _media_state(value: str | None) -> MediaPlayerState | None:
    if value is None:
        return None
    try:
        return MediaPlayerState(value)
    except ValueError:
        return None


def _supported_features(state) -> MediaPlayerEntityFeature:
    value = state.attributes.get("supported_features", 0) if state else 0
    return MediaPlayerEntityFeature(value if isinstance(value, int) else 0)


def _live_position(state) -> float | None:
    """Return playback position corrected for time elapsed since the last update."""
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
    """Properties shared by the compact proxy media players."""

    def _source_state(self):
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
    """Single compact entity for one native Cast source."""

    _attr_name = "Controller"
    _attr_icon = "mdi:cast-connected"

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "media_player", "controller")
        )
        super().__init__(manager, source_registry_id, unique_id)

    def _source_state(self):
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
    """Single compact entity for power, apps, inputs and playback on one TV."""

    _attr_name = "Controller"
    _attr_icon = "mdi:television"
    _attr_device_class = MediaPlayerDeviceClass.TV

    def __init__(self, manager: TvManager, source_registry_id: str) -> None:
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "media_player", "tv_controller")
        )
        super().__init__(manager, source_registry_id, unique_id)

    def _source_state(self):
        return self._manager.get_source_state(self._source_registry_id)

    def _normalized_name(self, source_registry_id: str) -> str:
        state = self._manager.get_source_state(source_registry_id)
        value = state.attributes.get("friendly_name") if state else ""
        return "".join(ch for ch in str(value).casefold() if ch.isalnum())

    def _source_actions(self) -> dict[str, tuple[str, str, str]]:
        """Return option -> (kind, source_registry_id, value)."""
        result: dict[str, tuple[str, str, str]] = {}
        apps = self._manager.get_apps(self._source_registry_id)
        for app_id, name in sorted(apps.items(), key=lambda item: item[1].casefold()):
            option = f"{APP_PREFIX}{name}"
            if option in result:
                option = f"{option} [{app_id}]"
            result[option] = ("app", self._source_registry_id, app_id)

        platform = self._manager.get_source_platform(self._source_registry_id)
        sources = self._manager.get_sources(self._source_registry_id)
        if platform == ANDROID_TV_ADB_DOMAIN:
            for source in sources:
                result.setdefault(
                    f"{APP_PREFIX}{source}",
                    ("native_source", self._source_registry_id, source),
                )
        else:
            for source in sources:
                result[f"{INPUT_PREFIX}{source}"] = (
                    "native_source",
                    self._source_registry_id,
                    source,
                )

        own_name = self._normalized_name(self._source_registry_id)
        if own_name:
            for other_id in self._manager.source_ids:
                if (
                    other_id == self._source_registry_id
                    or self._manager.get_source_platform(other_id)
                    != ANDROID_TV_ADB_DOMAIN
                    or self._normalized_name(other_id) != own_name
                ):
                    continue
                for source in self._manager.get_sources(other_id):
                    result.setdefault(
                        f"{APP_PREFIX}{source}",
                        ("native_source", other_id, source),
                    )
        return result

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = _supported_features(self._source_state())
        if self.source_list:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        return features

    @property
    def source_list(self) -> list[str]:
        return list(self._source_actions())

    @property
    def source(self) -> str | None:
        state = self._source_state()
        if state is None:
            return None
        app_id = state.attributes.get("app_id")
        app_name = state.attributes.get("app_name")
        native_source = state.attributes.get("source")
        actions = self._source_actions()
        for option, (kind, source_id, value) in actions.items():
            if source_id != self._source_registry_id:
                continue
            if kind == "app" and isinstance(app_id, str) and value == app_id:
                return option
            if option.startswith(APP_PREFIX) and isinstance(app_name, str):
                if option.removeprefix(APP_PREFIX) == app_name:
                    return option
            if kind == "native_source" and value == native_source:
                return option
        return None

    async def async_select_source(self, source: str) -> None:
        kind, source_id, value = self._source_actions()[source]
        if kind == "app":
            await self._manager.async_launch_app(source_id, value)
        else:
            await self._manager.async_call_media_player(
                source_id, "select_source", {"source": value}
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

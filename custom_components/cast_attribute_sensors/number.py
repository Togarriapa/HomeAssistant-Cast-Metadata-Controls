"""Cast and TV volume plus Cast media-position number entities."""

from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UID_SEPARATOR, UID_VERSION
from .entity import CastLinkedEntity
from .manager import CastManager
from .platform import setup_source_entities
from .tv_entity import TvLinkedEntity
from .tv_manager import TvManager
from .tv_platform import setup_tv_entities


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Cast and TV number controls."""
    cast_manager: CastManager = entry.runtime_data.manager
    tv_manager: TvManager = entry.runtime_data.tv_manager
    setup_source_entities(entry, cast_manager, async_add_entities, _make_cast_numbers)
    setup_tv_entities(entry, tv_manager, async_add_entities, _make_tv_numbers)


def _make_cast_numbers(
    manager: CastManager, source_registry_id: str
) -> list[NumberEntity]:
    return [
        CastVolumeNumber(manager, source_registry_id),
        CastPositionNumber(manager, source_registry_id),
    ]


def _make_tv_numbers(manager: TvManager, source_registry_id: str) -> list[NumberEntity]:
    return [TvVolumeNumber(manager, source_registry_id)]


class CastVolumeNumber(CastLinkedEntity, NumberEntity):
    """Expose Cast volume as a 0-100 percentage slider."""

    _attr_name = "Cast volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        """Initialize the volume slider."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "number", "volume")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether direct volume setting is supported."""
        return super().available and self._manager.source_supports(
            self._source_registry_id, MediaPlayerEntityFeature.VOLUME_SET
        )

    @property
    def native_value(self) -> float | None:
        """Return volume as a percentage."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        volume = state.attributes.get("volume_level")
        if not isinstance(volume, (int, float)):
            return None
        return round(float(volume) * 100, 1)

    async def async_set_native_value(self, value: float) -> None:
        """Set native Cast volume from a percentage."""
        await self._manager.async_call_media_player(
            self._source_registry_id,
            "volume_set",
            {"volume_level": max(0.0, min(1.0, float(value) / 100.0))},
        )


class CastPositionNumber(CastLinkedEntity, NumberEntity):
    """Expose Cast media position as a 0-100 percentage slider."""

    _attr_name = "Cast media position"
    _attr_icon = "mdi:progress-clock"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        """Initialize the media-position slider."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "number", "media_position")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether seeking and duration are available."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return False
        duration = state.attributes.get("media_duration")
        return (
            super().available
            and self._manager.source_supports(
                self._source_registry_id, MediaPlayerEntityFeature.SEEK
            )
            and isinstance(duration, (int, float))
            and duration > 0
        )

    @property
    def native_value(self) -> float | None:
        """Return current media position as a percentage."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        position = state.attributes.get("media_position")
        duration = state.attributes.get("media_duration")
        if not isinstance(position, (int, float)) or not isinstance(
            duration, (int, float)
        ):
            return None
        if duration <= 0:
            return None
        return round(max(0.0, min(100.0, float(position) / float(duration) * 100)), 1)

    async def async_set_native_value(self, value: float) -> None:
        """Seek to a percentage of the current media duration."""
        state = self._manager.get_source_state(self._source_registry_id)
        duration = state.attributes.get("media_duration") if state else None
        if not isinstance(duration, (int, float)) or duration <= 0:
            return
        target = float(duration) * max(0.0, min(100.0, float(value))) / 100.0
        await self._manager.async_call_media_player(
            self._source_registry_id,
            "media_seek",
            {"seek_position": target},
        )


class TvVolumeNumber(TvLinkedEntity, NumberEntity):
    """Expose native TV volume as a 0-100 percentage slider when supported."""

    _attr_name = "TV volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, manager: TvManager, source_registry_id: str) -> None:
        """Initialize the TV volume slider."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "number", "tv_volume")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether direct TV volume setting is supported."""
        return super().available and self._manager.source_supports(
            self._source_registry_id, MediaPlayerEntityFeature.VOLUME_SET
        )

    @property
    def native_value(self) -> float | None:
        """Return native TV volume as a percentage."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        volume = state.attributes.get("volume_level")
        if not isinstance(volume, (int, float)):
            return None
        return round(float(volume) * 100, 1)

    async def async_set_native_value(self, value: float) -> None:
        """Set native TV volume from a percentage."""
        await self._manager.async_call_media_player(
            self._source_registry_id,
            "volume_set",
            {"volume_level": max(0.0, min(1.0, float(value) / 100.0))},
        )

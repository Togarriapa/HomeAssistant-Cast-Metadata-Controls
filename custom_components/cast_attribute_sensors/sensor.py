"""Dynamic metadata sensors for native Cast media players."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DOMAIN,
    KIND_ATTRIBUTE,
    KIND_SNAPSHOT,
    KIND_STATE,
    LEGACY_UID_PREFIXES,
    SENSOR_DOMAIN,
)
from .manager import CastManager
from .util import build_unique_id, humanize, normalize_native_value, parse_unique_id

_MISSING = object()

_ICON_BY_ATTRIBUTE: dict[str, str] = {
    "app_id": "mdi:identifier",
    "app_name": "mdi:application",
    "entity_picture": "mdi:image",
    "friendly_name": "mdi:rename-box",
    "is_volume_muted": "mdi:volume-mute",
    "media_album_artist": "mdi:account-music",
    "media_album_name": "mdi:album",
    "media_artist": "mdi:account-music",
    "media_content_id": "mdi:identifier",
    "media_content_type": "mdi:file-music-outline",
    "media_duration": "mdi:timer-outline",
    "media_episode": "mdi:television-classic",
    "media_image_url": "mdi:image",
    "media_position": "mdi:progress-clock",
    "media_position_updated_at": "mdi:clock-outline",
    "media_season": "mdi:television-classic",
    "media_series_title": "mdi:television-classic",
    "media_title": "mdi:format-title",
    "media_track": "mdi:music-note",
    "supported_features": "mdi:cog-outline",
    "volume_level": "mdi:volume-high",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up dynamic Cast metadata sensors."""
    manager: CastManager = entry.runtime_data.manager
    platform = CastSensorPlatform(hass, entry, manager, async_add_entities)
    platform.async_start()
    entry.async_on_unload(platform.async_stop)


class CastSensorPlatform:
    """Create metadata sensors only after their values first appear."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        manager: CastManager,
        async_add_entities: AddConfigEntryEntitiesCallback,
    ) -> None:
        """Initialize the dynamic sensor platform."""
        self.hass = hass
        self.entry = entry
        self.manager = manager
        self._async_add_entities = async_add_entities
        self._entity_registry = er.async_get(hass)
        self._sensors: dict[str, CastExtractedSensor] = {}
        self._sensor_uids_by_source: dict[str, set[str]] = defaultdict(set)
        self._source_unsubscribers: dict[str, CALLBACK_TYPE] = {}
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._started = False

    @callback
    def async_start(self) -> None:
        """Restore created sensors and begin dynamic metadata discovery."""
        if self._started:
            return
        self._started = True

        self._async_remove_legacy_v1_entities()
        self._async_restore_registered_sensors()

        for source_id in self.manager.source_ids:
            self._async_register_source(source_id)

        self._unsubscribers.append(
            self.manager.async_subscribe_source_added(self._async_register_source)
        )

    @callback
    def async_stop(self) -> None:
        """Stop platform subscriptions."""
        self._started = False
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        for unsubscribe in self._source_unsubscribers.values():
            unsubscribe()
        self._source_unsubscribers.clear()

    @callback
    def _async_remove_legacy_v1_entities(self) -> None:
        """Remove v1 placeholders so v2 can recreate metadata lazily."""
        for registry_entry in list(
            er.async_entries_for_config_entry(
                self._entity_registry, self.entry.entry_id
            )
        ):
            if (
                registry_entry.domain == SENSOR_DOMAIN
                and registry_entry.platform == DOMAIN
                and registry_entry.unique_id.startswith(LEGACY_UID_PREFIXES)
            ):
                self._entity_registry.async_remove(registry_entry.entity_id)

    @callback
    def _async_restore_registered_sensors(self) -> None:
        """Restore sensors for metadata that was observed previously."""
        entities: list[CastExtractedSensor] = []

        for registry_entry in er.async_entries_for_config_entry(
            self._entity_registry, self.entry.entry_id
        ):
            if (
                registry_entry.domain != SENSOR_DOMAIN
                or registry_entry.platform != DOMAIN
            ):
                continue

            parsed = parse_unique_id(registry_entry.unique_id)
            if parsed is None:
                continue

            source_id, kind, attribute = parsed
            sensor = self._async_create_sensor(source_id, kind, attribute)
            if sensor is not None:
                entities.append(sensor)

        if entities:
            self._async_add_entities(entities)

    @callback
    def _async_register_source(self, source_registry_id: str) -> None:
        """Register one current or newly added native Cast source."""
        if source_registry_id not in self._source_unsubscribers:
            self._source_unsubscribers[source_registry_id] = (
                self.manager.async_subscribe_source(
                    source_registry_id, self._async_handle_source_updated
                )
            )

        self._async_ensure_source_sensors(source_registry_id)
        self._async_refresh_source_sensors(source_registry_id)

    @callback
    def _async_ensure_source_sensors(self, source_registry_id: str) -> None:
        """Create base sensors and only metadata currently carrying a value."""
        entities: list[CastExtractedSensor] = []

        for kind in (KIND_STATE, KIND_SNAPSHOT):
            sensor = self._async_create_sensor(source_registry_id, kind, None)
            if sensor is not None:
                entities.append(sensor)

        state = self.manager.get_source_state(source_registry_id)
        if state is not None:
            for attribute, value in sorted(state.attributes.items()):
                if value is None:
                    continue
                sensor = self._async_create_sensor(
                    source_registry_id, KIND_ATTRIBUTE, attribute
                )
                if sensor is not None:
                    entities.append(sensor)

        if entities:
            self._async_add_entities(entities)

    @callback
    def _async_create_sensor(
        self,
        source_registry_id: str,
        kind: str,
        attribute: str | None,
    ) -> CastExtractedSensor | None:
        """Create one entity object unless its unique ID is already loaded."""
        unique_id = build_unique_id(source_registry_id, kind, attribute)
        if unique_id in self._sensors:
            return None

        sensor = CastExtractedSensor(
            self.manager,
            source_registry_id=source_registry_id,
            kind=kind,
            attribute=attribute,
            unique_id=unique_id,
        )
        self._sensors[unique_id] = sensor
        self._sensor_uids_by_source[source_registry_id].add(unique_id)
        return sensor

    @callback
    def _async_handle_source_updated(
        self,
        source_registry_id: str,
        old_state: State | None,
        new_state: State | None,
    ) -> None:
        """Create newly seen metadata sensors and refresh existing sensors."""
        if new_state is not None:
            new_entities: list[CastExtractedSensor] = []
            for attribute, value in new_state.attributes.items():
                if value is None:
                    continue
                sensor = self._async_create_sensor(
                    source_registry_id, KIND_ATTRIBUTE, attribute
                )
                if sensor is not None:
                    new_entities.append(sensor)
            if new_entities:
                self._async_add_entities(new_entities)

        for unique_id in tuple(self._sensor_uids_by_source[source_registry_id]):
            sensor = self._sensors.get(unique_id)
            if sensor is not None:
                sensor.async_source_updated(old_state, new_state)

    @callback
    def _async_refresh_source_sensors(self, source_registry_id: str) -> None:
        """Refresh source-device links after source discovery or rename."""
        for unique_id in tuple(self._sensor_uids_by_source[source_registry_id]):
            sensor = self._sensors.get(unique_id)
            if sensor is not None:
                sensor.async_refresh_source()


class CastExtractedSensor(SensorEntity):
    """Expose one value from a native Cast media-player state object."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        manager: CastManager,
        *,
        source_registry_id: str,
        kind: str,
        attribute: str | None,
        unique_id: str,
    ) -> None:
        """Initialize an extracted sensor."""
        self._manager = manager
        self._source_registry_id = source_registry_id
        self._kind = kind
        self._attribute = attribute
        self._attr_unique_id = unique_id
        self._attr_name = self._sensor_name
        self._attr_icon = self._sensor_icon

        if kind == KIND_SNAPSHOT:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        self._refresh_device_link()

    @property
    def _sensor_name(self) -> str:
        """Return the device-relative entity name."""
        if self._kind == KIND_STATE:
            return "Cast state"
        if self._kind == KIND_SNAPSHOT:
            return "Cast attributes"
        assert self._attribute is not None
        return f"Cast {humanize(self._attribute)}"

    @property
    def _sensor_icon(self) -> str:
        """Return an icon appropriate for the extracted value."""
        if self._kind == KIND_STATE:
            return "mdi:cast-connected"
        if self._kind == KIND_SNAPSHOT:
            return "mdi:code-json"
        assert self._attribute is not None
        return _ICON_BY_ATTRIBUTE.get(self._attribute, "mdi:information-outline")

    @property
    def available(self) -> bool:
        """Return whether the native Cast source is available."""
        return self._manager.source_available(self._source_registry_id)

    @property
    def native_value(self) -> str | int | float | Decimal | None:
        """Return the extracted sensor state."""
        source_state = self._manager.get_source_state(self._source_registry_id)
        if source_state is None:
            return None

        if self._kind == KIND_STATE:
            return normalize_native_value(source_state.state)[0]

        if self._kind == KIND_SNAPSHOT:
            return len(source_state.attributes)

        assert self._attribute is not None
        value = source_state.attributes.get(self._attribute)
        return normalize_native_value(value)[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return source metadata and values that cannot fit in entity state."""
        source_entity_id = self._manager.get_source_entity_id(self._source_registry_id)
        source_state = self._manager.get_source_state(self._source_registry_id)

        if self._kind == KIND_SNAPSHOT:
            attributes: dict[str, Any] = (
                dict(source_state.attributes) if source_state is not None else {}
            )
            attributes["_source_entity_id"] = source_entity_id
            attributes["_source_state"] = (
                source_state.state if source_state is not None else None
            )
            if source_state is not None:
                attributes["_source_last_changed"] = source_state.last_changed
                attributes["_source_last_updated"] = source_state.last_updated
                attributes["_source_last_reported"] = source_state.last_reported
            return attributes

        attributes = {"source_entity_id": source_entity_id}

        if self._kind == KIND_STATE:
            return attributes

        assert self._attribute is not None
        attributes["source_attribute"] = self._attribute

        if source_state is None:
            return attributes

        raw_value = source_state.attributes.get(self._attribute)
        _, extra = normalize_native_value(raw_value)
        attributes.update(extra)
        return attributes

    @callback
    def async_source_updated(
        self, old_state: State | None, new_state: State | None
    ) -> None:
        """Write state only when this sensor's relevant value changed."""
        self._refresh_device_link()
        if self.entity_id is None:
            return

        old_available = old_state is not None and old_state.state != "unavailable"
        new_available = new_state is not None and new_state.state != "unavailable"

        if old_available != new_available:
            self.async_write_ha_state()
            return

        if self._kind == KIND_STATE:
            old_value = old_state.state if old_state is not None else _MISSING
            new_value = new_state.state if new_state is not None else _MISSING
        elif self._kind == KIND_SNAPSHOT:
            old_value = (
                (old_state.state, dict(old_state.attributes))
                if old_state is not None
                else _MISSING
            )
            new_value = (
                (new_state.state, dict(new_state.attributes))
                if new_state is not None
                else _MISSING
            )
        else:
            assert self._attribute is not None
            old_value = (
                old_state.attributes.get(self._attribute, _MISSING)
                if old_state is not None
                else _MISSING
            )
            new_value = (
                new_state.attributes.get(self._attribute, _MISSING)
                if new_state is not None
                else _MISSING
            )

        if old_value != new_value:
            self.async_write_ha_state()

    @callback
    def async_refresh_source(self) -> None:
        """Refresh the source device link and state."""
        self._refresh_device_link()
        if self.entity_id is not None:
            self.async_write_ha_state()

    @callback
    def _refresh_device_link(self) -> None:
        """Link the sensor to the native Cast device."""
        source_entity_id = self._manager.get_source_entity_id(self._source_registry_id)
        self.device_entry = (
            async_entity_id_to_device(self._manager.hass, source_entity_id)
            if source_entity_id is not None
            else None
        )

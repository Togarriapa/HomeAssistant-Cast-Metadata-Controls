"""Lazy metadata sensors grouped under their physical media device."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ANDROID_TV_ADB_DOMAIN,
    ANDROID_TV_REMOTE_DOMAIN,
    CAST_DOMAIN,
    DOMAIN,
    KIND_ATTRIBUTE,
    KIND_SNAPSHOT,
    KIND_STATE,
    SENSOR_DOMAIN,
)
from .runtime import IntegrationRuntime
from .util import (
    humanize,
    normalize_native_value,
    parse_sensor_unique_id,
    sensor_unique_id,
)

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
    "repeat": "mdi:repeat",
    "shuffle": "mdi:shuffle-variant",
    "source": "mdi:video-input-hdmi",
    "source_list": "mdi:format-list-bulleted",
    "supported_features": "mdi:cog-outline",
    "volume_level": "mdi:volume-high",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Start lazy sensor creation."""
    platform = DynamicSensorPlatform(entry.runtime_data, async_add_entities)
    platform.start()
    entry.async_on_unload(platform.stop)


class DynamicSensorPlatform:
    """Persistently create a sensor after a source value first appears."""

    def __init__(
        self,
        runtime: IntegrationRuntime,
        async_add_entities: AddConfigEntryEntitiesCallback,
    ) -> None:
        self.runtime = runtime
        self._async_add_entities = async_add_entities
        self._registry = er.async_get(runtime.hass)
        self._sensors: dict[str, MetadataSensor] = {}
        self._uids_by_source: dict[str, set[str]] = defaultdict(set)
        self._source_unsubscribers: dict[str, CALLBACK_TYPE] = {}
        self._topology_unsubscribe: CALLBACK_TYPE | None = None

    @callback
    def start(self) -> None:
        self._restore_registered_sensors()
        for source_id in self.runtime.manager.source_ids:
            self._register_source(source_id)
        self._topology_unsubscribe = self.runtime.manager.async_subscribe_topology(
            self._register_all_sources
        )

    @callback
    def stop(self) -> None:
        if self._topology_unsubscribe:
            self._topology_unsubscribe()
            self._topology_unsubscribe = None
        for unsubscribe in self._source_unsubscribers.values():
            unsubscribe()
        self._source_unsubscribers.clear()

    @callback
    def _register_all_sources(self) -> None:
        for source_id in self.runtime.manager.source_ids:
            self._register_source(source_id)

    @callback
    def _restore_registered_sensors(self) -> None:
        entities: list[MetadataSensor] = []
        for entry in er.async_entries_for_config_entry(
            self._registry, self.runtime.entry.entry_id
        ):
            if entry.domain != SENSOR_DOMAIN or entry.platform != DOMAIN:
                continue
            parsed = parse_sensor_unique_id(entry.unique_id)
            if parsed is None:
                continue
            source_id, kind, attribute = parsed
            if self.runtime.manager.get_source(source_id) is None:
                continue
            sensor = self._create_sensor(source_id, kind, attribute)
            if sensor:
                entities.append(sensor)
        if entities:
            self._async_add_entities(entities)

    @callback
    def _register_source(self, source_id: str) -> None:
        if source_id not in self._source_unsubscribers:
            self._source_unsubscribers[source_id] = (
                self.runtime.manager.async_subscribe_source(
                    source_id, self._source_updated
                )
            )
        entities: list[MetadataSensor] = []
        state_sensor = self._create_sensor(source_id, KIND_STATE, None)
        if state_sensor:
            entities.append(state_sensor)
        snapshot_sensor = self._create_sensor(source_id, KIND_SNAPSHOT, None)
        if snapshot_sensor:
            entities.append(snapshot_sensor)

        state = self.runtime.manager.get_state(source_id)
        if state is not None:
            for attribute, value in sorted(state.attributes.items()):
                if value is None:
                    continue
                sensor = self._create_sensor(source_id, KIND_ATTRIBUTE, attribute)
                if sensor:
                    entities.append(sensor)
        if entities:
            self._async_add_entities(entities)

    @callback
    def _create_sensor(
        self, source_id: str, kind: str, attribute: str | None
    ) -> MetadataSensor | None:
        unique_id = sensor_unique_id(source_id, kind, attribute)
        if unique_id in self._sensors:
            return None
        sensor = MetadataSensor(
            self.runtime,
            source_id=source_id,
            kind=kind,
            attribute=attribute,
            unique_id=unique_id,
        )
        self._sensors[unique_id] = sensor
        self._uids_by_source[source_id].add(unique_id)
        return sensor

    @callback
    def _source_updated(
        self, source_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        entities: list[MetadataSensor] = []
        if new_state is not None:
            for attribute, value in new_state.attributes.items():
                if value is None:
                    continue
                sensor = self._create_sensor(source_id, KIND_ATTRIBUTE, attribute)
                if sensor:
                    entities.append(sensor)
        if entities:
            self._async_add_entities(entities)

        for unique_id in tuple(self._uids_by_source[source_id]):
            sensor = self._sensors.get(unique_id)
            if sensor:
                sensor.source_updated(old_state, new_state)


class MetadataSensor(SensorEntity):
    """Expose one state value from one underlying source entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        runtime: IntegrationRuntime,
        *,
        source_id: str,
        kind: str,
        attribute: str | None,
        unique_id: str,
    ) -> None:
        self.runtime = runtime
        self.source_id = source_id
        self.kind = kind
        self.attribute = attribute
        self._attr_unique_id = unique_id
        self._attr_name = self._name
        self._attr_icon = self._icon
        group = runtime.group_for_source(source_id)
        if group:
            self._attr_device_info = runtime.device_info(group)
        if kind == KIND_SNAPSHOT:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False

    @property
    def _source_label(self) -> str:
        platform = self.runtime.manager.platform(self.source_id)
        if platform == CAST_DOMAIN:
            return "Cast"
        if platform == ANDROID_TV_REMOTE_DOMAIN:
            return "Android TV Remote"
        if platform == ANDROID_TV_ADB_DOMAIN:
            return "Android TV ADB"
        return humanize(platform or "TV")

    @property
    def _name(self) -> str:
        if self.kind == KIND_STATE:
            return f"{self._source_label} state"
        if self.kind == KIND_SNAPSHOT:
            return f"{self._source_label} attributes"
        return f"{self._source_label} {humanize(self.attribute or 'value')}"

    @property
    def _icon(self) -> str:
        if self.kind == KIND_STATE:
            return (
                "mdi:cast-connected"
                if self._source_label == "Cast"
                else "mdi:television"
            )
        if self.kind == KIND_SNAPSHOT:
            return "mdi:code-json"
        return _ICON_BY_ATTRIBUTE.get(self.attribute or "", "mdi:information-outline")

    @property
    def available(self) -> bool:
        return self.runtime.manager.available(self.source_id)

    @property
    def native_value(self) -> str | int | float | Decimal | None:
        state = self.runtime.manager.get_state(self.source_id)
        if state is None:
            return None
        if self.kind == KIND_STATE:
            return normalize_native_value(state.state)[0]
        if self.kind == KIND_SNAPSHOT:
            return len(state.attributes)
        return normalize_native_value(state.attributes.get(self.attribute))[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.runtime.manager.get_state(self.source_id)
        source_entity_id = self.runtime.manager.get_entity_id(self.source_id)
        platform = self.runtime.manager.platform(self.source_id)
        if self.kind == KIND_SNAPSHOT:
            values = dict(state.attributes) if state else {}
            values.update(
                {
                    "_source_entity_id": source_entity_id,
                    "_source_platform": platform,
                    "_source_state": state.state if state else None,
                }
            )
            return values
        values: dict[str, Any] = {
            "source_entity_id": source_entity_id,
            "source_platform": platform,
        }
        if self.kind == KIND_ATTRIBUTE and state is not None:
            values["source_attribute"] = self.attribute
            _, extra = normalize_native_value(state.attributes.get(self.attribute))
            values.update(extra)
        return values

    @callback
    def source_updated(self, old_state: State | None, new_state: State | None) -> None:
        if self.entity_id is None:
            return
        if self.kind == KIND_STATE:
            old_value = old_state.state if old_state else _MISSING
            new_value = new_state.state if new_state else _MISSING
        elif self.kind == KIND_SNAPSHOT:
            old_value = (
                (old_state.state, dict(old_state.attributes)) if old_state else _MISSING
            )
            new_value = (
                (new_state.state, dict(new_state.attributes)) if new_state else _MISSING
            )
        else:
            old_value = (
                old_state.attributes.get(self.attribute, _MISSING)
                if old_state
                else _MISSING
            )
            new_value = (
                new_state.attributes.get(self.attribute, _MISSING)
                if new_state
                else _MISSING
            )
        if old_value != new_value:
            self.async_write_ha_state()

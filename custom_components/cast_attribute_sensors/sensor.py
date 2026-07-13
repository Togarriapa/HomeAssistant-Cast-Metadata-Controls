"""Dynamic metadata sensors grouped by physical Cast/TV device."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
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
from .media_player import (
    _matching_cast_source_ids,
    _primary_tv_source_ids,
    _tv_group_source_ids,
)
from .tv_manager import TvManager
from .util import build_unique_id, humanize, normalize_native_value, parse_unique_id

_MISSING = object()
_SOURCE_CAST = "cast"
_SOURCE_TV = "tv"

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
    """Set up lazy metadata sensors for every tracked source."""
    platform = DynamicMetadataPlatform(
        hass,
        entry,
        entry.runtime_data.manager,
        entry.runtime_data.tv_manager,
        async_add_entities,
    )
    platform.async_start()
    entry.async_on_unload(platform.async_stop)


class DynamicMetadataPlatform:
    """Create sensors when attributes first appear on Cast or TV sources."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        cast_manager: CastManager,
        tv_manager: TvManager,
        async_add_entities: AddConfigEntryEntitiesCallback,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.cast_manager = cast_manager
        self.tv_manager = tv_manager
        self._async_add_entities = async_add_entities
        self._entity_registry = er.async_get(hass)
        self._sensors: dict[str, ExtractedMetadataSensor] = {}
        self._sensor_uids_by_source: dict[tuple[str, str], set[str]] = defaultdict(set)
        self._source_unsubscribers: dict[tuple[str, str], CALLBACK_TYPE] = {}
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._started = False

    @callback
    def async_start(self) -> None:
        if self._started:
            return
        self._started = True
        self._async_remove_legacy_v1_entities()
        self._async_restore_registered_sensors()

        for source_id in self.cast_manager.source_ids:
            self._async_register_source(_SOURCE_CAST, source_id)
        for source_id in self.tv_manager.source_ids:
            self._async_register_source(_SOURCE_TV, source_id)

        self._unsubscribers.append(
            self.cast_manager.async_subscribe_source_added(
                lambda source_id: self._async_register_source(_SOURCE_CAST, source_id)
            )
        )
        self._unsubscribers.append(
            self.tv_manager.async_subscribe_source_added(
                lambda source_id: self._async_register_source(_SOURCE_TV, source_id)
            )
        )

    @callback
    def async_stop(self) -> None:
        self._started = False
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        for unsubscribe in self._source_unsubscribers.values():
            unsubscribe()
        self._source_unsubscribers.clear()

    def _manager_for(self, source_type: str):
        return self.cast_manager if source_type == _SOURCE_CAST else self.tv_manager

    def _source_type_for_id(self, source_id: str) -> str | None:
        if source_id in self.cast_manager.source_ids:
            return _SOURCE_CAST
        if source_id in self.tv_manager.source_ids:
            return _SOURCE_TV
        return None

    @callback
    def _async_remove_legacy_v1_entities(self) -> None:
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
        entities: list[ExtractedMetadataSensor] = []
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
            source_type = self._source_type_for_id(source_id)
            if source_type is None:
                continue
            sensor = self._async_create_sensor(
                source_type, source_id, kind, attribute
            )
            if sensor is not None:
                entities.append(sensor)
        if entities:
            self._async_add_entities(entities)

    @callback
    def _async_register_source(self, source_type: str, source_id: str) -> None:
        key = (source_type, source_id)
        manager = self._manager_for(source_type)
        if key not in self._source_unsubscribers:
            self._source_unsubscribers[key] = manager.async_subscribe_source(
                source_id,
                lambda updated_source_id, old_state, new_state: self._async_handle_source_updated(
                    source_type, updated_source_id, old_state, new_state
                ),
            )
        self._async_ensure_source_sensors(source_type, source_id)
        self._async_refresh_source_sensors(source_type, source_id)

    @callback
    def _async_ensure_source_sensors(self, source_type: str, source_id: str) -> None:
        entities: list[ExtractedMetadataSensor] = []
        for kind in (KIND_STATE, KIND_SNAPSHOT):
            sensor = self._async_create_sensor(source_type, source_id, kind, None)
            if sensor is not None:
                entities.append(sensor)

        state = self._manager_for(source_type).get_source_state(source_id)
        if state is not None:
            for attribute, value in sorted(state.attributes.items()):
                if value is None:
                    continue
                sensor = self._async_create_sensor(
                    source_type, source_id, KIND_ATTRIBUTE, attribute
                )
                if sensor is not None:
                    entities.append(sensor)
        if entities:
            self._async_add_entities(entities)

    @callback
    def _async_create_sensor(
        self,
        source_type: str,
        source_id: str,
        kind: str,
        attribute: str | None,
    ) -> ExtractedMetadataSensor | None:
        unique_id = build_unique_id(source_id, kind, attribute)
        if unique_id in self._sensors:
            return None
        sensor = ExtractedMetadataSensor(
            self.cast_manager,
            self.tv_manager,
            source_type=source_type,
            source_registry_id=source_id,
            kind=kind,
            attribute=attribute,
            unique_id=unique_id,
        )
        self._sensors[unique_id] = sensor
        self._sensor_uids_by_source[(source_type, source_id)].add(unique_id)
        return sensor

    @callback
    def _async_handle_source_updated(
        self,
        source_type: str,
        source_id: str,
        old_state: State | None,
        new_state: State | None,
    ) -> None:
        if new_state is not None:
            new_entities: list[ExtractedMetadataSensor] = []
            for attribute, value in new_state.attributes.items():
                if value is None:
                    continue
                sensor = self._async_create_sensor(
                    source_type, source_id, KIND_ATTRIBUTE, attribute
                )
                if sensor is not None:
                    new_entities.append(sensor)
            if new_entities:
                self._async_add_entities(new_entities)

        for unique_id in tuple(
            self._sensor_uids_by_source[(source_type, source_id)]
        ):
            sensor = self._sensors.get(unique_id)
            if sensor is not None:
                sensor.async_source_updated(old_state, new_state)

    @callback
    def _async_refresh_source_sensors(
        self, source_type: str, source_id: str
    ) -> None:
        for unique_id in tuple(
            self._sensor_uids_by_source[(source_type, source_id)]
        ):
            sensor = self._sensors.get(unique_id)
            if sensor is not None:
                sensor.async_refresh_source()


class ExtractedMetadataSensor(SensorEntity):
    """Expose one dynamically discovered Cast or TV state value."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        cast_manager: CastManager,
        tv_manager: TvManager,
        *,
        source_type: str,
        source_registry_id: str,
        kind: str,
        attribute: str | None,
        unique_id: str,
    ) -> None:
        self._cast_manager = cast_manager
        self._tv_manager = tv_manager
        self._source_type = source_type
        self._source_registry_id = source_registry_id
        self._kind = kind
        self._attribute = attribute
        self._attr_unique_id = unique_id
        self._attr_name = self._sensor_name
        self._attr_icon = self._sensor_icon
        if kind == KIND_SNAPSHOT:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def _manager(self):
        return (
            self._cast_manager
            if self._source_type == _SOURCE_CAST
            else self._tv_manager
        )

    @property
    def _source_label(self) -> str:
        if self._source_type == _SOURCE_CAST:
            return "Cast"
        platform = self._tv_manager.get_source_platform(self._source_registry_id)
        if platform == "androidtv_remote":
            return "Android TV Remote"
        if platform == "androidtv":
            return "Android TV ADB"
        return humanize(platform or "TV")

    @property
    def _sensor_name(self) -> str:
        if self._kind == KIND_STATE:
            return f"{self._source_label} state"
        if self._kind == KIND_SNAPSHOT:
            return f"{self._source_label} attributes"
        assert self._attribute is not None
        return f"{self._source_label} {humanize(self._attribute)}"

    @property
    def _sensor_icon(self) -> str:
        if self._kind == KIND_STATE:
            return "mdi:cast-connected" if self._source_type == _SOURCE_CAST else "mdi:television"
        if self._kind == KIND_SNAPSHOT:
            return "mdi:code-json"
        assert self._attribute is not None
        return _ICON_BY_ATTRIBUTE.get(self._attribute, "mdi:information-outline")

    def _physical_tv_primary_source_id(self) -> str | None:
        if self._source_type == _SOURCE_TV:
            for primary_id in _primary_tv_source_ids(self._tv_manager):
                if self._source_registry_id in _tv_group_source_ids(
                    self._tv_manager, primary_id
                ):
                    return primary_id
            return self._source_registry_id

        for primary_id in _primary_tv_source_ids(self._tv_manager):
            if self._source_registry_id in _matching_cast_source_ids(
                self._cast_manager, self._tv_manager, primary_id
            ):
                return primary_id
        return None

    @property
    def device_info(self) -> DeviceInfo:
        primary_tv_id = self._physical_tv_primary_source_id()
        if primary_tv_id is not None:
            state = self._tv_manager.get_source_state(primary_tv_id)
            entity_id = self._tv_manager.get_source_entity_id(primary_tv_id)
            name = (
                state.attributes.get("friendly_name") if state is not None else None
            ) or entity_id or "Television"
            return DeviceInfo(
                identifiers={(DOMAIN, f"tv:{primary_tv_id}")},
                name=f"{name} Controller",
                manufacturer="Home Assistant",
                model="Virtual TV Controller",
            )

        state = self._cast_manager.get_source_state(self._source_registry_id)
        entity_id = self._cast_manager.get_source_entity_id(self._source_registry_id)
        name = (
            state.attributes.get("friendly_name") if state is not None else None
        ) or entity_id or "Cast device"
        return DeviceInfo(
            identifiers={(DOMAIN, f"cast:{self._source_registry_id}")},
            name=f"{name} Controller",
            manufacturer="Home Assistant",
            model="Virtual Cast Controller",
        )

    @property
    def available(self) -> bool:
        return self._manager.source_available(self._source_registry_id)

    @property
    def native_value(self) -> str | int | float | Decimal | None:
        source_state = self._manager.get_source_state(self._source_registry_id)
        if source_state is None:
            return None
        if self._kind == KIND_STATE:
            return normalize_native_value(source_state.state)[0]
        if self._kind == KIND_SNAPSHOT:
            return len(source_state.attributes)
        assert self._attribute is not None
        return normalize_native_value(source_state.attributes.get(self._attribute))[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        source_entity_id = self._manager.get_source_entity_id(
            self._source_registry_id
        )
        source_state = self._manager.get_source_state(self._source_registry_id)
        source_platform = (
            "cast"
            if self._source_type == _SOURCE_CAST
            else self._tv_manager.get_source_platform(self._source_registry_id)
        )

        if self._kind == KIND_SNAPSHOT:
            attributes: dict[str, Any] = (
                dict(source_state.attributes) if source_state is not None else {}
            )
            attributes["_source_entity_id"] = source_entity_id
            attributes["_source_platform"] = source_platform
            attributes["_source_state"] = (
                source_state.state if source_state is not None else None
            )
            if source_state is not None:
                attributes["_source_last_changed"] = source_state.last_changed
                attributes["_source_last_updated"] = source_state.last_updated
                attributes["_source_last_reported"] = source_state.last_reported
            return attributes

        attributes = {
            "source_entity_id": source_entity_id,
            "source_platform": source_platform,
        }
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
        if self.entity_id is not None:
            self.async_write_ha_state()

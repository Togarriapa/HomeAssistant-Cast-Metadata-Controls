"""Physical-device transition events."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import State, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UID_SEPARATOR, UID_VERSION
from .grouping import PhysicalGroup
from .runtime import IntegrationRuntime

_EVENT_TYPES = [
    "power_changed",
    "application_changed",
    "input_changed",
    "playback_changed",
    "volume_changed",
    "mute_changed",
]


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create and hot-add one transition event entity per physical device."""
    platform = DynamicTransitionPlatform(entry.runtime_data, async_add_entities)
    platform.start()
    entry.async_on_unload(platform.stop)


class DynamicTransitionPlatform:
    """Own transition event entities."""

    def __init__(self, runtime: IntegrationRuntime, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
        self.runtime = runtime
        self._async_add_entities = async_add_entities
        self._entities: dict[str, DeviceTransitionEvent] = {}
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
        entities: list[DeviceTransitionEvent] = []
        for group in groups:
            if group.key in self._entities:
                continue
            entity = DeviceTransitionEvent(self.runtime, group)
            self._entities[group.key] = entity
            entities.append(entity)
        if entities:
            self._async_add_entities(entities)


class DeviceTransitionEvent(EventEntity):
    """Emit normalized TV/Cast transitions for automations."""

    _attr_has_entity_name = True
    _attr_name = "Transitions"
    _attr_icon = "mdi:timeline-clock-outline"
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_event_types = _EVENT_TYPES

    def __init__(self, runtime: IntegrationRuntime, group: PhysicalGroup) -> None:
        self.runtime = runtime
        self.group = group
        self._attr_unique_id = UID_SEPARATOR.join((UID_VERSION, group.key, "event", "transitions"))
        self._attr_device_info = runtime.device_info(group)
        self._snapshot = self._current_snapshot()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._snapshot = self._current_snapshot()
        for source_id in self.group.source_ids:
            self.async_on_remove(self.runtime.manager.async_subscribe_source(source_id, self._async_source_updated))

    def _current_snapshot(self) -> dict[str, Any]:
        states = [self.runtime.manager.get_state(source_id) for source_id in self.group.source_ids]
        available = [state for state in states if state is not None]
        primary = self.runtime.primary_state(self.group)
        playing = next((state for state in available if state.state in {"playing", "paused", "buffering"}), primary)
        app_state = next((state for state in available if state.attributes.get("app_id") or state.attributes.get("app_name")), playing)
        input_state = next((state for state in available if state.attributes.get("source") is not None), primary)
        volume_state = next((state for state in available if state.attributes.get("volume_level") is not None), primary)
        return {
            "power": primary.state if primary else "unavailable",
            "application": (app_state.attributes.get("app_name") or app_state.attributes.get("app_id")) if app_state else None,
            "input": input_state.attributes.get("source") if input_state else None,
            "playback": playing.state if playing else "unavailable",
            "volume": volume_state.attributes.get("volume_level") if volume_state else None,
            "mute": volume_state.attributes.get("is_volume_muted") if volume_state else None,
        }

    @callback
    def _async_source_updated(self, source_id: str, old_state: State | None, new_state: State | None) -> None:
        current = self._current_snapshot()
        mapping = {
            "power": "power_changed",
            "application": "application_changed",
            "input": "input_changed",
            "playback": "playback_changed",
            "volume": "volume_changed",
            "mute": "mute_changed",
        }
        source_entity_id = self.runtime.manager.get_entity_id(source_id)
        for key, event_type in mapping.items():
            old_value = self._snapshot.get(key)
            new_value = current.get(key)
            if old_value == new_value:
                continue
            self._trigger_event(event_type, {
                "field": key,
                "old_value": old_value,
                "new_value": new_value,
                "source_entity_id": source_entity_id,
                "physical_device_id": self.group.key,
            })
            self.async_write_ha_state()
        self._snapshot = current

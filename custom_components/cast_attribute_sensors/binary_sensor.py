"""Controller health diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import State, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UID_SEPARATOR, UID_VERSION
from .grouping import PhysicalGroup
from .runtime import IntegrationRuntime


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one health diagnostic per physical device."""
    platform = DynamicHealthPlatform(entry.runtime_data, async_add_entities)
    platform.start()
    entry.async_on_unload(platform.stop)


class DynamicHealthPlatform:
    """Hot-add diagnostics for newly discovered independent devices."""

    def __init__(
        self,
        runtime: IntegrationRuntime,
        async_add_entities: AddConfigEntryEntitiesCallback,
    ) -> None:
        self.runtime = runtime
        self._async_add_entities = async_add_entities
        self._entities: dict[str, ControllerHealthBinarySensor] = {}
        self._unsubscribe = None

    @callback
    def start(self) -> None:
        self._add_groups(self.runtime.groups)
        self._unsubscribe = self.runtime.async_subscribe_group_additions(
            self._add_groups
        )

    @callback
    def stop(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _add_groups(self, groups: tuple[PhysicalGroup, ...]) -> None:
        entities: list[ControllerHealthBinarySensor] = []
        for group in groups:
            if group.key in self._entities:
                continue
            entity = ControllerHealthBinarySensor(self.runtime, group)
            self._entities[group.key] = entity
            entities.append(entity)
        if entities:
            self._async_add_entities(entities)


class ControllerHealthBinarySensor(BinarySensorEntity):
    """Report degraded or unavailable controller source topology."""

    _attr_has_entity_name = True
    _attr_name = "Controller problem"
    _attr_icon = "mdi:heart-pulse"
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: IntegrationRuntime, group: PhysicalGroup) -> None:
        self.runtime = runtime
        self.group = group
        self._attr_unique_id = UID_SEPARATOR.join(
            (UID_VERSION, group.key, "binary_sensor", "health")
        )
        self._attr_device_info = runtime.device_info(group)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        for source_id in self.group.source_ids:
            self.async_on_remove(
                self.runtime.manager.async_subscribe_source(
                    source_id, self._async_source_updated
                )
            )

    @callback
    def _async_source_updated(
        self, source_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        if self.entity_id:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        status, _ = self.runtime.health(self.group)
        return status != "healthy"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status, details = self.runtime.health(self.group)
        return {"health": status, **details}

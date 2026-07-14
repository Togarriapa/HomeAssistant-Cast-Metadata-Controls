"""Per-device opt-in controls for automatic YouTube ad skipping."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .ad_skip_registry import get_manager
from .const import UID_SEPARATOR, UID_VERSION
from .grouping import PhysicalGroup
from .runtime import IntegrationRuntime


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one opt-in ad-skip switch per physical media device."""
    platform = DynamicAdSkipSwitchPlatform(
        entry.runtime_data,
        get_manager(entry.entry_id),
        async_add_entities,
    )
    platform.start()
    entry.async_on_unload(platform.stop)


class DynamicAdSkipSwitchPlatform:
    """Own switches and hot-add them for newly discovered devices."""

    def __init__(self, runtime, manager, async_add_entities) -> None:
        self.runtime = runtime
        self.manager = manager
        self._async_add_entities = async_add_entities
        self._entities: dict[str, AutoSkipYouTubeAdsSwitch] = {}
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
        entities: list[AutoSkipYouTubeAdsSwitch] = []
        for group in groups:
            if group.key in self._entities:
                continue
            entity = AutoSkipYouTubeAdsSwitch(
                self.runtime,
                self.manager,
                group,
            )
            self._entities[group.key] = entity
            entities.append(entity)
        if entities:
            self._async_add_entities(entities)


class AutoSkipYouTubeAdsSwitch(SwitchEntity):
    """Enable positive-detection ad skipping for one physical device."""

    _attr_has_entity_name = True
    _attr_name = "Auto-skip YouTube ads"
    _attr_icon = "mdi:advertisements-off"
    _attr_should_poll = False

    def __init__(self, runtime: IntegrationRuntime, manager, group: PhysicalGroup) -> None:
        self.runtime = runtime
        self.manager = manager
        self.group = group
        self._attr_unique_id = UID_SEPARATOR.join(
            (UID_VERSION, group.key, "switch", "auto_skip_youtube_ads")
        )
        self._attr_device_info = runtime.device_info(group)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.manager.async_subscribe(
                self.group.key,
                self._async_manager_updated,
            )
        )

    @callback
    def _async_manager_updated(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return bool(self.manager.details(self.group)["available_methods"])

    @property
    def is_on(self) -> bool:
        return self.manager.is_enabled(self.group.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.manager.details(self.group)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.manager.async_set_enabled(self.group.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.manager.async_set_enabled(self.group.key, False)

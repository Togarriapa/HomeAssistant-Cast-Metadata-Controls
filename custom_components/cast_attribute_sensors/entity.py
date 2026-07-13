"""Base entities linked to a native Cast media player."""

from __future__ import annotations

from homeassistant.core import State, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import CastManager


class CastLinkedEntity(Entity):
    """Base entity placed on a dedicated virtual Cast-controller device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        manager: CastManager,
        source_registry_id: str,
        unique_id: str,
    ) -> None:
        self._manager = manager
        self._source_registry_id = source_registry_id
        self._attr_unique_id = unique_id

    @property
    def available(self) -> bool:
        return self._manager.source_available(self._source_registry_id)

    @property
    def device_info(self) -> DeviceInfo:
        state = self._manager.get_source_state(self._source_registry_id)
        entity_id = self._manager.get_source_entity_id(self._source_registry_id)
        name = (
            state.attributes.get("friendly_name") if state is not None else None
        ) or entity_id or "Cast device"
        return DeviceInfo(
            identifiers={(DOMAIN, f"cast:{self._source_registry_id}")},
            name=f"{name} Controller",
            manufacturer="Home Assistant",
            model="Virtual Cast Controller",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._manager.async_subscribe_source(
                self._source_registry_id, self._async_source_event
            )
        )

    @callback
    def _async_source_event(
        self,
        source_registry_id: str,
        old_state: State | None,
        new_state: State | None,
    ) -> None:
        if self.entity_id is not None:
            self.async_write_ha_state()

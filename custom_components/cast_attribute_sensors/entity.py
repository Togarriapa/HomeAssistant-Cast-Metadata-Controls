"""Base entities linked to a native Cast media player."""

from __future__ import annotations

from homeassistant.core import State, callback
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.entity import Entity

from .manager import CastManager


class CastLinkedEntity(Entity):
    """Base entity that follows a native Cast entity across renames."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        manager: CastManager,
        source_registry_id: str,
        unique_id: str,
    ) -> None:
        """Initialize the linked entity."""
        self._manager = manager
        self._source_registry_id = source_registry_id
        self._attr_unique_id = unique_id
        self._refresh_device_link()

    @property
    def available(self) -> bool:
        """Return whether the native Cast entity is available."""
        return self._manager.source_available(self._source_registry_id)

    async def async_added_to_hass(self) -> None:
        """Subscribe to source updates."""
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
        """Refresh device linking and entity state after a source update."""
        self._refresh_device_link()
        if self.entity_id is not None:
            self.async_write_ha_state()

    @callback
    def _refresh_device_link(self) -> None:
        """Link this entity to the same device as its native Cast entity."""
        source_entity_id = self._manager.get_source_entity_id(self._source_registry_id)
        self.device_entry = (
            async_entity_id_to_device(self._manager.hass, source_entity_id)
            if source_entity_id is not None
            else None
        )

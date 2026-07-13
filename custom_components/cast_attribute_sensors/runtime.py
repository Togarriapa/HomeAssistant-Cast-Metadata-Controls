"""Runtime model shared by platforms and service handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_GROUPS, DOMAIN
from .grouping import PhysicalGroup, build_physical_groups
from .source_manager import SourceManager


@dataclass(slots=True)
class IntegrationRuntime:
    """Runtime state for the single config entry."""

    hass: HomeAssistant
    entry: ConfigEntry
    manager: SourceManager
    groups: tuple[PhysicalGroup, ...] = ()
    controllers: dict[str, Any] = field(default_factory=dict)
    _topology_unsubscribe: CALLBACK_TYPE | None = None
    _reload_task: asyncio.Task[None] | None = None
    _fingerprint: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def configured_groups(self) -> list[Mapping[str, Any]]:
        value = self.entry.options.get(CONF_GROUPS, [])
        return list(value) if isinstance(value, list) else []

    @callback
    def refresh_groups(self) -> None:
        self.groups = build_physical_groups(
            self.manager.snapshots(), self.configured_groups()
        )
        self._fingerprint = self.group_fingerprint()

    def group_fingerprint(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return tuple((group.key, group.source_ids) for group in self.groups)

    def group_for_source(self, source_id: str) -> PhysicalGroup | None:
        return next(
            (group for group in self.groups if source_id in group.source_ids), None
        )

    def group_by_key(self, key: str) -> PhysicalGroup | None:
        return next((group for group in self.groups if group.key == key), None)

    def primary_state(self, group: PhysicalGroup):
        return self.manager.get_state(group.primary_source_id)

    def device_info(self, group: PhysicalGroup) -> DeviceInfo:
        state = self.primary_state(group)
        name = (
            str(state.attributes.get("friendly_name", "")).strip()
            if state is not None
            else ""
        )
        return DeviceInfo(
            identifiers={(DOMAIN, f"physical:{group.key}")},
            name=group.name or name or "Media device",
            manufacturer="Cast Metadata & TV Controls",
            model="Unified TV Controller" if group.is_tv else "Unified Cast Controller",
            configuration_url=(
                "https://github.com/Togarriapa/HomeAssistant-Cast-Metadata-Controls"
            ),
        )

    @callback
    def start_topology_watch(self) -> None:
        if self._topology_unsubscribe is not None:
            return
        self._topology_unsubscribe = self.manager.async_subscribe_topology(
            self._async_topology_changed
        )
        self.entry.async_on_unload(self._topology_unsubscribe)

    @callback
    def _async_topology_changed(self) -> None:
        candidate = build_physical_groups(
            self.manager.snapshots(), self.configured_groups()
        )
        fingerprint = tuple((group.key, group.source_ids) for group in candidate)
        if fingerprint == self._fingerprint:
            return
        if self._reload_task is not None and not self._reload_task.done():
            return
        self._reload_task = self.hass.async_create_task(
            self._async_delayed_reload(), f"{DOMAIN}-topology-reload"
        )

    async def _async_delayed_reload(self) -> None:
        await asyncio.sleep(2)
        await self.hass.config_entries.async_reload(self.entry.entry_id)

    @callback
    def register_controller(self, entity_id: str, controller: Any) -> None:
        self.controllers[entity_id] = controller

    @callback
    def unregister_controller(self, entity_id: str) -> None:
        self.controllers.pop(entity_id, None)

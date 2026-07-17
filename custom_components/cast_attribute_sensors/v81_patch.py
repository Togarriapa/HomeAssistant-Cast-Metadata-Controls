"""V8.1 runtime hardening for physical-device consolidation.

This module is imported once during integration startup. It patches the stable V8
runtime in place so existing entity unique IDs and config-entry migrations remain
compatible while fixing real-device evidence and registry reconciliation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CAST_DOMAIN, DOMAIN, MEDIA_PLAYER_DOMAIN, UID_VERSION
from .device_evidence import is_native_tv
from .grouping import SourceSnapshot
from .runtime import IntegrationRuntime
from .source_manager import SourceManager
from .util import parse_sensor_unique_id

_LOGGER = logging.getLogger(__name__)
_RECONCILE_TASKS: dict[str, asyncio.Task[None]] = {}
_INSTALLED = False


@callback
def _classify(
    self: SourceManager, entry: er.RegistryEntry
) -> tuple[bool, bool] | None:
    """Classify every supported native media representation using device data."""
    if entry.domain != MEDIA_PLAYER_DOMAIN or entry.platform == DOMAIN:
        return None

    state = self.hass.states.get(entry.entity_id)
    device = (
        self.device_registry.async_get(entry.device_id)
        if entry.device_id is not None
        else None
    )
    registry_device_class = getattr(entry, "device_class", None) or getattr(
        entry, "original_device_class", None
    )
    state_device_class = state.attributes.get("device_class") if state else None
    friendly_name = state.attributes.get("friendly_name") if state else None
    is_cast = entry.platform == CAST_DOMAIN
    is_tv = is_native_tv(
        platform=entry.platform,
        registry_device_class=registry_device_class,
        state_device_class=state_device_class,
        manufacturer=device.manufacturer if device else None,
        model=device.model if device else None,
        device_name=device.name if device else None,
        friendly_name=friendly_name,
    )
    return (is_cast, is_tv) if is_cast or is_tv else None


@callback
def _snapshots(self: SourceManager) -> tuple[SourceSnapshot, ...]:
    """Build grouping snapshots with the hardware evidence exposed by HA."""
    snapshots: list[SourceSnapshot] = []
    for source in self._sources.values():
        if source.entity_id is None:
            continue
        state = self.hass.states.get(source.entity_id)
        entry = self.entity_registry.async_get(source.entity_id)
        device = (
            self.device_registry.async_get(source.device_id)
            if source.device_id is not None
            else None
        )
        friendly_name = (
            str(state.attributes.get("friendly_name", "")).strip()
            if state is not None
            else ""
        )
        snapshots.append(
            SourceSnapshot(
                registry_id=source.registry_id,
                entity_id=source.entity_id,
                platform=source.platform,
                name=friendly_name or source.entity_id,
                device_id=source.device_id,
                connections=(
                    frozenset(device.connections) if device else frozenset()
                ),
                area_id=(device.area_id if device else None)
                or (entry.area_id if entry else None),
                is_cast=source.is_cast,
                is_tv=source.is_tv,
                manufacturer=device.manufacturer if device else None,
                model=device.model if device else None,
                device_name=device.name if device else None,
            )
        )
    return tuple(snapshots)


def _group_key(unique_id: str) -> str | None:
    parts = unique_id.split("|")
    if len(parts) < 2 or parts[0] != UID_VERSION:
        return None
    return parts[1]


async def _async_reconcile_registry(runtime: IntegrationRuntime) -> None:
    """Move all integration entities onto the surviving physical device."""
    await asyncio.sleep(1)
    entity_registry = er.async_get(runtime.hass)
    device_registry = dr.async_get(runtime.hass)
    valid_groups = {group.key: group for group in runtime.groups}
    entries = list(
        er.async_entries_for_config_entry(entity_registry, runtime.entry.entry_id)
    )

    target_devices: dict[str, str] = {}
    for entity in entries:
        if (
            entity.platform != DOMAIN
            or entity.domain != MEDIA_PLAYER_DOMAIN
            or entity.device_id is None
        ):
            continue
        key = _group_key(entity.unique_id)
        if key in valid_groups:
            target_devices[key] = entity.device_id

    if not target_devices:
        return

    moved = 0
    removed = 0
    for entity in entries:
        if entity.platform != DOMAIN:
            continue

        target_key: str | None = None
        if entity.domain == "sensor":
            parsed = parse_sensor_unique_id(entity.unique_id)
            if parsed is not None:
                group = runtime.group_for_source(parsed[0])
                target_key = group.key if group else None
        else:
            target_key = _group_key(entity.unique_id)
            if target_key is not None and target_key not in valid_groups:
                entity_registry.async_remove(entity.entity_id)
                removed += 1
                continue

        target_device_id = target_devices.get(target_key or "")
        if target_device_id and entity.device_id != target_device_id:
            entity_registry.async_update_entity(
                entity.entity_id,
                device_id=target_device_id,
            )
            moved += 1

    used_device_ids = {
        entity.device_id
        for entity in er.async_entries_for_config_entry(
            entity_registry, runtime.entry.entry_id
        )
        if entity.device_id is not None
    }
    removed_devices = 0
    for device in list(device_registry.devices.values()):
        if runtime.entry.entry_id not in device.config_entries:
            continue
        if not any(identifier[0] == DOMAIN for identifier in device.identifiers):
            continue
        if device.id not in used_device_ids:
            device_registry.async_remove_device(device.id)
            removed_devices += 1

    if moved or removed or removed_devices:
        _LOGGER.info(
            "Physical-device reconciliation moved %s entities, removed %s stale "
            "entities, and removed %s obsolete devices",
            moved,
            removed,
            removed_devices,
        )


def _schedule_reconcile(runtime: IntegrationRuntime) -> None:
    current = _RECONCILE_TASKS.get(runtime.entry.entry_id)
    if current is not None and not current.done():
        return

    async def run() -> None:
        try:
            await _async_reconcile_registry(runtime)
        finally:
            _RECONCILE_TASKS.pop(runtime.entry.entry_id, None)

    _RECONCILE_TASKS[runtime.entry.entry_id] = runtime.hass.async_create_task(
        run(),
        f"{DOMAIN}-physical-device-reconcile",
    )


def install_v81_patches() -> None:
    """Install V8.1 fixes exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    SourceManager._classify = _classify
    SourceManager.snapshots = _snapshots

    original_register_controller = IntegrationRuntime.register_controller

    @callback
    def register_controller(
        self: IntegrationRuntime, entity_id: str, controller: Any
    ) -> None:
        original_register_controller(self, entity_id, controller)
        _schedule_reconcile(self)

    IntegrationRuntime.register_controller = register_controller

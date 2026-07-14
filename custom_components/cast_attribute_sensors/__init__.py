"""Cast Metadata & TV Controls integration."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    ANDROID_TV_REMOTE_DOMAIN,
    ATTR_ACTIVITY,
    ATTR_APP_ID,
    ATTR_APP_NAME,
    ATTR_COMMAND,
    ATTR_SECONDS,
    DOMAIN,
    SERVICE_LAUNCH_CAST_APP,
    SERVICE_LAUNCH_TV_APP,
    SERVICE_REGISTER_TV_APP,
    SERVICE_RESTART_DEVICE,
    SERVICE_RUN_ACTIVITY,
    SERVICE_SEEK_RELATIVE,
    SERVICE_SEND_COMMAND,
)
from .identity import PhysicalIdentityStore
from .runtime import IntegrationRuntime
from .source_manager import SourceManager

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
]


def _entity_ids(call: ServiceCall) -> list[str]:
    value = call.data[ATTR_ENTITY_ID]
    return [value] if isinstance(value, str) else list(value)


def _controller(runtime: IntegrationRuntime, entity_id: str):
    controller = runtime.controllers.get(entity_id)
    if controller is None:
        raise ServiceValidationError(
            f"{entity_id} is not a Cast Metadata & TV Controls controller"
        )
    return controller


async def _async_cleanup_orphan_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove empty virtual devices retained by older entity layouts."""
    await asyncio.sleep(5)
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    used_device_ids = {
        entity.device_id
        for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if entity.device_id is not None
    }
    for device in list(device_registry.devices.values()):
        if entry.entry_id not in device.config_entries:
            continue
        if not any(identifier[0] == DOMAIN for identifier in device.identifiers):
            continue
        if device.id not in used_device_ids:
            device_registry.async_remove_device(device.id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the single integration hub."""
    manager = SourceManager(hass)
    identities = PhysicalIdentityStore(hass)
    await manager.async_initialize()
    await identities.async_initialize()
    runtime = IntegrationRuntime(hass=hass, entry=entry, manager=manager, identities=identities)
    runtime.refresh_groups()
    runtime.start_topology_watch()
    entry.runtime_data = runtime

    async def launch_cast_app(call: ServiceCall) -> None:
        app_id = call.data[ATTR_APP_ID].strip()
        for entity_id in _entity_ids(call):
            if entity_id in runtime.controllers:
                controller = _controller(runtime, entity_id)
                source_id = next((source_id for source_id in controller.group.source_ids if (source := manager.get_source(source_id)) is not None and source.is_cast), None)
            else:
                source_id = manager.source_id_for_entity(entity_id)
            source = manager.get_source(source_id) if source_id is not None else None
            if source is None or not source.is_cast:
                raise ServiceValidationError(f"{entity_id} has no Cast receiver")
            await manager.launch_cast_app(source_id, app_id)

    async def launch_tv_app(call: ServiceCall) -> None:
        app_id = call.data[ATTR_APP_ID].strip()
        for entity_id in _entity_ids(call):
            if entity_id in runtime.controllers:
                controller = _controller(runtime, entity_id)
                source_id = next((source_id for source_id in controller.group.source_ids if manager.platform(source_id) == ANDROID_TV_REMOTE_DOMAIN), None)
            else:
                source_id = manager.source_id_for_entity(entity_id)
            if source_id is None or manager.platform(source_id) != ANDROID_TV_REMOTE_DOMAIN:
                raise ServiceValidationError(f"{entity_id} has no Android TV Remote media player")
            await manager.launch_tv_app(source_id, app_id)

    async def register_tv_app(call: ServiceCall) -> None:
        app_id = call.data[ATTR_APP_ID].strip()
        app_name = call.data[ATTR_APP_NAME].strip()
        for entity_id in _entity_ids(call):
            if entity_id in runtime.controllers:
                source_ids = _controller(runtime, entity_id).group.source_ids
            else:
                source_id = manager.source_id_for_entity(entity_id)
                source_ids = (source_id,) if source_id else ()
            remote_id = next((source_id for source_id in source_ids if manager.platform(source_id) == ANDROID_TV_REMOTE_DOMAIN), None)
            if remote_id is None:
                raise ServiceValidationError(f"{entity_id} has no Android TV Remote media player")
            manager.register_app(remote_id, app_id, app_name)

    async def send_command(call: ServiceCall) -> None:
        command = call.data[ATTR_COMMAND].strip()
        for entity_id in _entity_ids(call):
            await _controller(runtime, entity_id).async_send_command(command)

    async def seek_relative(call: ServiceCall) -> None:
        seconds = float(call.data[ATTR_SECONDS])
        for entity_id in _entity_ids(call):
            await _controller(runtime, entity_id).async_seek_relative(seconds)

    async def restart_device(call: ServiceCall) -> None:
        for entity_id in _entity_ids(call):
            await _controller(runtime, entity_id).async_restart()

    async def run_activity(call: ServiceCall) -> None:
        activity = call.data[ATTR_ACTIVITY].strip()
        for entity_id in _entity_ids(call):
            await _controller(runtime, entity_id).async_run_activity(activity)

    app_schema = vol.Schema({
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_APP_ID): vol.All(cv.string, vol.Length(min=1)),
    })
    controller_schema: dict[Any, Any] = {vol.Required(ATTR_ENTITY_ID): cv.entity_ids}
    hass.services.async_register(DOMAIN, SERVICE_LAUNCH_CAST_APP, launch_cast_app, schema=app_schema)
    hass.services.async_register(DOMAIN, SERVICE_LAUNCH_TV_APP, launch_tv_app, schema=app_schema)
    hass.services.async_register(DOMAIN, SERVICE_REGISTER_TV_APP, register_tv_app, schema=vol.Schema({
        **controller_schema,
        vol.Required(ATTR_APP_ID): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_APP_NAME): vol.All(cv.string, vol.Length(min=1)),
    }))
    hass.services.async_register(DOMAIN, SERVICE_SEND_COMMAND, send_command, schema=vol.Schema({
        **controller_schema,
        vol.Required(ATTR_COMMAND): vol.All(cv.string, vol.Length(min=1)),
    }))
    hass.services.async_register(DOMAIN, SERVICE_SEEK_RELATIVE, seek_relative, schema=vol.Schema({
        **controller_schema,
        vol.Required(ATTR_SECONDS): vol.Coerce(float),
    }))
    hass.services.async_register(DOMAIN, SERVICE_RESTART_DEVICE, restart_device, schema=vol.Schema(controller_schema))
    hass.services.async_register(DOMAIN, SERVICE_RUN_ACTIVITY, run_activity, schema=vol.Schema({
        **controller_schema,
        vol.Required(ATTR_ACTIVITY): vol.All(cv.string, vol.Length(min=1)),
    }))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.async_create_task(_async_cleanup_orphan_devices(hass, entry), f"{DOMAIN}-orphan-cleanup")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the hub."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    for service in (
        SERVICE_LAUNCH_CAST_APP,
        SERVICE_LAUNCH_TV_APP,
        SERVICE_REGISTER_TV_APP,
        SERVICE_SEND_COMMAND,
        SERVICE_SEEK_RELATIVE,
        SERVICE_RESTART_DEVICE,
        SERVICE_RUN_ACTIVITY,
    ):
        hass.services.async_remove(DOMAIN, service)
    await entry.runtime_data.manager.async_stop()
    await entry.runtime_data.identities.async_stop()
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Rebuild generated controller entities while retaining metadata sensors."""
    registry = er.async_get(hass)
    if entry.version < 9:
        for entity in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
            if entity.domain in {"binary_sensor", "button", "event", "media_player", "number", "select", "switch"} or (entity.domain == "sensor" and entity.unique_id.startswith("v1|")):
                registry.async_remove(entity.entity_id)
        hass.config_entries.async_update_entry(entry, version=9)
    return True

"""Cast Metadata & TV Controls integration."""

from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_APP_ID,
    ATTR_COMMAND,
    DOMAIN,
    SERVICE_LAUNCH_APP,
    SERVICE_LAUNCH_TV_APP,
    SERVICE_SEND_TV_COMMAND,
)
from .manager import CastManager
from .tv_manager import TvManager

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
]


@dataclass(slots=True)
class CastAttributeRuntimeData:
    """Runtime data for Cast Metadata & TV Controls."""

    manager: CastManager
    tv_manager: TvManager


type CastAttributeConfigEntry = ConfigEntry[CastAttributeRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: CastAttributeConfigEntry
) -> bool:
    """Set up Cast Metadata & TV Controls from a config entry."""
    manager = CastManager(hass)
    tv_manager = TvManager(hass)
    await manager.async_initialize()
    await tv_manager.async_initialize()
    entry.runtime_data = CastAttributeRuntimeData(
        manager=manager, tv_manager=tv_manager
    )

    async def async_handle_launch_app(call: ServiceCall) -> None:
        """Launch an arbitrary Cast receiver app by app ID."""
        app_id: str = call.data[ATTR_APP_ID]
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        for entity_id in entity_ids:
            source_id = manager.get_source_id_for_entity_id(entity_id)
            if source_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a media_player from the native Cast integration"
                )
            await manager.async_launch_app(source_id, app_id)

    async def async_handle_launch_tv_app(call: ServiceCall) -> None:
        """Launch an Android/Google TV app by package ID."""
        app_id: str = call.data[ATTR_APP_ID]
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        for entity_id in entity_ids:
            source_id = tv_manager.get_source_id_for_entity_id(entity_id)
            if source_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a tracked native TV media_player"
                )
            await tv_manager.async_launch_app(source_id, app_id)

    async def async_handle_send_tv_command(call: ServiceCall) -> None:
        """Send an Android TV Remote key command."""
        command: str = call.data[ATTR_COMMAND]
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        for entity_id in entity_ids:
            source_id = tv_manager.get_source_id_for_entity_id(entity_id)
            if source_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a tracked native TV media_player"
                )
            await tv_manager.async_send_remote_command(source_id, command)

    entity_and_app_schema = vol.Schema(
        {
            vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
            vol.Required(ATTR_APP_ID): vol.All(cv.string, vol.Length(min=1)),
        }
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LAUNCH_APP,
        async_handle_launch_app,
        schema=entity_and_app_schema,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LAUNCH_TV_APP,
        async_handle_launch_tv_app,
        schema=entity_and_app_schema,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_TV_COMMAND,
        async_handle_send_tv_command,
        schema=vol.Schema(
            {
                vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
                vol.Required(ATTR_COMMAND): vol.All(cv.string, vol.Length(min=1)),
            }
        ),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CastAttributeConfigEntry
) -> bool:
    """Unload a Cast Metadata & TV Controls config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    for service in (
        SERVICE_LAUNCH_APP,
        SERVICE_LAUNCH_TV_APP,
        SERVICE_SEND_TV_COMMAND,
    ):
        hass.services.async_remove(DOMAIN, service)
    await entry.runtime_data.manager.async_stop()
    await entry.runtime_data.tv_manager.async_stop()
    return True


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
) -> bool:
    """Migrate old config-entry versions without user intervention."""
    if config_entry.version < 3:
        hass.config_entries.async_update_entry(config_entry, version=3)
    return True

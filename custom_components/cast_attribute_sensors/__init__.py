"""Cast Metadata & TV Controls integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_APP_ID,
    ATTR_APP_NAME,
    ATTR_COMMAND,
    ATTR_SECONDS,
    DOMAIN,
    SERVICE_LAUNCH_APP,
    SERVICE_LAUNCH_TV_APP,
    SERVICE_REGISTER_TV_APP,
    SERVICE_SEEK_RELATIVE,
    SERVICE_SEND_TV_COMMAND,
)
from .manager import CastManager
from .tv_manager import TvManager

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.MEDIA_PLAYER]


@dataclass(slots=True)
class CastAttributeRuntimeData:
    """Runtime data for Cast Metadata & TV Controls."""

    manager: CastManager
    tv_manager: TvManager


type CastAttributeConfigEntry = ConfigEntry[CastAttributeRuntimeData]


def _current_position(state) -> float | None:
    """Calculate a live position instead of using a stale Cast position."""
    if state is None:
        return None
    position = state.attributes.get("media_position")
    if not isinstance(position, (int, float)):
        return None
    result = float(position)
    updated_at = state.attributes.get("media_position_updated_at")
    parsed: datetime | None = None
    if isinstance(updated_at, datetime):
        parsed = updated_at
    elif isinstance(updated_at, str):
        parsed = dt_util.parse_datetime(updated_at)
    if state.state == MediaPlayerState.PLAYING and parsed is not None:
        result += max(0.0, (dt_util.utcnow() - parsed).total_seconds())
    duration = state.attributes.get("media_duration")
    if isinstance(duration, (int, float)) and duration > 0:
        result = min(result, float(duration))
    return max(0.0, result)


async def async_setup_entry(
    hass: HomeAssistant, entry: CastAttributeConfigEntry
) -> bool:
    """Set up Cast Metadata & TV Controls from a config entry."""
    manager = CastManager(hass)
    tv_manager = TvManager(hass)
    await manager.async_initialize()
    await tv_manager.async_initialize()
    entry.runtime_data = CastAttributeRuntimeData(manager=manager, tv_manager=tv_manager)

    async def async_handle_launch_app(call: ServiceCall) -> None:
        app_id: str = call.data[ATTR_APP_ID]
        for entity_id in call.data[ATTR_ENTITY_ID]:
            source_id = manager.get_source_id_for_entity_id(entity_id)
            if source_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a native Cast media_player"
                )
            await manager.async_launch_app(source_id, app_id)

    async def async_handle_launch_tv_app(call: ServiceCall) -> None:
        app_id: str = call.data[ATTR_APP_ID]
        for entity_id in call.data[ATTR_ENTITY_ID]:
            source_id = tv_manager.get_source_id_for_entity_id(entity_id)
            if source_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a tracked native TV media_player"
                )
            await tv_manager.async_launch_app(source_id, app_id)

    async def async_handle_register_tv_app(call: ServiceCall) -> None:
        app_id = call.data[ATTR_APP_ID].strip()
        app_name = call.data[ATTR_APP_NAME].strip()
        for entity_id in call.data[ATTR_ENTITY_ID]:
            source_id = tv_manager.get_source_id_for_entity_id(entity_id)
            if source_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a tracked native TV media_player"
                )
            tv_manager._learned_apps.setdefault(source_id, {})[app_id] = app_name
            tv_manager._async_schedule_save()
            state = tv_manager.get_source_state(source_id)
            tv_manager._async_notify_source(source_id, state, state)

    async def async_handle_send_tv_command(call: ServiceCall) -> None:
        command: str = call.data[ATTR_COMMAND]
        for entity_id in call.data[ATTR_ENTITY_ID]:
            source_id = tv_manager.get_source_id_for_entity_id(entity_id)
            if source_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a tracked native TV media_player"
                )
            await tv_manager.async_send_remote_command(source_id, command)

    async def async_handle_seek_relative(call: ServiceCall) -> None:
        seconds = float(call.data[ATTR_SECONDS])
        for entity_id in call.data[ATTR_ENTITY_ID]:
            source_id = manager.get_source_id_for_entity_id(entity_id)
            if source_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a native Cast media_player"
                )
            state = manager.get_source_state(source_id)
            position = _current_position(state)
            if position is None:
                raise ServiceValidationError(
                    f"{entity_id} is not reporting a media position"
                )
            target = max(0.0, position + seconds)
            duration = state.attributes.get("media_duration") if state else None
            if isinstance(duration, (int, float)) and duration > 0:
                target = min(target, float(duration))
            await manager.async_call_media_player(
                source_id, "media_seek", {"seek_position": target}
            )

    entity_and_app_schema = vol.Schema(
        {
            vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
            vol.Required(ATTR_APP_ID): vol.All(cv.string, vol.Length(min=1)),
        }
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LAUNCH_APP, async_handle_launch_app, schema=entity_and_app_schema
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LAUNCH_TV_APP,
        async_handle_launch_tv_app,
        schema=entity_and_app_schema,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REGISTER_TV_APP,
        async_handle_register_tv_app,
        schema=vol.Schema(
            {
                vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
                vol.Required(ATTR_APP_ID): vol.All(cv.string, vol.Length(min=1)),
                vol.Required(ATTR_APP_NAME): vol.All(cv.string, vol.Length(min=1)),
            }
        ),
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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEEK_RELATIVE,
        async_handle_seek_relative,
        schema=vol.Schema(
            {
                vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
                vol.Required(ATTR_SECONDS): vol.Coerce(float),
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
        SERVICE_REGISTER_TV_APP,
        SERVICE_SEND_TV_COMMAND,
        SERVICE_SEEK_RELATIVE,
    ):
        hass.services.async_remove(DOMAIN, service)
    await entry.runtime_data.manager.async_stop()
    await entry.runtime_data.tv_manager.async_stop()
    return True


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
) -> bool:
    """Remove obsolete generated entities before rebuilding consolidated controllers."""
    registry = er.async_get(hass)
    entries = list(er.async_entries_for_config_entry(registry, config_entry.entry_id))

    if config_entry.version < 4:
        for registry_entry in entries:
            if registry_entry.domain in {"button", "number", "select", "switch"}:
                registry.async_remove(registry_entry.entity_id)

    if config_entry.version < 5:
        for registry_entry in entries:
            if registry_entry.domain == "media_player":
                registry.async_remove(registry_entry.entity_id)

    if config_entry.version < 5:
        hass.config_entries.async_update_entry(config_entry, version=5)
    return True

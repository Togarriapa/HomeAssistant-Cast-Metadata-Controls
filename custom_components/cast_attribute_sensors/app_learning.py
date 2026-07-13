"""Runtime learning for newly discovered TV and Cast applications."""

from __future__ import annotations

import re

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import ANDROID_TV_REMOTE_DOMAIN
from .manager import CastManager
from .tv_manager import TvManager

_CAST_SESSION_MARKERS = ("ready to cast", "cast receiver", "chromecast built-in")
_GENERIC_NAMES = {"tv", "television", "androidtv", "googletv", "chromecast", "cast"}


def _normalized_name(state: State | None) -> str:
    name = str(state.attributes.get("friendly_name", "")) if state else ""
    name = re.sub(
        r"\b(android tv remote|google tv remote|remote|controller|media player|adb)\b",
        " ",
        name,
        flags=re.IGNORECASE,
    )
    return "".join(character for character in name.casefold() if character.isalnum())


def _same_physical_tv(
    hass: HomeAssistant,
    tv_manager: TvManager,
    first_source_id: str,
    second_source_id: str,
) -> bool:
    registry = er.async_get(hass)
    devices = dr.async_get(hass)

    def signature(source_id: str):
        entity_id = tv_manager.get_source_entity_id(source_id)
        entry = registry.async_get(entity_id) if entity_id else None
        device = devices.async_get(entry.device_id) if entry and entry.device_id else None
        return (
            entry.device_id if entry else None,
            frozenset(device.connections) if device else frozenset(),
            device.area_id if device else None,
            _normalized_name(tv_manager.get_source_state(source_id)),
        )

    first_device, first_connections, first_area, first_name = signature(first_source_id)
    second_device, second_connections, second_area, second_name = signature(second_source_id)

    if first_device and first_device == second_device:
        return True
    if first_connections and second_connections and first_connections & second_connections:
        return True
    return bool(
        first_name
        and first_name == second_name
        and first_name not in _GENERIC_NAMES
        and not (first_area and second_area and first_area != second_area)
    )


def async_setup_dynamic_app_learning(
    hass: HomeAssistant,
    cast_manager: CastManager,
    tv_manager: TvManager,
) -> CALLBACK_TYPE:
    """Learn applications and refresh source lists immediately."""

    @callback
    def async_handle_state_changed(event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        if new_state is None or not new_state.entity_id.startswith("media_player."):
            return

        app_id_value = new_state.attributes.get("app_id")
        if not isinstance(app_id_value, str) or not app_id_value.strip():
            return
        app_id = app_id_value.strip()

        app_name_value = new_state.attributes.get("app_name")
        app_name = (
            app_name_value.strip()
            if isinstance(app_name_value, str) and app_name_value.strip()
            else app_id
        )

        cast_source_id = cast_manager.get_source_id_for_entity_id(new_state.entity_id)
        if cast_source_id is not None:
            apps = cast_manager._learned_apps.setdefault(cast_source_id, {})
            changed = apps.get(app_id) != app_name
            apps[app_id] = app_name
            if changed:
                cast_manager._async_schedule_save()
            cast_manager._async_notify_source(cast_source_id, new_state, new_state)
            return

        tv_source_id = tv_manager.get_source_id_for_entity_id(new_state.entity_id)
        if tv_source_id is None:
            return
        if any(marker in app_name.casefold() for marker in _CAST_SESSION_MARKERS):
            return

        target_source_ids = {
            source_id
            for source_id in tv_manager.source_ids
            if tv_manager.get_source_platform(source_id) == ANDROID_TV_REMOTE_DOMAIN
            and _same_physical_tv(hass, tv_manager, tv_source_id, source_id)
        }
        if tv_manager.get_source_platform(tv_source_id) == ANDROID_TV_REMOTE_DOMAIN:
            target_source_ids.add(tv_source_id)

        for target_source_id in target_source_ids:
            apps = tv_manager._learned_apps.setdefault(target_source_id, {})
            changed = apps.get(app_id) != app_name
            apps[app_id] = app_name
            if changed:
                tv_manager._async_schedule_save()
            target_state = tv_manager.get_source_state(target_source_id)
            tv_manager._async_notify_source(target_source_id, target_state, target_state)

    return hass.bus.async_listen(EVENT_STATE_CHANGED, async_handle_state_changed)

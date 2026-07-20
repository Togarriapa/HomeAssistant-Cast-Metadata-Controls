"""Reliable V8.4 physical-device configuration flows.

This layer replaces the fragile entity selectors and synchronous options reload used by
older V8 releases.  It deliberately exposes only external entities, stores media-player
members through SourceManager, saves the options result first, and reloads the config
entry after Home Assistant has persisted the new options.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    BUTTON_DOMAIN,
    CONF_ACTIVITIES,
    CONF_APP_PREFERENCES,
    CONF_DELAYS,
    CONF_ENTITIES,
    CONF_GROUP_ID,
    CONF_GROUP_NAME,
    CONF_GROUPS,
    CONF_ROUTES,
    CONF_WOL,
    DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    REMOTE_DOMAIN,
)
from .merge_options import MANUAL_GROUP_PREFIX

_LOGGER = logging.getLogger(__name__)
_RELOAD_TASKS: dict[str, asyncio.Task[None]] = {}
_SUPPORTED_INVENTORY_DOMAINS = frozenset(
    {MEDIA_PLAYER_DOMAIN, REMOTE_DOMAIN, BUTTON_DOMAIN}
)


def _friendly_name(self, entity_id: str) -> str:
    state = self.hass.states.get(entity_id)
    if state is not None:
        value = state.attributes.get("friendly_name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity_id


def _external_media_options(self) -> list[selector.SelectOptionDict]:
    """Return every external media-player tracked by SourceManager."""
    runtime = self.config_entry.runtime_data
    registry = er.async_get(self.hass)
    options: list[selector.SelectOptionDict] = []
    for source_id in runtime.manager.source_ids:
        entity_id = runtime.manager.get_entity_id(source_id)
        if entity_id is None:
            continue
        entry = registry.async_get(entity_id)
        if (
            entry is None
            or entry.domain != MEDIA_PLAYER_DOMAIN
            or entry.platform == DOMAIN
            or entry.disabled_by is not None
        ):
            continue
        options.append(
            selector.SelectOptionDict(
                value=entity_id,
                label=(
                    f"{self._v840_friendly_name(entity_id)} · "
                    f"{entry.domain}/{entry.platform}"
                ),
            )
        )
    return sorted(options, key=lambda item: str(item["label"]).casefold())


def _inventory_options(self) -> list[selector.SelectOptionDict]:
    """Return every supported external entity; never expose generated controllers."""
    registry = er.async_get(self.hass)
    runtime = self.config_entry.runtime_data
    options: list[selector.SelectOptionDict] = []
    for entry in registry.entities.values():
        if (
            entry.domain not in _SUPPORTED_INVENTORY_DOMAINS
            or entry.platform == DOMAIN
            or entry.disabled_by is not None
        ):
            continue
        if (
            entry.domain == MEDIA_PLAYER_DOMAIN
            and runtime.manager.source_id_for_entity(entry.entity_id) is None
        ):
            continue
        options.append(
            selector.SelectOptionDict(
                value=entry.entity_id,
                label=(
                    f"{self._v840_friendly_name(entry.entity_id)} · "
                    f"{entry.domain}/{entry.platform}"
                ),
            )
        )
    return sorted(options, key=lambda item: str(item["label"]).casefold())


def _schedule_reload(self, expected_options: dict[str, Any]) -> None:
    """Reload only after Home Assistant has persisted the options-flow result."""
    entry = self.config_entry
    existing = _RELOAD_TASKS.get(entry.entry_id)
    if existing is not None and not existing.done():
        existing.cancel()

    async def reload_when_saved() -> None:
        try:
            for _ in range(60):
                if dict(entry.options) == expected_options:
                    break
                await asyncio.sleep(0.1)
            else:
                _LOGGER.error(
                    "Options for %s were not persisted before the reload timeout",
                    entry.entry_id,
                )
                return
            await self.hass.config_entries.async_reload(entry.entry_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Saved Cast Metadata options but failed to reload config entry %s",
                entry.entry_id,
            )
        finally:
            _RELOAD_TASKS.pop(entry.entry_id, None)

    _RELOAD_TASKS[entry.entry_id] = self.hass.async_create_task(
        reload_when_saved(), f"{DOMAIN}-options-reload-{entry.entry_id}"
    )


def _save_without_blocking_reload(self, **updates: Any) -> ConfigFlowResult:
    """Create a normal options result and reload outside the flow response."""
    data = dict(self.config_entry.options)
    data.setdefault(CONF_GROUPS, self._groups())
    data.setdefault(CONF_ROUTES, self._routes())
    data.setdefault(CONF_APP_PREFERENCES, self._preferences())
    data.setdefault(CONF_DELAYS, self._option_dict(CONF_DELAYS))
    data.setdefault(CONF_ACTIVITIES, self._activities())
    data.setdefault(CONF_WOL, self._option_dict(CONF_WOL))
    data.update(updates)

    # Bypass OptionsFlowWithReload.async_create_entry.  Reloading synchronously
    # caused the frontend's opaque "Unknown error occurred" response whenever a
    # platform took too long or failed to unload while a merge was being saved.
    result = OptionsFlow.async_create_entry(self, data=data)
    self._v840_schedule_reload(data)
    return result


def _media_source_ids(self, entity_ids: list[str]) -> list[str]:
    runtime = self.config_entry.runtime_data
    registry = er.async_get(self.hass)
    source_ids: list[str] = []
    for entity_id in entity_ids:
        entry = registry.async_get(entity_id)
        if (
            entry is None
            or entry.domain != MEDIA_PLAYER_DOMAIN
            or entry.platform == DOMAIN
        ):
            continue
        source_id = runtime.manager.source_id_for_entity(entity_id)
        if source_id is not None:
            source_ids.append(source_id)
    return list(dict.fromkeys(source_ids))


async def async_step_merge_sources(self, user_input=None):
    """Merge native sources without ever presenting our Controller entity."""
    runtime = self.config_entry.runtime_data
    errors: dict[str, str] = {}
    options = self._v840_external_media_options()
    if len(options) < 2:
        return self.async_abort(reason="not_enough_source_entities")

    if user_input is not None:
        raw = user_input.get(CONF_ENTITIES, [])
        entity_ids = [raw] if isinstance(raw, str) else list(raw)
        member_ids = self._v840_media_source_ids(entity_ids)
        if len(member_ids) < 2:
            errors[CONF_ENTITIES] = "two_entities_required"
        else:
            old_group_keys = {
                group.key
                for source_id in member_ids
                if (group := runtime.group_for_source(source_id)) is not None
            }
            try:
                return self._save_manual_merge(
                    member_ids=member_ids,
                    name=str(user_input.get(CONF_GROUP_NAME, "")).strip(),
                    old_group_keys=old_group_keys,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Failed to save advanced physical-device merge")
                errors["base"] = "merge_failed"

    return self.async_show_form(
        step_id="merge_sources",
        data_schema=vol.Schema(
            {
                vol.Optional(CONF_GROUP_NAME): selector.TextSelector(),
                vol.Required(CONF_ENTITIES): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, multiple=True)
                ),
            }
        ),
        errors=errors,
    )


async def async_step_edit_group_members(self, user_input=None):
    """Edit a manual group using validated external source entities only."""
    group_id = self._selected_manual_group_id or ""
    configured = next(
        (
            group
            for group in self._groups()
            if str(group.get(CONF_GROUP_ID, "")) == group_id
        ),
        None,
    )
    if configured is None:
        return self.async_abort(reason="group_not_found")

    current_members = [str(item) for item in configured.get("members", [])]
    current_entities = self._source_entity_ids(current_members)
    errors: dict[str, str] = {}
    if user_input is not None:
        raw = user_input.get(CONF_ENTITIES, [])
        entity_ids = [raw] if isinstance(raw, str) else list(raw)
        member_ids = self._v840_media_source_ids(entity_ids)
        if len(member_ids) < 2:
            errors[CONF_ENTITIES] = "two_entities_required"
        else:
            try:
                return self._save_manual_merge(
                    member_ids=member_ids,
                    name=str(user_input.get(CONF_GROUP_NAME, "")).strip(),
                    old_group_keys=[f"{MANUAL_GROUP_PREFIX}{group_id}"],
                    group_id=group_id,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Failed to edit merged physical device %s", group_id)
                errors["base"] = "merge_failed"

    return self.async_show_form(
        step_id="edit_group_members",
        data_schema=vol.Schema(
            {
                vol.Optional(
                    CONF_GROUP_NAME,
                    default=str(configured.get(CONF_GROUP_NAME, "")),
                ): selector.TextSelector(),
                vol.Required(
                    CONF_ENTITIES,
                    default=current_entities,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._v840_external_media_options(), multiple=True
                    )
                ),
            }
        ),
        errors=errors,
    )


async def async_step_device_entities_group(self, user_input=None):
    """Save the complete external entity inventory for one physical device."""
    runtime = self.config_entry.runtime_data
    group = runtime.group_by_key(self._selected_group_key or "")
    if group is None:
        return self.async_abort(reason="group_not_found")

    options = self._v840_inventory_options()
    allowed = {str(item["value"]) for item in options}
    defaults = [
        entity_id
        for entity_id in self._candidate_entities(group)
        if entity_id in allowed
    ]
    errors: dict[str, str] = {}
    if user_input is not None:
        raw = user_input.get(CONF_ENTITIES, [])
        selected = [raw] if isinstance(raw, str) else list(raw)
        selected = list(dict.fromkeys(str(item) for item in selected if item in allowed))
        if not self._v840_media_source_ids(selected):
            errors[CONF_ENTITIES] = "media_player_required"
        else:
            try:
                result = self._save_physical_device(
                    current_group=group,
                    selected_entities=selected,
                    name=str(user_input.get(CONF_GROUP_NAME, "")).strip(),
                )
                if result is not None:
                    return result
                errors[CONF_ENTITIES] = "media_player_required"
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Failed to save physical-device inventory for %s", group.key
                )
                errors["base"] = "inventory_save_failed"

    return self.async_show_form(
        step_id="device_entities_group",
        data_schema=vol.Schema(
            {
                vol.Optional(CONF_GROUP_NAME, default=group.name): selector.TextSelector(),
                vol.Required(CONF_ENTITIES, default=defaults): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, multiple=True)
                ),
            }
        ),
        description_placeholders={"name": group.name},
        errors=errors,
    )


def install_v840_options(flow_class: type) -> None:
    """Install V8.4 options behavior exactly once."""
    if getattr(flow_class, "_v840_options_installed", False):
        return
    flow_class._v840_options_installed = True
    flow_class._v840_friendly_name = _friendly_name
    flow_class._v840_external_media_options = _external_media_options
    flow_class._v840_inventory_options = _inventory_options
    flow_class._v840_schedule_reload = _schedule_reload
    flow_class._v840_media_source_ids = _media_source_ids
    flow_class._save = _save_without_blocking_reload
    flow_class.async_step_merge_sources = async_step_merge_sources
    flow_class.async_step_edit_group_members = async_step_edit_group_members
    flow_class.async_step_device_entities_group = async_step_device_entities_group

"""V8.3 options for selecting a remote provider per physical device."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_REMOTE_CONTROLS,
    CONF_REMOTE_ENTITY,
    CONF_REMOTE_PROFILE,
    REMOTE_DOMAIN,
)
from .universal_remote import PROFILE_AUTO, PROFILE_LABELS, profile_for_platform

_AUTOMATIC = "__automatic__"


def _remote_controls(self) -> dict[str, dict[str, str]]:
    value = self._option_dict(CONF_REMOTE_CONTROLS)
    return {
        str(group_key): {
            CONF_REMOTE_ENTITY: str(config.get(CONF_REMOTE_ENTITY, "")).strip(),
            CONF_REMOTE_PROFILE: str(
                config.get(CONF_REMOTE_PROFILE, PROFILE_AUTO)
            ).strip(),
        }
        for group_key, config in value.items()
        if isinstance(config, dict)
    }


def _remote_entity_options(self) -> list[selector.SelectOptionDict]:
    registry = er.async_get(self.hass)
    options = [
        selector.SelectOptionDict(value=_AUTOMATIC, label="Automatic detection")
    ]
    for entry in sorted(
        registry.entities.values(), key=lambda item: item.entity_id
    ):
        if entry.domain != REMOTE_DOMAIN or entry.disabled_by is not None:
            continue
        state = self.hass.states.get(entry.entity_id)
        name = (
            str(state.attributes.get("friendly_name", "")).strip()
            if state is not None
            else ""
        )
        options.append(
            selector.SelectOptionDict(
                value=entry.entity_id,
                label=f"{name or entry.entity_id} · {entry.platform}",
            )
        )
    return options


async def async_step_configure_remote(self, user_input=None):
    return await self._choose_group(
        "configure_remote", "remote_group", user_input
    )


async def async_step_remote_group(self, user_input=None):
    runtime = self.config_entry.runtime_data
    group = runtime.group_by_key(self._selected_group_key or "")
    if group is None:
        return self.async_abort(reason="group_not_found")

    controls = self._remote_controls()
    current = controls.get(group.key, {})
    current_entity = current.get(CONF_REMOTE_ENTITY) or _AUTOMATIC
    current_profile = current.get(CONF_REMOTE_PROFILE) or PROFILE_AUTO

    if user_input is not None:
        selected_entity = str(user_input[CONF_REMOTE_ENTITY]).strip()
        selected_profile = str(user_input[CONF_REMOTE_PROFILE]).strip()
        if selected_entity == _AUTOMATIC:
            controls.pop(group.key, None)
        else:
            registry = er.async_get(self.hass)
            entry = registry.async_get(selected_entity)
            if entry is not None and selected_profile == PROFILE_AUTO:
                selected_profile = profile_for_platform(entry.platform)
            controls[group.key] = {
                CONF_REMOTE_ENTITY: selected_entity,
                CONF_REMOTE_PROFILE: selected_profile,
            }
        return self._save(**{CONF_REMOTE_CONTROLS: controls})

    profile_options = [
        selector.SelectOptionDict(value=value, label=label)
        for value, label in PROFILE_LABELS.items()
    ]
    return self.async_show_form(
        step_id="remote_group",
        data_schema=vol.Schema(
            {
                vol.Required(
                    CONF_REMOTE_ENTITY, default=current_entity
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._remote_entity_options()
                    )
                ),
                vol.Required(
                    CONF_REMOTE_PROFILE, default=current_profile
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=profile_options)
                ),
            }
        ),
        description_placeholders={"name": group.name},
    )


def install_v83_options(flow_class: type) -> None:
    """Extend the installed V8 options flow with remote-provider controls."""
    original_init = flow_class.async_step_init
    original_remap = flow_class._remap_settings
    original_remove = flow_class._remove_settings

    async def async_step_init(self, user_input=None):
        result = await original_init(self, user_input)
        menu_options = list(result.get("menu_options", []))
        if "configure_remote" not in menu_options:
            index = (
                menu_options.index("configure_routes") + 1
                if "configure_routes" in menu_options
                else len(menu_options)
            )
            menu_options.insert(index, "configure_remote")
            result["menu_options"] = menu_options
        return result

    def _remap_settings(
        self, old_keys, new_key: str
    ) -> dict[str, Any]:
        updates = original_remap(self, old_keys, new_key)
        ordered = list(dict.fromkeys(str(key) for key in old_keys if key))
        if new_key not in ordered:
            ordered.insert(0, new_key)
        controls = self._remote_controls()
        selected = next(
            (dict(controls[key]) for key in ordered if key in controls),
            None,
        )
        for key in ordered:
            controls.pop(key, None)
        if selected:
            controls[new_key] = selected
        updates[CONF_REMOTE_CONTROLS] = controls
        return updates

    def _remove_settings(self, group_keys) -> dict[str, Any]:
        updates = original_remove(self, group_keys)
        controls = self._remote_controls()
        for key in group_keys:
            controls.pop(str(key), None)
        updates[CONF_REMOTE_CONTROLS] = controls
        return updates

    flow_class._remote_controls = _remote_controls
    flow_class._remote_entity_options = _remote_entity_options
    flow_class.async_step_init = async_step_init
    flow_class.async_step_configure_remote = async_step_configure_remote
    flow_class.async_step_remote_group = async_step_remote_group
    flow_class._remap_settings = _remap_settings
    flow_class._remove_settings = _remove_settings

"""V8 physical-device options layered onto the stable controller options flow."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_DELAYS,
    CONF_ENTITIES,
    CONF_GROUP_ID,
    CONF_GROUP_KEYS,
    CONF_GROUP_NAME,
    CONF_GROUPS,
    CONF_MEMBERS,
    CONF_WOL,
    DOMAIN,
    MEDIA_PLAYER_DOMAIN,
)
from .merge_options import (
    MANUAL_GROUP_PREFIX,
    merge_manual_group_configs,
    remap_group_settings,
    remove_group_settings,
)


def _group_options(self, *, detailed: bool = False):
    options: list[selector.SelectOptionDict] = []
    runtime = self.config_entry.runtime_data
    for group in runtime.groups:
        label = group.name
        if detailed:
            platforms = sorted(
                {
                    runtime.manager.platform(source_id) or "unknown"
                    for source_id in group.source_ids
                }
            )
            label = (
                f"{group.name} · {len(group.source_ids)} source entities · "
                f"{', '.join(platforms)}"
            )
        options.append(selector.SelectOptionDict(value=group.key, label=label))
    return options


def _manual_group_options(self):
    options: list[selector.SelectOptionDict] = []
    for index, group in enumerate(self._groups()):
        group_id = str(group.get(CONF_GROUP_ID, "")).strip()
        if not group_id:
            continue
        name = str(group.get(CONF_GROUP_NAME, "")).strip()
        count = len(group.get(CONF_MEMBERS, []))
        options.append(
            selector.SelectOptionDict(
                value=group_id,
                label=name or f"Merged device {index + 1} ({count} sources)",
            )
        )
    return options


def _source_entity_ids(self, source_ids: Iterable[str]) -> list[str]:
    runtime = self.config_entry.runtime_data
    return [
        entity_id
        for source_id in source_ids
        if (entity_id := runtime.manager.get_entity_id(source_id))
    ]


def _group_summary(self) -> str:
    runtime = self.config_entry.runtime_data
    manual_ids = {
        str(group.get(CONF_GROUP_ID, "")).strip() for group in self._groups()
    }
    lines: list[str] = []
    for group in runtime.groups:
        mode = (
            "manual"
            if group.key.startswith(MANUAL_GROUP_PREFIX)
            and group.key.removeprefix(MANUAL_GROUP_PREFIX) in manual_ids
            else "automatic"
        )
        entities = self._source_entity_ids(group.source_ids)
        lines.append(
            f"- **{group.name}** ({mode}, {len(group.source_ids)} sources): "
            + ", ".join(f"`{entity_id}`" for entity_id in entities)
        )
    return "\n".join(lines) or "- No supported media-player sources found."


def _remap_settings(self, old_keys: Iterable[str], new_key: str) -> dict[str, Any]:
    return remap_group_settings(
        old_keys=old_keys,
        new_key=new_key,
        routes=self._routes(),
        preferences=self._preferences(),
        delays=self._option_dict(CONF_DELAYS),
        activities=self._activities(),
        wol=self._option_dict(CONF_WOL),
    )


def _save_manual_merge(
    self,
    *,
    member_ids: Iterable[str],
    name: str,
    old_group_keys: Iterable[str],
    group_id: str | None = None,
) -> ConfigFlowResult:
    groups, target_id = merge_manual_group_configs(
        self._groups(),
        member_ids=member_ids,
        name=name,
        group_id=group_id,
    )
    target_key = f"{MANUAL_GROUP_PREFIX}{target_id}"
    updates = self._remap_settings(old_group_keys, target_key)
    updates[CONF_GROUPS] = groups
    return self._save(**updates)


def _remove_settings(self, group_keys: Iterable[str]) -> dict[str, Any]:
    return remove_group_settings(
        group_keys,
        routes=self._routes(),
        preferences=self._preferences(),
        delays=self._option_dict(CONF_DELAYS),
        activities=self._activities(),
        wol=self._option_dict(CONF_WOL),
    )


async def async_step_init(self, user_input=None):
    options = [
        "review_groups",
        "merge_devices",
        "merge_sources",
        "configure_routes",
        "manage_apps",
        "configure_timing",
        "configure_wol",
        "add_activity",
    ]
    if self._groups():
        options.extend(["edit_group", "remove_group", "clear_groups"])
    if self._routes():
        options.append("clear_routes")
    if self._preferences():
        options.append("clear_app_preferences")
    if any(self._activities().values()):
        options.extend(["remove_activity", "clear_activities"])
    return self.async_show_menu(step_id="init", menu_options=options)


async def async_step_review_groups(self, user_input=None):
    if user_input is not None:
        return await self.async_step_init()
    return self.async_show_form(
        step_id="review_groups",
        data_schema=vol.Schema({}),
        description_placeholders={"groups": self._group_summary()},
    )


async def async_step_merge_devices(self, user_input=None):
    runtime = self.config_entry.runtime_data
    if len(runtime.groups) < 2:
        return self.async_abort(reason="not_enough_devices")
    errors: dict[str, str] = {}
    if user_input is not None:
        selected_keys = user_input[CONF_GROUP_KEYS]
        if isinstance(selected_keys, str):
            selected_keys = [selected_keys]
        selected_groups = [
            group
            for key in dict.fromkeys(selected_keys)
            if (group := runtime.group_by_key(str(key))) is not None
        ]
        if len(selected_groups) < 2:
            errors[CONF_GROUP_KEYS] = "two_devices_required"
        else:
            member_ids = [
                source_id
                for group in selected_groups
                for source_id in group.source_ids
            ]
            existing_manual_id = next(
                (
                    group.key.removeprefix(MANUAL_GROUP_PREFIX)
                    for group in selected_groups
                    if group.key.startswith(MANUAL_GROUP_PREFIX)
                ),
                None,
            )
            name = str(user_input.get(CONF_GROUP_NAME, "")).strip()
            return self._save_manual_merge(
                member_ids=member_ids,
                name=name or selected_groups[0].name,
                old_group_keys=[group.key for group in selected_groups],
                group_id=existing_manual_id,
            )
    return self.async_show_form(
        step_id="merge_devices",
        data_schema=vol.Schema(
            {
                vol.Optional(CONF_GROUP_NAME): selector.TextSelector(),
                vol.Required(CONF_GROUP_KEYS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._group_options(detailed=True),
                        multiple=True,
                    )
                ),
            }
        ),
        errors=errors,
    )


async def async_step_merge_sources(self, user_input=None):
    runtime = self.config_entry.runtime_data
    errors: dict[str, str] = {}
    if user_input is not None:
        entity_ids = user_input[CONF_ENTITIES]
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        registry = er.async_get(self.hass)
        member_ids = [
            entry.id
            for entity_id in entity_ids
            if (entry := registry.async_get(entity_id)) is not None
            and entry.domain == MEDIA_PLAYER_DOMAIN
            and entry.platform != DOMAIN
        ]
        if len(set(member_ids)) < 2:
            errors[CONF_ENTITIES] = "two_entities_required"
        else:
            old_group_keys = {
                group.key
                for member_id in member_ids
                if (group := runtime.group_for_source(member_id)) is not None
            }
            return self._save_manual_merge(
                member_ids=member_ids,
                name=str(user_input.get(CONF_GROUP_NAME, "")).strip(),
                old_group_keys=old_group_keys,
            )
    return self.async_show_form(
        step_id="merge_sources",
        data_schema=vol.Schema(
            {
                vol.Optional(CONF_GROUP_NAME): selector.TextSelector(),
                vol.Required(CONF_ENTITIES): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=MEDIA_PLAYER_DOMAIN,
                        multiple=True,
                    )
                ),
            }
        ),
        errors=errors,
    )


async def async_step_add_group(self, user_input=None):
    """Keep old deep links/bookmarks working after the v8 menu rename."""
    return await self.async_step_merge_sources(user_input)


async def async_step_edit_group(self, user_input=None):
    if user_input is not None:
        self._selected_manual_group_id = str(user_input[CONF_GROUP_ID])
        return await self.async_step_edit_group_members()
    return self.async_show_form(
        step_id="edit_group",
        data_schema=vol.Schema(
            {
                vol.Required(CONF_GROUP_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._manual_group_options()
                    )
                )
            }
        ),
    )


async def async_step_edit_group_members(self, user_input=None):
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

    current_members = [str(item) for item in configured.get(CONF_MEMBERS, [])]
    current_entities = self._source_entity_ids(current_members)
    errors: dict[str, str] = {}
    if user_input is not None:
        entity_ids = user_input[CONF_ENTITIES]
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        registry = er.async_get(self.hass)
        member_ids = [
            entry.id
            for entity_id in entity_ids
            if (entry := registry.async_get(entity_id)) is not None
            and entry.domain == MEDIA_PLAYER_DOMAIN
            and entry.platform != DOMAIN
        ]
        if len(set(member_ids)) < 2:
            errors[CONF_ENTITIES] = "two_entities_required"
        else:
            old_key = f"{MANUAL_GROUP_PREFIX}{group_id}"
            return self._save_manual_merge(
                member_ids=member_ids,
                name=str(user_input.get(CONF_GROUP_NAME, "")).strip(),
                old_group_keys=[old_key],
                group_id=group_id,
            )
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
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=MEDIA_PLAYER_DOMAIN,
                        multiple=True,
                    )
                ),
            }
        ),
        errors=errors,
    )


async def async_step_remove_group(self, user_input=None):
    groups = self._groups()
    if user_input is not None:
        group_id = str(user_input[CONF_GROUP_ID])
        updates = self._remove_settings(
            [f"{MANUAL_GROUP_PREFIX}{group_id}"]
        )
        updates[CONF_GROUPS] = [
            group
            for group in groups
            if str(group.get(CONF_GROUP_ID, "")) != group_id
        ]
        return self._save(**updates)
    return self.async_show_form(
        step_id="remove_group",
        data_schema=vol.Schema(
            {
                vol.Required(CONF_GROUP_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._manual_group_options()
                    )
                )
            }
        ),
    )


async def async_step_clear_groups(self, user_input=None):
    if user_input is not None and user_input.get("confirm"):
        manual_keys = [
            f"{MANUAL_GROUP_PREFIX}{group.get(CONF_GROUP_ID)}"
            for group in self._groups()
            if group.get(CONF_GROUP_ID)
        ]
        updates = self._remove_settings(manual_keys)
        updates[CONF_GROUPS] = []
        return self._save(**updates)
    return self.async_show_form(
        step_id="clear_groups",
        data_schema=vol.Schema(
            {vol.Required("confirm", default=False): bool}
        ),
    )


def install_v8_options(flow_class: type) -> None:
    """Install v8 steps without duplicating the stable non-grouping flow code."""
    flow_class._selected_manual_group_id = None
    flow_class._group_options = _group_options
    flow_class._manual_group_options = _manual_group_options
    flow_class._source_entity_ids = _source_entity_ids
    flow_class._group_summary = _group_summary
    flow_class._remap_settings = _remap_settings
    flow_class._save_manual_merge = _save_manual_merge
    flow_class._remove_settings = _remove_settings
    flow_class.async_step_init = async_step_init
    flow_class.async_step_review_groups = async_step_review_groups
    flow_class.async_step_merge_devices = async_step_merge_devices
    flow_class.async_step_merge_sources = async_step_merge_sources
    flow_class.async_step_add_group = async_step_add_group
    flow_class.async_step_edit_group = async_step_edit_group
    flow_class.async_step_edit_group_members = async_step_edit_group_members
    flow_class.async_step_remove_group = async_step_remove_group
    flow_class.async_step_clear_groups = async_step_clear_groups

"""Config and options flows."""

from __future__ import annotations

from typing import Any, override
from uuid import uuid4

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ACTIVITIES,
    CONF_ACTIVITY_ID,
    CONF_ACTIVITY_MUTE,
    CONF_ACTIVITY_NAME,
    CONF_ACTIVITY_SOURCE,
    CONF_ACTIVITY_VOLUME,
    CONF_APP_KEY,
    CONF_APP_PREFERENCES,
    CONF_BROADCAST_ADDRESS,
    CONF_BROADCAST_PORT,
    CONF_DELAYS,
    CONF_DISPLAY_NAME,
    CONF_ENTITIES,
    CONF_FAVORITE,
    CONF_GROUP_ID,
    CONF_GROUP_KEY,
    CONF_GROUP_NAME,
    CONF_GROUPS,
    CONF_MAC,
    CONF_MEMBERS,
    CONF_ORDER,
    CONF_ROUTES,
    CONF_VISIBLE,
    CONF_WOL,
    DEFAULT_DELAYS,
    DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    NAME,
    ROUTE_KEYS,
)

_AUTOMATIC = "__automatic__"
_UNCHANGED = "unchanged"


class CastMetadataConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single hub entry."""

    VERSION = 9

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> ControllerOptionsFlow:
        return ControllerOptionsFlow()

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))


class ControllerOptionsFlow(OptionsFlowWithReload):
    """Configure grouping, routing, applications, activities, timing, and WOL."""

    _selected_group_key: str | None = None
    _selected_app_key: str | None = None

    def _option_dict(self, key: str) -> dict[str, Any]:
        value = self.config_entry.options.get(key, {})
        return dict(value) if isinstance(value, dict) else {}

    def _groups(self) -> list[dict[str, Any]]:
        value = self.config_entry.options.get(CONF_GROUPS, [])
        return [dict(group) for group in value] if isinstance(value, list) else []

    def _routes(self) -> dict[str, dict[str, str]]:
        return {str(key): dict(value) for key, value in self._option_dict(CONF_ROUTES).items() if isinstance(value, dict)}

    def _preferences(self) -> dict[str, dict[str, dict[str, Any]]]:
        return {
            str(group_key): {str(app_key): dict(pref) for app_key, pref in value.items() if isinstance(pref, dict)}
            for group_key, value in self._option_dict(CONF_APP_PREFERENCES).items()
            if isinstance(value, dict)
        }

    def _activities(self) -> dict[str, list[dict[str, Any]]]:
        return {
            str(group_key): [dict(item) for item in value if isinstance(item, dict)]
            for group_key, value in self._option_dict(CONF_ACTIVITIES).items()
            if isinstance(value, list)
        }

    def _save(self, **updates: Any) -> ConfigFlowResult:
        data = dict(self.config_entry.options)
        data.setdefault(CONF_GROUPS, self._groups())
        data.setdefault(CONF_ROUTES, self._routes())
        data.setdefault(CONF_APP_PREFERENCES, self._preferences())
        data.setdefault(CONF_DELAYS, self._option_dict(CONF_DELAYS))
        data.setdefault(CONF_ACTIVITIES, self._activities())
        data.setdefault(CONF_WOL, self._option_dict(CONF_WOL))
        data.update(updates)
        return self.async_create_entry(data=data)

    def _group_options(self) -> list[selector.SelectOptionDict]:
        return [selector.SelectOptionDict(value=group.key, label=group.name) for group in self.config_entry.runtime_data.groups]

    async def _choose_group(self, step_id: str, next_step: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        if user_input is not None:
            self._selected_group_key = str(user_input[CONF_GROUP_KEY])
            return await getattr(self, f"async_step_{next_step}")()
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_GROUP_KEY): selector.SelectSelector(selector.SelectSelectorConfig(options=self._group_options()))}),
        )

    @override
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        options = ["add_group", "configure_routes", "manage_apps", "configure_timing", "configure_wol", "add_activity"]
        if self._groups():
            options.extend(["remove_group", "clear_groups"])
        if self._routes():
            options.append("clear_routes")
        if self._preferences():
            options.append("clear_app_preferences")
        if any(self._activities().values()):
            options.extend(["remove_activity", "clear_activities"])
        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_add_group(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_ids = user_input[CONF_ENTITIES]
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            registry = er.async_get(self.hass)
            member_ids = [entry.id for entity_id in entity_ids if (entry := registry.async_get(entity_id)) is not None and entry.domain == MEDIA_PLAYER_DOMAIN and entry.platform != DOMAIN]
            if len(set(member_ids)) < 2:
                errors[CONF_ENTITIES] = "two_entities_required"
            else:
                groups = self._groups()
                groups.append({CONF_GROUP_ID: uuid4().hex, CONF_GROUP_NAME: str(user_input.get(CONF_GROUP_NAME, "")).strip(), CONF_MEMBERS: list(dict.fromkeys(member_ids))})
                return self._save(**{CONF_GROUPS: groups})
        return self.async_show_form(
            step_id="add_group",
            data_schema=vol.Schema({
                vol.Optional(CONF_GROUP_NAME): selector.TextSelector(),
                vol.Required(CONF_ENTITIES): selector.EntitySelector(selector.EntitySelectorConfig(domain=MEDIA_PLAYER_DOMAIN, multiple=True, reorder=True)),
            }),
            errors=errors,
        )

    async def async_step_remove_group(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        groups = self._groups()
        if user_input is not None:
            group_id = user_input[CONF_GROUP_ID]
            return self._save(**{CONF_GROUPS: [group for group in groups if group[CONF_GROUP_ID] != group_id]})
        options = [selector.SelectOptionDict(value=group[CONF_GROUP_ID], label=group.get(CONF_GROUP_NAME) or f"Group {index + 1} ({len(group.get(CONF_MEMBERS, []))} entities)") for index, group in enumerate(groups)]
        return self.async_show_form(step_id="remove_group", data_schema=vol.Schema({vol.Required(CONF_GROUP_ID): selector.SelectSelector(selector.SelectSelectorConfig(options=options))}))

    async def async_step_clear_groups(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None and user_input.get("confirm"):
            return self._save(**{CONF_GROUPS: []})
        return self.async_show_form(step_id="clear_groups", data_schema=vol.Schema({vol.Required("confirm", default=False): bool}))

    async def async_step_configure_routes(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._choose_group("configure_routes", "route_group", user_input)

    async def async_step_route_group(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        runtime = self.config_entry.runtime_data
        group = runtime.group_by_key(self._selected_group_key or "")
        if group is None:
            return self.async_abort(reason="group_not_found")
        current = self._routes().get(group.key, {})
        source_options = [selector.SelectOptionDict(value=_AUTOMATIC, label="Automatic")]
        for source_id in group.source_ids:
            entity_id = runtime.manager.get_entity_id(source_id)
            state = runtime.manager.get_state(source_id)
            if entity_id:
                name = str(state.attributes.get("friendly_name", "")).strip() if state else ""
                source_options.append(selector.SelectOptionDict(value=entity_id, label=f"{name or entity_id} · {runtime.manager.platform(source_id) or 'unknown'}"))
        if user_input is not None:
            routes = self._routes()
            selected: dict[str, str] = {}
            for capability in ROUTE_KEYS:
                entity_id = str(user_input.get(capability, _AUTOMATIC)).strip()
                source_id = runtime.manager.source_id_for_entity(entity_id) if entity_id != _AUTOMATIC else None
                if source_id in group.source_ids:
                    selected[capability] = source_id
            if selected:
                routes[group.key] = selected
            else:
                routes.pop(group.key, None)
            return self._save(**{CONF_ROUTES: routes})
        schema: dict[Any, Any] = {}
        for capability in ROUTE_KEYS:
            source_id = current.get(capability)
            entity_id = runtime.manager.get_entity_id(source_id) if source_id else _AUTOMATIC
            schema[vol.Optional(capability, default=entity_id or _AUTOMATIC)] = selector.SelectSelector(selector.SelectSelectorConfig(options=source_options))
        return self.async_show_form(step_id="route_group", data_schema=vol.Schema(schema), description_placeholders={"name": group.name})

    async def async_step_clear_routes(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None and user_input.get("confirm"):
            return self._save(**{CONF_ROUTES: {}})
        return self.async_show_form(step_id="clear_routes", data_schema=vol.Schema({vol.Required("confirm", default=False): bool}))

    async def async_step_manage_apps(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._choose_group("manage_apps", "choose_app", user_input)

    async def async_step_choose_app(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        runtime = self.config_entry.runtime_data
        controller = runtime.controller_for_group(self._selected_group_key or "")
        if controller is None:
            return self.async_abort(reason="group_not_found")
        catalog = controller.app_catalog()
        if user_input is not None:
            self._selected_app_key = str(user_input[CONF_APP_KEY])
            return await self.async_step_edit_app()
        options = [selector.SelectOptionDict(value=item["key"], label=f"{item['name']} · {item['kind']}") for item in catalog]
        return self.async_show_form(step_id="choose_app", data_schema=vol.Schema({vol.Required(CONF_APP_KEY): selector.SelectSelector(selector.SelectSelectorConfig(options=options))}))

    async def async_step_edit_app(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        group_key = self._selected_group_key or ""
        app_key = self._selected_app_key or ""
        preferences = self._preferences()
        current = preferences.get(group_key, {}).get(app_key, {})
        if user_input is not None:
            group_preferences = preferences.setdefault(group_key, {})
            preference = {CONF_DISPLAY_NAME: str(user_input.get(CONF_DISPLAY_NAME, "")).strip(), CONF_VISIBLE: bool(user_input.get(CONF_VISIBLE, True)), CONF_FAVORITE: bool(user_input.get(CONF_FAVORITE, False)), CONF_ORDER: int(user_input.get(CONF_ORDER, 1000))}
            if preference == {CONF_DISPLAY_NAME: "", CONF_VISIBLE: True, CONF_FAVORITE: False, CONF_ORDER: 1000}:
                group_preferences.pop(app_key, None)
            else:
                group_preferences[app_key] = preference
            if not group_preferences:
                preferences.pop(group_key, None)
            return self._save(**{CONF_APP_PREFERENCES: preferences})
        return self.async_show_form(
            step_id="edit_app",
            data_schema=vol.Schema({
                vol.Optional(CONF_DISPLAY_NAME, default=str(current.get(CONF_DISPLAY_NAME, ""))): selector.TextSelector(),
                vol.Required(CONF_VISIBLE, default=current.get(CONF_VISIBLE, True)): selector.BooleanSelector(),
                vol.Required(CONF_FAVORITE, default=current.get(CONF_FAVORITE, False)): selector.BooleanSelector(),
                vol.Required(CONF_ORDER, default=int(current.get(CONF_ORDER, 1000))): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=9999, step=1, mode=selector.NumberSelectorMode.BOX)),
            }),
        )

    async def async_step_clear_app_preferences(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None and user_input.get("confirm"):
            return self._save(**{CONF_APP_PREFERENCES: {}})
        return self.async_show_form(step_id="clear_app_preferences", data_schema=vol.Schema({vol.Required("confirm", default=False): bool}))

    async def async_step_configure_timing(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._choose_group("configure_timing", "timing_group", user_input)

    async def async_step_timing_group(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        group_key = self._selected_group_key or ""
        delays = self._option_dict(CONF_DELAYS)
        current = delays.get(group_key, DEFAULT_DELAYS)
        if user_input is not None:
            delays[group_key] = {key: float(user_input[key]) for key in DEFAULT_DELAYS}
            return self._save(**{CONF_DELAYS: delays})
        schema = {vol.Required(key, default=float(current.get(key, default))): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=30, step=0.05, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")) for key, default in DEFAULT_DELAYS.items()}
        return self.async_show_form(step_id="timing_group", data_schema=vol.Schema(schema))

    async def async_step_configure_wol(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._choose_group("configure_wol", "wol_group", user_input)

    async def async_step_wol_group(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        runtime = self.config_entry.runtime_data
        group = runtime.group_by_key(self._selected_group_key or "")
        if group is None:
            return self.async_abort(reason="group_not_found")
        wol = self._option_dict(CONF_WOL)
        current = wol.get(group.key, {})
        detected_mac = next((value for snapshot in runtime.manager.snapshots() if snapshot.registry_id in group.source_ids for connection_type, value in snapshot.connections if connection_type == "mac"), "")
        if user_input is not None:
            mac = str(user_input.get(CONF_MAC, "")).strip()
            if mac:
                wol[group.key] = {CONF_MAC: mac, CONF_BROADCAST_ADDRESS: str(user_input.get(CONF_BROADCAST_ADDRESS, "")).strip(), CONF_BROADCAST_PORT: int(user_input.get(CONF_BROADCAST_PORT, 9))}
            else:
                wol.pop(group.key, None)
            return self._save(**{CONF_WOL: wol})
        return self.async_show_form(
            step_id="wol_group",
            data_schema=vol.Schema({
                vol.Optional(CONF_MAC, default=str(current.get(CONF_MAC, detected_mac))): selector.TextSelector(),
                vol.Optional(CONF_BROADCAST_ADDRESS, default=str(current.get(CONF_BROADCAST_ADDRESS, "255.255.255.255"))): selector.TextSelector(),
                vol.Optional(CONF_BROADCAST_PORT, default=int(current.get(CONF_BROADCAST_PORT, 9))): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=65535, step=1, mode=selector.NumberSelectorMode.BOX)),
            }),
        )

    async def async_step_add_activity(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._choose_group("add_activity", "activity_group", user_input)

    async def async_step_activity_group(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        runtime = self.config_entry.runtime_data
        controller = runtime.controller_for_group(self._selected_group_key or "")
        if controller is None:
            return self.async_abort(reason="group_not_found")
        source_options = [selector.SelectOptionDict(value=_UNCHANGED, label="No source change")]
        source_options.extend(selector.SelectOptionDict(value=item["key"], label=item["label"]) for item in controller.action_catalog())
        if user_input is not None:
            name = str(user_input[CONF_ACTIVITY_NAME]).strip()
            activities = self._activities()
            group_activities = activities.setdefault(controller.group.key, [])
            group_activities = [item for item in group_activities if str(item.get(CONF_ACTIVITY_NAME, "")).casefold() != name.casefold()]
            mute_value = str(user_input.get(CONF_ACTIVITY_MUTE, _UNCHANGED))
            activity: dict[str, Any] = {CONF_ACTIVITY_ID: uuid4().hex, CONF_ACTIVITY_NAME: name, CONF_ACTIVITY_SOURCE: "" if user_input.get(CONF_ACTIVITY_SOURCE) == _UNCHANGED else str(user_input.get(CONF_ACTIVITY_SOURCE, "")), CONF_ACTIVITY_VOLUME: float(user_input.get(CONF_ACTIVITY_VOLUME, -1))}
            if mute_value != _UNCHANGED:
                activity[CONF_ACTIVITY_MUTE] = mute_value == "muted"
            group_activities.append(activity)
            activities[controller.group.key] = group_activities
            return self._save(**{CONF_ACTIVITIES: activities})
        return self.async_show_form(
            step_id="activity_group",
            data_schema=vol.Schema({
                vol.Required(CONF_ACTIVITY_NAME): selector.TextSelector(),
                vol.Optional(CONF_ACTIVITY_SOURCE, default=_UNCHANGED): selector.SelectSelector(selector.SelectSelectorConfig(options=source_options)),
                vol.Optional(CONF_ACTIVITY_VOLUME, default=-1): selector.NumberSelector(selector.NumberSelectorConfig(min=-1, max=100, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="%")),
                vol.Optional(CONF_ACTIVITY_MUTE, default=_UNCHANGED): selector.SelectSelector(selector.SelectSelectorConfig(options=[selector.SelectOptionDict(value=_UNCHANGED, label="No mute change"), selector.SelectOptionDict(value="muted", label="Muted"), selector.SelectOptionDict(value="unmuted", label="Unmuted")])),
            }),
        )

    async def async_step_remove_activity(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        activities = self._activities()
        options = [selector.SelectOptionDict(value=f"{group_key}::{item.get(CONF_ACTIVITY_ID)}", label=f"{self.config_entry.runtime_data.group_by_key(group_key).name if self.config_entry.runtime_data.group_by_key(group_key) else group_key} · {item.get(CONF_ACTIVITY_NAME)}") for group_key, items in activities.items() for item in items]
        if user_input is not None:
            group_key, activity_id = str(user_input[CONF_ACTIVITY_ID]).split("::", 1)
            activities[group_key] = [item for item in activities.get(group_key, []) if str(item.get(CONF_ACTIVITY_ID)) != activity_id]
            if not activities[group_key]:
                activities.pop(group_key, None)
            return self._save(**{CONF_ACTIVITIES: activities})
        return self.async_show_form(step_id="remove_activity", data_schema=vol.Schema({vol.Required(CONF_ACTIVITY_ID): selector.SelectSelector(selector.SelectSelectorConfig(options=options))}))

    async def async_step_clear_activities(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None and user_input.get("confirm"):
            return self._save(**{CONF_ACTIVITIES: {}})
        return self.async_show_form(step_id="clear_activities", data_schema=vol.Schema({vol.Required("confirm", default=False): bool}))

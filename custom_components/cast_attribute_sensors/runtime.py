"""Runtime model shared by platforms and service handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_GROUPS, CONF_MEMBERS, CONF_ROUTES, DOMAIN
from .grouping import PhysicalGroup, build_physical_groups
from .identity import PhysicalIdentityStore
from .source_manager import SourceManager

GroupCallback = Callable[[tuple[PhysicalGroup, ...]], None]


@dataclass(slots=True)
class IntegrationRuntime:
    """Runtime state for the single config entry."""

    hass: HomeAssistant
    entry: ConfigEntry
    manager: SourceManager
    identities: PhysicalIdentityStore
    groups: tuple[PhysicalGroup, ...] = ()
    controllers: dict[str, Any] = field(default_factory=dict)
    _topology_unsubscribe: CALLBACK_TYPE | None = None
    _reload_task: asyncio.Task[None] | None = None
    _fingerprint: tuple[tuple[str, tuple[str, ...]], ...] = ()
    _group_callbacks: set[GroupCallback] = field(default_factory=set)
    _active_issue_ids: set[str] = field(default_factory=set)

    def configured_groups(self) -> list[Mapping[str, Any]]:
        value = self.entry.options.get(CONF_GROUPS, [])
        return list(value) if isinstance(value, list) else []

    def configured_routes(self) -> dict[str, dict[str, str]]:
        value = self.entry.options.get(CONF_ROUTES, {})
        if not isinstance(value, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for group_key, routes in value.items():
            if isinstance(routes, dict):
                result[str(group_key)] = {
                    str(capability): str(source_id)
                    for capability, source_id in routes.items()
                    if source_id
                }
        return result

    @callback
    def refresh_groups(self) -> None:
        snapshots = self.manager.snapshots()
        raw_groups = build_physical_groups(snapshots, self.configured_groups())
        self.groups = self.identities.resolve_groups(raw_groups, snapshots)
        self._fingerprint = self.group_fingerprint()
        self.update_repairs()

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

    def route_source(self, group: PhysicalGroup, capability: str) -> str | None:
        source_id = self.configured_routes().get(group.key, {}).get(capability)
        return source_id if source_id in group.source_ids else None

    def device_info(self, group: PhysicalGroup) -> DeviceInfo:
        state = self.primary_state(group)
        name = (
            str(state.attributes.get("friendly_name", "")).strip()
            if state is not None
            else ""
        )
        return DeviceInfo(
            identifiers={(DOMAIN, group.key)},
            name=group.name or name or "Media device",
            manufacturer="Cast Metadata & TV Controls",
            model="Unified TV Controller" if group.is_tv else "Unified Cast Controller",
            configuration_url=(
                "https://github.com/Togarriapa/HomeAssistant-Cast-Metadata-Controls"
            ),
        )

    def health(self, group: PhysicalGroup) -> tuple[str, dict[str, Any]]:
        available = [
            source_id
            for source_id in group.source_ids
            if self.manager.available(source_id)
        ]
        unavailable = [
            source_id for source_id in group.source_ids if source_id not in available
        ]
        stale_routes = [
            capability
            for capability, source_id in self.configured_routes()
            .get(group.key, {})
            .items()
            if source_id not in group.source_ids
            or self.manager.get_source(source_id) is None
        ]
        if not available:
            status = "unavailable"
        elif unavailable or stale_routes:
            status = "degraded"
        else:
            status = "healthy"
        return status, {
            "physical_device_id": group.key,
            "source_count": len(group.source_ids),
            "available_source_count": len(available),
            "available_sources": [self.manager.get_entity_id(item) for item in available],
            "unavailable_sources": [
                self.manager.get_entity_id(item) or item for item in unavailable
            ],
            "platforms": sorted(
                {
                    platform
                    for source_id in group.source_ids
                    if (platform := self.manager.platform(source_id))
                }
            ),
            "configured_routes": self.configured_routes().get(group.key, {}),
            "stale_routes": stale_routes,
        }

    @callback
    def start_topology_watch(self) -> None:
        if self._topology_unsubscribe is not None:
            return
        self._topology_unsubscribe = self.manager.async_subscribe_topology(
            self._async_topology_changed
        )
        self.entry.async_on_unload(self._topology_unsubscribe)

    @callback
    def async_subscribe_group_additions(
        self, callback_func: GroupCallback
    ) -> CALLBACK_TYPE:
        self._group_callbacks.add(callback_func)

        @callback
        def unsubscribe() -> None:
            self._group_callbacks.discard(callback_func)

        return unsubscribe

    @callback
    def _async_topology_changed(self) -> None:
        snapshots = self.manager.snapshots()
        raw_groups = build_physical_groups(snapshots, self.configured_groups())
        candidate = self.identities.resolve_groups(raw_groups, snapshots)
        fingerprint = tuple((group.key, group.source_ids) for group in candidate)
        if fingerprint == self._fingerprint:
            return

        old_by_key = {group.key: group for group in self.groups}
        new_by_key = {group.key: group for group in candidate}
        added = tuple(
            group for key, group in new_by_key.items() if key not in old_by_key
        )
        removed = set(old_by_key) - set(new_by_key)
        changed = {
            key
            for key in set(old_by_key) & set(new_by_key)
            if old_by_key[key].source_ids != new_by_key[key].source_ids
        }
        self.groups = candidate
        self._fingerprint = fingerprint
        self.update_repairs()

        # A completely new independent device can be hot-added without taking any
        # existing controller offline. Membership changes still reload because
        # Home Assistant must move existing sensor registry entries between devices.
        if added and not removed and not changed:
            for callback_func in tuple(self._group_callbacks):
                callback_func(added)
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

    @callback
    def update_repairs(self) -> None:
        desired: set[str] = set()
        for configured in self.configured_groups():
            group_id = str(configured.get("group_id", "")).strip()
            if not group_id:
                continue
            missing = [
                source_id
                for source_id in configured.get(CONF_MEMBERS, [])
                if self.manager.get_source(str(source_id)) is None
                or self.manager.get_entity_id(str(source_id)) is None
            ]
            issue_id = f"missing_group_members_{group_id}"
            if missing:
                desired.add(issue_id)
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    is_persistent=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="group_members_missing",
                    translation_placeholders={
                        "name": str(configured.get("name") or group_id),
                        "count": str(len(missing)),
                    },
                    learn_more_url=(
                        "https://github.com/Togarriapa/"
                        "HomeAssistant-Cast-Metadata-Controls#physical-device-grouping"
                    ),
                )

        for group_key, routes in self.configured_routes().items():
            stale = [
                capability
                for capability, source_id in routes.items()
                if self.manager.get_source(source_id) is None
                or self.manager.get_entity_id(source_id) is None
            ]
            issue_id = f"stale_routes_{group_key.replace(':', '_')}"
            if stale:
                desired.add(issue_id)
                group = self.group_by_key(group_key)
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    is_persistent=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="route_source_missing",
                    translation_placeholders={
                        "name": group.name if group else group_key,
                        "capabilities": ", ".join(stale),
                    },
                    learn_more_url=(
                        "https://github.com/Togarriapa/"
                        "HomeAssistant-Cast-Metadata-Controls#capability-routing"
                    ),
                )

        for issue_id in self._active_issue_ids - desired:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._active_issue_ids = desired

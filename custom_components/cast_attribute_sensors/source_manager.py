"""Unified discovery, state tracking, storage, and native actions."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_added_domain,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store

from .const import (
    ANDROID_TV_REMOTE_DOMAIN,
    BUTTON_DOMAIN,
    CAST_DOMAIN,
    DEFAULT_ANDROID_TV_APPS,
    DEFAULT_CAST_APPS,
    DOMAIN,
    LEGACY_CAST_STORAGE_KEY,
    LEGACY_TV_STORAGE_KEY,
    MEDIA_PLAYER_DOMAIN,
    REMOTE_DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    TV_PLATFORMS,
)
from .grouping import SourceSnapshot

SourceUpdateCallback = Callable[[str, State | None, State | None], None]
TopologyCallback = Callable[[], None]


@dataclass(slots=True)
class MediaSource:
    """A native media-player entity tracked by registry ID."""

    registry_id: str
    platform: str
    config_entry_id: str | None
    device_id: str | None
    entity_id: str | None = None
    is_cast: bool = False
    is_tv: bool = False
    unsubscribe: CALLBACK_TYPE | None = None


class SourceManager:
    """Track all Cast and TV representations without tracking our own proxies."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.entity_registry = er.async_get(hass)
        self.device_registry = dr.async_get(hass)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._legacy_cast_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, LEGACY_CAST_STORAGE_KEY
        )
        self._legacy_tv_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, LEGACY_TV_STORAGE_KEY
        )
        self._sources: dict[str, MediaSource] = {}
        self._source_callbacks: dict[str, set[SourceUpdateCallback]] = defaultdict(set)
        self._topology_callbacks: set[TopologyCallback] = set()
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._learned_apps: dict[str, dict[str, str]] = {}
        self._save_task: asyncio.Task[None] | None = None
        self._started = False

    async def async_initialize(self) -> None:
        """Load current and legacy app metadata, then begin discovery."""
        stored_values = await asyncio.gather(
            self._legacy_cast_store.async_load(),
            self._legacy_tv_store.async_load(),
            self._store.async_load(),
        )
        for stored in stored_values:
            if not isinstance(stored, dict):
                continue
            raw_apps = stored.get("apps", {})
            if not isinstance(raw_apps, dict):
                continue
            for source_id, apps in raw_apps.items():
                if not isinstance(apps, dict):
                    continue
                learned = self._learned_apps.setdefault(str(source_id), {})
                learned.update(
                    {str(app_id): str(app_name) for app_id, app_name in apps.items()}
                )
        self.async_start()

    @callback
    def async_start(self) -> None:
        if self._started:
            return
        self._started = True
        self._async_rescan_sources()
        self._unsubscribers.append(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED,
                self._async_handle_entity_registry_updated,
            )
        )
        self._unsubscribers.append(
            async_track_state_added_domain(
                self.hass,
                MEDIA_PLAYER_DOMAIN,
                self._async_handle_media_player_added,
            )
        )

    async def async_stop(self) -> None:
        self._started = False
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        for source in self._sources.values():
            if source.unsubscribe is not None:
                source.unsubscribe()
                source.unsubscribe = None
        if self._save_task is not None and not self._save_task.done():
            self._save_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._save_task
        await self._store.async_save({"apps": self._learned_apps})

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(self._sources)

    @callback
    def async_subscribe_topology(
        self, callback_func: TopologyCallback
    ) -> CALLBACK_TYPE:
        self._topology_callbacks.add(callback_func)

        @callback
        def unsubscribe() -> None:
            self._topology_callbacks.discard(callback_func)

        return unsubscribe

    @callback
    def async_subscribe_source(
        self, source_id: str, callback_func: SourceUpdateCallback
    ) -> CALLBACK_TYPE:
        self._source_callbacks[source_id].add(callback_func)

        @callback
        def unsubscribe() -> None:
            callbacks = self._source_callbacks.get(source_id)
            if callbacks is None:
                return
            callbacks.discard(callback_func)
            if not callbacks:
                self._source_callbacks.pop(source_id, None)

        return unsubscribe

    @callback
    def _classify(self, entry: er.RegistryEntry) -> tuple[bool, bool] | None:
        if entry.domain != MEDIA_PLAYER_DOMAIN or entry.platform == DOMAIN:
            return None
        is_cast = entry.platform == CAST_DOMAIN
        registry_device_class = getattr(entry, "device_class", None) or getattr(
            entry, "original_device_class", None
        )
        state = self.hass.states.get(entry.entity_id)
        state_device_class = state.attributes.get("device_class") if state else None
        is_tv = (
            entry.platform in TV_PLATFORMS
            or registry_device_class == "tv"
            or state_device_class == "tv"
        )
        return (is_cast, is_tv) if is_cast or is_tv else None

    @callback
    def _async_rescan_sources(self) -> None:
        previous_signature = self.topology_signature()
        current_ids: set[str] = set()
        for entry in self.entity_registry.entities.values():
            classification = self._classify(entry)
            if classification is None:
                continue
            current_ids.add(entry.id)
            self._async_register_or_update(entry, *classification)

        removed = False
        for source_id, source in self._sources.items():
            if source_id in current_ids or source.entity_id is None:
                continue
            old_state = self.get_state(source_id)
            self._async_set_entity_id(source, None)
            self._async_notify_source(source_id, old_state, None)
            removed = True

        if removed or previous_signature != self.topology_signature():
            self._async_notify_topology()

    @callback
    def _async_register_or_update(
        self, entry: er.RegistryEntry, is_cast: bool, is_tv: bool
    ) -> None:
        source = self._sources.get(entry.id)
        is_new = source is None
        if source is None:
            source = MediaSource(
                registry_id=entry.id,
                platform=entry.platform,
                config_entry_id=entry.config_entry_id,
                device_id=entry.device_id,
                is_cast=is_cast,
                is_tv=is_tv,
            )
            self._sources[entry.id] = source
        else:
            source.platform = entry.platform
            source.config_entry_id = entry.config_entry_id
            source.device_id = entry.device_id
            source.is_cast = is_cast
            source.is_tv = is_tv

        if source.entity_id != entry.entity_id:
            old_state = self.get_state(entry.id)
            self._async_set_entity_id(source, entry.entity_id)
            new_state = self.get_state(entry.id)
            self._async_learn_active_app(entry.id, new_state)
            self._async_notify_source(entry.id, old_state, new_state)
        if is_new:
            self._async_notify_topology()

    @callback
    def _async_set_entity_id(self, source: MediaSource, entity_id: str | None) -> None:
        if source.unsubscribe is not None:
            source.unsubscribe()
            source.unsubscribe = None
        source.entity_id = entity_id
        if entity_id is None:
            return

        @callback
        def handle(event: Event[EventStateChangedData]) -> None:
            old_state = event.data["old_state"]
            new_state = event.data["new_state"]
            apps_changed = self._async_learn_active_app(source.registry_id, new_state)
            self._async_notify_source(source.registry_id, old_state, new_state)
            if apps_changed:
                self._async_notify_source(source.registry_id, new_state, new_state)

        source.unsubscribe = async_track_state_change_event(
            self.hass, entity_id, handle
        )

    @callback
    def _async_handle_media_player_added(
        self, event: Event[EventStateChangedData]
    ) -> None:
        new_state = event.data["new_state"]
        if new_state is None:
            return
        entry = self.entity_registry.async_get(new_state.entity_id)
        if entry is None:
            return
        classification = self._classify(entry)
        if classification is not None:
            self._async_register_or_update(entry, *classification)

    @callback
    def _async_handle_entity_registry_updated(self, event: Event) -> None:
        entity_id = str(event.data.get("entity_id", ""))
        old_entity_id = str(event.data.get("old_entity_id", ""))
        if entity_id.startswith("media_player.") or old_entity_id.startswith(
            "media_player."
        ):
            self._async_rescan_sources()

    @callback
    def _async_notify_source(
        self, source_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        for callback_func in tuple(self._source_callbacks.get(source_id, ())):
            callback_func(source_id, old_state, new_state)

    @callback
    def _async_notify_topology(self) -> None:
        for callback_func in tuple(self._topology_callbacks):
            callback_func()

    @callback
    def _async_learn_active_app(self, source_id: str, state: State | None) -> bool:
        if state is None:
            return False
        app_id_value = state.attributes.get("app_id")
        if not isinstance(app_id_value, str) or not app_id_value.strip():
            return False
        app_id = app_id_value.strip()
        app_name_value = state.attributes.get("app_name")
        app_name = (
            app_name_value.strip()
            if isinstance(app_name_value, str) and app_name_value.strip()
            else app_id
        )
        apps = self._learned_apps.setdefault(source_id, {})
        if apps.get(app_id) == app_name:
            return False
        apps[app_id] = app_name
        self._async_schedule_save()
        return True

    @callback
    def register_app(self, source_id: str, app_id: str, app_name: str) -> None:
        apps = self._learned_apps.setdefault(source_id, {})
        apps[app_id] = app_name
        self._async_schedule_save()
        state = self.get_state(source_id)
        self._async_notify_source(source_id, state, state)

    @callback
    def _async_schedule_save(self) -> None:
        if self._save_task is not None and not self._save_task.done():
            return
        self._save_task = self.hass.async_create_task(
            self._async_delayed_save(), f"{STORAGE_KEY}-save"
        )

    async def _async_delayed_save(self) -> None:
        await asyncio.sleep(1)
        await self._store.async_save({"apps": self._learned_apps})

    @callback
    def topology_signature(self) -> tuple[tuple[Any, ...], ...]:
        return tuple(
            sorted(
                (
                    source.registry_id,
                    source.entity_id,
                    source.platform,
                    source.device_id,
                    source.is_cast,
                    source.is_tv,
                )
                for source in self._sources.values()
                if source.entity_id is not None
            )
        )

    @callback
    def snapshots(self) -> tuple[SourceSnapshot, ...]:
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
                    connections=frozenset(device.connections)
                    if device
                    else frozenset(),
                    area_id=(device.area_id if device else None)
                    or (entry.area_id if entry else None),
                    is_cast=source.is_cast,
                    is_tv=source.is_tv,
                )
            )
        return tuple(snapshots)

    def get_source(self, source_id: str) -> MediaSource | None:
        return self._sources.get(source_id)

    def get_entity_id(self, source_id: str) -> str | None:
        source = self._sources.get(source_id)
        return source.entity_id if source else None

    def source_id_for_entity(self, entity_id: str) -> str | None:
        return next(
            (
                source.registry_id
                for source in self._sources.values()
                if source.entity_id == entity_id
            ),
            None,
        )

    def get_state(self, source_id: str) -> State | None:
        entity_id = self.get_entity_id(source_id)
        return self.hass.states.get(entity_id) if entity_id else None

    def available(self, source_id: str) -> bool:
        state = self.get_state(source_id)
        return state is not None and state.state != STATE_UNAVAILABLE

    def supports(self, source_id: str, feature: MediaPlayerEntityFeature) -> bool:
        state = self.get_state(source_id)
        supported = state.attributes.get("supported_features", 0) if state else 0
        return isinstance(supported, int) and bool(supported & int(feature))

    def platform(self, source_id: str) -> str | None:
        source = self._sources.get(source_id)
        return source.platform if source else None

    def cast_apps(self, source_id: str) -> dict[str, str]:
        apps = dict(DEFAULT_CAST_APPS)
        apps.update(self._learned_apps.get(source_id, {}))
        return apps

    def tv_apps(self, source_id: str) -> dict[str, str]:
        source = self._sources.get(source_id)
        if source is None or source.platform != ANDROID_TV_REMOTE_DOMAIN:
            return {}
        apps = dict(DEFAULT_ANDROID_TV_APPS)
        if source.config_entry_id:
            entry = self.hass.config_entries.async_get_entry(source.config_entry_id)
            configured = entry.options.get("apps", {}) if entry else {}
            if isinstance(configured, Mapping):
                for app_id, app_data in configured.items():
                    if isinstance(app_data, Mapping):
                        name = app_data.get("app_name")
                        apps[str(app_id)] = str(name or app_id)
        apps.update(self._learned_apps.get(source_id, {}))
        return apps

    def sources(self, source_id: str) -> list[str]:
        state = self.get_state(source_id)
        values = state.attributes.get("source_list") if state else None
        if not isinstance(values, (list, tuple)):
            return []
        return [str(value) for value in values if str(value).strip()]

    async def call_media_player(
        self, source_id: str, service: str, data: dict[str, Any] | None = None
    ) -> None:
        entity_id = self.get_entity_id(source_id)
        if entity_id is None:
            raise HomeAssistantError("Source is no longer available")
        service_data: dict[str, Any] = {ATTR_ENTITY_ID: entity_id}
        if data:
            service_data.update(data)
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN, service, service_data, blocking=True
        )

    async def launch_cast_app(self, source_id: str, app_id: str) -> None:
        await self.call_media_player(
            source_id,
            "play_media",
            {
                "media": {
                    "media_content_type": CAST_DOMAIN,
                    "media_content_id": json.dumps(
                        {"app_id": app_id.strip()}, separators=(",", ":")
                    ),
                }
            },
        )

    async def launch_tv_app(self, source_id: str, app_id: str) -> None:
        if self.platform(source_id) != ANDROID_TV_REMOTE_DOMAIN:
            raise HomeAssistantError("TV app launch requires Android TV Remote")
        await self.call_media_player(
            source_id,
            "play_media",
            {
                "media": {
                    "media_content_type": "app",
                    "media_content_id": app_id.strip(),
                }
            },
        )

    def remote_entity_id(self, source_ids: tuple[str, ...]) -> str | None:
        """Resolve the Android TV remote linked to one physical TV safely."""
        sources = [
            source
            for source_id in source_ids
            if (source := self._sources.get(source_id)) is not None
        ]
        config_entry_ids = {
            source.config_entry_id for source in sources if source.config_entry_id
        }
        device_ids = {source.device_id for source in sources if source.device_id}
        source_devices = [
            device
            for device_id in device_ids
            if (device := self.device_registry.async_get(device_id)) is not None
        ]
        connections = {
            connection
            for device in source_devices
            for connection in device.connections
        }
        areas = {device.area_id for device in source_devices if device.area_id}

        candidates: list[tuple[int, str]] = []
        for entry in self.entity_registry.entities.values():
            if (
                entry.domain != REMOTE_DOMAIN
                or entry.platform != ANDROID_TV_REMOTE_DOMAIN
                or entry.disabled_by is not None
            ):
                continue
            score = 0
            if entry.device_id in device_ids:
                score = max(score, 120)
            if entry.config_entry_id in config_entry_ids:
                score = max(score, 100)
            device = (
                self.device_registry.async_get(entry.device_id)
                if entry.device_id is not None
                else None
            )
            if device is not None and connections & set(device.connections):
                score = max(score, 110)
            if device is not None and device.area_id in areas:
                score = max(score, 20)
            candidates.append((score, entry.entity_id))

        if not candidates:
            return None
        best_score = max(score for score, _ in candidates)
        if best_score > 0:
            best = [entity_id for score, entity_id in candidates if score == best_score]
            return best[0] if len(best) == 1 else None
        return candidates[0][1] if len(candidates) == 1 else None

    def android_tv_remote_source_id(
        self, source_ids: tuple[str, ...]
    ) -> str | None:
        """Resolve the companion Android TV Remote media player."""
        direct = next(
            (
                source_id
                for source_id in source_ids
                if self.platform(source_id) == ANDROID_TV_REMOTE_DOMAIN
            ),
            None,
        )
        if direct is not None:
            return direct

        remote_entity_id = self.remote_entity_id(source_ids)
        remote_entry = (
            self.entity_registry.async_get(remote_entity_id)
            if remote_entity_id is not None
            else None
        )
        matches = [
            source.registry_id
            for source in self._sources.values()
            if source.platform == ANDROID_TV_REMOTE_DOMAIN
            and source.entity_id is not None
            and remote_entry is not None
            and (
                source.config_entry_id == remote_entry.config_entry_id
                or (
                    source.device_id is not None
                    and source.device_id == remote_entry.device_id
                )
            )
        ]
        if len(matches) == 1:
            return matches[0]

        available = [
            source.registry_id
            for source in self._sources.values()
            if source.platform == ANDROID_TV_REMOTE_DOMAIN
            and source.entity_id is not None
        ]
        return available[0] if len(available) == 1 else None

    async def send_command(self, source_ids: tuple[str, ...], command: str) -> None:
        remote_entity_id = self.remote_entity_id(source_ids)
        if remote_entity_id is None:
            raise HomeAssistantError("No Android TV Remote entity is linked")
        await self.hass.services.async_call(
            REMOTE_DOMAIN,
            "send_command",
            {ATTR_ENTITY_ID: remote_entity_id, "command": command.strip()},
            blocking=True,
        )

    def restart_button_entity_id(self, source_ids: tuple[str, ...]) -> str | None:
        device_ids = {
            source.device_id
            for source_id in source_ids
            if (source := self._sources.get(source_id)) is not None
            and source.device_id is not None
        }
        for entry in self.entity_registry.entities.values():
            device_class = getattr(entry, "device_class", None) or getattr(
                entry, "original_device_class", None
            )
            if (
                entry.domain == BUTTON_DOMAIN
                and entry.device_id in device_ids
                and device_class == "restart"
            ):
                return entry.entity_id
        return None

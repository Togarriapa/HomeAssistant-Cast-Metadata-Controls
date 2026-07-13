"""Discovery and control helpers for native TV media-player entities."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_added_domain,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store

from .const import (
    ANDROID_TV_REMOTE_DOMAIN,
    DEFAULT_ANDROID_TV_APPS,
    MEDIA_PLAYER_DOMAIN,
    REMOTE_DOMAIN,
    STORAGE_VERSION,
    TV_STORAGE_KEY,
)

TvUpdateCallback = Callable[[str, State | None, State | None], None]
TvAddedCallback = Callable[[str], None]


@dataclass(slots=True)
class TvSource:
    """A tracked native TV media-player registry entry."""

    registry_id: str
    platform: str
    config_entry_id: str | None
    device_id: str | None
    entity_id: str | None = None
    unsubscribe: CALLBACK_TYPE | None = None


class TvManager:
    """Track TV media players and expose capability-aware actions."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the TV manager."""
        self.hass = hass
        self._entity_registry = er.async_get(hass)
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, TV_STORAGE_KEY
        )
        self._sources: dict[str, TvSource] = {}
        self._source_callbacks: dict[str, set[TvUpdateCallback]] = defaultdict(set)
        self._source_added_callbacks: set[TvAddedCallback] = set()
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._learned_apps: dict[str, dict[str, str]] = {}
        self._save_task: asyncio.Task[None] | None = None
        self._started = False

    async def async_initialize(self) -> None:
        """Load persisted app data and begin TV source discovery."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            raw_apps = stored.get("apps", {})
            if isinstance(raw_apps, dict):
                self._learned_apps = {
                    str(source_id): {
                        str(app_id): str(app_name)
                        for app_id, app_name in source_apps.items()
                    }
                    for source_id, source_apps in raw_apps.items()
                    if isinstance(source_apps, dict)
                }
        self.async_start()

    @callback
    def async_start(self) -> None:
        """Start registry and state tracking."""
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
        """Stop tracking and flush learned TV applications."""
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
        """Return all known native TV source registry IDs."""
        return tuple(self._sources)

    @callback
    def async_subscribe_source_added(
        self, callback_func: TvAddedCallback
    ) -> CALLBACK_TYPE:
        """Subscribe to newly discovered TV sources."""
        self._source_added_callbacks.add(callback_func)

        @callback
        def unsubscribe() -> None:
            self._source_added_callbacks.discard(callback_func)

        return unsubscribe

    @callback
    def async_subscribe_source(
        self, source_registry_id: str, callback_func: TvUpdateCallback
    ) -> CALLBACK_TYPE:
        """Subscribe to updates from one TV source."""
        self._source_callbacks[source_registry_id].add(callback_func)

        @callback
        def unsubscribe() -> None:
            callbacks = self._source_callbacks.get(source_registry_id)
            if callbacks is None:
                return
            callbacks.discard(callback_func)
            if not callbacks:
                self._source_callbacks.pop(source_registry_id, None)

        return unsubscribe

    @callback
    def _is_tv_entry(self, registry_entry: er.RegistryEntry) -> bool:
        """Return whether a registry entry represents a controllable TV."""
        if registry_entry.domain != MEDIA_PLAYER_DOMAIN:
            return False
        if registry_entry.platform == "cast":
            return False
        if registry_entry.platform == ANDROID_TV_REMOTE_DOMAIN:
            return True
        registry_device_class = getattr(
            registry_entry, "device_class", None
        ) or getattr(registry_entry, "original_device_class", None)
        if registry_device_class == "tv":
            return True
        state = self.hass.states.get(registry_entry.entity_id)
        return state is not None and state.attributes.get("device_class") == "tv"

    @callback
    def _async_rescan_sources(self) -> None:
        """Find all native TV media-player registry entries."""
        current_source_ids: set[str] = set()
        for registry_entry in self._entity_registry.entities.values():
            if not self._is_tv_entry(registry_entry):
                continue
            current_source_ids.add(registry_entry.id)
            self._async_register_or_update_source(registry_entry)

        for source_id, source in self._sources.items():
            if source_id in current_source_ids or source.entity_id is None:
                continue
            old_state = self.get_source_state(source_id)
            self._async_set_source_entity_id(source, None)
            self._async_notify_source(source_id, old_state, None)

    @callback
    def _async_register_or_update_source(
        self, registry_entry: er.RegistryEntry
    ) -> None:
        """Register a TV source or follow a registry rename."""
        source = self._sources.get(registry_entry.id)
        is_new = source is None
        if source is None:
            source = TvSource(
                registry_id=registry_entry.id,
                platform=registry_entry.platform,
                config_entry_id=registry_entry.config_entry_id,
                device_id=registry_entry.device_id,
            )
            self._sources[registry_entry.id] = source
        else:
            source.platform = registry_entry.platform
            source.config_entry_id = registry_entry.config_entry_id
            source.device_id = registry_entry.device_id

        if source.entity_id == registry_entry.entity_id:
            return

        old_state = self.get_source_state(registry_entry.id)
        self._async_set_source_entity_id(source, registry_entry.entity_id)
        new_state = self.get_source_state(registry_entry.id)
        self._async_learn_active_app(registry_entry.id, new_state)

        if is_new:
            for callback_func in tuple(self._source_added_callbacks):
                callback_func(registry_entry.id)
        self._async_notify_source(registry_entry.id, old_state, new_state)

    @callback
    def _async_set_source_entity_id(
        self, source: TvSource, entity_id: str | None
    ) -> None:
        """Change a source entity ID and replace its listener."""
        if source.unsubscribe is not None:
            source.unsubscribe()
            source.unsubscribe = None
        source.entity_id = entity_id
        if entity_id is None:
            return

        @callback
        def async_handle_source_event(event: Event[EventStateChangedData]) -> None:
            self._async_handle_source_state_changed(source.registry_id, event)

        source.unsubscribe = async_track_state_change_event(
            self.hass, entity_id, async_handle_source_event
        )

    @callback
    def _async_handle_source_state_changed(
        self,
        source_registry_id: str,
        event: Event[EventStateChangedData],
    ) -> None:
        """Handle a native TV state update."""
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        self._async_learn_active_app(source_registry_id, new_state)
        self._async_notify_source(source_registry_id, old_state, new_state)

    @callback
    def _async_handle_media_player_added(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle a TV media-player state added after startup."""
        new_state = event.data["new_state"]
        if new_state is None:
            return
        registry_entry = self._entity_registry.async_get(new_state.entity_id)
        if registry_entry is not None and self._is_tv_entry(registry_entry):
            self._async_register_or_update_source(registry_entry)

    @callback
    def _async_handle_entity_registry_updated(
        self, event: Event[er.EventEntityRegistryUpdatedData]
    ) -> None:
        """Handle TV or companion remote registry changes."""
        entity_id = event.data.get("entity_id", "")
        old_entity_id = event.data.get("old_entity_id", "")
        if not any(
            value.startswith((f"{MEDIA_PLAYER_DOMAIN}.", f"{REMOTE_DOMAIN}."))
            for value in (entity_id, old_entity_id)
        ):
            return
        self._async_rescan_sources()
        for source_id in tuple(self._sources):
            self._async_notify_source(
                source_id,
                self.get_source_state(source_id),
                self.get_source_state(source_id),
            )

    @callback
    def _async_notify_source(
        self,
        source_registry_id: str,
        old_state: State | None,
        new_state: State | None,
    ) -> None:
        """Notify all entities following one TV source."""
        for callback_func in tuple(self._source_callbacks.get(source_registry_id, ())):
            callback_func(source_registry_id, old_state, new_state)

    @callback
    def _async_learn_active_app(
        self, source_registry_id: str, state: State | None
    ) -> bool:
        """Remember a foreground TV app when its package ID appears."""
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
        apps = self._learned_apps.setdefault(source_registry_id, {})
        if apps.get(app_id) == app_name:
            return False
        apps[app_id] = app_name
        self._async_schedule_save()
        return True

    @callback
    def _async_schedule_save(self) -> None:
        """Debounce TV app storage writes."""
        if self._save_task is not None and not self._save_task.done():
            return
        self._save_task = self.hass.async_create_task(
            self._async_delayed_save(), f"{TV_STORAGE_KEY}-save"
        )

    async def _async_delayed_save(self) -> None:
        """Persist learned applications after a short delay."""
        await asyncio.sleep(1)
        await self._store.async_save({"apps": self._learned_apps})

    @callback
    def get_source_entity_id(self, source_registry_id: str) -> str | None:
        """Return a TV source's current media-player entity ID."""
        source = self._sources.get(source_registry_id)
        return source.entity_id if source is not None else None

    @callback
    def get_source_id_for_entity_id(self, entity_id: str) -> str | None:
        """Resolve a tracked TV media-player entity ID to its registry ID."""
        for source_id, source in self._sources.items():
            if source.entity_id == entity_id:
                return source_id
        return None

    @callback
    def get_source_state(self, source_registry_id: str) -> State | None:
        """Return the current TV media-player state."""
        entity_id = self.get_source_entity_id(source_registry_id)
        return self.hass.states.get(entity_id) if entity_id is not None else None

    @callback
    def get_source_platform(self, source_registry_id: str) -> str | None:
        """Return the source integration platform."""
        source = self._sources.get(source_registry_id)
        return source.platform if source is not None else None

    @callback
    def source_available(self, source_registry_id: str) -> bool:
        """Return whether the native TV source is currently available."""
        state = self.get_source_state(source_registry_id)
        return state is not None and state.state != STATE_UNAVAILABLE

    @callback
    def source_supports(
        self, source_registry_id: str, feature: MediaPlayerEntityFeature
    ) -> bool:
        """Return whether the TV source advertises a media-player feature."""
        state = self.get_source_state(source_registry_id)
        if state is None:
            return False
        supported = state.attributes.get("supported_features", 0)
        return isinstance(supported, int) and bool(supported & int(feature))

    @callback
    def get_sources(self, source_registry_id: str) -> list[str]:
        """Return the TV's native source/input list."""
        state = self.get_source_state(source_registry_id)
        if state is None:
            return []
        source_list = state.attributes.get("source_list")
        if not isinstance(source_list, (list, tuple)):
            return []
        return [str(source) for source in source_list if str(source).strip()]

    @callback
    def get_apps(self, source_registry_id: str) -> dict[str, str]:
        """Return common, configured, and learned Android TV applications."""
        source = self._sources.get(source_registry_id)
        if source is None or source.platform != ANDROID_TV_REMOTE_DOMAIN:
            return {}

        apps = dict(DEFAULT_ANDROID_TV_APPS)
        if source.config_entry_id:
            entry = self.hass.config_entries.async_get_entry(source.config_entry_id)
            if entry is not None:
                configured = entry.options.get("apps", {})
                if isinstance(configured, dict):
                    for app_id, app_data in configured.items():
                        if not isinstance(app_data, dict):
                            continue
                        app_name = app_data.get("app_name")
                        apps[str(app_id)] = (
                            str(app_name).strip()
                            if isinstance(app_name, str) and app_name.strip()
                            else str(app_id)
                        )
        apps.update(self._learned_apps.get(source_registry_id, {}))
        return apps

    @callback
    def get_restart_entity_id(self, source_registry_id: str) -> str | None:
        """Find a native restart button attached to the same TV device."""
        source = self._sources.get(source_registry_id)
        if source is None or source.device_id is None:
            return None
        for registry_entry in self._entity_registry.entities.values():
            device_class = getattr(registry_entry, "device_class", None) or getattr(
                registry_entry, "original_device_class", None
            )
            if (
                registry_entry.domain == "button"
                and registry_entry.device_id == source.device_id
                and device_class == "restart"
            ):
                return registry_entry.entity_id
        return None

    @callback
    def get_remote_entity_id(self, source_registry_id: str) -> str | None:
        """Find the companion Android TV Remote entity for a TV source."""
        source = self._sources.get(source_registry_id)
        if (
            source is None
            or source.platform != ANDROID_TV_REMOTE_DOMAIN
            or source.config_entry_id is None
        ):
            return None
        for registry_entry in self._entity_registry.entities.values():
            if (
                registry_entry.domain == REMOTE_DOMAIN
                and registry_entry.platform == ANDROID_TV_REMOTE_DOMAIN
                and registry_entry.config_entry_id == source.config_entry_id
            ):
                return registry_entry.entity_id
        return None

    async def async_call_media_player(
        self,
        source_registry_id: str,
        service: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Call a native media_player action for a tracked TV."""
        entity_id = self.get_source_entity_id(source_registry_id)
        if entity_id is None:
            raise HomeAssistantError("TV source is no longer available")
        service_data: dict[str, Any] = {ATTR_ENTITY_ID: entity_id}
        if data:
            service_data.update(data)
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN, service, service_data, blocking=True
        )

    async def async_launch_app(self, source_registry_id: str, app_id: str) -> None:
        """Launch an Android/Google TV app by package name."""
        normalized_app_id = app_id.strip()
        if not normalized_app_id:
            raise HomeAssistantError("TV app package ID cannot be empty")
        if self.get_source_platform(source_registry_id) != ANDROID_TV_REMOTE_DOMAIN:
            raise HomeAssistantError(
                "TV app launching requires Home Assistant's Android TV Remote integration"
            )
        await self.async_call_media_player(
            source_registry_id,
            "play_media",
            {
                "media": {
                    "media_content_type": "app",
                    "media_content_id": normalized_app_id,
                }
            },
        )

    async def async_send_remote_command(
        self, source_registry_id: str, command: str
    ) -> None:
        """Send one command through a companion Android TV Remote entity."""
        remote_entity_id = self.get_remote_entity_id(source_registry_id)
        if remote_entity_id is None:
            raise HomeAssistantError("No Android TV Remote entity is linked to this TV")
        normalized_command = command.strip()
        if not normalized_command:
            raise HomeAssistantError("TV remote command cannot be empty")
        await self.hass.services.async_call(
            REMOTE_DOMAIN,
            "send_command",
            {ATTR_ENTITY_ID: remote_entity_id, "command": normalized_command},
            blocking=True,
        )

    async def async_press_native_restart(self, source_registry_id: str) -> None:
        """Press a native restart button exposed on the same TV device."""
        restart_entity_id = self.get_restart_entity_id(source_registry_id)
        if restart_entity_id is None:
            raise HomeAssistantError("This TV does not expose a native restart button")
        await self.hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: restart_entity_id},
            blocking=True,
        )

    async def async_reload_current_app(self, source_registry_id: str) -> None:
        """Return home and relaunch the currently reported Android TV app."""
        state = self.get_source_state(source_registry_id)
        if state is None:
            raise HomeAssistantError("TV source is unavailable")
        app_id = state.attributes.get("app_id")
        if not isinstance(app_id, str) or not app_id.strip():
            raise HomeAssistantError("The TV is not reporting a current app package ID")
        await self.async_send_remote_command(source_registry_id, "HOME")
        await asyncio.sleep(0.75)
        await self.async_launch_app(source_registry_id, app_id)

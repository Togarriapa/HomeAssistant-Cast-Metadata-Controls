"""Shared Cast source discovery, app learning, and action helpers."""

from __future__ import annotations

import asyncio
import json
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
    CAST_DOMAIN,
    DEFAULT_CAST_APPS,
    MEDIA_PLAYER_DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)

SourceUpdateCallback = Callable[[str, State | None, State | None], None]
SourceAddedCallback = Callable[[str], None]


@dataclass(slots=True)
class CastSource:
    """A tracked Cast media-player registry entry."""

    registry_id: str
    entity_id: str | None = None
    unsubscribe: CALLBACK_TYPE | None = None


class CastManager:
    """Track native Cast media players and expose safe wrapper actions."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the manager."""
        self.hass = hass
        self._entity_registry = er.async_get(hass)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._sources: dict[str, CastSource] = {}
        self._source_callbacks: dict[str, set[SourceUpdateCallback]] = defaultdict(set)
        self._source_added_callbacks: set[SourceAddedCallback] = set()
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._learned_apps: dict[str, dict[str, str]] = {}
        self._save_task: asyncio.Task[None] | None = None
        self._started = False

    async def async_initialize(self) -> None:
        """Load persisted app data and begin Cast source discovery."""
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
        """Start event tracking."""
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
        """Stop event tracking and flush learned app data."""
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
        """Return all currently known Cast registry IDs."""
        return tuple(self._sources)

    @callback
    def async_subscribe_source_added(
        self, callback_func: SourceAddedCallback
    ) -> CALLBACK_TYPE:
        """Subscribe to newly discovered Cast sources."""
        self._source_added_callbacks.add(callback_func)

        @callback
        def unsubscribe() -> None:
            self._source_added_callbacks.discard(callback_func)

        return unsubscribe

    @callback
    def async_subscribe_source(
        self, source_registry_id: str, callback_func: SourceUpdateCallback
    ) -> CALLBACK_TYPE:
        """Subscribe to state, rename, availability, and app-list changes."""
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
    def _async_rescan_sources(self) -> None:
        """Find current native Cast media-player registry entries."""
        current_source_ids: set[str] = set()

        for registry_entry in self._entity_registry.entities.values():
            if (
                registry_entry.domain != MEDIA_PLAYER_DOMAIN
                or registry_entry.platform != CAST_DOMAIN
            ):
                continue

            current_source_ids.add(registry_entry.id)
            self._async_register_or_update_source(
                registry_entry.id, registry_entry.entity_id
            )

        for source_id, source in self._sources.items():
            if source_id in current_source_ids or source.entity_id is None:
                continue

            old_state = self.get_source_state(source_id)
            self._async_set_source_entity_id(source, None)
            self._async_notify_source(source_id, old_state, None)

    @callback
    def _async_register_or_update_source(
        self, source_registry_id: str, entity_id: str
    ) -> None:
        """Register a new Cast source or follow an entity-ID rename."""
        source = self._sources.get(source_registry_id)
        is_new = source is None
        if source is None:
            source = CastSource(registry_id=source_registry_id)
            self._sources[source_registry_id] = source

        if source.entity_id == entity_id:
            return

        old_state = self.get_source_state(source_registry_id)
        self._async_set_source_entity_id(source, entity_id)
        new_state = self.get_source_state(source_registry_id)
        self._async_learn_active_app(source_registry_id, new_state)

        if is_new:
            for callback_func in tuple(self._source_added_callbacks):
                callback_func(source_registry_id)

        self._async_notify_source(source_registry_id, old_state, new_state)

    @callback
    def _async_set_source_entity_id(
        self, source: CastSource, entity_id: str | None
    ) -> None:
        """Change the source entity ID and replace its state listener."""
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
        """Handle a native Cast state update."""
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        self._async_learn_active_app(source_registry_id, new_state)
        self._async_notify_source(source_registry_id, old_state, new_state)

    @callback
    def _async_handle_media_player_added(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle a media player state added after startup."""
        new_state = event.data["new_state"]
        if new_state is None:
            return

        registry_entry = self._entity_registry.async_get(new_state.entity_id)
        if (
            registry_entry is None
            or registry_entry.domain != MEDIA_PLAYER_DOMAIN
            or registry_entry.platform != CAST_DOMAIN
        ):
            return

        self._async_register_or_update_source(
            registry_entry.id, registry_entry.entity_id
        )

    @callback
    def _async_handle_entity_registry_updated(
        self, event: Event[er.EventEntityRegistryUpdatedData]
    ) -> None:
        """Handle Cast entity creation, removal, disablement, or rename."""
        entity_id = event.data.get("entity_id", "")
        old_entity_id = event.data.get("old_entity_id", "")

        if not (
            entity_id.startswith(f"{MEDIA_PLAYER_DOMAIN}.")
            or old_entity_id.startswith(f"{MEDIA_PLAYER_DOMAIN}.")
        ):
            return

        self._async_rescan_sources()

    @callback
    def _async_notify_source(
        self,
        source_registry_id: str,
        old_state: State | None,
        new_state: State | None,
    ) -> None:
        """Notify all entities following one Cast source."""
        for callback_func in tuple(self._source_callbacks.get(source_registry_id, ())):
            callback_func(source_registry_id, old_state, new_state)

    @callback
    def _async_learn_active_app(
        self, source_registry_id: str, state: State | None
    ) -> bool:
        """Persist an app after its metadata appears for the first time."""
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
            else f"App {app_id}"
        )

        source_apps = self._learned_apps.setdefault(source_registry_id, {})
        if source_apps.get(app_id) == app_name:
            return False

        source_apps[app_id] = app_name
        self._async_schedule_save()
        return True

    @callback
    def _async_schedule_save(self) -> None:
        """Debounce storage writes after app changes."""
        if self._save_task is not None and not self._save_task.done():
            return

        self._save_task = self.hass.async_create_task(
            self._async_delayed_save(), f"{STORAGE_KEY}-save"
        )

    async def _async_delayed_save(self) -> None:
        """Write learned apps after a short coalescing delay."""
        await asyncio.sleep(1)
        await self._store.async_save({"apps": self._learned_apps})

    @callback
    def get_source_entity_id(self, source_registry_id: str) -> str | None:
        """Return the source's current entity ID."""
        source = self._sources.get(source_registry_id)
        return source.entity_id if source is not None else None

    @callback
    def get_source_id_for_entity_id(self, entity_id: str) -> str | None:
        """Resolve a native media-player entity ID to its registry ID."""
        for source_id, source in self._sources.items():
            if source.entity_id == entity_id:
                return source_id
        return None

    @callback
    def get_source_state(self, source_registry_id: str) -> State | None:
        """Return the current native Cast state object."""
        entity_id = self.get_source_entity_id(source_registry_id)
        return self.hass.states.get(entity_id) if entity_id is not None else None

    @callback
    def source_available(self, source_registry_id: str) -> bool:
        """Return whether the native Cast entity can currently be used."""
        state = self.get_source_state(source_registry_id)
        return state is not None and state.state != STATE_UNAVAILABLE

    @callback
    def source_supports(
        self, source_registry_id: str, feature: MediaPlayerEntityFeature
    ) -> bool:
        """Return whether the Cast source currently advertises a feature."""
        state = self.get_source_state(source_registry_id)
        if state is None:
            return False
        supported = state.attributes.get("supported_features", 0)
        return isinstance(supported, int) and bool(supported & int(feature))

    @callback
    def get_apps(self, source_registry_id: str) -> dict[str, str]:
        """Return default plus learned apps for a Cast device."""
        apps = dict(DEFAULT_CAST_APPS)
        apps.update(self._learned_apps.get(source_registry_id, {}))
        return apps

    async def async_call_media_player(
        self,
        source_registry_id: str,
        service: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Call a native media_player action for a tracked Cast entity."""
        entity_id = self.get_source_entity_id(source_registry_id)
        if entity_id is None:
            raise HomeAssistantError("Cast source is no longer available")

        service_data: dict[str, Any] = {ATTR_ENTITY_ID: entity_id}
        if data:
            service_data.update(data)

        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            service,
            service_data,
            blocking=True,
        )

    async def async_launch_app(self, source_registry_id: str, app_id: str) -> None:
        """Launch an arbitrary Cast app through the native Cast integration."""
        normalized_app_id = app_id.strip()
        if not normalized_app_id:
            raise HomeAssistantError("Cast app ID cannot be empty")

        await self.async_call_media_player(
            source_registry_id,
            "play_media",
            {
                "media": {
                    "media_content_type": CAST_DOMAIN,
                    "media_content_id": json.dumps(
                        {"app_id": normalized_app_id}, separators=(",", ":")
                    ),
                }
            },
        )

    async def async_soft_restart_receiver(self, source_registry_id: str) -> None:
        """Quit and restart the Cast receiver without rebooting the hardware."""
        can_turn_on = self.source_supports(
            source_registry_id, MediaPlayerEntityFeature.TURN_ON
        )
        can_turn_off = self.source_supports(
            source_registry_id, MediaPlayerEntityFeature.TURN_OFF
        )
        if can_turn_off:
            await self.async_call_media_player(source_registry_id, "turn_off")
            await asyncio.sleep(1)
        if can_turn_on:
            await self.async_call_media_player(source_registry_id, "turn_on")
            return
        raise HomeAssistantError("The Cast entity does not support receiver restart")

    async def async_seek_relative(
        self, source_registry_id: str, offset_seconds: float
    ) -> None:
        """Seek relative to the currently reported media position."""
        state = self.get_source_state(source_registry_id)
        if state is None:
            raise HomeAssistantError("Cast source is unavailable")
        position = state.attributes.get("media_position")
        duration = state.attributes.get("media_duration")
        if not isinstance(position, (int, float)):
            raise HomeAssistantError("The Cast entity is not reporting media position")
        target = max(0.0, float(position) + float(offset_seconds))
        if isinstance(duration, (int, float)) and duration > 0:
            target = min(target, float(duration))
        await self.async_call_media_player(
            source_registry_id, "media_seek", {"seek_position": target}
        )

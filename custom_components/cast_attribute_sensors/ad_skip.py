"""Opt-in, positive-detection YouTube ad skipping."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
import time
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .ad_detection import find_skip_target, is_youtube_attributes
from .const import (
    AD_SKIP_STORAGE_KEY,
    ANDROID_TV_ADB_DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    STORAGE_VERSION,
)
from .grouping import PhysicalGroup

_CAST_SKIP_COMMAND = 512
_CAST_COOLDOWN = 4.0
_ADB_POLL_INTERVAL = 1.5
_ADB_COOLDOWN = 5.0
_ADB_DUMP_COMMAND = (
    "uiautomator dump /sdcard/window.xml >/dev/null 2>&1 "
    "&& cat /sdcard/window.xml"
)

AdSkipCallback = Callable[[], None]


class AdSkipManager:
    """Detect only positively identifiable skippable ads and skip them."""

    def __init__(self, hass: HomeAssistant, runtime) -> None:
        self.hass = hass
        self.runtime = runtime
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, AD_SKIP_STORAGE_KEY
        )
        self._enabled: set[str] = set()
        self._callbacks: dict[str, set[AdSkipCallback]] = defaultdict(set)
        self._task: asyncio.Task[None] | None = None
        self._save_task: asyncio.Task[None] | None = None
        self._last_attempt: dict[str, float] = {}
        self._last_adb_poll: dict[str, float] = {}
        self._last_result: dict[str, str] = {}
        self._last_skip_at: dict[str, datetime] = {}
        self._started = False

    async def async_initialize(self) -> None:
        """Load per-device opt-in state."""
        stored = await self._store.async_load()
        if not isinstance(stored, dict):
            return
        enabled = stored.get("enabled", [])
        if isinstance(enabled, list):
            self._enabled = {str(group_key) for group_key in enabled}

    @callback
    def start(self) -> None:
        """Start the lightweight detection loop."""
        if self._started:
            return
        self._started = True
        self._task = self.hass.async_create_background_task(
            self._async_loop(), f"{AD_SKIP_STORAGE_KEY}-loop"
        )

    async def async_stop(self) -> None:
        """Stop detection and persist enabled devices."""
        self._started = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._save_task is not None and not self._save_task.done():
            self._save_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._save_task
        await self._async_save()

    def is_enabled(self, group_key: str) -> bool:
        return group_key in self._enabled

    async def async_set_enabled(self, group_key: str, enabled: bool) -> None:
        """Enable or disable automatic skipping for one physical device."""
        if enabled:
            self._enabled.add(group_key)
        else:
            self._enabled.discard(group_key)
            self._last_result[group_key] = "disabled"
        self._schedule_save()
        self._notify(group_key)

    @callback
    def async_subscribe(
        self, group_key: str, callback_func: AdSkipCallback
    ) -> CALLBACK_TYPE:
        self._callbacks[group_key].add(callback_func)

        @callback
        def unsubscribe() -> None:
            callbacks = self._callbacks.get(group_key)
            if callbacks is None:
                return
            callbacks.discard(callback_func)
            if not callbacks:
                self._callbacks.pop(group_key, None)

        return unsubscribe

    def details(self, group: PhysicalGroup) -> dict[str, Any]:
        """Return device diagnostics for the switch and future card clients."""
        methods = []
        for source_id in group.source_ids:
            source = self.runtime.manager.get_source(source_id)
            if source is None:
                continue
            if source.is_cast:
                methods.append("cast_protocol")
            elif source.platform == ANDROID_TV_ADB_DOMAIN:
                methods.append("android_tv_adb_ui")
        last_skip = self._last_skip_at.get(group.key)
        return {
            "available_methods": sorted(set(methods)),
            "last_result": self._last_result.get(group.key, "idle"),
            "last_skip_at": last_skip.isoformat() if last_skip else None,
            "positive_detection_only": True,
        }

    async def async_skip_now(self, group: PhysicalGroup) -> bool:
        """Try every safe method immediately, even when automation is off."""
        if await self._async_try_cast(group, ignore_cooldown=True):
            return True
        return await self._async_try_adb(group, ignore_cooldown=True)

    async def _async_loop(self) -> None:
        while self._started:
            for group in tuple(self.runtime.groups):
                if group.key not in self._enabled:
                    continue
                try:
                    skipped = await self._async_try_cast(group)
                    if not skipped:
                        now = time.monotonic()
                        if now - self._last_adb_poll.get(group.key, 0) >= _ADB_POLL_INTERVAL:
                            self._last_adb_poll[group.key] = now
                            await self._async_try_adb(group)
                except Exception:  # noqa: BLE001
                    # Detection is optional and must never destabilize media control.
                    self._set_result(group.key, "detection_error")
            await asyncio.sleep(0.5)

    def _youtube_state(self, source_id: str):
        state = self.runtime.manager.get_state(source_id)
        if state is None or state.state == STATE_UNAVAILABLE:
            return None
        return state if is_youtube_attributes(state.attributes) else None

    def _native_entity(self, entity_id: str):
        component = self.hass.data.get(DATA_INSTANCES, {}).get(MEDIA_PLAYER_DOMAIN)
        return component.get_entity(entity_id) if component is not None else None

    def _cast_context(self, source_id: str):
        source = self.runtime.manager.get_source(source_id)
        if source is None or not source.is_cast or self._youtube_state(source_id) is None:
            return None
        entity_id = self.runtime.manager.get_entity_id(source_id)
        if entity_id is None:
            return None
        entity = self._native_entity(entity_id)
        if entity is None or not entity.__class__.__module__.startswith(
            "homeassistant.components.cast."
        ):
            return None
        try:
            chromecast = entity._get_chromecast()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            return None
        controller = chromecast.media_controller
        status = controller.status
        if (
            status.media_session_id is None
            or not status.supported_media_commands & _CAST_SKIP_COMMAND
        ):
            return None
        return controller, status.media_session_id

    async def _async_try_cast(
        self, group: PhysicalGroup, *, ignore_cooldown: bool = False
    ) -> bool:
        now = time.monotonic()
        if (
            not ignore_cooldown
            and now - self._last_attempt.get(group.key, 0) < _CAST_COOLDOWN
        ):
            return False
        for source_id in group.source_ids:
            context = self._cast_context(source_id)
            if context is None:
                continue
            controller, media_session_id = context
            self._last_attempt[group.key] = now

            def send_skip() -> None:
                controller.send_message(
                    {
                        "type": "SKIP_AD",
                        "mediaSessionId": media_session_id,
                    },
                    inc_session_id=True,
                )

            await self.hass.async_add_executor_job(send_skip)
            self._mark_skipped(group.key, "skipped_cast")
            return True
        return False

    async def _async_try_adb(
        self, group: PhysicalGroup, *, ignore_cooldown: bool = False
    ) -> bool:
        now = time.monotonic()
        if (
            not ignore_cooldown
            and now - self._last_attempt.get(group.key, 0) < _ADB_COOLDOWN
        ):
            return False
        if not self.hass.services.has_service(ANDROID_TV_ADB_DOMAIN, "adb_command"):
            return False
        for source_id in group.source_ids:
            source = self.runtime.manager.get_source(source_id)
            if (
                source is None
                or source.platform != ANDROID_TV_ADB_DOMAIN
                or self._youtube_state(source_id) is None
            ):
                continue
            entity_id = self.runtime.manager.get_entity_id(source_id)
            if entity_id is None:
                continue
            await self.hass.services.async_call(
                ANDROID_TV_ADB_DOMAIN,
                "adb_command",
                {
                    ATTR_ENTITY_ID: entity_id,
                    "command": _ADB_DUMP_COMMAND,
                },
                blocking=True,
            )
            current = self.hass.states.get(entity_id)
            if current is None or not is_youtube_attributes(current.attributes):
                return False
            response = current.attributes.get("adb_response")
            if not isinstance(response, str):
                return False
            target = find_skip_target(response)
            if target is None:
                return False
            x_position, y_position = target
            # Re-check immediately before the tap to avoid acting after an app change.
            current = self.hass.states.get(entity_id)
            if current is None or not is_youtube_attributes(current.attributes):
                return False
            self._last_attempt[group.key] = now
            await self.hass.services.async_call(
                ANDROID_TV_ADB_DOMAIN,
                "adb_command",
                {
                    ATTR_ENTITY_ID: entity_id,
                    "command": f"input tap {x_position} {y_position}",
                },
                blocking=True,
            )
            self._mark_skipped(group.key, "skipped_android_tv")
            return True
        return False

    def _mark_skipped(self, group_key: str, result: str) -> None:
        self._last_skip_at[group_key] = dt_util.utcnow()
        self._set_result(group_key, result)

    def _set_result(self, group_key: str, result: str) -> None:
        if self._last_result.get(group_key) == result and not result.startswith("skipped"):
            return
        self._last_result[group_key] = result
        self._notify(group_key)

    @callback
    def _notify(self, group_key: str) -> None:
        for callback_func in tuple(self._callbacks.get(group_key, ())):
            callback_func()

    def _schedule_save(self) -> None:
        if self._save_task is not None and not self._save_task.done():
            return
        self._save_task = self.hass.async_create_task(
            self._async_delayed_save(), f"{AD_SKIP_STORAGE_KEY}-save"
        )

    async def _async_delayed_save(self) -> None:
        await asyncio.sleep(0.5)
        await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save({"enabled": sorted(self._enabled)})

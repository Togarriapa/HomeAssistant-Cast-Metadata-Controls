"""V8.4 runtime fixes for configured providers, native apps, and manual ad skip."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE

from .ad_skip import AdSkipManager
from .media_player import UnifiedMediaController
from .source_manager import SourceManager

_LOGGER = logging.getLogger(__name__)
_INSTALLED = False


def _configured_apps(self: SourceManager, source_id: str) -> dict[str, str]:
    """Collect applications from every linked native provider generically."""
    source = self.get_source(source_id)
    if source is None or source.is_cast:
        return {}

    apps = dict(_configured_apps.original(self, source_id))
    if source.config_entry_id:
        config_entry = self.hass.config_entries.async_get_entry(source.config_entry_id)
        if config_entry is not None:
            for container in (config_entry.data, config_entry.options):
                raw_apps = container.get("apps", {}) if isinstance(container, Mapping) else {}
                if isinstance(raw_apps, Mapping):
                    for app_id, app_data in raw_apps.items():
                        if isinstance(app_data, Mapping):
                            name = app_data.get("app_name") or app_data.get("name")
                        else:
                            name = app_data
                        app_key = str(app_id).strip()
                        if app_key:
                            apps[app_key] = str(name or app_key).strip()
                elif isinstance(raw_apps, (list, tuple)):
                    for item in raw_apps:
                        if not isinstance(item, Mapping):
                            continue
                        app_id = str(
                            item.get("app_id")
                            or item.get("package")
                            or item.get("id")
                            or ""
                        ).strip()
                        name = str(
                            item.get("app_name") or item.get("name") or app_id
                        ).strip()
                        if app_id:
                            apps[app_id] = name or app_id

    state = self.get_state(source_id)
    if state is not None and state.state != STATE_UNAVAILABLE:
        app_id = state.attributes.get("app_id")
        app_name = state.attributes.get("app_name")
        if isinstance(app_id, str) and app_id.strip():
            apps[app_id.strip()] = (
                app_name.strip()
                if isinstance(app_name, str) and app_name.strip()
                else app_id.strip()
            )
    apps.update(self._learned_apps.get(source_id, {}))
    return apps


def _extra_state_attributes(self: UnifiedMediaController) -> dict[str, Any]:
    attributes = dict(_extra_state_attributes.original.fget(self))
    manager = self.runtime.manager
    native_sources = [
        source_id
        for source_id in self.group.source_ids
        if (source := manager.get_source(source_id)) is not None and not source.is_cast
    ]
    attributes.update(
        {
            "runtime_release": "8.4.0",
            "native_source_entities": [
                entity_id
                for source_id in native_sources
                if (entity_id := manager.get_entity_id(source_id))
            ],
            "native_application_count": sum(
                len(manager.tv_apps(source_id)) for source_id in native_sources
            ),
            "manual_ad_skip_available": bool(
                manager.remote_entity_id(self.group.source_ids)
            ),
        }
    )
    return attributes


async def _async_skip_now(self: AdSkipManager, group) -> bool:
    """Use safe detection first, then an explicit manual remote attempt."""
    if await _async_skip_now.original(self, group):
        return True

    youtube_sources = [
        source_id
        for source_id in group.source_ids
        if self._youtube_state(source_id) is not None
    ]
    if not youtube_sources:
        self._set_result(group.key, "youtube_not_detected")
        return False

    if self.runtime.manager.remote_entity_id(group.source_ids) is not None:
        try:
            await self.runtime.manager.send_command(group.source_ids, "DPAD_CENTER")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Manual remote ad-skip attempt failed for %s", group.key)
            self._set_result(group.key, "manual_remote_attempt_failed")
            return False
        self._set_result(group.key, "manual_remote_confirm_sent")
        return True

    self._set_result(group.key, "no_manual_skip_provider")
    return False


def _details(self: AdSkipManager, group) -> dict[str, Any]:
    details = dict(_details.original(self, group))
    details.update(
        {
            "automatic_positive_detection_only": True,
            "manual_remote_provider": self.runtime.manager.remote_entity_id(
                group.source_ids
            ),
        }
    )
    return details


def install_v840_patches() -> None:
    """Install V8.4 runtime behavior exactly once after V8.3.1."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    _configured_apps.original = SourceManager.tv_apps
    SourceManager.tv_apps = _configured_apps

    _extra_state_attributes.original = UnifiedMediaController.extra_state_attributes
    UnifiedMediaController.extra_state_attributes = property(_extra_state_attributes)

    _async_skip_now.original = AdSkipManager.async_skip_now
    AdSkipManager.async_skip_now = _async_skip_now
    _details.original = AdSkipManager.details
    AdSkipManager.details = _details

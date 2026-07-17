"""Pure helpers for physical-device merge option migration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from uuid import uuid4

from .const import (
    CONF_ACTIVITIES,
    CONF_ACTIVITY_ID,
    CONF_ACTIVITY_NAME,
    CONF_APP_PREFERENCES,
    CONF_DELAYS,
    CONF_GROUP_ID,
    CONF_GROUP_NAME,
    CONF_MEMBERS,
    CONF_ROUTES,
    CONF_WOL,
)

MANUAL_GROUP_PREFIX = "manual:"


def merge_manual_group_configs(
    configured_groups: Iterable[Mapping[str, Any]],
    *,
    member_ids: Iterable[str],
    name: str,
    group_id: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Create or replace one manual group and remove member overlap elsewhere."""
    selected = list(dict.fromkeys(str(item) for item in member_ids if item))
    target_id = group_id or uuid4().hex
    selected_set = set(selected)
    result: list[dict[str, Any]] = []

    for configured in configured_groups:
        configured_id = str(configured.get(CONF_GROUP_ID, "")).strip()
        if configured_id == target_id:
            continue
        remaining = [
            str(item)
            for item in configured.get(CONF_MEMBERS, [])
            if str(item) not in selected_set
        ]
        if len(remaining) < 2:
            continue
        updated = dict(configured)
        updated[CONF_MEMBERS] = list(dict.fromkeys(remaining))
        result.append(updated)

    result.append(
        {
            CONF_GROUP_ID: target_id,
            CONF_GROUP_NAME: name.strip(),
            CONF_MEMBERS: selected,
        }
    )
    return result, target_id


def remap_group_settings(
    *,
    old_keys: Iterable[str],
    new_key: str,
    routes: Mapping[str, Any],
    preferences: Mapping[str, Any],
    delays: Mapping[str, Any],
    activities: Mapping[str, Any],
    wol: Mapping[str, Any],
) -> dict[str, Any]:
    """Move per-device configuration from duplicate groups onto the merged device."""
    ordered_keys = list(dict.fromkeys(str(key) for key in old_keys if key))
    if new_key not in ordered_keys:
        ordered_keys.insert(0, new_key)

    routes_out = {
        str(key): dict(value)
        for key, value in routes.items()
        if isinstance(value, dict)
    }
    preferences_out = {
        str(key): {
            str(app_key): dict(preference)
            for app_key, preference in value.items()
            if isinstance(preference, dict)
        }
        for key, value in preferences.items()
        if isinstance(value, dict)
    }
    delays_out = {
        str(key): dict(value)
        for key, value in delays.items()
        if isinstance(value, dict)
    }
    activities_out = {
        str(key): [dict(item) for item in value if isinstance(item, dict)]
        for key, value in activities.items()
        if isinstance(value, list)
    }
    wol_out = {
        str(key): dict(value)
        for key, value in wol.items()
        if isinstance(value, dict)
    }

    merged_routes: dict[str, str] = {}
    merged_preferences: dict[str, dict[str, Any]] = {}
    activities_by_name: dict[str, dict[str, Any]] = {}

    # Apply lower-priority groups first so the selected target group wins conflicts.
    for key in reversed(ordered_keys):
        merged_routes.update(routes_out.get(key, {}))
        merged_preferences.update(preferences_out.get(key, {}))
        for activity in activities_out.get(key, []):
            activity_name = str(
                activity.get(CONF_ACTIVITY_NAME, "")
            ).strip().casefold()
            activity_id = str(activity.get(CONF_ACTIVITY_ID, "")).strip()
            activities_by_name[activity_name or activity_id] = dict(activity)

    merged_delays = next(
        (dict(delays_out[key]) for key in ordered_keys if key in delays_out),
        None,
    )
    merged_wol = next(
        (dict(wol_out[key]) for key in ordered_keys if key in wol_out),
        None,
    )

    for mapping in (
        routes_out,
        preferences_out,
        delays_out,
        activities_out,
        wol_out,
    ):
        for key in ordered_keys:
            mapping.pop(key, None)

    if merged_routes:
        routes_out[new_key] = merged_routes
    if merged_preferences:
        preferences_out[new_key] = merged_preferences
    if merged_delays:
        delays_out[new_key] = merged_delays
    if activities_by_name:
        activities_out[new_key] = list(activities_by_name.values())
    if merged_wol:
        wol_out[new_key] = merged_wol

    return {
        CONF_ROUTES: routes_out,
        CONF_APP_PREFERENCES: preferences_out,
        CONF_DELAYS: delays_out,
        CONF_ACTIVITIES: activities_out,
        CONF_WOL: wol_out,
    }


def remove_group_settings(
    group_keys: Iterable[str],
    *,
    routes: Mapping[str, Any],
    preferences: Mapping[str, Any],
    delays: Mapping[str, Any],
    activities: Mapping[str, Any],
    wol: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove every per-device option belonging to deleted manual groups."""
    keys = {str(key) for key in group_keys}
    output = remap_group_settings(
        old_keys=(),
        new_key="__unused__",
        routes=routes,
        preferences=preferences,
        delays=delays,
        activities=activities,
        wol=wol,
    )
    for mapping in output.values():
        for key in keys:
            mapping.pop(key, None)
    return output

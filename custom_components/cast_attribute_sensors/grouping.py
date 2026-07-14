"""Pure physical-device grouping logic."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .const import ANDROID_TV_ADB_DOMAIN, ANDROID_TV_REMOTE_DOMAIN, CAST_DOMAIN

_STRIP_WORDS = re.compile(
    r"\b(android|google|tv|television|remote|controller|media|player|adb|cast|"
    r"chromecast|built[ -]?in|smart|device)\b",
    re.IGNORECASE,
)
_DISPLAY_SUFFIX = re.compile(
    r"(?:\s+(?:controller|remote|media\s+player|android\s+tv|adb|cast))+$",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_GENERIC_NAMES = frozenset(
    {"", "livingroom", "bedroom", "office", "kitchen", "room"}
)
_MATCH_STOPWORDS = frozenset(
    {
        "android",
        "bedroom",
        "controller",
        "device",
        "google",
        "hisense",
        "kitchen",
        "living",
        "media",
        "office",
        "panasonic",
        "philips",
        "player",
        "remote",
        "samsung",
        "smart",
        "sony",
        "television",
    }
)
_ANDROID_TV_PLATFORMS = frozenset(
    {ANDROID_TV_REMOTE_DOMAIN, ANDROID_TV_ADB_DOMAIN}
)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Stable source facts used by the grouping engine."""

    registry_id: str
    entity_id: str
    platform: str
    name: str
    device_id: str | None
    connections: frozenset[tuple[str, str]]
    area_id: str | None
    is_cast: bool
    is_tv: bool
    manufacturer: str | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class PhysicalGroup:
    """One integration-owned representation of a physical media device."""

    key: str
    name: str
    source_ids: tuple[str, ...]
    primary_source_id: str
    is_tv: bool


def clean_device_name(name: str) -> str:
    """Remove integration-generated suffixes from a physical device name."""
    cleaned = _DISPLAY_SUFFIX.sub("", name.strip()).strip(" -–—")
    return cleaned or name.strip()


def normalized_device_name(name: str) -> str:
    """Normalize names from different integrations for conservative matching."""
    stripped = _STRIP_WORDS.sub(" ", clean_device_name(name).casefold())
    return _NON_ALNUM.sub("", stripped)


def _significant_tokens(*values: str | None) -> frozenset[str]:
    """Return distinctive model/family tokens suitable for same-room matching."""
    return frozenset(
        token
        for value in values
        if value
        for token in _TOKEN.findall(clean_device_name(value).casefold())
        if len(token) >= 5
        and token not in _MATCH_STOPWORDS
        and not token.isdecimal()
    )


def _same_room_family_match(first: SourceSnapshot, second: SourceSnapshot) -> bool:
    """Match complementary TV representations with shared hardware evidence."""
    if not first.area_id or first.area_id != second.area_id:
        return False

    has_android_tv = (
        first.platform in _ANDROID_TV_PLATFORMS
        or second.platform in _ANDROID_TV_PLATFORMS
    )
    is_tv_cast_pair = (first.is_cast and second.is_tv) or (
        second.is_cast and first.is_tv
    )
    is_complementary_tv_pair = first.is_tv and second.is_tv and has_android_tv
    if not (is_tv_cast_pair or is_complementary_tv_pair):
        return False

    first_tokens = _significant_tokens(first.name, first.model)
    second_tokens = _significant_tokens(second.name, second.model)
    if first_tokens & second_tokens:
        return True

    first_manufacturer = (first.manufacturer or "").casefold().strip()
    second_manufacturer = (second.manufacturer or "").casefold().strip()
    return bool(
        first_manufacturer
        and first_manufacturer == second_manufacturer
        and "bravia" in first_tokens
        and "bravia" in second_tokens
    )


def _strong_match(first: SourceSnapshot, second: SourceSnapshot) -> bool:
    if first.device_id and first.device_id == second.device_id:
        return True
    if (
        first.connections
        and second.connections
        and first.connections & second.connections
    ):
        return True

    first_name = normalized_device_name(first.name)
    second_name = normalized_device_name(second.name)
    if (
        first_name
        and first_name == second_name
        and first_name not in _GENERIC_NAMES
        and not (
            first.area_id
            and second.area_id
            and first.area_id != second.area_id
        )
    ):
        return True

    return _same_room_family_match(first, second)


def _source_priority(source: SourceSnapshot) -> tuple[int, str]:
    # Manufacturer-native integrations provide the best identity and device name.
    if source.is_tv and source.platform not in {
        ANDROID_TV_REMOTE_DOMAIN,
        ANDROID_TV_ADB_DOMAIN,
        CAST_DOMAIN,
    }:
        priority = 0
    elif source.platform == ANDROID_TV_REMOTE_DOMAIN:
        priority = 1
    elif source.platform == ANDROID_TV_ADB_DOMAIN:
        priority = 2
    else:
        priority = 3
    return priority, source.entity_id


def _manual_groups(
    sources_by_id: Mapping[str, SourceSnapshot],
    configured_groups: Iterable[Mapping[str, Any]],
) -> tuple[list[PhysicalGroup], set[str]]:
    groups: list[PhysicalGroup] = []
    claimed: set[str] = set()
    for configured in configured_groups:
        group_id = str(configured.get("group_id", "")).strip()
        member_ids = tuple(
            source_id
            for source_id in configured.get("members", [])
            if source_id in sources_by_id and source_id not in claimed
        )
        if not group_id or not member_ids:
            continue
        members = tuple(sources_by_id[source_id] for source_id in member_ids)
        primary = min(members, key=_source_priority)
        configured_name = str(configured.get("name", "")).strip()
        groups.append(
            PhysicalGroup(
                key=f"manual:{group_id}",
                name=configured_name or clean_device_name(primary.name),
                source_ids=tuple(source.registry_id for source in members),
                primary_source_id=primary.registry_id,
                is_tv=any(source.is_tv for source in members),
            )
        )
        claimed.update(member_ids)
    return groups, claimed


def build_physical_groups(
    sources: Iterable[SourceSnapshot],
    configured_groups: Iterable[Mapping[str, Any]] = (),
) -> tuple[PhysicalGroup, ...]:
    """Build deterministic groups with manual overrides and safe auto-matching."""
    source_list = sorted(sources, key=lambda item: item.registry_id)
    sources_by_id = {source.registry_id: source for source in source_list}
    groups, claimed = _manual_groups(sources_by_id, configured_groups)

    remaining_tv = [
        source
        for source in source_list
        if source.is_tv and source.registry_id not in claimed
    ]
    tv_clusters: list[list[SourceSnapshot]] = []
    for source in remaining_tv:
        for cluster in tv_clusters:
            if any(_strong_match(source, member) for member in cluster):
                cluster.append(source)
                break
        else:
            tv_clusters.append([source])

    remaining_cast = [
        source
        for source in source_list
        if source.is_cast and source.registry_id not in claimed
    ]

    for cluster in tv_clusters:
        attached_cast: list[SourceSnapshot] = []
        for cast_source in tuple(remaining_cast):
            if any(_strong_match(cast_source, tv_source) for tv_source in cluster):
                attached_cast.append(cast_source)
                remaining_cast.remove(cast_source)
        members = tuple(sorted((*cluster, *attached_cast), key=_source_priority))
        primary = members[0]
        groups.append(
            PhysicalGroup(
                key=f"tv:{primary.registry_id}",
                name=clean_device_name(primary.name),
                source_ids=tuple(source.registry_id for source in members),
                primary_source_id=primary.registry_id,
                is_tv=True,
            )
        )
        claimed.update(source.registry_id for source in members)

    for source in remaining_cast:
        groups.append(
            PhysicalGroup(
                key=f"cast:{source.registry_id}",
                name=clean_device_name(source.name),
                source_ids=(source.registry_id,),
                primary_source_id=source.registry_id,
                is_tv=False,
            )
        )
        claimed.add(source.registry_id)

    for source in source_list:
        if source.registry_id in claimed:
            continue
        groups.append(
            PhysicalGroup(
                key=f"source:{source.registry_id}",
                name=clean_device_name(source.name),
                source_ids=(source.registry_id,),
                primary_source_id=source.registry_id,
                is_tv=source.is_tv,
            )
        )

    return tuple(sorted(groups, key=lambda item: (item.name.casefold(), item.key)))

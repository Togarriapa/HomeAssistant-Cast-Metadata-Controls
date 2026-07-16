"""Pure physical-device grouping logic."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .const import ANDROID_TV_ADB_DOMAIN, ANDROID_TV_REMOTE_DOMAIN, CAST_DOMAIN

_STRIP_WORDS = re.compile(
    r"\b(android|google|tv|television|remote|controller|media|renderer|player|adb|cast|"
    r"chromecast|built[ -]?in|smart|device)\b",
    re.IGNORECASE,
)
_DISPLAY_SUFFIX = re.compile(
    r"(?:\s+(?:controller|remote|media\s+(?:player|renderer)|android\s+tv|adb|cast))+$",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_GENERIC_NAMES = frozenset(
    {"", "livingroom", "bedroom", "office", "kitchen", "room", "renderer", "mediarenderer"}
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
        "renderer",
        "samsung",
        "smart",
        "sony",
        "television",
    }
)
_ANDROID_TV_PLATFORMS = frozenset(
    {ANDROID_TV_REMOTE_DOMAIN, ANDROID_TV_ADB_DOMAIN}
)
_SONY_NATIVE_PLATFORMS = frozenset({"braviatv", "sony_bravia"})
_GENERIC_DMR_PLATFORMS = frozenset({"dlna_dmr"})


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
    device_name: str | None = None


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


def _source_names(source: SourceSnapshot) -> tuple[str, ...]:
    """Return every useful identity label exposed for one source."""
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in (source.name, source.device_name, source.model)
            if isinstance(value, str) and value.strip()
        )
    )


def _normalized_names(source: SourceSnapshot) -> frozenset[str]:
    return frozenset(
        normalized
        for value in _source_names(source)
        if (normalized := normalized_device_name(value))
        and normalized not in _GENERIC_NAMES
    )


def _significant_tokens(*values: str | None) -> frozenset[str]:
    """Return distinctive model/family tokens suitable for matching."""
    return frozenset(
        token
        for value in values
        if value
        for token in _TOKEN.findall(clean_device_name(value).casefold())
        if len(token) >= 5
        and token not in _MATCH_STOPWORDS
        and not token.isdecimal()
    )


def _source_tokens(source: SourceSnapshot) -> frozenset[str]:
    return _significant_tokens(*_source_names(source))


def _areas_conflict(first: SourceSnapshot, second: SourceSnapshot) -> bool:
    return bool(
        first.area_id
        and second.area_id
        and first.area_id != second.area_id
    )


def _is_manufacturer_tv(source: SourceSnapshot) -> bool:
    return source.is_tv and source.platform not in {
        ANDROID_TV_REMOTE_DOMAIN,
        ANDROID_TV_ADB_DOMAIN,
        CAST_DOMAIN,
    }


def _is_generic_renderer(source: SourceSnapshot) -> bool:
    """Return whether a source is a generic DLNA MediaRenderer representation."""
    return bool(
        source.platform in _GENERIC_DMR_PLATFORMS
        and normalized_device_name(source.name) in _GENERIC_NAMES
    )


def _is_sony_bravia(source: SourceSnapshot) -> bool:
    """Recognize Sony TV sources even when the entity is only MediaRenderer."""
    manufacturer = (source.manufacturer or "").casefold().strip()
    return bool(
        source.platform in _SONY_NATIVE_PLATFORMS
        or manufacturer == "sony"
        or "bravia" in _source_tokens(source)
        or _is_generic_renderer(source)
    )


def _is_sony_renderer_pair(
    first: SourceSnapshot, second: SourceSnapshot
) -> bool:
    """Match one Sony TV representation with one generic renderer safely."""
    return bool(
        (
            _is_generic_renderer(first)
            and second.platform not in _GENERIC_DMR_PLATFORMS
            and _is_sony_bravia(second)
        )
        or (
            _is_generic_renderer(second)
            and first.platform not in _GENERIC_DMR_PLATFORMS
            and _is_sony_bravia(first)
        )
    )


def _is_complementary_family_pair(
    first: SourceSnapshot, second: SourceSnapshot
) -> bool:
    """Limit family-only matching to complementary representations."""
    native_android = (
        _is_manufacturer_tv(first)
        and second.platform in _ANDROID_TV_PLATFORMS
    ) or (
        _is_manufacturer_tv(second)
        and first.platform in _ANDROID_TV_PLATFORMS
    )
    tv_cast = (first.is_cast and second.is_tv) or (
        second.is_cast and first.is_tv
    )
    return native_android or tv_cast or _is_sony_renderer_pair(first, second)


def _family_match(first: SourceSnapshot, second: SourceSnapshot) -> bool:
    """Return whether two complementary sources share family-level evidence."""
    if _areas_conflict(first, second):
        return False
    if not _is_complementary_family_pair(first, second):
        return False

    first_tokens = _source_tokens(first)
    second_tokens = _source_tokens(second)
    shared = first_tokens & second_tokens
    if shared - {"bravia"}:
        return True

    first_manufacturer = (first.manufacturer or "").casefold().strip()
    second_manufacturer = (second.manufacturer or "").casefold().strip()
    manufacturers_compatible = (
        not first_manufacturer
        or not second_manufacturer
        or first_manufacturer == second_manufacturer
    )
    return bool(
        manufacturers_compatible
        and _is_sony_bravia(first)
        and _is_sony_bravia(second)
    )


def _identity_match(first: SourceSnapshot, second: SourceSnapshot) -> bool:
    """Return only direct, non-ambiguous identity matches."""
    if first.device_id and first.device_id == second.device_id:
        return True
    if (
        first.connections
        and second.connections
        and first.connections & second.connections
    ):
        return True
    if _areas_conflict(first, second):
        return False
    return bool(_normalized_names(first) & _normalized_names(second))


def _clusters_family_match(
    first: list[SourceSnapshot], second: list[SourceSnapshot]
) -> bool:
    """Check family evidence while rejecting conflicting known areas."""
    areas = {
        source.area_id
        for source in (*first, *second)
        if source.area_id
    }
    if len(areas) > 1:
        return False
    return any(
        _family_match(first_source, second_source)
        for first_source in first
        for second_source in second
    )


def _merge_unambiguous_family_clusters(
    clusters: list[list[SourceSnapshot]],
) -> list[list[SourceSnapshot]]:
    """Merge family matches only when each cluster has one reciprocal candidate."""
    while True:
        candidates: dict[int, set[int]] = {
            index: set() for index in range(len(clusters))
        }
        for first_index, first_cluster in enumerate(clusters):
            for second_index in range(first_index + 1, len(clusters)):
                if _clusters_family_match(
                    first_cluster, clusters[second_index]
                ):
                    candidates[first_index].add(second_index)
                    candidates[second_index].add(first_index)

        pair: tuple[int, int] | None = None
        for first_index, matches in candidates.items():
            if len(matches) != 1:
                continue
            second_index = next(iter(matches))
            if candidates.get(second_index) == {first_index}:
                pair = (min(first_index, second_index), max(first_index, second_index))
                break
        if pair is None:
            return clusters

        first_index, second_index = pair
        clusters[first_index].extend(clusters[second_index])
        del clusters[second_index]


def _source_priority(source: SourceSnapshot) -> tuple[int, str]:
    # Manufacturer-native integrations provide the best identity and device name.
    if _is_manufacturer_tv(source):
        priority = 0
    elif source.platform == ANDROID_TV_REMOTE_DOMAIN:
        priority = 1
    elif source.platform == ANDROID_TV_ADB_DOMAIN:
        priority = 2
    else:
        priority = 3
    return priority, source.entity_id


def _preferred_group_name(members: Iterable[SourceSnapshot]) -> str:
    """Prefer a meaningful native hardware name, then a companion TV name."""
    ordered = sorted(members, key=_source_priority)
    for source in ordered:
        for candidate in (source.device_name, source.name, source.model):
            if not candidate:
                continue
            cleaned = clean_device_name(candidate)
            normalized = normalized_device_name(cleaned)
            if normalized and normalized not in _GENERIC_NAMES:
                return cleaned
    return clean_device_name(ordered[0].name)


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
                name=configured_name or _preferred_group_name(members),
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
            if any(_identity_match(source, member) for member in cluster):
                cluster.append(source)
                break
        else:
            tv_clusters.append([source])

    tv_clusters = _merge_unambiguous_family_clusters(tv_clusters)

    remaining_cast = [
        source
        for source in source_list
        if source.is_cast and source.registry_id not in claimed
    ]

    for cluster in tv_clusters:
        attached_cast: list[SourceSnapshot] = []
        for cast_source in tuple(remaining_cast):
            if any(_identity_match(cast_source, tv_source) for tv_source in cluster):
                attached_cast.append(cast_source)
                remaining_cast.remove(cast_source)
                continue

            family_candidates = [
                candidate
                for candidate in tv_clusters
                if _clusters_family_match([cast_source], candidate)
            ]
            if len(family_candidates) == 1 and family_candidates[0] is cluster:
                attached_cast.append(cast_source)
                remaining_cast.remove(cast_source)

        members = tuple(sorted((*cluster, *attached_cast), key=_source_priority))
        primary = members[0]
        groups.append(
            PhysicalGroup(
                key=f"tv:{primary.registry_id}",
                name=_preferred_group_name(members),
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
                name=_preferred_group_name((source,)),
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
                name=_preferred_group_name((source,)),
                source_ids=(source.registry_id,),
                primary_source_id=source.registry_id,
                is_tv=source.is_tv,
            )
        )

    return tuple(sorted(groups, key=lambda item: (item.name.casefold(), item.key)))

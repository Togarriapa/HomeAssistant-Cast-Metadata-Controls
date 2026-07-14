"""Pure helpers for safe YouTube ad detection."""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping

from .const import YOUTUBE_APP_IDS

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_SKIP_RESOURCE_MARKERS = (
    "skip_ad",
    "skip_ads",
    "skipad",
    "skipads",
    "skip_button",
)
_SKIP_LABELS = tuple(
    {
        "skip ad",
        "skip ads",
        "skip advertisement",
        "skip advertisements",
        "ignorar anuncio",
        "ignorar anuncios",
        "saltar anuncio",
        "saltar anuncios",
        "omitir anuncio",
        "omitir anuncios",
        "ignorer l annonce",
        "passer l annonce",
        "werbung uberspringen",
        "anzeige uberspringen",
        "salta annuncio",
        "salta annunci",
        "advertentie overslaan",
        "reclame overslaan",
        "pomin reklame",
    }
)


def normalize_ui_text(value: str) -> str:
    """Normalize localized UI text for conservative label matching."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def is_youtube_attributes(attributes: Mapping[str, object]) -> bool:
    """Return whether current media-player attributes identify YouTube."""
    values = (
        attributes.get("app_id"),
        attributes.get("app_name"),
        attributes.get("source"),
        attributes.get("media_title"),
    )
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped in YOUTUBE_APP_IDS:
            return True
        if "youtube" in normalize_ui_text(stripped):
            return True
    return False


def _node_matches(node: ET.Element) -> bool:
    values = (
        node.attrib.get("text", ""),
        node.attrib.get("content-desc", ""),
        node.attrib.get("resource-id", ""),
    )
    normalized = normalize_ui_text(" ".join(values))
    resource_id = values[2].casefold()
    return any(marker in resource_id for marker in _SKIP_RESOURCE_MARKERS) or any(
        label in normalized for label in _SKIP_LABELS
    )


def _center(bounds: str) -> tuple[int, int] | None:
    match = _BOUNDS.fullmatch(bounds.strip())
    if match is None:
        return None
    left, top, right, bottom = (int(value) for value in match.groups())
    if right <= left or bottom <= top:
        return None
    return ((left + right) // 2, (top + bottom) // 2)


def find_skip_target(raw_xml: str) -> tuple[int, int] | None:
    """Find the center of a positively identified visible Skip-ad control."""
    start = raw_xml.find("<hierarchy")
    if start < 0:
        return None
    try:
        root = ET.fromstring(raw_xml[start:])
    except ET.ParseError:
        return None

    parents = {child: parent for parent in root.iter() for child in parent}
    for node in root.iter():
        if not _node_matches(node):
            continue
        candidate = node
        for _ in range(4):
            if (
                candidate.attrib.get("enabled", "true") != "false"
                and candidate.attrib.get("displayed", "true") != "false"
            ):
                point = _center(candidate.attrib.get("bounds", ""))
                if point is not None and (
                    candidate.attrib.get("clickable", "false") == "true"
                    or candidate is node
                ):
                    return point
            parent = parents.get(candidate)
            if parent is None:
                break
            candidate = parent
    return None


def contains_skip_label(values: Iterable[str]) -> bool:
    """Test helper for localized label coverage."""
    normalized = normalize_ui_text(" ".join(values))
    return any(label in normalized for label in _SKIP_LABELS)

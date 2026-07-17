"""Pure evidence rules for classifying native television representations."""

from __future__ import annotations

from typing import Any

NATIVE_TV_PLATFORMS = frozenset(
    {
        "androidtv",
        "androidtv_remote",
        "braviatv",
        "panasonic_viera",
        "philips_js",
        "samsungtv",
        "sony_bravia",
        "webostv",
    }
)
DLNA_DMR_PLATFORM = "dlna_dmr"


def _text(value: Any) -> str:
    return str(value or "").casefold().strip()


def is_native_tv(
    *,
    platform: str,
    registry_device_class: str | None = None,
    state_device_class: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    device_name: str | None = None,
    friendly_name: str | None = None,
) -> bool:
    """Return whether a media-player source is positively identifiable as a TV."""
    if platform in NATIVE_TV_PLATFORMS:
        return True
    if registry_device_class == "tv" or state_device_class == "tv":
        return True
    if platform != DLNA_DMR_PLATFORM:
        return False

    evidence = " ".join(
        _text(value)
        for value in (manufacturer, model, device_name, friendly_name)
        if value
    )
    words = set(evidence.replace("-", " ").replace("_", " ").split())
    return bool(
        "bravia" in evidence
        or "television" in words
        or "sony" in words
        or "tv" in words
    )

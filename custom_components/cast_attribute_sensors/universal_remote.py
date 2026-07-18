"""Pure helpers for universal television remote routing."""

from __future__ import annotations

import re
from typing import Final

PROFILE_AUTO: Final = "auto"
PROFILE_ANDROID_TV_REMOTE: Final = "androidtv_remote"
PROFILE_ANDROID_TV_ADB: Final = "androidtv"
PROFILE_BRAVIA: Final = "braviatv"
PROFILE_GENERIC: Final = "generic"

PROFILE_LABELS: Final[dict[str, str]] = {
    PROFILE_AUTO: "Automatic",
    PROFILE_ANDROID_TV_REMOTE: "Android TV Remote",
    PROFILE_ANDROID_TV_ADB: "Android TV ADB",
    PROFILE_BRAVIA: "Sony BRAVIA",
    PROFILE_GENERIC: "Generic (send command unchanged)",
}

_PLATFORM_PROFILES: Final[dict[str, str]] = {
    "androidtv_remote": PROFILE_ANDROID_TV_REMOTE,
    "androidtv": PROFILE_ANDROID_TV_ADB,
    "braviatv": PROFILE_BRAVIA,
    "sony_bravia": PROFILE_BRAVIA,
}

_COMMAND_MAPS: Final[dict[str, dict[str, str]]] = {
    PROFILE_ANDROID_TV_REMOTE: {},
    PROFILE_ANDROID_TV_ADB: {
        "DPAD_UP": "UP",
        "DPAD_DOWN": "DOWN",
        "DPAD_LEFT": "LEFT",
        "DPAD_RIGHT": "RIGHT",
        "DPAD_CENTER": "CENTER",
        "BACK": "BACK",
        "HOME": "HOME",
        "SETTINGS": "SETTINGS",
    },
    PROFILE_BRAVIA: {
        "DPAD_UP": "Up",
        "DPAD_DOWN": "Down",
        "DPAD_LEFT": "Left",
        "DPAD_RIGHT": "Right",
        "DPAD_CENTER": "Confirm",
        "BACK": "Return",
        "HOME": "Home",
        "SETTINGS": "ActionMenu",
    },
    PROFILE_GENERIC: {},
}

_INPUT_PATTERN = re.compile(
    r"(?:^|\b)(?:tv|hdmi|scart|av|component|composite|tuner|digital|analog|"
    r"antenna|satellite|cable|screen mirroring)(?:\b|$)",
    re.IGNORECASE,
)


def profile_for_platform(platform: str | None) -> str:
    """Return the command profile associated with a remote platform."""
    return _PLATFORM_PROFILES.get(str(platform or "").casefold(), PROFILE_GENERIC)


def is_auto_supported_platform(platform: str | None) -> bool:
    """Return whether an integration can be selected automatically and translated."""
    return str(platform or "").casefold() in _PLATFORM_PROFILES


def translate_command(profile: str, command: str) -> str:
    """Translate the card's Android-style command into the provider command."""
    normalized = command.strip()
    return _COMMAND_MAPS.get(profile, {}).get(normalized, normalized)


def native_source_kind(name: str) -> str:
    """Classify a Sony source-list item as an input or an application."""
    cleaned = name.strip()
    if not cleaned:
        return "input"
    return "input" if _INPUT_PATTERN.search(cleaned) else "native_app"

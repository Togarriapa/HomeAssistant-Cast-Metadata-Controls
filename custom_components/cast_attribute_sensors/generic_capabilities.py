"""Pure helpers for user-defined physical-device capability routing."""

from __future__ import annotations

import re
from typing import Final

CAPABILITY_NAVIGATION: Final = "navigation"
CAPABILITY_RESTART: Final = "restart"

LOGICAL_COMMANDS: Final[tuple[str, ...]] = (
    "HOME",
    "BACK",
    "SETTINGS",
    "DPAD_UP",
    "DPAD_DOWN",
    "DPAD_LEFT",
    "DPAD_RIGHT",
    "DPAD_CENTER",
)

COMMAND_LABELS: Final[dict[str, str]] = {
    "HOME": "Home",
    "BACK": "Back",
    "SETTINGS": "Settings",
    "DPAD_UP": "Up",
    "DPAD_DOWN": "Down",
    "DPAD_LEFT": "Left",
    "DPAD_RIGHT": "Right",
    "DPAD_CENTER": "OK / Select",
}

_INPUT_PATTERN = re.compile(
    r"^(?:"
    r"tv(?:\s+(?:tuner|input))?|"
    r"hdmi(?:\s|$).*|"
    r"scart(?:\s|$).*|"
    r"av(?:\s|$).*|"
    r"component(?:\s|$).*|"
    r"composite(?:\s|$).*|"
    r"tuner(?:\s|$).*|"
    r"digital(?:\s+(?:tuner|tv|input))?|"
    r"analog(?:\s+(?:tuner|tv|input))?|"
    r"antenna(?:\s|$).*|"
    r"satellite(?:\s|$).*|"
    r"cable(?:\s|$).*|"
    r"screen\s+mirroring|"
    r"displayport(?:\s|$).*|"
    r"usb(?:\s|$).*"
    r")$",
    re.IGNORECASE,
)


def source_kind(value: str) -> str:
    """Classify a generic source-list item as an input or a launchable source."""
    cleaned = " ".join(value.split())
    if not cleaned:
        return "input"
    return "input" if _INPUT_PATTERN.fullmatch(cleaned) else "native_source"


def command_for(command_map: dict[str, str], logical_command: str) -> str:
    """Return the user-configured provider command or pass the logical name through."""
    configured = str(command_map.get(logical_command, "")).strip()
    return configured or logical_command.strip()


def normalized_command_map(value: object) -> dict[str, str]:
    """Normalize a stored command mapping and discard unsupported keys."""
    if not isinstance(value, dict):
        return {}
    return {
        command: configured.strip()
        for command in LOGICAL_COMMANDS
        if isinstance((configured := value.get(command)), str)
        and configured.strip()
        and configured.strip() != command
    }

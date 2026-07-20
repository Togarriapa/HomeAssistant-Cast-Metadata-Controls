"""Runtime registry for opt-in ad-skip managers."""

from __future__ import annotations

from .ad_skip import AdSkipManager

_MANAGERS: dict[str, AdSkipManager] = {}


def register_manager(entry_id: str, manager: AdSkipManager) -> None:
    """Register the manager belonging to one config entry."""
    # Install the runtime layers before controller platforms are forwarded. Keeping
    # this idempotent hook preserves startup compatibility with the v8.3 release.
    from .v83_patch import install_v83_patches
    from .v831_patch import install_v831_patches

    install_v83_patches()
    install_v831_patches()
    _MANAGERS[entry_id] = manager


def get_manager(entry_id: str) -> AdSkipManager:
    """Return the manager for a loaded config entry."""
    return _MANAGERS[entry_id]


def remove_manager(entry_id: str) -> AdSkipManager | None:
    """Remove and return a manager during unload."""
    return _MANAGERS.pop(entry_id, None)

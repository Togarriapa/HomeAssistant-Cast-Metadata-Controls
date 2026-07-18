"""Runtime registry for opt-in ad-skip managers."""

from __future__ import annotations

from .ad_skip import AdSkipManager

_MANAGERS: dict[str, AdSkipManager] = {}


def register_manager(entry_id: str, manager: AdSkipManager) -> None:
    """Register the manager belonging to one config entry."""
    # This runs after the V8.1 startup patch and before controller platforms are
    # forwarded, so the generic V8.3 capability layer is installed in the
    # correct order without relying on integration-specific import timing.
    from .v83_patch import install_v83_patches

    install_v83_patches()
    _MANAGERS[entry_id] = manager


def get_manager(entry_id: str) -> AdSkipManager:
    """Return the manager for a loaded config entry."""
    return _MANAGERS[entry_id]


def remove_manager(entry_id: str) -> AdSkipManager | None:
    """Remove and return a manager during unload."""
    return _MANAGERS.pop(entry_id, None)

"""Runtime registry for opt-in ad-skip managers."""

from __future__ import annotations

from .ad_skip import AdSkipManager

_MANAGERS: dict[str, AdSkipManager] = {}


def register_manager(entry_id: str, manager: AdSkipManager) -> None:
    """Register the manager belonging to one config entry."""
    # Install runtime layers before controller platforms are forwarded. Each layer is
    # idempotent and preserves existing entity IDs and stored configuration.
    from .v83_patch import install_v83_patches
    from .v831_patch import install_v831_patches
    from .v840_patch import install_v840_patches

    install_v83_patches()
    install_v831_patches()
    install_v840_patches()

    # V8.4 also tracks external media players that require explicit assignment. The
    # initial source scan happened before the release patches were installed, so rescan
    # and rebuild groups once before entities are forwarded to their platforms.
    manager.runtime.manager._async_rescan_sources()  # noqa: SLF001
    manager.runtime.refresh_groups()
    _MANAGERS[entry_id] = manager


def get_manager(entry_id: str) -> AdSkipManager:
    """Return the manager belonging to a loaded config entry."""
    return _MANAGERS[entry_id]


def remove_manager(entry_id: str) -> AdSkipManager | None:
    """Remove and return a manager during unload."""
    return _MANAGERS.pop(entry_id, None)

"""Helpers for creating one fixed entity set per Cast source."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .manager import CastManager


def setup_source_entities[EntityT: Entity](
    entry: ConfigEntry,
    manager: CastManager,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[CastManager, str], Iterable[EntityT]],
) -> None:
    """Create fixed entities for current and newly discovered Cast sources."""
    added_sources: set[str] = set()

    def add_source(source_registry_id: str) -> None:
        if source_registry_id in added_sources:
            return
        added_sources.add(source_registry_id)
        entities = list(factory(manager, source_registry_id))
        if entities:
            async_add_entities(entities)

    for source_registry_id in manager.source_ids:
        add_source(source_registry_id)

    entry.async_on_unload(manager.async_subscribe_source_added(add_source))

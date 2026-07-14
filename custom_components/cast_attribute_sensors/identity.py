"""Persistent physical-device identity matching."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import replace
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import IDENTITY_STORAGE_KEY, STORAGE_VERSION
from .grouping import PhysicalGroup, SourceSnapshot, normalized_device_name


class PhysicalIdentityStore:
    """Keep a stable integration device ID when native entities are recreated."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, IDENTITY_STORAGE_KEY
        )
        self._profiles: dict[str, set[str]] = {}
        self._save_task: asyncio.Task[None] | None = None

    async def async_initialize(self) -> None:
        stored = await self._store.async_load()
        if not isinstance(stored, dict):
            return
        raw_profiles = stored.get("profiles", {})
        if not isinstance(raw_profiles, dict):
            return
        for profile_id, values in raw_profiles.items():
            if isinstance(values, list):
                self._profiles[str(profile_id)] = {str(value) for value in values}

    async def async_stop(self) -> None:
        if self._save_task is not None and not self._save_task.done():
            self._save_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._save_task
        await self._async_save()

    def resolve_groups(
        self,
        groups: Iterable[PhysicalGroup],
        snapshots: Iterable[SourceSnapshot],
    ) -> tuple[PhysicalGroup, ...]:
        """Replace transient automatic keys with persistent profile IDs."""
        by_id = {snapshot.registry_id: snapshot for snapshot in snapshots}
        resolved: list[PhysicalGroup] = []
        changed = False
        claimed_profiles: set[str] = set()

        for group in groups:
            if group.key.startswith("manual:"):
                resolved.append(group)
                continue
            members = [
                by_id[source_id]
                for source_id in group.source_ids
                if source_id in by_id
            ]
            tokens = self._tokens(members)
            profile_id = self._best_profile(tokens, claimed_profiles)
            if profile_id is None:
                profile_id = uuid4().hex
                self._profiles[profile_id] = set()
                changed = True
            claimed_profiles.add(profile_id)
            before = len(self._profiles[profile_id])
            self._profiles[profile_id].update(tokens)
            changed |= len(self._profiles[profile_id]) != before
            resolved.append(replace(group, key=f"physical:{profile_id}"))

        if changed:
            self._schedule_save()
        return tuple(resolved)

    def _tokens(self, members: Iterable[SourceSnapshot]) -> set[str]:
        tokens: set[str] = set()
        for member in members:
            for connection_type, value in member.connections:
                tokens.add(f"connection:{connection_type}:{value.casefold()}")
            if member.device_id:
                tokens.add(f"device:{member.device_id}")
            normalized = normalized_device_name(member.name)
            if normalized:
                area = member.area_id or "_"
                tokens.add(f"name-area:{normalized}:{area}")
                tokens.add(f"platform-name:{member.platform}:{normalized}")
        return tokens

    def _best_profile(self, tokens: set[str], claimed: set[str]) -> str | None:
        best_id: str | None = None
        best_score = 0
        tied = False
        for profile_id, existing in self._profiles.items():
            if profile_id in claimed:
                continue
            overlap = tokens & existing
            score = sum(self._token_weight(token) for token in overlap)
            if score > best_score:
                best_id = profile_id
                best_score = score
                tied = False
            elif score and score == best_score:
                tied = True
        return None if tied or best_score < 20 else best_id

    @staticmethod
    def _token_weight(token: str) -> int:
        if token.startswith("connection:mac:"):
            return 100
        if token.startswith("connection:"):
            return 80
        if token.startswith("device:"):
            return 90
        if token.startswith("name-area:"):
            return 35
        if token.startswith("platform-name:"):
            return 20
        return 1

    def _schedule_save(self) -> None:
        if self._save_task is not None and not self._save_task.done():
            return
        self._save_task = self.hass.async_create_task(
            self._async_delayed_save(), f"{IDENTITY_STORAGE_KEY}-save"
        )

    async def _async_delayed_save(self) -> None:
        await asyncio.sleep(1)
        await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "profiles": {
                    key: sorted(values) for key, values in self._profiles.items()
                }
            }
        )

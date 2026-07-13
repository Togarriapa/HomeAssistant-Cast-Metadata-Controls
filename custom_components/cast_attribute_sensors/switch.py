"""Power, mute, and shuffle switch entities."""

from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UID_SEPARATOR, UID_VERSION
from .entity import CastLinkedEntity
from .manager import CastManager
from .platform import setup_source_entities
from .tv_entity import TvLinkedEntity
from .tv_manager import TvManager
from .tv_platform import setup_tv_entities


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Cast and native TV switches."""
    cast_manager: CastManager = entry.runtime_data.manager
    tv_manager: TvManager = entry.runtime_data.tv_manager
    setup_source_entities(entry, cast_manager, async_add_entities, _make_cast_switches)
    setup_tv_entities(entry, tv_manager, async_add_entities, _make_tv_switches)


def _make_cast_switches(
    manager: CastManager, source_registry_id: str
) -> list[SwitchEntity]:
    return [
        CastReceiverPowerSwitch(manager, source_registry_id),
        CastMuteSwitch(manager, source_registry_id),
        CastShuffleSwitch(manager, source_registry_id),
    ]


def _make_tv_switches(
    manager: TvManager, source_registry_id: str
) -> list[SwitchEntity]:
    return [
        TvPowerSwitch(manager, source_registry_id),
        TvMuteSwitch(manager, source_registry_id),
    ]


class CastReceiverPowerSwitch(CastLinkedEntity, SwitchEntity):
    """Start or close the Cast receiver application."""

    _attr_name = "Cast receiver power"
    _attr_icon = "mdi:cast-connected"

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        """Initialize the Cast receiver power switch."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "switch", "receiver_power")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether both receiver start and close are supported."""
        return super().available and (
            self._manager.source_supports(
                self._source_registry_id, MediaPlayerEntityFeature.TURN_ON
            )
            or self._manager.source_supports(
                self._source_registry_id, MediaPlayerEntityFeature.TURN_OFF
            )
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether the Cast entity reports an active receiver."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        return state.state not in ("off", "unavailable", "unknown")

    async def async_turn_on(self, **kwargs) -> None:
        """Start the Cast receiver."""
        await self._manager.async_call_media_player(self._source_registry_id, "turn_on")

    async def async_turn_off(self, **kwargs) -> None:
        """Close the current Cast receiver app."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "turn_off"
        )


class CastMuteSwitch(CastLinkedEntity, SwitchEntity):
    """Expose Cast mute as a normal switch entity."""

    _attr_name = "Cast mute"
    _attr_icon = "mdi:volume-mute"

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        """Initialize the mute switch."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "switch", "mute")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether volume muting is supported."""
        return super().available and self._manager.source_supports(
            self._source_registry_id, MediaPlayerEntityFeature.VOLUME_MUTE
        )

    @property
    def is_on(self) -> bool | None:
        """Return the current mute state."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        muted = state.attributes.get("is_volume_muted")
        return muted if isinstance(muted, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        """Mute the Cast device."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "volume_mute", {"is_volume_muted": True}
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Unmute the Cast device."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "volume_mute", {"is_volume_muted": False}
        )


class CastShuffleSwitch(CastLinkedEntity, SwitchEntity):
    """Expose native media shuffle as a switch."""

    _attr_name = "Cast shuffle"
    _attr_icon = "mdi:shuffle"

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        """Initialize the shuffle switch."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "switch", "shuffle")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether shuffle is supported."""
        return super().available and self._manager.source_supports(
            self._source_registry_id, MediaPlayerEntityFeature.SHUFFLE_SET
        )

    @property
    def is_on(self) -> bool | None:
        """Return the current shuffle state."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        shuffle = state.attributes.get("shuffle")
        return shuffle if isinstance(shuffle, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        """Enable shuffle."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "shuffle_set", {"shuffle": True}
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Disable shuffle."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "shuffle_set", {"shuffle": False}
        )


class TvPowerSwitch(TvLinkedEntity, SwitchEntity):
    """Expose reliable native TV power when supported."""

    _attr_name = "TV power"
    _attr_icon = "mdi:television"

    def __init__(self, manager: TvManager, source_registry_id: str) -> None:
        """Initialize the TV power switch."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "switch", "tv_power")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether native power control is supported."""
        return super().available and (
            self._manager.source_supports(
                self._source_registry_id, MediaPlayerEntityFeature.TURN_ON
            )
            or self._manager.source_supports(
                self._source_registry_id, MediaPlayerEntityFeature.TURN_OFF
            )
        )

    @property
    def is_on(self) -> bool | None:
        """Return the native TV power state."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        return state.state not in ("off", "unavailable", "unknown")

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the TV on."""
        await self._manager.async_call_media_player(self._source_registry_id, "turn_on")

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the TV off."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "turn_off"
        )


class TvMuteSwitch(TvLinkedEntity, SwitchEntity):
    """Expose native TV mute as a switch."""

    _attr_name = "TV mute"
    _attr_icon = "mdi:volume-mute"

    def __init__(self, manager: TvManager, source_registry_id: str) -> None:
        """Initialize the TV mute switch."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "switch", "tv_mute")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether TV volume muting is supported."""
        return super().available and self._manager.source_supports(
            self._source_registry_id, MediaPlayerEntityFeature.VOLUME_MUTE
        )

    @property
    def is_on(self) -> bool | None:
        """Return the current TV mute state."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        muted = state.attributes.get("is_volume_muted")
        return muted if isinstance(muted, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        """Mute the TV."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "volume_mute", {"is_volume_muted": True}
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Unmute the TV."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "volume_mute", {"is_volume_muted": False}
        )

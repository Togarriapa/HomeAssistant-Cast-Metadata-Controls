"""Cast and native TV control button entities."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import UID_SEPARATOR, UID_VERSION
from .entity import CastLinkedEntity
from .manager import CastManager
from .platform import setup_source_entities
from .tv_entity import TvLinkedEntity
from .tv_manager import TvManager
from .tv_platform import setup_tv_entities


@dataclass(frozen=True, kw_only=True)
class CastButtonDescription:
    """Describe one Cast button."""

    key: str
    name: str
    icon: str
    service: str | None = None
    feature: MediaPlayerEntityFeature | None = None
    play_pause: bool = False
    restart_receiver: bool = False
    seek_offset: float | None = None
    enabled_default: bool = True


CAST_BUTTONS: tuple[CastButtonDescription, ...] = (
    CastButtonDescription(
        key="power_on",
        name="Start receiver",
        icon="mdi:cast-connected",
        service="turn_on",
        feature=MediaPlayerEntityFeature.TURN_ON,
    ),
    CastButtonDescription(
        key="restart_receiver",
        name="Restart Cast receiver",
        icon="mdi:restart",
        restart_receiver=True,
    ),
    CastButtonDescription(
        key="play_pause",
        name="Play / pause",
        icon="mdi:play-pause",
        play_pause=True,
    ),
    CastButtonDescription(
        key="stop",
        name="Stop media",
        icon="mdi:stop",
        service="media_stop",
        feature=MediaPlayerEntityFeature.STOP,
    ),
    CastButtonDescription(
        key="seek_back_10",
        name="Rewind 10 seconds",
        icon="mdi:rewind-10",
        feature=MediaPlayerEntityFeature.SEEK,
        seek_offset=-10,
    ),
    CastButtonDescription(
        key="seek_forward_10",
        name="Forward 10 seconds",
        icon="mdi:fast-forward-10",
        feature=MediaPlayerEntityFeature.SEEK,
        seek_offset=10,
    ),
    CastButtonDescription(
        key="previous",
        name="Previous track",
        icon="mdi:skip-previous",
        service="media_previous_track",
        feature=MediaPlayerEntityFeature.PREVIOUS_TRACK,
    ),
    CastButtonDescription(
        key="next",
        name="Next track",
        icon="mdi:skip-next",
        service="media_next_track",
        feature=MediaPlayerEntityFeature.NEXT_TRACK,
    ),
    CastButtonDescription(
        key="volume_down",
        name="Volume down",
        icon="mdi:volume-minus",
        service="volume_down",
        feature=MediaPlayerEntityFeature.VOLUME_STEP,
    ),
    CastButtonDescription(
        key="volume_up",
        name="Volume up",
        icon="mdi:volume-plus",
        service="volume_up",
        feature=MediaPlayerEntityFeature.VOLUME_STEP,
    ),
    CastButtonDescription(
        key="close_app",
        name="Close app",
        icon="mdi:close-box-outline",
        service="turn_off",
        feature=MediaPlayerEntityFeature.TURN_OFF,
    ),
)


@dataclass(frozen=True, kw_only=True)
class TvButtonDescription:
    """Describe one native TV control button."""

    key: str
    name: str
    icon: str
    service: str | None = None
    feature: MediaPlayerEntityFeature | None = None
    command: str | None = None
    play_pause: bool = False
    reload_app: bool = False
    restart_device: bool = False
    enabled_default: bool = True


TV_BUTTONS: tuple[TvButtonDescription, ...] = (
    TvButtonDescription(
        key="play_pause",
        name="TV play / pause",
        icon="mdi:play-pause",
        play_pause=True,
    ),
    TvButtonDescription(
        key="volume_down",
        name="TV volume down",
        icon="mdi:volume-minus",
        service="volume_down",
        feature=MediaPlayerEntityFeature.VOLUME_STEP,
    ),
    TvButtonDescription(
        key="volume_up",
        name="TV volume up",
        icon="mdi:volume-plus",
        service="volume_up",
        feature=MediaPlayerEntityFeature.VOLUME_STEP,
    ),
    TvButtonDescription(
        key="home",
        name="TV home",
        icon="mdi:home",
        command="HOME",
    ),
    TvButtonDescription(
        key="back",
        name="TV back",
        icon="mdi:arrow-left",
        command="BACK",
    ),
    TvButtonDescription(
        key="restart_device",
        name="Restart TV",
        icon="mdi:restart-alert",
        restart_device=True,
    ),
    TvButtonDescription(
        key="reload_app",
        name="Reload current TV app",
        icon="mdi:restart",
        reload_app=True,
    ),
    TvButtonDescription(
        key="settings",
        name="TV settings",
        icon="mdi:cog",
        command="SETTINGS",
        enabled_default=False,
    ),
    TvButtonDescription(
        key="info",
        name="TV information",
        icon="mdi:information-outline",
        command="INFO",
        enabled_default=False,
    ),
    TvButtonDescription(
        key="channel_up",
        name="TV channel up",
        icon="mdi:chevron-up",
        command="CHANNEL_UP",
        enabled_default=False,
    ),
    TvButtonDescription(
        key="channel_down",
        name="TV channel down",
        icon="mdi:chevron-down",
        command="CHANNEL_DOWN",
        enabled_default=False,
    ),
    TvButtonDescription(
        key="dpad_up",
        name="TV navigate up",
        icon="mdi:arrow-up-bold",
        command="DPAD_UP",
        enabled_default=False,
    ),
    TvButtonDescription(
        key="dpad_down",
        name="TV navigate down",
        icon="mdi:arrow-down-bold",
        command="DPAD_DOWN",
        enabled_default=False,
    ),
    TvButtonDescription(
        key="dpad_left",
        name="TV navigate left",
        icon="mdi:arrow-left-bold",
        command="DPAD_LEFT",
        enabled_default=False,
    ),
    TvButtonDescription(
        key="dpad_right",
        name="TV navigate right",
        icon="mdi:arrow-right-bold",
        command="DPAD_RIGHT",
        enabled_default=False,
    ),
    TvButtonDescription(
        key="dpad_ok",
        name="TV select",
        icon="mdi:checkbox-blank-circle-outline",
        command="DPAD_CENTER",
        enabled_default=False,
    ),
)


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Cast and native TV control buttons."""
    cast_manager: CastManager = entry.runtime_data.manager
    tv_manager: TvManager = entry.runtime_data.tv_manager
    setup_source_entities(entry, cast_manager, async_add_entities, _make_cast_buttons)
    setup_tv_entities(entry, tv_manager, async_add_entities, _make_tv_buttons)


def _make_cast_buttons(
    manager: CastManager, source_registry_id: str
) -> list[CastControlButton]:
    return [
        CastControlButton(manager, source_registry_id, description)
        for description in CAST_BUTTONS
    ]


def _make_tv_buttons(
    manager: TvManager, source_registry_id: str
) -> list[TvControlButton]:
    has_remote = manager.get_remote_entity_id(source_registry_id) is not None
    has_restart = manager.get_restart_entity_id(source_registry_id) is not None
    return [
        TvControlButton(manager, source_registry_id, description)
        for description in TV_BUTTONS
        if (
            (description.restart_device and has_restart)
            or has_remote
            or (
                description.command is None
                and not description.reload_app
                and not description.restart_device
            )
        )
    ]


class CastControlButton(CastLinkedEntity, ButtonEntity):
    """A standalone control for a native Cast media player."""

    def __init__(
        self,
        manager: CastManager,
        source_registry_id: str,
        description: CastButtonDescription,
    ) -> None:
        """Initialize the Cast button."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "button", description.key)
        )
        super().__init__(manager, source_registry_id, unique_id)
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def available(self) -> bool:
        """Return whether this Cast action is currently supported."""
        if not super().available:
            return False
        if self._description.restart_receiver:
            return self._manager.source_supports(
                self._source_registry_id, MediaPlayerEntityFeature.TURN_ON
            )
        if self._description.play_pause:
            state = self._manager.get_source_state(self._source_registry_id)
            if state is None:
                return False
            feature = (
                MediaPlayerEntityFeature.PAUSE
                if state.state == "playing"
                else MediaPlayerEntityFeature.PLAY
            )
            return self._manager.source_supports(self._source_registry_id, feature)
        if self._description.feature is None:
            return True
        return self._manager.source_supports(
            self._source_registry_id, self._description.feature
        )

    async def async_press(self) -> None:
        """Execute the requested Cast action."""
        if self._description.restart_receiver:
            await self._manager.async_soft_restart_receiver(self._source_registry_id)
            return
        if self._description.seek_offset is not None:
            await self._manager.async_seek_relative(
                self._source_registry_id, self._description.seek_offset
            )
            return
        service = self._description.service
        if self._description.play_pause:
            state = self._manager.get_source_state(self._source_registry_id)
            service = (
                "media_pause" if state and state.state == "playing" else "media_play"
            )
        assert service is not None
        await self._manager.async_call_media_player(self._source_registry_id, service)


class TvControlButton(TvLinkedEntity, ButtonEntity):
    """A standalone native TV or Android TV Remote control."""

    def __init__(
        self,
        manager: TvManager,
        source_registry_id: str,
        description: TvButtonDescription,
    ) -> None:
        """Initialize the TV control button."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "button", description.key)
        )
        super().__init__(manager, source_registry_id, unique_id)
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def available(self) -> bool:
        """Return whether this TV action is currently supported."""
        if not super().available:
            return False
        if self._description.restart_device:
            return (
                self._manager.get_restart_entity_id(self._source_registry_id)
                is not None
            )
        if self._description.command is not None:
            return (
                self._manager.get_remote_entity_id(self._source_registry_id) is not None
            )
        if self._description.reload_app:
            state = self._manager.get_source_state(self._source_registry_id)
            return (
                self._manager.get_remote_entity_id(self._source_registry_id) is not None
                and state is not None
                and isinstance(state.attributes.get("app_id"), str)
            )
        if self._description.play_pause:
            if self._manager.get_remote_entity_id(self._source_registry_id) is not None:
                return True
            state = self._manager.get_source_state(self._source_registry_id)
            if state is None:
                return False
            feature = (
                MediaPlayerEntityFeature.PAUSE
                if state.state == "playing"
                else MediaPlayerEntityFeature.PLAY
            )
            return self._manager.source_supports(self._source_registry_id, feature)
        if self._description.feature is None:
            return True
        return self._manager.source_supports(
            self._source_registry_id, self._description.feature
        )

    async def async_press(self) -> None:
        """Execute the requested TV action."""
        if self._description.restart_device:
            await self._manager.async_press_native_restart(self._source_registry_id)
            return
        if self._description.command is not None:
            await self._manager.async_send_remote_command(
                self._source_registry_id, self._description.command
            )
            return
        if self._description.reload_app:
            await self._manager.async_reload_current_app(self._source_registry_id)
            return
        service = self._description.service
        if self._description.play_pause:
            if self._manager.get_remote_entity_id(self._source_registry_id) is not None:
                await self._manager.async_send_remote_command(
                    self._source_registry_id, "MEDIA_PLAY_PAUSE"
                )
                return
            state = self._manager.get_source_state(self._source_registry_id)
            service = (
                "media_pause" if state and state.state == "playing" else "media_play"
            )
        assert service is not None
        await self._manager.async_call_media_player(self._source_registry_id, service)

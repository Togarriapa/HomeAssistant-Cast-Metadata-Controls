"""Cast receiver, TV application, input, and repeat selectors."""

from __future__ import annotations

from collections import Counter

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.components.select import SelectEntity
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
    """Set up Cast and native TV selectors."""
    cast_manager: CastManager = entry.runtime_data.manager
    tv_manager: TvManager = entry.runtime_data.tv_manager
    setup_source_entities(entry, cast_manager, async_add_entities, _make_cast_selects)
    setup_tv_entities(entry, tv_manager, async_add_entities, _make_tv_selects)


def _make_cast_selects(
    manager: CastManager, source_registry_id: str
) -> list[SelectEntity]:
    return [
        CastAppSelect(manager, source_registry_id),
        CastRepeatSelect(manager, source_registry_id),
    ]


def _make_tv_selects(manager: TvManager, source_registry_id: str) -> list[SelectEntity]:
    entities: list[SelectEntity] = [TvSourceSelect(manager, source_registry_id)]
    if manager.get_apps(source_registry_id):
        entities.insert(0, TvAppSelect(manager, source_registry_id))
    return entities


def _build_option_maps(apps: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Build stable display-option mappings for an application catalogue."""
    name_counts = Counter(apps.values())
    option_to_id: dict[str, str] = {}
    id_to_option: dict[str, str] = {}
    for app_id, app_name in sorted(
        apps.items(), key=lambda item: (item[1].casefold(), item[0])
    ):
        option = app_name if name_counts[app_name] == 1 else f"{app_name} [{app_id}]"
        option_to_id[option] = app_id
        id_to_option[app_id] = option
    return option_to_id, id_to_option


class CastAppSelect(CastLinkedEntity, SelectEntity):
    """Select and launch default or previously observed Cast apps."""

    _attr_name = "Cast app"
    _attr_icon = "mdi:application-cog-outline"

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        """Initialize the Cast receiver app selector."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "select", "app")
        )
        super().__init__(manager, source_registry_id, unique_id)

    def _option_maps(self) -> tuple[dict[str, str], dict[str, str]]:
        return _build_option_maps(self._manager.get_apps(self._source_registry_id))

    @property
    def options(self) -> list[str]:
        """Return default and learned Cast receiver applications."""
        return list(self._option_maps()[0])

    @property
    def current_option(self) -> str | None:
        """Return the currently active Cast application."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        app_id = state.attributes.get("app_id")
        if not isinstance(app_id, str):
            return None
        return self._option_maps()[1].get(app_id)

    async def async_select_option(self, option: str) -> None:
        """Launch the selected Cast receiver application."""
        await self._manager.async_launch_app(
            self._source_registry_id, self._option_maps()[0][option]
        )


class CastRepeatSelect(CastLinkedEntity, SelectEntity):
    """Expose native media repeat mode as a select."""

    _attr_name = "Cast repeat"
    _attr_icon = "mdi:repeat"
    _attr_options = ["off", "all", "one"]

    def __init__(self, manager: CastManager, source_registry_id: str) -> None:
        """Initialize the repeat selector."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "select", "repeat")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether repeat mode is supported."""
        return super().available and self._manager.source_supports(
            self._source_registry_id, MediaPlayerEntityFeature.REPEAT_SET
        )

    @property
    def current_option(self) -> str | None:
        """Return the reported repeat mode."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        repeat = state.attributes.get("repeat")
        return repeat if isinstance(repeat, str) and repeat in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Set the native media repeat mode."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "repeat_set", {"repeat": option}
        )


class TvAppSelect(TvLinkedEntity, SelectEntity):
    """Select an installed/configured Android or Google TV application."""

    _attr_name = "TV app"
    _attr_icon = "mdi:apps"

    def __init__(self, manager: TvManager, source_registry_id: str) -> None:
        """Initialize the native TV app selector."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "select", "tv_app")
        )
        super().__init__(manager, source_registry_id, unique_id)

    def _option_maps(self) -> tuple[dict[str, str], dict[str, str]]:
        return _build_option_maps(self._manager.get_apps(self._source_registry_id))

    @property
    def available(self) -> bool:
        """Return whether Android TV app launching is available."""
        return super().available and bool(self._option_maps()[0])

    @property
    def options(self) -> list[str]:
        """Return common, configured, and learned TV applications."""
        return list(self._option_maps()[0])

    @property
    def current_option(self) -> str | None:
        """Return the foreground Android TV application."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        app_id = state.attributes.get("app_id")
        if not isinstance(app_id, str):
            return None
        return self._option_maps()[1].get(app_id)

    async def async_select_option(self, option: str) -> None:
        """Launch the selected Android/Google TV application."""
        await self._manager.async_launch_app(
            self._source_registry_id, self._option_maps()[0][option]
        )


class TvSourceSelect(TvLinkedEntity, SelectEntity):
    """Select an HDMI input, tuner, application, or other TV source."""

    _attr_name = "TV input"
    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, manager: TvManager, source_registry_id: str) -> None:
        """Initialize the TV source selector."""
        unique_id = UID_SEPARATOR.join(
            (UID_VERSION, source_registry_id, "select", "tv_source")
        )
        super().__init__(manager, source_registry_id, unique_id)

    @property
    def available(self) -> bool:
        """Return whether native source selection is supported."""
        return (
            super().available
            and self._manager.source_supports(
                self._source_registry_id, MediaPlayerEntityFeature.SELECT_SOURCE
            )
            and bool(self.options)
        )

    @property
    def options(self) -> list[str]:
        """Return the native TV source list."""
        return self._manager.get_sources(self._source_registry_id)

    @property
    def current_option(self) -> str | None:
        """Return the currently selected TV source."""
        state = self._manager.get_source_state(self._source_registry_id)
        if state is None:
            return None
        source = state.attributes.get("source")
        return source if isinstance(source, str) and source in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Select the requested TV source."""
        await self._manager.async_call_media_player(
            self._source_registry_id, "select_source", {"source": option}
        )

"""Constants for Cast Metadata & TV Controls."""

from typing import Final

DOMAIN: Final = "cast_attribute_sensors"
NAME: Final = "Cast Metadata & TV Controls"
VERSION: Final = "7.4.2"

CAST_DOMAIN: Final = "cast"
ANDROID_TV_REMOTE_DOMAIN: Final = "androidtv_remote"
ANDROID_TV_ADB_DOMAIN: Final = "androidtv"
MEDIA_PLAYER_DOMAIN: Final = "media_player"
REMOTE_DOMAIN: Final = "remote"
BUTTON_DOMAIN: Final = "button"
SENSOR_DOMAIN: Final = "sensor"
EVENT_DOMAIN: Final = "event"
WAKE_ON_LAN_DOMAIN: Final = "wake_on_lan"

TV_PLATFORMS: Final[frozenset[str]] = frozenset(
    {ANDROID_TV_REMOTE_DOMAIN, ANDROID_TV_ADB_DOMAIN}
)

CONF_GROUPS: Final = "groups"
CONF_GROUP_ID: Final = "group_id"
CONF_GROUP_KEY: Final = "group_key"
CONF_GROUP_NAME: Final = "name"
CONF_MEMBERS: Final = "members"
CONF_ENTITIES: Final = "entities"
CONF_ROUTES: Final = "capability_routes"
CONF_APP_PREFERENCES: Final = "app_preferences"
CONF_DELAYS: Final = "command_delays"
CONF_ACTIVITIES: Final = "activities"
CONF_WOL: Final = "wake_on_lan"
CONF_APP_KEY: Final = "app_key"
CONF_DISPLAY_NAME: Final = "display_name"
CONF_VISIBLE: Final = "visible"
CONF_FAVORITE: Final = "favorite"
CONF_ORDER: Final = "order"
CONF_ACTIVITY_ID: Final = "activity_id"
CONF_ACTIVITY_NAME: Final = "activity_name"
CONF_ACTIVITY_SOURCE: Final = "activity_source"
CONF_ACTIVITY_VOLUME: Final = "activity_volume"
CONF_ACTIVITY_MUTE: Final = "activity_mute"
CONF_MAC: Final = "mac"
CONF_BROADCAST_ADDRESS: Final = "broadcast_address"
CONF_BROADCAST_PORT: Final = "broadcast_port"
CONF_POWER_DELAY: Final = "power_delay"
CONF_CAST_EXIT_DELAY: Final = "cast_exit_delay"
CONF_APP_CONFIRM_DELAY: Final = "app_confirm_delay"
CONF_RETRY_DELAY: Final = "retry_delay"
CONF_RESTART_DELAY: Final = "restart_delay"

ROUTE_POWER: Final = "power"
ROUTE_VOLUME: Final = "volume"
ROUTE_PLAYBACK: Final = "playback"
ROUTE_SEEK: Final = "seek"
ROUTE_METADATA: Final = "metadata"
ROUTE_TV_APPS: Final = "tv_apps"
ROUTE_CAST_APPS: Final = "cast_apps"
ROUTE_INPUTS: Final = "inputs"
ROUTE_NAVIGATION: Final = "navigation"
ROUTE_RESTART: Final = "restart"
ROUTE_KEYS: Final[tuple[str, ...]] = (
    ROUTE_POWER,
    ROUTE_VOLUME,
    ROUTE_PLAYBACK,
    ROUTE_SEEK,
    ROUTE_METADATA,
    ROUTE_TV_APPS,
    ROUTE_CAST_APPS,
    ROUTE_INPUTS,
    ROUTE_NAVIGATION,
    ROUTE_RESTART,
)

DEFAULT_DELAYS: Final[dict[str, float]] = {
    CONF_POWER_DELAY: 0.8,
    CONF_CAST_EXIT_DELAY: 0.75,
    CONF_APP_CONFIRM_DELAY: 1.25,
    CONF_RETRY_DELAY: 0.5,
    CONF_RESTART_DELAY: 2.0,
}

UID_VERSION: Final = "v7"
UID_SEPARATOR: Final = "|"
KIND_STATE: Final = "state"
KIND_SNAPSHOT: Final = "snapshot"
KIND_ATTRIBUTE: Final = "attribute"
MAX_SENSOR_STATE_LENGTH: Final = 255

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.runtime"
IDENTITY_STORAGE_KEY: Final = f"{DOMAIN}.physical_identities"
AD_SKIP_STORAGE_KEY: Final = f"{DOMAIN}.ad_skip"
LEGACY_CAST_STORAGE_KEY: Final = f"{DOMAIN}.apps"
LEGACY_TV_STORAGE_KEY: Final = f"{DOMAIN}.tv_apps"

SERVICE_LAUNCH_CAST_APP: Final = "launch_cast_app"
SERVICE_LAUNCH_TV_APP: Final = "launch_tv_app"
SERVICE_REGISTER_TV_APP: Final = "register_tv_app"
SERVICE_SEND_COMMAND: Final = "send_command"
SERVICE_SEEK_RELATIVE: Final = "seek_relative"
SERVICE_RESTART_DEVICE: Final = "restart_device"
SERVICE_RUN_ACTIVITY: Final = "run_activity"
SERVICE_SKIP_AD: Final = "skip_ad"

ATTR_APP_ID: Final = "app_id"
ATTR_APP_NAME: Final = "app_name"
ATTR_COMMAND: Final = "command"
ATTR_SECONDS: Final = "seconds"
ATTR_ACTIVITY: Final = "activity"

TV_APP_PREFIX: Final = "TV App · "
CAST_APP_PREFIX: Final = "Cast · "
INPUT_PREFIX: Final = "Input · "

TRANSIENT_APP_MARKERS: Final[tuple[str, ...]] = (
    "ready to cast",
    "cast receiver",
    "chromecast built-in",
)

YOUTUBE_APP_IDS: Final[frozenset[str]] = frozenset(
    {
        "233637DE",
        "com.google.android.youtube.tv",
        "com.google.android.youtube.tvkids",
    }
)

DEFAULT_CAST_APPS: Final[dict[str, str]] = {
    "E8C28D3C": "Home / Backdrop",
    "233637DE": "YouTube",
    "CC1AD845": "Default Media Receiver",
}

DEFAULT_ANDROID_TV_APPS: Final[dict[str, str]] = {
    "com.google.android.tvlauncher": "Home",
    "com.google.android.youtube.tv": "YouTube",
    "com.google.android.youtube.tvkids": "YouTube Kids",
    "com.netflix.ninja": "Netflix",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.disney.disneyplus": "Disney+",
    "com.hbo.max": "Max",
    "com.apple.atve.androidtv.appletv": "Apple TV",
    "com.skyshowtime.skyshowtime.google": "SkyShowtime",
    "com.cbs.ott": "Paramount+",
    "com.plexapp.android": "Plex",
    "org.xbmc.kodi": "Kodi",
    "org.videolan.vlc": "VLC",
    "com.spotify.tv.android": "Spotify",
    "tv.twitch.android.app": "Twitch",
    "com.google.android.videos": "Google TV",
    "com.google.android.apps.youtube.music": "YouTube Music",
    "com.android.vending": "Google Play Store",
    "com.crunchyroll.crunchyroid": "Crunchyroll",
    "tv.pluto.android": "Pluto TV",
    "com.rakutentv.ui": "Rakuten TV",
    "com.dazn": "DAZN",
    "pt.meo.androidtv": "MEO",
    "pt.nos.iris.online": "NOS TV",
    "pt.vodafone.vtv": "Vodafone TV",
    "com.tivimate.tv": "TiviMate",
    "com.teamsmart.videomanager.tv": "SmartTube",
    "com.stremio.one": "Stremio",
    "com.emby.embyatv": "Emby",
    "tv.jellyfin.androidtv": "Jellyfin",
}

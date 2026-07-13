"""Constants for Cast Metadata & TV Controls."""

from typing import Final

DOMAIN: Final = "cast_attribute_sensors"
NAME: Final = "Cast Metadata & TV Controls"
VERSION: Final = "7.0.0"

CAST_DOMAIN: Final = "cast"
ANDROID_TV_REMOTE_DOMAIN: Final = "androidtv_remote"
ANDROID_TV_ADB_DOMAIN: Final = "androidtv"
MEDIA_PLAYER_DOMAIN: Final = "media_player"
REMOTE_DOMAIN: Final = "remote"
BUTTON_DOMAIN: Final = "button"
SENSOR_DOMAIN: Final = "sensor"

TV_PLATFORMS: Final[frozenset[str]] = frozenset(
    {ANDROID_TV_REMOTE_DOMAIN, ANDROID_TV_ADB_DOMAIN}
)

CONF_GROUPS: Final = "groups"
CONF_GROUP_ID: Final = "group_id"
CONF_GROUP_NAME: Final = "name"
CONF_MEMBERS: Final = "members"
CONF_ENTITIES: Final = "entities"

UID_VERSION: Final = "v7"
UID_SEPARATOR: Final = "|"
KIND_STATE: Final = "state"
KIND_SNAPSHOT: Final = "snapshot"
KIND_ATTRIBUTE: Final = "attribute"
MAX_SENSOR_STATE_LENGTH: Final = 255

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.runtime"
LEGACY_CAST_STORAGE_KEY: Final = f"{DOMAIN}.apps"
LEGACY_TV_STORAGE_KEY: Final = f"{DOMAIN}.tv_apps"

SERVICE_LAUNCH_CAST_APP: Final = "launch_cast_app"
SERVICE_LAUNCH_TV_APP: Final = "launch_tv_app"
SERVICE_REGISTER_TV_APP: Final = "register_tv_app"
SERVICE_SEND_COMMAND: Final = "send_command"
SERVICE_SEEK_RELATIVE: Final = "seek_relative"
SERVICE_RESTART_DEVICE: Final = "restart_device"

ATTR_APP_ID: Final = "app_id"
ATTR_APP_NAME: Final = "app_name"
ATTR_COMMAND: Final = "command"
ATTR_SECONDS: Final = "seconds"

TV_APP_PREFIX: Final = "TV App · "
CAST_APP_PREFIX: Final = "Cast · "
INPUT_PREFIX: Final = "Input · "

TRANSIENT_APP_MARKERS: Final[tuple[str, ...]] = (
    "ready to cast",
    "cast receiver",
    "chromecast built-in",
    "default media receiver",
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

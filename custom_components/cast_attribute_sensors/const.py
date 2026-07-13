"""Constants for the Cast Metadata & TV Controls integration."""

from typing import Final

DOMAIN: Final = "cast_attribute_sensors"
NAME: Final = "Cast Metadata & TV Controls"
VERSION: Final = "3.0.0"

CAST_DOMAIN: Final = "cast"
ANDROID_TV_REMOTE_DOMAIN: Final = "androidtv_remote"
MEDIA_PLAYER_DOMAIN: Final = "media_player"
REMOTE_DOMAIN: Final = "remote"
SENSOR_DOMAIN: Final = "sensor"

UID_VERSION: Final = "v2"
UID_SEPARATOR: Final = "|"
LEGACY_UID_PREFIXES: Final[tuple[str, ...]] = ("v1|",)
KIND_STATE: Final = "state"
KIND_SNAPSHOT: Final = "snapshot"
KIND_ATTRIBUTE: Final = "attribute"

MAX_SENSOR_STATE_LENGTH: Final = 255

SERVICE_LAUNCH_APP: Final = "launch_app"
SERVICE_LAUNCH_TV_APP: Final = "launch_tv_app"
SERVICE_SEND_TV_COMMAND: Final = "send_tv_command"
ATTR_APP_ID: Final = "app_id"
ATTR_COMMAND: Final = "command"

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.apps"
TV_STORAGE_KEY: Final = f"{DOMAIN}.tv_apps"

# Safe starter entries from pychromecast's public app-ID catalogue. Additional
# apps are learned automatically from app_id/app_name metadata after they are
# observed on each Cast device.
DEFAULT_CAST_APPS: Final[dict[str, str]] = {
    "E8C28D3C": "Home / Backdrop",
    "233637DE": "YouTube",
    "CC1AD845": "Default Media Receiver",
}

# Common Android/Google TV package names. The TV app selector also imports the
# user's Android TV Remote application list and learns foreground apps.
DEFAULT_ANDROID_TV_APPS: Final[dict[str, str]] = {
    "com.google.android.tvlauncher": "Home",
    "com.google.android.youtube.tv": "YouTube",
    "com.netflix.ninja": "Netflix",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.disney.disneyplus": "Disney+",
    "com.plexapp.android": "Plex",
    "org.xbmc.kodi": "Kodi",
    "tv.twitch.android.app": "Twitch",
    "com.spotify.tv.android": "Spotify",
}

"""Constants for the Cast Metadata & TV Controls integration."""

from typing import Final

DOMAIN: Final = "cast_attribute_sensors"
NAME: Final = "Cast Metadata & TV Controls"
VERSION: Final = "6.0.0"

CAST_DOMAIN: Final = "cast"
ANDROID_TV_REMOTE_DOMAIN: Final = "androidtv_remote"
ANDROID_TV_ADB_DOMAIN: Final = "androidtv"
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
SERVICE_REGISTER_TV_APP: Final = "register_tv_app"
SERVICE_SEND_TV_COMMAND: Final = "send_tv_command"
SERVICE_SEEK_RELATIVE: Final = "seek_relative"
ATTR_APP_ID: Final = "app_id"
ATTR_APP_NAME: Final = "app_name"
ATTR_COMMAND: Final = "command"
ATTR_SECONDS: Final = "seconds"

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.apps"
TV_STORAGE_KEY: Final = f"{DOMAIN}.tv_apps"

DEFAULT_CAST_APPS: Final[dict[str, str]] = {
    "E8C28D3C": "Home / Backdrop",
    "233637DE": "YouTube",
    "CC1AD845": "Default Media Receiver",
}

# Android TV Remote cannot enumerate every installed app. This catalogue is
# combined with configured apps, foreground apps learned at runtime, manually
# registered apps, and Android TV (ADB) source lists when available.
DEFAULT_ANDROID_TV_APPS: Final[dict[str, str]] = {
    "com.google.android.tvlauncher": "Home",
    "com.google.android.youtube.tv": "YouTube",
    "com.google.android.youtube.tvkids": "YouTube Kids",
    "com.netflix.ninja": "Netflix",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.disney.disneyplus": "Disney+",
    "com.hbo.hbonow": "Max",
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
    "com.google.android.apps.photos": "Google Photos",
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

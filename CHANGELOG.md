# Changelog

## 6.0.0

- Added automatic versioned GitHub releases so HACS installs the current code instead of remaining on the last recognized release.
- Rebuilt controller entities during migration to eliminate layouts retained from versions 3–5.
- Consolidated Android TV Remote, Android TV ADB, Google Cast, and manufacturer entities into one controller per matched physical television.
- Kept standalone Chromecast dongles, Cast speakers, and displays as independent devices.
- Grouped every dynamically discovered Cast and TV sensor under the matching integration-owned physical device.
- Added runtime app learning: newly observed TV and Cast apps are added to the controller immediately and persisted across restarts.
- Separated source options into `TV App ·`, `Cast ·`, and `Input ·` mechanisms.
- Filtered transient Ready-to-Cast receiver states from native TV application options.
- Improved switching from Cast sessions back to native TV apps and physical inputs.
- Added local HACS icon/logo assets and README banner artwork.
- Re-enabled HACS brand validation.
- Added cleanup of obsolete empty virtual controller devices.

## 5.0.0

- Added physical-device matching through Home Assistant device IDs, network connections, areas, and normalized names.
- Moved metadata from matching Cast and TV representations onto the same virtual controller device.
- Reclassified the integration from a helper to a hub integration.

## 4.0.0

- Replaced the large standalone control-entity set with compact `media_player` controllers.
- Added integration-owned controller devices.
- Removed generated button, number, select, and switch clutter during migration.
- Corrected relative seeking by calculating the live playback position from `media_position_updated_at`.
- Added `cast_attribute_sensors.seek_relative`.
- Expanded the built-in Android/Google TV application catalogue.
- Added configured, learned, and Android TV ADB application sources.
- Added `cast_attribute_sensors.register_tv_app`.

## 3.0.0

- Added native TV discovery alongside Google Cast discovery.
- Added TV power, input, application, volume, mute, playback, navigation, and restart controls.
- Added Android/Google TV app launching and Android TV Remote commands.
- Added Cast receiver soft restart, relative seeking, media-position slider, shuffle, and repeat controls.

## 2.0.0

- Changed attribute sensors to lazy creation after a non-null value first appears.
- Retained observed metadata sensors permanently through the entity registry.
- Added learned Cast app selection and arbitrary Cast app launching.

## 1.0.0

- Initial metadata sensor implementation.

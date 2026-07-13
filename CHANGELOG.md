# Changelog

## 4.0.0

- Replaced the large standalone control-entity set with one compact `media_player` controller per Cast or TV source.
- Added dedicated virtual controller devices owned by this integration, so devices and entities appear under **Settings → Devices & services → Cast Metadata & TV Controls**.
- Added automatic migration that removes the old generated button, number, select, and switch entities while preserving metadata sensors.
- Corrected relative seeking by calculating the live playback position from `media_position_updated_at` before applying the offset.
- Added `cast_attribute_sensors.seek_relative` for reliable forward and rewind actions.
- Expanded the built-in Android/Google TV application catalogue.
- Added application aggregation from Android TV Remote configuration, learned foreground apps, and matching Android TV (ADB) source lists.
- Added `cast_attribute_sensors.register_tv_app` for permanently registering missing applications.
- Combined applications and physical inputs in the compact TV controller source selector with clear `App ·` and `Input ·` prefixes.

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

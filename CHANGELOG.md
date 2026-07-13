# Changelog

## 3.0.0

- Added native TV discovery alongside Google Cast discovery.
- Added a TV power switch when the underlying television entity supports power control.
- Added a TV input selector for HDMI, tuner, consoles, receivers, and other sources published by the native TV integration.
- Added Android and Google TV application selection through Home Assistant's Android TV Remote integration.
- Added `cast_attribute_sensors.launch_tv_app` for launching arbitrary Android package IDs.
- Added `cast_attribute_sensors.send_tv_command` for Android TV Remote key commands.
- Added TV volume, mute, play/pause, Home, Back, app reload, channel, settings, information, and navigation controls.
- Added a real TV restart button only when the television's native device exposes a restart entity.
- Added Cast receiver soft restart, relative seeking, media-position slider, shuffle, and repeat controls.
- Kept v2 control unique IDs stable where applicable to reduce duplicate entities during upgrade.

## 2.0.0

- Changed attribute sensors to lazy creation: they now appear only after a non-null value is first reported.
- Retained previously observed metadata sensors permanently through the Home Assistant entity registry.
- Added a per-device learned Cast app selector.
- Added `cast_attribute_sensors.launch_app` for arbitrary Cast app IDs.
- Added start, play/pause, stop, previous, next, volume up/down, and close-app buttons.
- Added volume percentage and mute control entities.
- Added automatic handling of existing, newly added, renamed, unavailable, and removed native Cast entities.
- Added HACS validation and repository packaging.

## 1.0.0

- Initial metadata sensor implementation.

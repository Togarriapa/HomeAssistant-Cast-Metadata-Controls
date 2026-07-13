# Changelog

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

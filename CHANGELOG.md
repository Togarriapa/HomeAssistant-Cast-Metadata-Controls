# Changelog

## 7.0.0

- Rebuilt the integration around one unified source manager and one physical-device resolver.
- Added one controller device per independent physical TV, Chromecast, Cast speaker, or smart display.
- Added explicit physical-device grouping through the integration Configure menu for cases automatic matching cannot resolve safely.
- Preserved existing v2 metadata sensor unique IDs while moving sensors onto the correct consolidated device.
- Added automatic lazy sensors for every non-null Cast and TV state attribute.
- Disabled complete attribute snapshots by default while keeping them available as diagnostic entities.
- Removed all generated button, select, number, and switch clutter.
- Added robust native-app, Cast-app, and physical-input routing through one source selector.
- Added a retry path when leaving a Cast session and launching a native Android/Google TV app.
- Filtered Ready-to-Cast and receiver pseudo-apps from the native app list.
- Corrected relative seeking using the elapsed time since `media_position_updated_at`.
- Added repeat and shuffle proxy support.
- Added controller actions for remote commands, relative seeking, app launching, app registration, and restart.
- Added a one-time v7 migration and delayed orphan-device cleanup.
- Added migration of learned apps from both legacy storage files.
- Added integration-local Home Assistant/HACS brand assets and updated README artwork.
- Consolidated validation into HACS, hassfest, Ruff, compilation, JSON/YAML validation, and unit tests.
- Standardized the release workflow and repository documentation.

## 6.0.0

- Added versioned GitHub releases and v6 controller migration.
- Consolidated matched TV, ADB, Remote, and Cast entities.
- Added runtime app learning and local brand assets.

## 5.0.0

- Added device matching using registry IDs, network connections, areas, and normalized names.
- Reclassified the integration as a hub.

## 4.0.0

- Replaced standalone control helpers with compact media-player controllers.
- Corrected stale-position relative seeking.

## 3.0.0

- Added native TV controls and Android TV Remote support.

## 2.0.0

- Added lazy metadata sensors and learned Cast apps.

## 1.0.0

- Initial metadata sensor implementation.

# Changelog

## 7.4.2

- Automatically merges one Sony-native BRAVIA representation with one generic Sony DLNA `MediaRenderer` representation when the match is reciprocal and unambiguous.
- Keeps conflicting-area and multi-TV ambiguity safeguards, preventing unrelated televisions from being combined.
- Makes **Merge representations of the same physical device** the first and clearest option in the integration Configure menu.
- Documents selecting the BRAVIA, MediaRenderer, Android TV Remote, ADB, and built-in Cast entities that belong to one physical TV.
- Clarifies that the integration-owned Controller entity must not be selected as a native source.
- Adds English and Portuguese configuration guidance plus targeted Sony native/DLNA regression tests.

## 7.4.1

- Fixed duplicate Sony BRAVIA controller devices when the native representation is exposed as `MediaRenderer` and the Android TV representation has no area assigned yet.
- Added reciprocal, unambiguous complementary-platform matching that permits one missing area but refuses ambiguous matches involving multiple TVs.
- Treats generic renderer labels as non-identifying and selects the meaningful BRAVIA name from the consolidated representations.
- Added exact screenshot, ambiguity, conflicting-area, and same-platform safety regression tests.

## 7.4.0

- Added an opt-in `Auto-skip YouTube ads` switch to each physical media device.
- Added event-driven Cast ad detection using the receiver's official `SKIP_AD` capability bit.
- Added native Android TV ADB detection using the local UI hierarchy while YouTube is active.
- Added positive localized Skip-ad label and YouTube resource-ID detection with coordinate extraction.
- Rechecks the foreground app immediately before any Android TV tap and never sends blind timed clicks.
- Added the `cast_attribute_sensors.skip_ad` action for manual testing and automations.
- Added persisted per-device enablement plus last-result, last-skip-time, and available-method diagnostics.
- Added English and Portuguese skip-control tests, resource-ID tests, and false-positive rejection tests.
- Rewrote the README around the unified current architecture and documented privacy/performance behaviour.

## 7.3.0

- Added conservative same-room family/model matching for complementary manufacturer, Android TV Remote, Android TV ADB, and Cast representations.
- Added automatic grouping for Sony BRAVIA entities whose integrations expose different model-oriented names.
- Kept generic manufacturer-only matches excluded to avoid combining two unrelated televisions in the same room.
- Normalized generated physical-device names by removing repeated Controller, Remote, ADB, Cast, and media-player suffixes.
- Added delayed cleanup of stale controller, health, and transition entities after physical-device groups are merged.
- Added regression tests for the BRAVIA naming pattern and same-area safety boundary.

## 7.2.0

- Added a per-device application manager for renaming, hiding, favouriting, and ordering native TV and Cast applications.
- Added stable application preference keys based on launch mechanism and package/receiver identifier.
- Published managed application details and favourite sources through the compact controller for dashboard clients.
- Added helper-free activity presets that can power on, select an app or input, set volume, and set mute.
- Added the `cast_attribute_sensors.run_activity` action.
- Added configurable command delays per physical device for power-on, Cast exit, app confirmation, app retry, and power-cycle restart.
- Added optional Wake-on-LAN power-on fallback with detected MAC address, broadcast address, and port configuration.
- Added a diagnostic transition event entity per physical device.
- Added normalized power, application, input, playback, volume, and mute transition events for automations.
- Added controller attributes for favourite sources, activity names, and the managed application catalogue.
- Added a version 9 config-entry migration for the new event platform while preserving metadata sensors, learned apps, persistent physical identities, and existing options.
- Added full English and Portuguese configuration for applications, timing, Wake-on-LAN, and activities.

## 7.1.0

- Added persistent physical-device identities so controllers reconnect to the same integration device after native TV, Cast, ADB, or manufacturer entities are recreated.
- Added configurable per-capability routing for power, volume, playback, seeking, metadata, TV apps, Cast apps, inputs, navigation, and restart.
- Added one disabled-by-default diagnostic health model to every controller and a `Controller problem` binary sensor.
- Added Home Assistant Repairs warnings for missing explicit-group members and stale capability routes.
- Added hot-plug controller creation for completely new independent TVs, Chromecasts, speakers, and displays without reloading existing devices.
- Retained a controlled reload only when existing physical-device membership changes and entity-registry device assignments must be rebuilt.
- Added physical identity, health, source-platform, source-entity, and configured-route attributes to the compact controller.
- Ensured dynamically discovered metadata sensors resolve the physical device before entering the entity registry.
- Added a version 8 config-entry migration that rebuilds controller and health entities while retaining learned applications and metadata sensor registrations.
- Added full English and Portuguese configuration and Repairs translations.
- Added documentation for the companion Unified TV Card.

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

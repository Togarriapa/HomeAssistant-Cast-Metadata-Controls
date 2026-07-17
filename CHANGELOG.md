# Changelog

## 8.0.0

- Added a first-class **Merge duplicate physical devices** wizard that works with the integration-owned controller devices shown in Home Assistant instead of requiring users to identify low-level source entities.
- The wizard automatically expands selected controllers into all underlying manufacturer, MediaRenderer, Android TV Remote, Android TV ADB, Cast, and receiver source entities.
- Added **Review detected physical devices** with source counts, native entity IDs, platforms, and automatic/manual grouping status.
- Added **Edit a merged physical device**, **Unmerge**, and advanced **Merge native source entities** flows.
- Manual merges remove overlapping members from older groups, prevent a native source from belonging to two physical devices, and clean obsolete one-member groups.
- Capability routes, managed apps, command timing, activities, and Wake-on-LAN settings are migrated onto the surviving merged device.
- Kept the existing v7 entity unique-ID namespace so dashboards, automations, entity IDs, and the Unified TV Card survive the v8 upgrade without needless entity recreation.
- Lowered the HACS compatibility floor from Home Assistant 2026.7 to 2025.12; the previous unnecessarily high minimum could hide updates on otherwise compatible installations.
- Rebuilt the release workflow to validate version consistency, create or repair a full GitHub release, verify the published release, and perform a daily self-heal check so HACS can reliably discover updates.
- Added CI validation that the manifest, Python version constant, and changelog all describe the same release.
- Added regression tests for overlapping manual groups, per-device setting migration, and complete cleanup when a manual merge is removed.
- Rewrote grouping, upgrade, HACS troubleshooting, and recovery documentation for v8.

## 7.4.2

- Automatically merges one Sony-native BRAVIA representation with one generic Sony DLNA `MediaRenderer` representation when the match is reciprocal and unambiguous.
- Keeps conflicting-area and multi-TV ambiguity safeguards, preventing unrelated televisions from being combined.
- Makes manual physical-device merging explicit and adds targeted Sony native/DLNA regression tests.

## 7.4.1

- Fixed duplicate Sony BRAVIA controller devices when the native representation is exposed as `MediaRenderer` and the Android TV representation has no area assigned.
- Added reciprocal, unambiguous complementary-platform matching while preserving multiple-TV and conflicting-area safeguards.

## 7.4.0

- Added opt-in positive-detection-only YouTube ad skipping for Cast and Android TV ADB.
- Added a per-device switch, manual skip action, localized skip-control detection, diagnostics, and false-positive regression tests.

## 7.3.0

- Added conservative family/model matching for complementary manufacturer, Android TV Remote, Android TV ADB, Cast, and Sony BRAVIA representations.
- Added registry cleanup, concise entity naming, inherited native model/area, and persistent identity consolidation.

## 7.2.0

- Added managed applications, favourites, activities, per-device command timing, Wake-on-LAN, and transition event entities.

## 7.1.0

- Added persistent physical-device identities, per-capability routing, health diagnostics, Repairs warnings, and hot-plug discovery.

## 7.0.0

- Rebuilt the integration around one unified source manager and one controller/device per physical media device.
- Added lazy metadata sensors, explicit grouping, app/input routing, corrected seeking, migration, branding, validation, and versioned releases.

<p align="center">
  <img src="assets/banner.svg" alt="Cast Metadata & TV Controls" width="100%">
</p>

# Cast Metadata & TV Controls

A fully local Home Assistant integration that combines Google Cast, Android TV Remote, Android TV ADB, DLNA/MediaRenderer, manufacturer TV integrations, and optional AV-receiver media players into **one organized controller device per real physical device**.

## V8 architecture

- One integration entry under **Settings → Devices & services**.
- One integration-owned device and one compact `media_player` controller per physical TV, Chromecast, Cast speaker, or smart display.
- All native representations become capability providers beneath that physical device.
- All lazy metadata sensors are attached to the same physical device.
- Completely new independent devices are detected automatically.
- No generated button/select/number helper swarm.
- Existing v7 controller and sensor unique IDs are preserved during the v8 upgrade.

## Fixing duplicate devices

Automatic grouping deliberately avoids risky merges. Some televisions expose insufficient or contradictory identity information—for example, a Sony BRAVIA integration may expose one device while Android TV, ADB, Cast, and `MediaRenderer` expose separate representations.

V8 provides an authoritative device-level merge flow that matches what you see in Home Assistant.

### Merge duplicate controller devices

1. Open **Settings → Devices & services**.
2. Open **Cast Metadata & TV Controls**.
3. Select **Configure**.
4. Choose **Review detected physical devices** to inspect the current grouping.
5. Choose **Merge duplicate physical devices**.
6. Select the two or more controller devices that are actually the same television.
7. Optionally enter the final physical-device name.
8. Save. The integration reloads, migrates the selected device settings, and removes obsolete generated devices/entities.

You select the duplicate **physical controller devices**, not every BRAVIA/ADB/Cast entity manually. V8 expands them automatically into their underlying native sources.

### Advanced native-source merge

For unusual cases, choose **Merge native source entities (advanced)** and select the manufacturer, `MediaRenderer`, Android TV Remote, Android TV ADB, Cast, or receiver `media_player` entities directly.

Do not select the `Controller` entity created by this integration in the advanced source selector.

### Edit or undo a merge

The Configure menu also provides:

- **Edit a merged physical device**
- **Unmerge a manually merged device**
- **Remove all manual device merges**

When devices are merged, V8 also moves their capability routes, managed-app preferences, command delays, activities, and Wake-on-LAN configuration to the surviving physical device.

## Automatic grouping

Automatic grouping uses conservative evidence:

1. Shared Home Assistant device-registry identity.
2. Shared network connections such as MAC addresses.
3. Matching meaningful names with area validation.
4. Reciprocal manufacturer/model-family evidence between complementary integrations.
5. Platform and capability priority.

The manufacturer-native TV representation is preferred for the final name, manufacturer, model, and area. Standalone Chromecast dongles, speakers, and displays remain independent.

## Controller capabilities

The unified controller selects the most suitable source for each supported capability:

- Power on/off and restart
- Wake-on-LAN fallback
- Volume, mute, and volume stepping
- Play, pause, stop, previous, and next
- Corrected absolute and relative seeking
- Shuffle and repeat
- Native Android/Google TV application launching
- Cast receiver launching
- HDMI, tuner, console, receiver, and manufacturer inputs
- Remote navigation
- Current app, title, artist, album, artwork, duration, and position

Use **Configure → Route controller capabilities** only when a specific native integration is more reliable than automatic routing.

## Applications and inputs

The application catalogue combines configured, learned, discovered, and manually registered apps. The controller separates mechanisms clearly:

```text
TV App · YouTube
TV App · Netflix
Cast · YouTube
Input · HDMI 1
Input · PlayStation 5
```

Transient receiver states such as **Ready to Cast** are filtered. Apps can be renamed, hidden, favourited, and reordered under **Configure → Manage applications**.

Register a missing TV app:

```yaml
action: cast_attribute_sensors.register_tv_app
data:
  entity_id: media_player.living_room_tv_controller
  app_id: com.example.androidtv
  app_name: Example TV App
```

## Dynamic metadata sensors

Each native source is watched continuously. A metadata sensor is created when a non-null value first appears, remains registered, and becomes unavailable/unknown when the source stops reporting it.

Examples include `media_title`, `media_artist`, `app_id`, `app_name`, `source`, `volume_level`, and manufacturer-specific media attributes.

Complete source snapshots are disabled by default as diagnostic entities to reduce interface and recorder clutter.

## YouTube ad skipping

Each physical device can expose an opt-in **Auto-skip YouTube ads** switch.

- Cast uses the receiver's reported `SKIP_AD` capability.
- Android TV ADB acts only after positively identifying a visible skip control while YouTube is confirmed active.
- No blind timed clicks or fixed screen coordinates.
- Unskippable advertisements are not bypassed.

Manual test:

```yaml
action: cast_attribute_sensors.skip_ad
data:
  entity_id: media_player.living_room_tv_controller
```

## Activities, timing, and Wake-on-LAN

All are configured from the integration's Configure menu without YAML helpers:

- Activity presets can power on, choose an app/input, set volume, and set mute.
- Per-device delays support slower televisions.
- Wake-on-LAN is used only when no working native power-on route exists.

## Health, Repairs, and events

Every physical device includes health/problem diagnostics and a transition event entity. Home Assistant Repairs warns about missing manually merged sources and stale capability routes.

Transition types include `power_changed`, `application_changed`, `input_changed`, `playback_changed`, `volume_changed`, and `mute_changed`.

## Unified TV Card

The companion HACS dashboard repository is:

[**Togarriapa/HomeAssistant-Unified-TV-Card**](https://github.com/Togarriapa/HomeAssistant-Unified-TV-Card)

It provides responsive artwork, playback, app/input dropdowns, mute beside volume, remote navigation, activities, favourites, diagnostics, and ad-skip controls.

```yaml
type: custom:unified-tv-card
entity: media_player.living_room_tv_controller
show_artwork: true
show_remote: true
seek_seconds: 10
```

## Installation with HACS

1. Open **HACS → Integrations**.
2. Add this custom repository as category **Integration**:

   ```text
   https://github.com/Togarriapa/HomeAssistant-Cast-Metadata-Controls
   ```

3. Install the latest version.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration**.
6. Add **Cast Metadata & TV Controls**.

No YAML configuration is required.

## When an update does not appear in Home Assistant

HACS tracks the latest compatible **full GitHub release**. V8's release workflow creates and verifies that release automatically and also checks daily for a missing release.

If HACS still does not show the update:

1. Confirm your Home Assistant Core version is at least **2025.12.0**.
2. Open HACS and use **Update information** / reload the repository data.
3. Confirm the repository is installed as an **Integration**, not Dashboard or Theme.
4. Open the repository in HACS and select **Redownload** if its local metadata is stale.
5. Restart Home Assistant after the integration update.

V8 lowers the accidental 2026.7 compatibility floor used by older releases, which could prevent compatible installations from seeing an update.

## Upgrade to V8

1. Update or redownload the integration in HACS.
2. Confirm HACS reports **8.0.0**.
3. Restart Home Assistant completely.
4. Wait several seconds for registry cleanup.
5. Open the integration and use **Review detected physical devices**.
6. Merge any remaining duplicate controller devices with **Merge duplicate physical devices**.

The v7 unique-ID namespace is deliberately retained, so existing dashboards and automations should continue using the same controller and metadata entity IDs.

## Privacy and performance

The integration is local-first and adds no account, cloud API, telemetry, or analytics. Normal discovery is event-driven. Android TV ad detection polls locally only while explicitly enabled and while YouTube is active.

For recorder-sensitive installations, complete snapshot sensors remain disabled by default. They can also be excluded with:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_attributes
```

## License

MIT License.

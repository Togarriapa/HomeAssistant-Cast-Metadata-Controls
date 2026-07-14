<p align="center">
  <img src="assets/banner.svg" alt="Cast Metadata & TV Controls" width="100%">
</p>

# Cast Metadata & TV Controls

A fully local Home Assistant integration that combines Google Cast, Android TV Remote, Android TV ADB, and manufacturer TV integrations into **one organized controller device per physical device**.

## Current architecture — v7.4

- One integration entry under **Settings → Devices & services**.
- One normal Home Assistant device for each independent physical TV, Chromecast, Cast speaker, or smart display.
- One compact `media_player` controller per physical device.
- Manufacturer-native identity, model, and area are retained where available.
- Cast, Android TV Remote, Android TV ADB, and manufacturer entities become capability providers inside that device.
- Every discovered metadata sensor belongs to the same physical device.
- New metadata sensors appear only after a non-null value is first reported.
- Completely new independent devices are hot-added automatically.
- Persistent physical identities survive native entity recreation and integration reloads.
- No generated button, select, or number helper swarm.

## Physical-device grouping

Automatic grouping uses conservative evidence:

1. Shared Home Assistant device-registry identity.
2. Shared network connections such as MAC addresses.
3. Matching non-generic names with area validation.
4. Manufacturer/model family evidence for complementary TV integrations.
5. Platform and capability priority.

The manufacturer-native TV entity is preferred for the final device name and model. Android TV Remote, ADB, and Cast remain available for the capabilities they implement best.

A physical TV can combine:

```text
Sony / Samsung / LG / Philips manufacturer media player
Android TV Remote
Android TV ADB
Google Cast
AV receiver media player
```

Standalone Chromecast dongles, Cast speakers, and smart displays remain separate.

### Explicit grouping fallback

When Home Assistant exposes insufficient identity information:

1. Open **Settings → Devices & services**.
2. Open **Cast Metadata & TV Controls**.
3. Select **Configure**.
4. Choose **Combine source entities**.
5. Select every native `media_player` representing the same physical setup.

## Capability routing

Automatic routing is recommended. For unusual installations, route each category through a specific native entity:

**Configure → Route controller capabilities**

```text
Power
Volume and mute
Playback
Seeking
Media metadata
Native TV applications
Cast applications
Physical inputs
Remote navigation
Restart
```

Example:

```text
Power: Sony BRAVIA
Volume: AV receiver
Playback: Google Cast
Metadata: Google Cast
Native apps: Android TV Remote
Inputs: Sony BRAVIA
Navigation: Android TV Remote
Restart: Android TV ADB
```

Missing configured routes produce a Home Assistant Repairs warning.

## Applications and inputs

The application catalogue combines:

- Common Android/Google TV packages
- Apps configured in Android TV Remote
- Apps learned when active
- Android TV ADB source entries
- Manually registered applications
- Cast receiver applications

Transient pseudo-apps such as **Ready to Cast** are filtered.

Under **Configure → Manage applications**, apps can be renamed, hidden, marked as favourites, and reordered. The controller publishes `favorite_sources` and `managed_apps` for dashboard cards.

Register a missing native TV app:

```yaml
action: cast_attribute_sensors.register_tv_app
data:
  entity_id: media_player.living_room_tv_controller
  app_id: com.example.androidtv
  app_name: Example TV App
```

The controller source selector separates launch mechanisms:

```text
TV App · YouTube
TV App · Netflix
Cast · YouTube
Input · HDMI 1
Input · PlayStation 5
```

When leaving Cast for a native app or input, the controller returns to TV Home when possible, launches the target, and retries one failed native launch.

## Opt-in YouTube ad skipping

Version 7.4 adds **positive-detection-only** ad skipping. It is disabled by default for every physical device.

Enable the device entity:

```text
switch.<tv>_auto_skip_youtube_ads
```

Two safe methods are used:

### Cast receiver

When YouTube is active, the integration checks the Cast receiver's official `SKIP_AD` capability. A command is sent only while the receiver explicitly reports that the current ad is skippable.

### Android TV ADB

When native YouTube is active and Android TV ADB is available, the integration reads the local Android UI hierarchy. It taps only when a visible Skip-ad control is positively identified by localized text, accessibility description, or YouTube skip-button resource ID.

The Android TV path:

- Never sends blind timed clicks.
- Rechecks that YouTube is still active immediately before tapping.
- Polls only while the per-device switch is enabled and YouTube is active.
- Supports common English, Portuguese, Spanish, French, German, Italian, Dutch, and Polish labels.

Manual test action:

```yaml
action: cast_attribute_sensors.skip_ad
data:
  entity_id: media_player.living_room_tv_controller
```

The switch attributes show available methods, last result, and last successful skip time. Detection depends on information exposed by the receiver or Android accessibility hierarchy; unskippable ads are not bypassed.

## Activities

Activities are helper-free presets stored by the integration. They can:

- Power on the physical device
- Select a native app, Cast app, or physical input
- Set volume
- Set mute state

Create activities under **Configure → Add or replace an activity**.

```yaml
action: cast_attribute_sensors.run_activity
data:
  entity_id: media_player.living_room_tv_controller
  activity: Movie Night
```

## Command timing

Some TVs need extra time after power-on, leaving Cast, or launching an app. Configure per-device delays under:

**Configure → Configure command timing**

Available delays include power-on, Cast exit, application confirmation, retry, and power-cycle restart.

## Wake-on-LAN

Wake-on-LAN is an optional fallback when no native source exposes `turn_on`.

**Configure → Configure Wake-on-LAN**

Native power-on always has priority.

## Controller health and Repairs

Every physical device receives a diagnostic **Problem** binary sensor. It reports:

- Persistent physical-device ID
- Native source entities and platforms
- Available and unavailable sources
- Configured and stale capability routes
- Managed-app and activity counts
- Wake-on-LAN configuration
- Overall health: `healthy`, `degraded`, or `unavailable`

Optional companion-source outages do not mark a controller broken while another representation still provides working control. Explicit unavailable routes remain degraded.

Home Assistant Repairs reports missing explicit-group members and stale capability routes.

## Transition events

Each physical device receives a diagnostic **Transitions** event entity:

```text
power_changed
application_changed
input_changed
playback_changed
volume_changed
mute_changed
```

Event data contains the old value, new value, source entity, and persistent physical-device ID.

## Controller capabilities

The controller exposes capabilities supported by at least one underlying source:

- Power on/off and restart
- Play, pause, stop, previous, and next
- Volume, mute, and volume stepping
- Shuffle and repeat
- Corrected absolute and relative seeking
- Native Android/Google TV application launching
- Cast receiver launching
- HDMI, tuner, console, receiver, and manufacturer inputs
- Current app, title, artist, album, artwork, duration, and position

## Dynamic metadata sensors

Every underlying source is watched continuously. A sensor is created after its value first appears, remains registered, and becomes `unknown` when the source temporarily stops reporting it.

Examples:

```text
sensor.living_room_tv_cast_media_title
sensor.living_room_tv_cast_media_artist
sensor.living_room_tv_cast_app_id
sensor.living_room_tv_android_tv_remote_app_name
sensor.living_room_tv_manufacturer_source
```

Complete source snapshots remain available as disabled-by-default diagnostics.

## Unified TV Card

The companion HACS dashboard repository provides a responsive controller card:

[**Togarriapa/HomeAssistant-Unified-TV-Card**](https://github.com/Togarriapa/HomeAssistant-Unified-TV-Card)

It includes dynamic app and input dropdowns, mute beside volume, power/restart, playback, corrected relative seeking, directional controls, artwork, managed favourites, activities, and diagnostics.

```yaml
type: custom:unified-tv-card
entity: media_player.living_room_tv_controller
show_artwork: true
show_remote: true
seek_seconds: 10
```

## Useful actions

```yaml
# Seek forward ten seconds from the corrected live position
action: cast_attribute_sensors.seek_relative
data:
  entity_id: media_player.living_room_tv_controller
  seconds: 10
```

```yaml
# Send a remote key
action: cast_attribute_sensors.send_command
data:
  entity_id: media_player.living_room_tv_controller
  command: HOME
```

```yaml
# Restart the physical device
action: cast_attribute_sensors.restart_device
data:
  entity_id: media_player.living_room_tv_controller
```

Available actions:

- `cast_attribute_sensors.launch_cast_app`
- `cast_attribute_sensors.launch_tv_app`
- `cast_attribute_sensors.register_tv_app`
- `cast_attribute_sensors.send_command`
- `cast_attribute_sensors.seek_relative`
- `cast_attribute_sensors.restart_device`
- `cast_attribute_sensors.run_activity`
- `cast_attribute_sensors.skip_ad`

## Automatic discovery

When a supported TV or Cast `media_player` appears:

1. The source manager detects it.
2. Physical identity and grouping are calculated.
3. A completely new independent controller and device entities are hot-added.
4. Existing controllers remain available.

A controlled reload occurs only when a new source must be attached to an existing physical device or membership changes, because Home Assistant must move registered entities between devices.

## Installation with HACS

1. Open **HACS → Integrations**.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add:

   ```text
   https://github.com/Togarriapa/HomeAssistant-Cast-Metadata-Controls
   ```

4. Select **Integration**.
5. Install and restart Home Assistant.
6. Open **Settings → Devices & services → Add integration**.
7. Add **Cast Metadata & TV Controls**.

No YAML configuration is required.

## Recorder considerations

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_attributes
```

## Scope, privacy, and performance

The integration is local-first and adds no account, cloud API, telemetry, or external analytics.

Normal media/device discovery is event-driven. The only periodic operation added by v7.4 is the local Android TV UI check, and it runs only for a device whose **Auto-skip YouTube ads** switch is enabled while YouTube is active. Cast ad detection is event-driven.

## License

MIT License.

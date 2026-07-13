![Cast Metadata & TV Controls](assets/banner.svg)

# Cast Metadata & TV Controls for Home Assistant

A fully local Home Assistant integration that combines Google Cast, Android/Google TV Remote, Android TV ADB, and manufacturer TV entities into one organized controller per physical device.

## One physical device, one controller

A television may already be represented in Home Assistant by several integrations:

- Android TV Remote
- Android TV ADB
- Google Cast
- The TV manufacturer's integration

This integration matches those entities using Home Assistant device IDs, network connections, areas, and normalized names. Their controls and metadata are grouped under one integration-owned device.

Standalone Chromecast dongles, Cast speakers, and smart displays remain separate devices.

After setup, open:

**Settings → Devices & services → Integrations → Cast Metadata & TV Controls**

Each physical device contains:

- One primary `media_player` controller
- All metadata sensors discovered for that device
- New sensors created automatically when new state attributes first appear
- Newly discovered TV and Cast applications added to the controller dynamically

## Controller features

The controller exposes only capabilities supported by the underlying entities:

- Power on and off
- Play, pause, stop, previous, and next
- Volume, mute, and volume stepping
- Corrected seeking based on the live playback position
- Android/Google TV applications
- Cast receiver applications
- HDMI, tuner, console, AV receiver, and manufacturer inputs
- Current app, title, artist, album, artwork, duration, and playback position

The source selector separates each mechanism clearly:

```text
TV App · YouTube
TV App · Netflix
Cast · YouTube
Input · HDMI 1
Input · PlayStation 5
```

When leaving a Cast receiver session, the controller returns the TV to Home before launching a native TV app or input. Transient entries such as **Ready to Cast** are filtered from the native app list.

## Dynamic application discovery

The integration learns applications while Home Assistant is running.

When a TV or Cast source reports a previously unseen `app_id` and `app_name`, the app is:

1. Added immediately to the matching controller's source list
2. Persisted locally
3. Restored after Home Assistant restarts

Android TV Remote does not provide a complete installed-app inventory. The final app list combines:

- A built-in catalogue of common Android/Google TV apps
- Apps configured in Android TV Remote
- Apps learned when they become active
- Android TV ADB sources
- Apps manually registered through the integration action

### Register a missing TV app manually

```yaml
action: cast_attribute_sensors.register_tv_app
data:
  entity_id: media_player.living_room_tv
  app_id: com.example.androidtv
  app_name: Example TV App
```

## Dynamic metadata sensors

The integration watches every matching Cast and TV media-player entity.

A sensor is created only after its corresponding state or attribute becomes available. Once created, it remains registered and becomes `unknown` when the source temporarily stops reporting the value.

Examples:

```text
sensor.living_room_tv_cast_media_title
sensor.living_room_tv_cast_media_artist
sensor.living_room_tv_cast_app_id
sensor.living_room_tv_android_tv_remote_app_name
sensor.living_room_tv_manufacturer_source
```

All of these sensors are attached to the same integration-owned physical-device controller.

## Corrected relative seeking

Cast's reported `media_position` can be several seconds old. The integration corrects it using `media_position_updated_at` before applying the offset.

Forward 10 seconds:

```yaml
action: cast_attribute_sensors.seek_relative
data:
  entity_id: media_player.living_room_cast
  seconds: 10
```

Rewind 10 seconds:

```yaml
action: cast_attribute_sensors.seek_relative
data:
  entity_id: media_player.living_room_cast
  seconds: -10
```

## Installation with HACS

1. Open **HACS → Integrations**.
2. Open the three-dot menu and select **Custom repositories**.
3. Add:

   ```text
   https://github.com/Togarriapa/HomeAssistant-Cast-Metadata-Controls
   ```

4. Select **Integration**.
5. Install **Cast Metadata & TV Controls**.
6. Restart Home Assistant.
7. Open **Settings → Devices & services → Add integration**.
8. Add **Cast Metadata & TV Controls**.

No YAML configuration is required.

## Updating

This repository publishes a versioned GitHub release whenever the integration version changes on `main`. HACS installs those releases rather than relying on unversioned development commits.

After HACS installs an update, restart Home Assistant so config-entry migrations can rebuild old controller layouts and move sensors onto the consolidated physical-device structure.

## Available actions

- `cast_attribute_sensors.launch_app`
- `cast_attribute_sensors.launch_tv_app`
- `cast_attribute_sensors.register_tv_app`
- `cast_attribute_sensors.send_tv_command`
- `cast_attribute_sensors.seek_relative`

## Branding

The repository contains:

```text
assets/banner.svg
assets/icon.png
custom_components/cast_attribute_sensors/brand/icon.png
custom_components/cast_attribute_sensors/brand/logo.png
```

The local HACS brand assets are validated by the repository workflow.

## Recorder considerations

To exclude complete attribute snapshots while retaining individual metadata sensors:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_attributes
```

## Scope

The integration controls and reports only information already exposed by Home Assistant's native Cast, Android TV Remote, Android TV ADB, and television integrations. It does not add a separate cloud dependency.

## License

MIT License.

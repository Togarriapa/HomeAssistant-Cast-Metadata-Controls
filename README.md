<p align="center">
  <img src="assets/banner.svg" alt="Cast Metadata & TV Controls" width="100%">
</p>

# Cast Metadata & TV Controls

A fully local Home Assistant integration that combines every useful representation of a television—Google Cast, Android TV Remote, Android TV ADB, and manufacturer integrations—into **one organized controller device per physical device**.

## Version 7 architecture

Version 7 is a clean consolidation release:

- One integration entry under **Settings → Devices & services → Integrations**.
- One integration-owned device for each independent physical TV, Chromecast, Cast speaker, or smart display.
- One primary `media_player` controller per physical device.
- Every discovered metadata sensor is attached to that same device.
- New sensors are created automatically when new non-null attributes first appear.
- No generated button, select, number, or switch entity swarm.
- Advanced operations are exposed as Home Assistant actions instead of extra helper entities.

## Physical-device grouping

Automatic grouping uses conservative evidence from Home Assistant:

1. Shared device-registry IDs.
2. Shared network connections such as MAC addresses.
3. Matching non-generic names, with area checks.
4. Source type and capability priority.

A physical TV can therefore combine:

```text
Android TV Remote
Android TV ADB
Google Cast
TV manufacturer media player
```

Standalone Chromecast dongles, Cast speakers, and smart displays remain separate devices.

### Explicit grouping when automatic matching is insufficient

Some manufacturers expose the same hardware with unrelated names or identifiers. Version 7 provides a reliable override:

1. Open **Settings → Devices & services**.
2. Open **Cast Metadata & TV Controls**.
3. Select **Configure**.
4. Choose **Combine source entities**.
5. Select every native `media_player` entity representing the same physical TV.

The integration reloads automatically and rebuilds one device. Explicit groups use stable entity-registry IDs, so normal entity renames do not break the grouping.

## Controller capabilities

The controller exposes only features genuinely supported by at least one underlying entity:

- Power on and off.
- Play, pause, stop, previous, and next.
- Volume, mute, and volume stepping.
- Shuffle and repeat.
- Corrected absolute and relative seeking.
- Android/Google TV application launching.
- Cast receiver application launching.
- HDMI, tuner, console, AV receiver, and manufacturer inputs.
- Current app, title, artist, album, artwork, duration, and playback position.

The source selector clearly separates mechanisms:

```text
TV App · YouTube
TV App · Netflix
Cast · YouTube
Input · HDMI 1
Input · PlayStation 5
```

When switching from a Cast session to a native app or input, the integration:

1. Sends the TV to Home through Android TV Remote when available.
2. Stops the active Cast session.
3. Launches the requested native app or selects the requested input.
4. Retries a native app launch once when the TV does not confirm the requested package.

Transient pseudo-apps such as **Ready to Cast** are filtered from native TV application options.

## Application discovery

Android TV Remote does not expose a complete inventory of installed applications. Version 7 combines:

- A built-in catalogue of common Android/Google TV apps.
- Apps configured in Android TV Remote.
- Apps learned when they become active.
- Android TV ADB source entries.
- Apps registered manually through the integration action.

Learned and manually registered apps are stored locally and restored after restart. Version 7 also imports the learned-app databases used by versions 2–6.

### Register a missing TV app

```yaml
action: cast_attribute_sensors.register_tv_app
data:
  entity_id: media_player.living_room_tv_controller
  app_id: com.example.androidtv
  app_name: Example TV App
```

## Dynamic metadata sensors

The integration watches every underlying source. A sensor is created after its value first appears, then remains registered and becomes `unknown` whenever the source temporarily stops reporting it.

Examples:

```text
sensor.living_room_tv_cast_media_title
sensor.living_room_tv_cast_media_artist
sensor.living_room_tv_cast_app_id
sensor.living_room_tv_android_tv_remote_app_name
sensor.living_room_tv_manufacturer_source
```

Structured or long values are preserved in `raw_value` when they cannot fit safely in the entity state. Complete attribute snapshots are available as disabled-by-default diagnostic sensors.

## Useful actions

### Seek forward or backward from the corrected live position

```yaml
action: cast_attribute_sensors.seek_relative
data:
  entity_id: media_player.living_room_tv_controller
  seconds: 10
```

Use `-10` to rewind. The calculation accounts for elapsed time since `media_position_updated_at`, avoiding the old behaviour where “forward 10 seconds” could seek backwards.

### Send a TV remote command

```yaml
action: cast_attribute_sensors.send_command
data:
  entity_id: media_player.living_room_tv_controller
  command: HOME
```

### Restart the device

```yaml
action: cast_attribute_sensors.restart_device
data:
  entity_id: media_player.living_room_tv_controller
```

The action uses a native restart button when one exists. Otherwise it performs the safest available controlled power or receiver reset.

Additional actions:

- `cast_attribute_sensors.launch_cast_app`
- `cast_attribute_sensors.launch_tv_app`
- `cast_attribute_sensors.register_tv_app`
- `cast_attribute_sensors.send_command`
- `cast_attribute_sensors.seek_relative`
- `cast_attribute_sensors.restart_device`

## Installation with HACS

1. Open **HACS → Integrations**.
2. Open the three-dot menu and choose **Custom repositories**.
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

## Upgrading from versions 1–6

Version 7 performs a one-time migration:

- Removes old generated controller/control entities.
- Preserves existing v2 metadata sensor registrations.
- Preserves learned application data.
- Rebuilds controllers using the unified physical-device model.
- Removes obsolete empty virtual devices after setup.

After installing v7 through HACS, restart Home Assistant and allow approximately ten seconds for registry cleanup.

## Recorder considerations

To exclude complete diagnostic snapshots while retaining individual sensors:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_attributes
```

## Scope and privacy

The integration uses only data and actions already exposed by Home Assistant’s native integrations. It adds no independent cloud account, external API, telemetry, or polling loop.

## License

MIT License.

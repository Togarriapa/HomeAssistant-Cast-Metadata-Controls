# Cast Metadata & Controls for Home Assistant

A fully local Home Assistant custom integration that enhances every media player provided by the native **Google Cast** integration.

It provides two things:

1. **Lazy metadata entities** — every Cast state attribute becomes its own sensor only after that attribute reports a real value for the first time.
2. **Convenient control entities** — app selection, playback buttons, volume control, mute control, and arbitrary Cast app launching.

## Main behavior

For a Cast source such as:

```text
media_player.living_room_tv
```

entities appear under the same Home Assistant device.

### Metadata sensors

The integration always creates two base sensors:

```text
sensor.living_room_tv_cast_state
sensor.living_room_tv_cast_attributes
```

Attribute sensors are **not pre-created**. They appear only when Home Assistant first exposes a non-null value, for example:

```text
sensor.living_room_tv_cast_media_title
sensor.living_room_tv_cast_media_artist
sensor.living_room_tv_cast_app_id
sensor.living_room_tv_cast_app_name
sensor.living_room_tv_cast_media_duration
```

This applies to every attribute reported by the source Cast `media_player`, including app-specific attributes that appear only in YouTube, Spotify, Plex, Netflix, or another receiver application.

After an attribute sensor has appeared once, it remains registered permanently. When the source temporarily stops reporting that attribute, the sensor becomes `unknown` and automatically resumes when the value returns.

> Upgrading from v1 removes the old pre-created v1 sensor definitions once. v2 then recreates sensors lazily as their values appear.

### Complete attribute snapshot

The **Cast attributes** sensor uses the number of currently reported attributes as its state and carries the complete source attribute dictionary as its own attributes.

```jinja
{{ state_attr('sensor.living_room_tv_cast_attributes', 'media_title') }}
{{ state_attr('sensor.living_room_tv_cast_attributes', 'app_name') }}
```

## Cast controls

Each Cast device receives the following control entities when supported by the native media player:

- **Cast app** select — launches known apps and applications previously observed on that device.
- **Start receiver** button.
- **Play / pause** button.
- **Stop media** button.
- **Previous track** and **Next track** buttons.
- **Volume down** and **Volume up** buttons.
- **Close app** button.
- **Cast volume** number slider from 0 to 100%.
- **Cast mute** switch.

Unsupported actions are shown as unavailable rather than sending invalid commands.

### App learning

The app selector starts with:

- Home / Backdrop
- YouTube
- Default Media Receiver

Whenever the source reports a new `app_id` and `app_name`, that application is saved for that Cast device and becomes a permanent option in its selector.

### Launch any app ID

For an app not yet learned, call:

```yaml
action: cast_attribute_sensors.launch_app
data:
  entity_id: media_player.living_room_tv
  app_id: 233637DE
```

The service accepts multiple Cast media players.

Launching an app by ID only asks the receiver to start that application. Some receiver apps require additional app-specific data or content before showing anything useful.

## Long and structured values

Home Assistant entity-state strings are limited to 255 characters, and sensor states cannot directly contain dictionaries or lists.

This integration therefore:

- Uses short primitive values directly as sensor state.
- JSON-encodes short lists and dictionaries.
- Summarizes values that cannot fit safely in state.
- Preserves the full original value in the sensor attribute `raw_value`.
- Sets `value_truncated: true` when the visible state is only a preview or summary.

```jinja
{{ state_attr('sensor.living_room_tv_cast_some_large_attribute', 'raw_value') }}
```

## Installation with HACS

This repository must be public for HACS.

1. Open **HACS**.
2. Open the three-dot menu.
3. Select **Custom repositories**.
4. Add:

   ```text
   https://github.com/Togarriapa/HomeAssistant-Cast-Metadata-Controls
   ```

5. Select **Integration**.
6. Install **Cast Metadata & Controls**.
7. Restart Home Assistant.
8. Open **Settings → Devices & services → Add integration**.
9. Search for **Cast Metadata & Controls** and complete the one-step setup.

No YAML configuration is required.

## Manual installation

Copy:

```text
custom_components/cast_attribute_sensors
```

to:

```text
/config/custom_components/cast_attribute_sensors
```

Restart Home Assistant and add the integration from **Settings → Devices & services**.

## Recorder considerations

The integration can create many metadata sensors. Each attribute sensor writes only when its own value changes, but the complete snapshot sensor changes whenever any source attribute changes.

To exclude only the snapshot sensors from Recorder:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_cast_attributes
```

## Availability and lifecycle

- Existing and newly added native Cast entities are detected automatically.
- Source entity renames are followed through the entity registry.
- Source unavailable: generated entities become unavailable.
- Attribute temporarily absent: its existing sensor becomes `unknown`.
- Source removed: generated entities remain registered but unavailable, preserving their identity if the source returns.
- All communication remains through Home Assistant's native Cast integration; this helper opens no additional Cast or cloud connection.

## Scope

A source is included when its entity-registry entry has:

```text
domain: media_player
platform: cast
```

“Every attribute” means every state attribute Home Assistant exposes on that Cast `media_player`. Private internal `pychromecast` objects that Home Assistant does not publish are outside this integration's scope.

## License

MIT License.

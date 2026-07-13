# Cast Metadata & TV Controls for Home Assistant

A fully local Home Assistant helper integration that enhances Google Cast devices and native television entities with lazily created metadata sensors and capability-aware controls.

## Features

### Lazy Cast metadata sensors

For every `media_player` provided by Home Assistant's native Google Cast integration, the integration creates:

```text
sensor.<device>_cast_state
sensor.<device>_cast_attributes
```

Every additional Cast attribute becomes a separate sensor only after Home Assistant reports a non-null value for it for the first time. Examples include:

```text
sensor.<device>_cast_media_title
sensor.<device>_cast_media_artist
sensor.<device>_cast_app_id
sensor.<device>_cast_app_name
sensor.<device>_cast_media_duration
```

This is dynamic rather than limited to a hard-coded metadata list. App-specific attributes exposed later by YouTube, Spotify, Plex, Netflix, or another receiver are detected automatically.

After a sensor has appeared once, it remains registered permanently. When that attribute is temporarily absent, the sensor becomes `unknown` and resumes automatically when the value returns.

The **Cast attributes** sensor contains a complete snapshot of the source entity's current attributes.

### Cast receiver controls

Controls are created for each native Cast entity and become available only when the source advertises the required capability:

- Cast receiver power
- Start receiver
- Soft restart of the Cast receiver application
- Close current Cast application
- Play/pause and stop
- Previous and next track
- Rewind and forward 10 seconds
- Media-position percentage slider
- Volume percentage, volume up/down, and mute
- Shuffle and repeat controls
- Learned Cast application selector

The Cast app selector starts with Home/Backdrop, YouTube, and Default Media Receiver. It permanently learns additional `app_id` and `app_name` pairs when they appear on each device.

Launch an arbitrary Cast receiver app by ID:

```yaml
action: cast_attribute_sensors.launch_app
data:
  entity_id: media_player.living_room_tv
  app_id: 233637DE
```

### Native TV power and inputs

The integration also tracks non-Cast `media_player` entities representing televisions.

Depending on the capabilities exposed by the television's native Home Assistant integration, it creates:

- TV power switch
- TV volume percentage, volume up/down, and mute
- TV input selector for HDMI, tuner, console, receiver, and other published sources
- Play/pause
- Native TV restart button when the same device exposes a real restart entity

The input selector appears only when the source entity publishes `source_list` and supports `media_player.select_source`.

### Android and Google TV applications

When a TV is configured through Home Assistant's **Android TV Remote** integration, the integration adds:

- TV app selector
- Home and Back buttons
- Reload-current-app button
- Settings, Info, channel, directional-pad, and Select controls; less common controls are disabled by default to avoid clutter
- Arbitrary remote-command service

The TV app selector combines:

- Common Android/Google TV packages
- Apps configured in Android TV Remote options
- Apps learned when their package IDs become active

Launch an application by Android package ID:

```yaml
action: cast_attribute_sensors.launch_tv_app
data:
  entity_id: media_player.living_room_tv_remote
  app_id: com.google.android.youtube.tv
```

Send an Android TV Remote command:

```yaml
action: cast_attribute_sensors.send_tv_command
data:
  entity_id: media_player.living_room_tv_remote
  command: HOME
```

Plain Chromecast devices cannot expose or launch the television's installed Android apps. For installed-app selection, the television must expose a compatible Android TV Remote media-player entity.

## Long and structured metadata

Home Assistant limits entity-state strings to 255 characters, and entity states cannot directly contain dictionaries or lists. The integration therefore:

- Uses short primitive values directly as state
- JSON-encodes short structured values
- Summarizes values that cannot safely fit in state
- Preserves the complete value in the sensor attribute `raw_value`
- Sets `value_truncated: true` when the visible state is a preview or summary

```jinja
{{ state_attr('sensor.living_room_tv_cast_some_large_attribute', 'raw_value') }}
```

## HACS installation

1. Open **HACS**.
2. Open the three-dot menu and select **Custom repositories**.
3. Add:

   ```text
   https://github.com/Togarriapa/HomeAssistant-Cast-Metadata-Controls
   ```

4. Select category **Integration**.
5. Install **Cast Metadata & TV Controls**.
6. Restart Home Assistant.
7. Go to **Settings → Devices & services → Add integration**.
8. Search for **Cast Metadata & TV Controls** and complete the one-step setup.

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

Metadata sensors write only when their own values change. The complete snapshot sensor changes whenever any source attribute changes. To exclude snapshot entities from Recorder:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_cast_attributes
```

## Availability and lifecycle

- Existing and newly added Cast and TV entities are detected automatically.
- Entity renames are followed through the Home Assistant entity registry.
- Unsupported controls remain unavailable instead of sending invalid commands.
- Removed sources leave generated entities registered but unavailable, preserving stable identities if the source returns.
- The integration communicates through Home Assistant's existing Cast, television, and Android TV Remote integrations; it opens no separate device or cloud connection.

## Scope and limitations

“Every Cast attribute” means every state attribute that Home Assistant exposes on the native Cast `media_player` entity. Private internal `pychromecast` objects are outside this integration's scope.

A Cast receiver restart is a soft application restart, not a hardware reboot. A real TV restart control is exposed only when the television's native integration provides a restart entity.

## License

MIT License.

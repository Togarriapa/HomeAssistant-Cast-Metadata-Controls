# Cast Metadata & TV Controls for Home Assistant

A fully local Home Assistant helper integration that adds compact controller devices for Google Cast and native televisions while exposing Cast metadata only when it actually appears.

## Version 4 architecture

Version 4 replaces the large collection of standalone buttons, switches, selects, and number helpers with one primary `media_player` controller per discovered source.

Under **Settings → Devices & services → Cast Metadata & TV Controls**, Home Assistant now creates dedicated virtual devices such as:

```text
Living Room TV Controller
Living Room Cast Controller
```

Each device contains one compact controller entity. Cast metadata sensors are grouped under the Cast controller device.

During upgrade from v3, the old generated button, number, select, and switch entities are removed automatically. Metadata sensors are preserved.

## Compact controller capabilities

The controller entity proxies only capabilities supported by the underlying device:

- Power on and off
- Play, pause, stop, previous, and next
- Volume level, volume step, and mute
- Media position and seeking
- Cast receiver application selection
- Android/Google TV application selection
- HDMI, tuner, console, receiver, and other TV inputs
- Current title, artist, app, artwork, duration, and position when available

Apps and inputs appear in the controller's source selector with clear prefixes:

```text
App · YouTube
App · Netflix
Input · HDMI 1
Input · PlayStation 5
```

## TV application discovery

Home Assistant's Android TV Remote integration does not provide a complete installed-app inventory. The integration therefore combines:

1. A built-in catalogue of common Android/Google TV apps.
2. Apps configured in Android TV Remote options.
3. Apps learned when they become active.
4. Apps and sources exposed by a matching Android TV (ADB) entity.
5. Apps registered manually through the `register_tv_app` action.

Using the Android TV (ADB) integration alongside Android TV Remote provides the broadest automatic app list available through Home Assistant.

### Register a missing app

```yaml
action: cast_attribute_sensors.register_tv_app
data:
  entity_id: media_player.living_room_tv
  app_id: com.example.androidtv
  app_name: Example TV
```

The application is stored permanently for that TV.

## Corrected relative seeking

The old relative-seek button used the last reported Cast position directly. Cast position reports can be several seconds old, so a `+10` operation could seek backwards.

Version 4 corrects the position using `media_position_updated_at` before applying the offset:

```yaml
action: cast_attribute_sensors.seek_relative
data:
  entity_id: media_player.living_room_cast
  seconds: 10
```

Use a negative value to rewind.

## Lazy Cast metadata

Every native Cast attribute becomes its own sensor only after Home Assistant reports a non-null value for it. Examples include:

```text
sensor.living_room_cast_media_title
sensor.living_room_cast_media_artist
sensor.living_room_cast_app_id
sensor.living_room_cast_app_name
```

Once created, the sensor remains registered. It becomes `unknown` while the source temporarily stops reporting that attribute.

## Installation with HACS

1. Open **HACS → Integrations**.
2. Open the three-dot menu and select **Custom repositories**.
3. Add:

   ```text
   https://github.com/Togarriapa/HomeAssistant-Cast-Metadata-Controls
   ```

4. Select **Integration**.
5. Install or update **Cast Metadata & TV Controls**.
6. Restart Home Assistant.
7. Open **Settings → Devices & services**.
8. Add or open **Cast Metadata & TV Controls**.

No YAML configuration is required.

## Available actions

- `cast_attribute_sensors.launch_app`
- `cast_attribute_sensors.launch_tv_app`
- `cast_attribute_sensors.register_tv_app`
- `cast_attribute_sensors.send_tv_command`
- `cast_attribute_sensors.seek_relative`

## Recorder considerations

To exclude the complete attribute snapshots while retaining individual metadata sensors:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_cast_attributes
```

## Scope

The integration controls and reports only information already exposed through Home Assistant's native Cast, Android TV Remote, Android TV (ADB), and television integrations. It does not create an independent cloud connection.

## License

MIT License.

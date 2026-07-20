"""Static V8.3 release checks without Home Assistant imports."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "cast_attribute_sensors"


class V83ActivationTests(unittest.TestCase):
    def test_runtime_patches_activate_before_platform_forwarding(self) -> None:
        registry = (COMPONENT / "ad_skip_registry.py").read_text()
        setup = (COMPONENT / "__init__.py").read_text()
        self.assertIn("install_v83_patches()", registry)
        self.assertIn("install_v831_patches()", registry)
        self.assertIn("install_v840_patches()", registry)
        self.assertLess(
            setup.index("register_manager(entry.entry_id"),
            setup.index("async_forward_entry_setups"),
        )

    def test_options_patch_is_activated(self) -> None:
        source = (COMPONENT / "config_flow.py").read_text()
        self.assertIn("install_v83_options(ControllerOptionsFlow)", source)
        self.assertIn("install_v840_options(ControllerOptionsFlow)", source)

    def test_release_versions_match(self) -> None:
        manifest = json.loads((COMPONENT / "manifest.json").read_text())
        const = (COMPONENT / "const.py").read_text()
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertEqual(manifest["version"], "8.4.0")
        self.assertIn('VERSION: Final = "8.4.0"', const)
        self.assertIn("## 8.4.0", changelog)

    def test_hacs_uses_verified_zip_release(self) -> None:
        hacs = json.loads((ROOT / "hacs.json").read_text())
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.assertIs(hacs["zip_release"], True)
        self.assertEqual(hacs["filename"], "cast_attribute_sensors.zip")
        self.assertIn("softprops/action-gh-release@v2", workflow)
        self.assertIn("make_latest: true", workflow)
        self.assertIn("cmp \"$ASSET\"", workflow)

    def test_generic_configuration_keys_are_declared(self) -> None:
        const = (COMPONENT / "const.py").read_text()
        self.assertIn('CONF_DEVICE_ENTITIES: Final = "device_entities"', const)
        self.assertIn(
            'CONF_PROVIDER_ROUTES: Final = "entity_provider_routes"', const
        )
        self.assertIn(
            'CONF_COMMAND_MAPS: Final = "remote_command_maps"', const
        )

    def test_hotfix_routes_apps_and_records_ad_skip_failures(self) -> None:
        patch = (COMPONENT / "v831_patch.py").read_text()
        self.assertIn("SourceManager.android_tv_remote_source_id", patch)
        self.assertIn('"generic_app"', patch)
        self.assertIn('"youtube_not_detected"', patch)
        self.assertIn('"cast_skip_not_advertised"', patch)
        self.assertIn('"skip_control_not_detected"', patch)

    def test_backend_contains_no_new_vendor_command_profiles(self) -> None:
        generic = (COMPONENT / "generic_capabilities.py").read_text().casefold()
        patch = (COMPONENT / "v83_patch.py").read_text().casefold()
        hotfix = (COMPONENT / "v831_patch.py").read_text().casefold()
        for forbidden in ("bravia", "sony", "samsung", "webos", "panasonic"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, generic)
                self.assertNotIn(forbidden, patch)
                self.assertNotIn(forbidden, hotfix)


if __name__ == "__main__":
    unittest.main()

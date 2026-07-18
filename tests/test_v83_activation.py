"""Static V8.3 release checks that do not import Home Assistant."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "cast_attribute_sensors"


class V83ActivationTests(unittest.TestCase):
    def test_runtime_patch_activates_before_platform_forwarding(self) -> None:
        registry = (COMPONENT / "ad_skip_registry.py").read_text()
        setup = (COMPONENT / "__init__.py").read_text()
        self.assertIn("install_v83_patches()", registry)
        self.assertLess(
            setup.index("register_manager(entry.entry_id"),
            setup.index("async_forward_entry_setups"),
        )

    def test_options_patch_is_activated(self) -> None:
        source = (COMPONENT / "config_flow.py").read_text()
        self.assertIn("install_v83_options(ControllerOptionsFlow)", source)

    def test_release_versions_match(self) -> None:
        manifest = json.loads((COMPONENT / "manifest.json").read_text())
        const = (COMPONENT / "const.py").read_text()
        self.assertEqual(manifest["version"], "8.3.0")
        self.assertIn('VERSION: Final = "8.3.0"', const)

    def test_generic_configuration_keys_are_declared(self) -> None:
        const = (COMPONENT / "const.py").read_text()
        self.assertIn('CONF_DEVICE_ENTITIES: Final = "device_entities"', const)
        self.assertIn(
            'CONF_PROVIDER_ROUTES: Final = "entity_provider_routes"', const
        )
        self.assertIn(
            'CONF_COMMAND_MAPS: Final = "remote_command_maps"', const
        )

    def test_backend_contains_no_new_vendor_command_profiles(self) -> None:
        generic = (COMPONENT / "generic_capabilities.py").read_text().casefold()
        patch = (COMPONENT / "v83_patch.py").read_text().casefold()
        for forbidden in ("bravia", "sony", "samsung", "webos", "panasonic"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, generic)
                self.assertNotIn(forbidden, patch)


if __name__ == "__main__":
    unittest.main()

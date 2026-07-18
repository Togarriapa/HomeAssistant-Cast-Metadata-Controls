"""Static release checks for V8.3 universal remote support."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "cast_attribute_sensors"


class V83ActivationTests(unittest.TestCase):
    def test_runtime_patch_is_activated(self) -> None:
        source = (COMPONENT / "ad_skip_registry.py").read_text()
        self.assertIn("install_v83_patches()", source)

    def test_options_patch_is_activated(self) -> None:
        source = (COMPONENT / "config_flow.py").read_text()
        self.assertIn("install_v83_options(ControllerOptionsFlow)", source)

    def test_release_versions_match(self) -> None:
        manifest = json.loads((COMPONENT / "manifest.json").read_text())
        const = (COMPONENT / "const.py").read_text()
        self.assertEqual(manifest["version"], "8.3.0")
        self.assertIn('VERSION: Final = "8.3.0"', const)

    def test_manual_remote_configuration_is_declared(self) -> None:
        const = (COMPONENT / "const.py").read_text()
        self.assertIn('CONF_REMOTE_CONTROLS: Final = "remote_controls"', const)
        self.assertIn('CONF_REMOTE_ENTITY: Final = "entity_id"', const)
        self.assertIn('CONF_REMOTE_PROFILE: Final = "profile"', const)


if __name__ == "__main__":
    unittest.main()

"""Tests for vendor-neutral capability helpers without Home Assistant imports."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1] / "custom_components" / "cast_attribute_sensors"
PACKAGE = "custom_components.cast_attribute_sensors"

custom_components = sys.modules.setdefault(
    "custom_components", types.ModuleType("custom_components")
)
custom_components.__path__ = []
package = sys.modules.setdefault(PACKAGE, types.ModuleType(PACKAGE))
package.__path__ = [str(ROOT)]

spec = importlib.util.spec_from_file_location(
    f"{PACKAGE}.generic_capabilities", ROOT / "generic_capabilities.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
assert spec.loader is not None
spec.loader.exec_module(module)

from custom_components.cast_attribute_sensors.generic_capabilities import (  # noqa: E402
    command_for,
    normalized_command_map,
    source_kind,
)


class GenericCapabilityTests(unittest.TestCase):
    def test_physical_inputs_are_classified_generically(self) -> None:
        for value in (
            "HDMI 1",
            "HDMI 2 (ARC)",
            "TV",
            "TV Tuner",
            "AV 1",
            "Digital Tuner",
            "USB",
        ):
            with self.subTest(value=value):
                self.assertEqual(source_kind(value), "input")

    def test_other_selectable_sources_become_native_apps(self) -> None:
        for value in (
            "YouTube",
            "YouTube TV",
            "Apple TV",
            "Netflix",
            "Plex",
            "Music",
        ):
            with self.subTest(value=value):
                self.assertEqual(source_kind(value), "native_source")

    def test_commands_pass_through_without_hardcoded_profiles(self) -> None:
        self.assertEqual(command_for({}, "DPAD_CENTER"), "DPAD_CENTER")
        self.assertEqual(command_for({}, "SETTINGS"), "SETTINGS")

    def test_user_mapping_controls_provider_command(self) -> None:
        mapping = {"DPAD_CENTER": "Confirm", "BACK": "Return"}
        self.assertEqual(command_for(mapping, "DPAD_CENTER"), "Confirm")
        self.assertEqual(command_for(mapping, "BACK"), "Return")

    def test_only_supported_non_default_mappings_are_stored(self) -> None:
        self.assertEqual(
            normalized_command_map(
                {
                    "HOME": "HOME",
                    "BACK": " Return ",
                    "UNKNOWN": "ignored",
                    "SETTINGS": "",
                }
            ),
            {"BACK": "Return"},
        )


if __name__ == "__main__":
    unittest.main()

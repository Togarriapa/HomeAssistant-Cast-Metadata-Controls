"""Tests for universal remote command profiles without Home Assistant imports."""

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
    f"{PACKAGE}.universal_remote", ROOT / "universal_remote.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
assert spec.loader is not None
spec.loader.exec_module(module)

from custom_components.cast_attribute_sensors.universal_remote import (  # noqa: E402
    PROFILE_ANDROID_TV_ADB,
    PROFILE_BRAVIA,
    native_source_kind,
    profile_for_platform,
    translate_command,
)


class UniversalRemoteTests(unittest.TestCase):
    def test_bravia_navigation_commands_are_translated(self) -> None:
        self.assertEqual(translate_command(PROFILE_BRAVIA, "DPAD_UP"), "Up")
        self.assertEqual(
            translate_command(PROFILE_BRAVIA, "DPAD_CENTER"), "Confirm"
        )
        self.assertEqual(translate_command(PROFILE_BRAVIA, "BACK"), "Return")
        self.assertEqual(
            translate_command(PROFILE_BRAVIA, "SETTINGS"), "ActionMenu"
        )

    def test_android_adb_commands_are_translated(self) -> None:
        self.assertEqual(
            translate_command(PROFILE_ANDROID_TV_ADB, "DPAD_LEFT"), "LEFT"
        )
        self.assertEqual(
            translate_command(PROFILE_ANDROID_TV_ADB, "DPAD_CENTER"), "CENTER"
        )

    def test_unknown_commands_pass_through(self) -> None:
        self.assertEqual(translate_command(PROFILE_BRAVIA, "VolumeUp"), "VolumeUp")

    def test_platform_profiles(self) -> None:
        self.assertEqual(profile_for_platform("braviatv"), PROFILE_BRAVIA)
        self.assertEqual(profile_for_platform("sony_bravia"), PROFILE_BRAVIA)

    def test_native_source_classification(self) -> None:
        self.assertEqual(native_source_kind("HDMI 1"), "input")
        self.assertEqual(native_source_kind("TV"), "input")
        self.assertEqual(native_source_kind("YouTube"), "native_app")
        self.assertEqual(native_source_kind("Netflix"), "native_app")


if __name__ == "__main__":
    unittest.main()

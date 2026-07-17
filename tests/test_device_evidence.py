"""Regression tests for native TV evidence used by V8.1 discovery."""

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

full_name = f"{PACKAGE}.device_evidence"
spec = importlib.util.spec_from_file_location(
    full_name, ROOT / "device_evidence.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[full_name] = module
assert spec and spec.loader
spec.loader.exec_module(module)

from custom_components.cast_attribute_sensors.device_evidence import (  # noqa: E402
    is_native_tv,
)


class DeviceEvidenceTests(unittest.TestCase):
    def test_known_native_platforms_are_tvs(self) -> None:
        for platform in (
            "androidtv_remote",
            "androidtv",
            "braviatv",
            "sony_bravia",
            "samsungtv",
            "webostv",
            "panasonic_viera",
            "philips_js",
        ):
            with self.subTest(platform=platform):
                self.assertTrue(is_native_tv(platform=platform))

    def test_registry_or_state_device_class_is_authoritative(self) -> None:
        self.assertTrue(
            is_native_tv(platform="custom_tv", registry_device_class="tv")
        )
        self.assertTrue(
            is_native_tv(platform="custom_tv", state_device_class="tv")
        )

    def test_sony_media_renderer_is_identified_from_hardware_metadata(self) -> None:
        self.assertTrue(
            is_native_tv(
                platform="dlna_dmr",
                manufacturer="Sony",
                model="BRAVIA 4K UR3",
                friendly_name="MediaRenderer",
            )
        )

    def test_generic_dlna_renderer_is_not_assumed_to_be_a_tv(self) -> None:
        self.assertFalse(
            is_native_tv(
                platform="dlna_dmr",
                manufacturer="Generic",
                friendly_name="MediaRenderer",
            )
        )

    def test_non_tv_media_players_remain_excluded(self) -> None:
        self.assertFalse(
            is_native_tv(
                platform="sonos",
                manufacturer="Sonos",
                model="Arc",
                friendly_name="Living room speaker",
            )
        )


if __name__ == "__main__":
    unittest.main()

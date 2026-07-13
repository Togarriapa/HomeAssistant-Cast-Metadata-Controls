"""Tests for sensor value and unique-ID utilities."""

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

for module_name in ("const", "util"):
    full_name = f"{PACKAGE}.{module_name}"
    if full_name in sys.modules:
        continue
    spec = importlib.util.spec_from_file_location(full_name, ROOT / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

from custom_components.cast_attribute_sensors.const import KIND_ATTRIBUTE  # noqa: E402
from custom_components.cast_attribute_sensors.util import (  # noqa: E402
    normalize_native_value,
    parse_sensor_unique_id,
    sensor_unique_id,
)


class UtilTests(unittest.TestCase):
    def test_unique_id_round_trip_retains_v2_compatibility(self) -> None:
        unique_id = sensor_unique_id("registry-id", KIND_ATTRIBUTE, "media_title")
        self.assertTrue(unique_id.startswith("v2|"))
        self.assertEqual(
            parse_sensor_unique_id(unique_id),
            ("registry-id", KIND_ATTRIBUTE, "media_title"),
        )

    def test_long_value_is_preserved(self) -> None:
        value = "x" * 400
        state, attributes = normalize_native_value(value)
        self.assertLessEqual(len(str(state)), 255)
        self.assertEqual(attributes["raw_value"], value)
        self.assertTrue(attributes["value_truncated"])

    def test_structured_value_is_preserved(self) -> None:
        value = {"apps": ["a", "b"]}
        state, attributes = normalize_native_value(value)
        self.assertIsInstance(state, str)
        self.assertEqual(attributes["raw_value"], value)


if __name__ == "__main__":
    unittest.main()

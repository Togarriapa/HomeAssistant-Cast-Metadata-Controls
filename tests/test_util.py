"""Standalone tests for Cast Metadata & Controls utility functions."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "custom_components" / "cast_attribute_sensors"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)

package = types.ModuleType("custom_components.cast_attribute_sensors")
package.__path__ = [str(PACKAGE)]
sys.modules.setdefault("custom_components.cast_attribute_sensors", package)

const = _load_module(
    "custom_components.cast_attribute_sensors.const",
    PACKAGE / "const.py",
)
util = _load_module(
    "custom_components.cast_attribute_sensors.util",
    PACKAGE / "util.py",
)


class UtilityTests(unittest.TestCase):
    """Test stable IDs, package consistency, and value normalization."""

    def test_attribute_unique_id_round_trip(self) -> None:
        attribute = "médiá|custom/value"
        unique_id = util.build_unique_id("registry-id", "attribute", attribute)
        self.assertEqual(
            util.parse_unique_id(unique_id),
            ("registry-id", "attribute", attribute),
        )

    def test_base_unique_ids(self) -> None:
        self.assertEqual(
            util.parse_unique_id(util.build_unique_id("id", "state", None)),
            ("id", "state", None),
        )
        self.assertEqual(
            util.parse_unique_id(util.build_unique_id("id", "snapshot", None)),
            ("id", "snapshot", None),
        )

    def test_long_string_is_preserved(self) -> None:
        original = "x" * 400
        state, extra = util.normalize_native_value(original)
        self.assertLessEqual(len(state), 255)
        self.assertEqual(extra["raw_value"], original)
        self.assertTrue(extra["value_truncated"])

    def test_mapping_is_json_encoded(self) -> None:
        original = {"title": "Example", "items": [1, 2]}
        state, extra = util.normalize_native_value(original)
        self.assertEqual(state, '{"title":"Example","items":[1,2]}')
        self.assertEqual(extra["raw_value"], original)

    def test_large_mapping_is_summarized(self) -> None:
        original = {str(index): "x" * 30 for index in range(30)}
        state, extra = util.normalize_native_value(original)
        self.assertEqual(state, "dict (30 items)")
        self.assertEqual(extra["raw_value"], original)
        self.assertTrue(extra["value_truncated"])

    def test_boolean_keeps_original_value(self) -> None:
        state, extra = util.normalize_native_value(True)
        self.assertEqual(state, "true")
        self.assertIs(extra["raw_value"], True)

    def test_no_precreated_attribute_catalogue(self) -> None:
        self.assertFalse(hasattr(const, "BASE_CAST_ATTRIBUTES"))

    def test_manifest_and_constant_versions_match(self) -> None:
        manifest = json.loads((PACKAGE / "manifest.json").read_text())
        self.assertEqual(manifest["version"], const.VERSION)
        self.assertEqual(manifest["domain"], const.DOMAIN)

    def test_default_app_catalogue(self) -> None:
        self.assertEqual(const.DEFAULT_CAST_APPS["233637DE"], "YouTube")
        self.assertEqual(const.DEFAULT_CAST_APPS["CC1AD845"], "Default Media Receiver")
        self.assertEqual(
            const.DEFAULT_ANDROID_TV_APPS["com.google.android.youtube.tv"],
            "YouTube",
        )
        self.assertEqual(const.DEFAULT_ANDROID_TV_APPS["com.netflix.ninja"], "Netflix")

    def test_control_unique_id_version_remains_stable(self) -> None:
        self.assertEqual(const.UID_VERSION, "v2")


if __name__ == "__main__":
    unittest.main()

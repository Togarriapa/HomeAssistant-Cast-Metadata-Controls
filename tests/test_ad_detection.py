"""Tests for positive-detection YouTube ad helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1] / "custom_components" / "cast_attribute_sensors"
PACKAGE = "custom_components.cast_attribute_sensors"

custom_components = types.ModuleType("custom_components")
custom_components.__path__ = []
sys.modules.setdefault("custom_components", custom_components)
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules.setdefault(PACKAGE, package)

for module_name in ("const", "ad_detection"):
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.{module_name}", ROOT / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

from custom_components.cast_attribute_sensors.ad_detection import (  # noqa: E402
    find_skip_target,
    is_youtube_attributes,
    normalize_ui_text,
)


class AdDetectionTests(unittest.TestCase):
    def test_youtube_app_ids_and_names(self) -> None:
        self.assertTrue(
            is_youtube_attributes({"app_id": "com.google.android.youtube.tv"})
        )
        self.assertTrue(is_youtube_attributes({"app_name": "YouTube"}))
        self.assertTrue(is_youtube_attributes({"app_id": "233637DE"}))
        self.assertFalse(is_youtube_attributes({"app_name": "Netflix"}))

    def test_normalize_localized_text(self) -> None:
        self.assertEqual(normalize_ui_text("Ignorar anúncio"), "ignorar anuncio")

    def test_finds_english_clickable_skip_ad(self) -> None:
        xml = """
        UI hierarchy dumped to: /sdcard/window.xml
        <hierarchy rotation="0">
          <node text="Skip ad" clickable="true" enabled="true"
                bounds="[1600,850][1900,980]" />
        </hierarchy>
        """
        self.assertEqual(find_skip_target(xml), (1750, 915))

    def test_finds_portuguese_child_inside_clickable_parent(self) -> None:
        xml = """
        <hierarchy rotation="0">
          <node clickable="true" enabled="true" bounds="[1500,800][1900,1000]">
            <node text="Ignorar anúncio" clickable="false" enabled="true"
                  bounds="[1550,830][1870,970]" />
          </node>
        </hierarchy>
        """
        self.assertEqual(find_skip_target(xml), (1710, 900))

    def test_resource_id_detection(self) -> None:
        xml = """
        <hierarchy>
          <node resource-id="com.google.android.youtube.tv:id/skip_ad_button"
                text="" clickable="true" enabled="true"
                bounds="[100,200][300,400]" />
        </hierarchy>
        """
        self.assertEqual(find_skip_target(xml), (200, 300))

    def test_rejects_unrelated_controls_and_invalid_xml(self) -> None:
        unrelated = """
        <hierarchy><node text="Next video" clickable="true"
        bounds="[0,0][100,100]" /></hierarchy>
        """
        self.assertIsNone(find_skip_target(unrelated))
        self.assertIsNone(find_skip_target("not xml"))


if __name__ == "__main__":
    unittest.main()

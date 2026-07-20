"""Static regressions for the V8.4 physical-device setup release."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "cast_attribute_sensors"


class V840ReleaseTests(unittest.TestCase):
    def test_generated_controller_is_never_a_merge_candidate(self) -> None:
        source = (COMPONENT / "v840_options.py").read_text()
        self.assertIn("entry.platform == DOMAIN", source)
        self.assertIn("_v840_external_media_options", source)

    def test_options_are_saved_before_reload(self) -> None:
        source = (COMPONENT / "v840_options.py").read_text()
        self.assertIn("OptionsFlow.async_create_entry", source)
        self.assertIn("reload_when_saved", source)

    def test_explicit_generic_media_players_are_tracked(self) -> None:
        source = (COMPONENT / "v840_patch.py").read_text()
        self.assertIn("return False, False", source)
        self.assertIn("SourceManager._classify = _classify", source)

    def test_native_apps_and_manual_skip_are_exposed(self) -> None:
        source = (COMPONENT / "v840_patch.py").read_text()
        self.assertIn('"runtime_release": "8.4.0"', source)
        self.assertIn('"native_application_count"', source)
        self.assertIn('"manual_remote_confirm_sent"', source)
        self.assertIn('"automatic_positive_detection_only": True', source)

    def test_release_versions_match(self) -> None:
        manifest = json.loads((COMPONENT / "manifest.json").read_text())
        const = (COMPONENT / "const.py").read_text()
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertEqual(manifest["version"], "8.4.0")
        self.assertIn('VERSION: Final = "8.4.0"', const)
        self.assertIn("## 8.4.0", changelog)

    def test_v840_contains_no_vendor_specific_profiles(self) -> None:
        content = "\n".join(
            (COMPONENT / name).read_text().casefold()
            for name in ("v840_options.py", "v840_patch.py")
        )
        for forbidden in ("bravia", "sony", "samsung", "webos", "panasonic"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, content)


if __name__ == "__main__":
    unittest.main()

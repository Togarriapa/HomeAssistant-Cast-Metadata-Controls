"""Release regressions that do not require importing Home Assistant."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "cast_attribute_sensors"


class V82ActivationTests(unittest.TestCase):
    def test_runtime_patch_is_activated(self) -> None:
        source = (COMPONENT / "__init__.py").read_text()
        self.assertIn("install_v81_patches()", source)

    def test_remote_and_artwork_fallbacks_are_present(self) -> None:
        manager = (COMPONENT / "source_manager.py").read_text()
        player = (COMPONENT / "media_player.py").read_text()
        self.assertIn("android_tv_remote_source_id", manager)
        self.assertIn("remote_available", player)
        self.assertIn('("entity_picture", "media_image_url")', player)

    def test_manifest_and_python_versions_match(self) -> None:
        manifest = json.loads((COMPONENT / "manifest.json").read_text())
        const = (COMPONENT / "const.py").read_text()
        self.assertIn(
            f'VERSION: Final = "{manifest["version"]}"',
            const,
        )


if __name__ == "__main__":
    unittest.main()

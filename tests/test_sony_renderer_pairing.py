"""Regression tests for Sony native and DLNA renderer pairing."""

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

for module_name in ("const", "grouping"):
    full_name = f"{PACKAGE}.{module_name}"
    if full_name in sys.modules:
        continue
    spec = importlib.util.spec_from_file_location(
        full_name, ROOT / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

from custom_components.cast_attribute_sensors.grouping import (  # noqa: E402
    SourceSnapshot,
    build_physical_groups,
)


def source(
    registry_id: str,
    name: str,
    *,
    platform: str,
    area_id: str | None,
    manufacturer: str | None = "Sony",
    device_name: str | None = None,
) -> SourceSnapshot:
    return SourceSnapshot(
        registry_id=registry_id,
        entity_id=f"media_player.{registry_id}",
        platform=platform,
        name=name,
        device_id=None,
        connections=frozenset(),
        area_id=area_id,
        is_cast=False,
        is_tv=True,
        manufacturer=manufacturer,
        model=None,
        device_name=device_name,
    )


class SonyRendererPairingTests(unittest.TestCase):
    def test_native_bravia_and_media_renderer_merge(self) -> None:
        groups = build_physical_groups(
            [
                source(
                    "bravia_ur3",
                    "BRAVIA 4K UR3",
                    platform="braviatv",
                    area_id=None,
                    device_name="BRAVIA 4K UR3",
                ),
                source(
                    "media_renderer",
                    "MediaRenderer",
                    platform="dlna_dmr",
                    area_id="living_room",
                    device_name="BRAVIA KE-55XH8096",
                ),
            ]
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(
            set(groups[0].source_ids), {"bravia_ur3", "media_renderer"}
        )
        self.assertNotEqual(groups[0].name, "MediaRenderer")

    def test_renderer_pairing_refuses_conflicting_areas(self) -> None:
        groups = build_physical_groups(
            [
                source(
                    "bravia_ur3",
                    "BRAVIA 4K UR3",
                    platform="braviatv",
                    area_id="office",
                ),
                source(
                    "media_renderer",
                    "MediaRenderer",
                    platform="dlna_dmr",
                    area_id="living_room",
                ),
            ]
        )

        self.assertEqual(len(groups), 2)

    def test_renderer_pairing_refuses_ambiguous_multiple_sony_tvs(self) -> None:
        groups = build_physical_groups(
            [
                source(
                    "bravia_ur3",
                    "BRAVIA 4K UR3",
                    platform="braviatv",
                    area_id=None,
                ),
                source(
                    "living_renderer",
                    "MediaRenderer",
                    platform="dlna_dmr",
                    area_id="living_room",
                    device_name="BRAVIA KE-55XH8096",
                ),
                source(
                    "bedroom_renderer",
                    "MediaRenderer",
                    platform="dlna_dmr",
                    area_id="bedroom",
                    device_name="BRAVIA KD-43X80J",
                ),
            ]
        )

        self.assertEqual(len(groups), 3)


if __name__ == "__main__":
    unittest.main()

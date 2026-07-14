"""Tests for physical-device grouping without importing Home Assistant."""

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

for module_name in ("const", "grouping"):
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.{module_name}", ROOT / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

from custom_components.cast_attribute_sensors.grouping import (  # noqa: E402
    SourceSnapshot,
    build_physical_groups,
    clean_device_name,
    normalized_device_name,
)


def source(
    registry_id: str,
    name: str,
    *,
    platform: str,
    device_id: str | None = None,
    connections: frozenset[tuple[str, str]] = frozenset(),
    area_id: str | None = "living_room",
    is_cast: bool = False,
    is_tv: bool = True,
) -> SourceSnapshot:
    return SourceSnapshot(
        registry_id=registry_id,
        entity_id=f"media_player.{registry_id}",
        platform=platform,
        name=name,
        device_id=device_id,
        connections=connections,
        area_id=area_id,
        is_cast=is_cast,
        is_tv=is_tv,
    )


class GroupingTests(unittest.TestCase):
    def test_normalized_names_remove_integration_suffixes(self) -> None:
        self.assertEqual(
            normalized_device_name("Living Room Android TV Remote"), "livingroom"
        )
        self.assertEqual(
            normalized_device_name("Living Room Chromecast Built-in"), "livingroom"
        )

    def test_display_name_removes_repeated_controller_suffix(self) -> None:
        self.assertEqual(
            clean_device_name("BRAVIA KE-55XH8096 Controller Controller"),
            "BRAVIA KE-55XH8096",
        )

    def test_shared_device_id_groups_all_representations(self) -> None:
        sources = [
            source(
                "remote", "Living Room TV", platform="androidtv_remote", device_id="abc"
            ),
            source(
                "adb", "Living Room Android TV", platform="androidtv", device_id="abc"
            ),
            source(
                "cast",
                "Living Room Chromecast",
                platform="cast",
                device_id="abc",
                is_cast=True,
                is_tv=False,
            ),
        ]
        groups = build_physical_groups(sources)
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0].source_ids), {"remote", "adb", "cast"})

    def test_matching_connections_group_sources(self) -> None:
        mac = frozenset({("mac", "AA:BB:CC:DD:EE:FF")})
        groups = build_physical_groups(
            [
                source(
                    "remote", "TV Remote", platform="androidtv_remote", connections=mac
                ),
                source(
                    "cast",
                    "TV Cast",
                    platform="cast",
                    connections=mac,
                    is_cast=True,
                    is_tv=False,
                ),
            ]
        )
        self.assertEqual(len(groups), 1)

    def test_bravia_native_and_android_names_group_in_same_area(self) -> None:
        groups = build_physical_groups(
            [
                source(
                    "sony",
                    "BRAVIA KE-55XH8096 Controller",
                    platform="braviatv",
                ),
                source(
                    "remote",
                    "BRAVIA 4K GB ATV3 Controller",
                    platform="androidtv_remote",
                ),
            ]
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0].source_ids), {"sony", "remote"})
        self.assertNotIn("Controller", groups[0].name)

    def test_family_match_requires_same_area(self) -> None:
        groups = build_physical_groups(
            [
                source(
                    "sony",
                    "BRAVIA KE-55XH8096",
                    platform="braviatv",
                    area_id="living_room",
                ),
                source(
                    "remote",
                    "BRAVIA 4K GB ATV3",
                    platform="androidtv_remote",
                    area_id="bedroom",
                ),
            ]
        )
        self.assertEqual(len(groups), 2)

    def test_different_named_devices_in_same_area_remain_separate(self) -> None:
        groups = build_physical_groups(
            [
                source("tv_a", "Sony Television", platform="sony"),
                source("tv_b", "Samsung Television", platform="samsung"),
            ]
        )
        self.assertEqual(len(groups), 2)

    def test_standalone_cast_remains_separate(self) -> None:
        groups = build_physical_groups(
            [
                source("tv", "Living Room TV", platform="androidtv_remote"),
                source(
                    "speaker",
                    "Kitchen Speaker",
                    platform="cast",
                    area_id="kitchen",
                    is_cast=True,
                    is_tv=False,
                ),
            ]
        )
        self.assertEqual(len(groups), 2)

    def test_manual_group_overrides_unrelated_names(self) -> None:
        sources = [
            source("remote", "TCL 55C", platform="androidtv_remote"),
            source(
                "cast",
                "Google Cast 9A21",
                platform="cast",
                is_cast=True,
                is_tv=False,
            ),
        ]
        groups = build_physical_groups(
            sources,
            [
                {
                    "group_id": "living",
                    "name": "Living Room TV",
                    "members": ["remote", "cast"],
                }
            ],
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].key, "manual:living")
        self.assertEqual(groups[0].name, "Living Room TV")


if __name__ == "__main__":
    unittest.main()

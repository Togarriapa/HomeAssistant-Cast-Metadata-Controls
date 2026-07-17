"""Regression tests for V8 physical-device option migration."""

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

for module_name in ("const", "merge_options"):
    full_name = f"{PACKAGE}.{module_name}"
    if full_name in sys.modules:
        continue
    spec = importlib.util.spec_from_file_location(
        full_name, ROOT / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)

from custom_components.cast_attribute_sensors.const import (  # noqa: E402
    CONF_ACTIVITIES,
    CONF_APP_PREFERENCES,
    CONF_DELAYS,
    CONF_GROUP_ID,
    CONF_GROUP_NAME,
    CONF_MEMBERS,
    CONF_ROUTES,
    CONF_WOL,
)
from custom_components.cast_attribute_sensors.merge_options import (  # noqa: E402
    merge_manual_group_configs,
    remap_group_settings,
    remove_group_settings,
)


class MergeOptionsTests(unittest.TestCase):
    def test_merge_flattens_overlap_and_keeps_unrelated_group(self) -> None:
        groups = [
            {
                CONF_GROUP_ID: "first",
                CONF_GROUP_NAME: "TV",
                CONF_MEMBERS: ["a", "b"],
            },
            {
                CONF_GROUP_ID: "second",
                CONF_GROUP_NAME: "Receiver",
                CONF_MEMBERS: ["b", "c", "d"],
            },
            {
                CONF_GROUP_ID: "other",
                CONF_GROUP_NAME: "Bedroom",
                CONF_MEMBERS: ["x", "y"],
            },
        ]
        result, target_id = merge_manual_group_configs(
            groups,
            member_ids=["a", "b", "c"],
            name="Living room TV",
            group_id="first",
        )
        self.assertEqual(target_id, "first")
        self.assertEqual(
            result,
            [
                {
                    CONF_GROUP_ID: "other",
                    CONF_GROUP_NAME: "Bedroom",
                    CONF_MEMBERS: ["x", "y"],
                },
                {
                    CONF_GROUP_ID: "first",
                    CONF_GROUP_NAME: "Living room TV",
                    CONF_MEMBERS: ["a", "b", "c"],
                },
            ],
        )

    def test_settings_move_to_new_manual_group(self) -> None:
        updates = remap_group_settings(
            old_keys=["physical:a", "physical:b"],
            new_key="manual:merged",
            routes={
                "physical:a": {"power": "a"},
                "physical:b": {"volume": "b"},
            },
            preferences={
                "physical:b": {"tv_app|netflix": {"favorite": True}}
            },
            delays={"physical:a": {"power_delay": 1.5}},
            activities={
                "physical:a": [
                    {"activity_id": "1", "activity_name": "Movie"}
                ],
                "physical:b": [
                    {"activity_id": "2", "activity_name": "Games"}
                ],
            },
            wol={"physical:b": {"mac": "AA:BB:CC:DD:EE:FF"}},
        )
        self.assertEqual(
            updates[CONF_ROUTES]["manual:merged"],
            {"power": "a", "volume": "b"},
        )
        self.assertIn(
            "tv_app|netflix",
            updates[CONF_APP_PREFERENCES]["manual:merged"],
        )
        self.assertEqual(
            updates[CONF_DELAYS]["manual:merged"]["power_delay"], 1.5
        )
        self.assertEqual(len(updates[CONF_ACTIVITIES]["manual:merged"]), 2)
        self.assertEqual(
            updates[CONF_WOL]["manual:merged"]["mac"],
            "AA:BB:CC:DD:EE:FF",
        )
        self.assertNotIn("physical:a", updates[CONF_ROUTES])
        self.assertNotIn("physical:b", updates[CONF_ROUTES])

    def test_remove_group_settings_clears_every_scope(self) -> None:
        updates = remove_group_settings(
            ["manual:old"],
            routes={
                "manual:old": {"power": "a"},
                "physical:x": {"volume": "x"},
            },
            preferences={"manual:old": {"app": {}}},
            delays={"manual:old": {"power_delay": 1}},
            activities={"manual:old": [{"activity_id": "1"}]},
            wol={"manual:old": {"mac": "AA"}},
        )
        for mapping in updates.values():
            self.assertNotIn("manual:old", mapping)
        self.assertIn("physical:x", updates[CONF_ROUTES])


if __name__ == "__main__":
    unittest.main()

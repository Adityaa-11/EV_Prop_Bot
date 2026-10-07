"""Dabble Android placer routing and hardware helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "hermes" / "skills" / "place-dfs-entry" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dabble_android import dabble_side_label, parse_android_release  # noqa: E402
from run_executor import placer_script  # noqa: E402


class PlacerRoutingTests(unittest.TestCase):
    def test_dabble_does_not_fall_through_to_underdog(self):
        self.assertEqual(placer_script("dabble"), "place_dabble.py")
        self.assertEqual(placer_script("prizepicks"), "place_prizepicks.py")
        self.assertEqual(placer_script("underdog"), "place_underdog.py")
        with self.assertRaises(ValueError):
            placer_script("chalkboard")


class DabbleAndroidHelperTests(unittest.TestCase):
    def test_side_labels_match_the_app(self):
        self.assertEqual(dabble_side_label("OVER"), "More")
        self.assertEqual(dabble_side_label("UNDER"), "Less")

    def test_android_version_floor(self):
        self.assertEqual(parse_android_release("9"), 9.0)
        self.assertEqual(parse_android_release("14"), 14.0)
        self.assertIsNone(parse_android_release(""))
        self.assertLess(parse_android_release("6.0.1") or 0, 7.0)

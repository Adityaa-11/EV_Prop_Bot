"""Tests for feed-health / dry-spell ops alert helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from automation.ops_health import (
    dry_spell_should_alert,
    platform_play_counts,
    should_send_alert,
)


class OpsHealthTests(unittest.TestCase):
    def test_should_send_alert_respects_cooldown(self):
        now = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
        prior = {"sent_at": (now - timedelta(hours=2)).isoformat()}
        self.assertFalse(should_send_alert(prior, now=now, cooldown_hours=6))
        prior_old = {"sent_at": (now - timedelta(hours=7)).isoformat()}
        self.assertTrue(should_send_alert(prior_old, now=now, cooldown_hours=6))

    def test_legacy_date_key_still_suppresses_same_day(self):
        now = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
        prior = {"date": "2026-09-10", "title": "old"}
        self.assertFalse(should_send_alert(prior, now=now, cooldown_hours=6))

    def test_platform_play_counts(self):
        plays = [
            {"prop": {"platform": "underdog"}},
            {"prop": {"platform": "underdog"}},
            {"prop": {"platform": "prizepicks"}},
        ]
        self.assertEqual(
            platform_play_counts(plays),
            {"underdog": 2, "prizepicks": 1},
        )

    def test_dry_spell_triggers_after_threshold(self):
        now = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
        last = (now - timedelta(hours=40)).isoformat()
        should_alert, elapsed = dry_spell_should_alert(
            last_entry_created_at=last,
            dry_spell_hours=36,
            prior_alert=None,
            now=now,
            cooldown_hours=12,
        )
        self.assertTrue(should_alert)
        self.assertAlmostEqual(elapsed or 0, 40.0, places=1)

    def test_dry_spell_skips_inside_threshold(self):
        now = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
        last = (now - timedelta(hours=10)).isoformat()
        should_alert, elapsed = dry_spell_should_alert(
            last_entry_created_at=last,
            dry_spell_hours=36,
            prior_alert=None,
            now=now,
            cooldown_hours=12,
        )
        self.assertFalse(should_alert)
        self.assertAlmostEqual(elapsed or 0, 10.0, places=1)


if __name__ == "__main__":
    unittest.main()

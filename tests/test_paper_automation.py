"""Tests for paper scheduler, delivery, settlement, and leases."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from automation.delivery import format_paper_slip
from automation.paper import PaperPolicy, build_paper_entries
from automation.scheduler import PaperScheduler
from automation.settlement import evaluate_leg, settle_espn_entries, settle_mlb_entries
from storage import PipelineStore


def paper_play(candidate_id, player, event_id, probability, books, dispersion, game_time):
    return {
        "candidate_id": candidate_id,
        "prop": {
            "platform": "prizepicks",
            "sport": "MLB",
            "player_name": player,
            "stat_type": "Hits",
            "market_key": "batter_hits",
            "event_id": event_id,
            "line": 0.5,
            "game_time": game_time,
        },
        "recommended_play": "OVER",
        "win_probability": probability,
        "consensus": {"book_count": books, "dispersion": dispersion},
        "sharp_odds": {"over_probability": probability, "under_probability": 100 - probability},
    }


class LeaseTests(unittest.TestCase):
    def test_lease_blocks_second_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "lease.db"))
            self.assertTrue(store.acquire_lease("paper_scheduler", owner="a", ttl_seconds=60))
            self.assertFalse(store.acquire_lease("paper_scheduler", owner="b", ttl_seconds=60))
            store.release_lease("paper_scheduler", owner="a")
            self.assertTrue(store.acquire_lease("paper_scheduler", owner="b", ttl_seconds=60))


class DeliveryFormatTests(unittest.TestCase):
    def test_slip_is_labeled_paper_only(self):
        payload = format_paper_slip(
            {
                "id": "paper-1",
                "platform": "prizepicks",
                "sport": "MLB",
                "tier": "excellent",
                "stake": 10,
                "potential_payout": 30,
                "expected_roi": 12.5,
                "lock_time": "2026-07-12T20:00:00+00:00",
                "legs": [
                    {
                        "player_name": "Example",
                        "side": "OVER",
                        "line": 1.5,
                        "stat_type": "Hits",
                        "win_probability": 60,
                        "book_count": 3,
                    }
                ],
            }
        )
        description = payload["embeds"][0]["description"]
        self.assertIn("PAPER — NO REAL WAGER", description)
        self.assertIn("Version: **V3**", description)
        self.assertIn("paper-1", description)


class DabbleDeliveryTests(unittest.TestCase):
    def test_dabble_webhook_does_not_fall_through(self):
        from automation.delivery import webhook_for_platform

        with patch.dict(
            os.environ,
            {
                "DISCORD_WEBHOOK_DABBLE": "",
                "DISCORD_WEBHOOK_UNDERDOG": "https://discord.com/api/webhooks/ud",
                "DISCORD_WEBHOOK_PRIZEPICKS": "https://discord.com/api/webhooks/pp",
            },
            clear=False,
        ):
            self.assertIsNone(webhook_for_platform("dabble"))

    def test_dabble_slip_is_a_phone_tap_card(self):
        payload = format_paper_slip(
            {
                "id": "paper-dabble-1",
                "platform": "dabble",
                "sport": "NFL",
                "tier": "excellent",
                "stake": 5,
                "potential_payout": 15,
                "expected_roi": 12.5,
                "lock_time": "2026-10-11T17:00:00+00:00",
                "legs": [
                    {
                        "player_name": "Geno Smith",
                        "side": "OVER",
                        "line": 1.5,
                        "stat_type": "Pass TDs",
                        "win_probability": 60,
                        "book_count": 4,
                    },
                    {
                        "player_name": "Jordan Love",
                        "side": "UNDER",
                        "line": 245.5,
                        "stat_type": "Pass Yards",
                        "win_probability": 59,
                        "book_count": 3,
                    },
                ],
            }
        )
        description = payload["embeds"][0]["description"]
        self.assertIn("PAPER — NO REAL WAGER", description)
        self.assertIn("All-In 2-pick", description)
        self.assertIn("More 1.5", description)
        self.assertIn("Less 245.5", description)
        self.assertIn("GPS shows Georgia", description)


class SettlementMathTests(unittest.TestCase):
    def test_evaluate_leg_over_under_push(self):
        self.assertEqual(evaluate_leg("OVER", 1.5, 2), "win")
        self.assertEqual(evaluate_leg("OVER", 1.5, 1), "loss")
        self.assertEqual(evaluate_leg("UNDER", 1.5, 1), "win")
        self.assertEqual(evaluate_leg("OVER", 1.5, 1.5), "push")


class SchedulerHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_scheduler_does_not_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "sched.db"))
            tick = AsyncMock(return_value={"created_count": 0, "status": "waiting"})
            settle = AsyncMock(return_value={"settled": 0, "pending": 0})
            deliver = AsyncMock(return_value={"sent": 0, "failed": 0, "pending": 0})
            scheduler = PaperScheduler(
                store=store,
                tick_sport=tick,
                settle_open=settle,
                deliver_pending=deliver,
                sports=["mlb"],
                heartbeat_seconds=300,
                enabled=False,
            )
            await scheduler.start()
            self.assertIsNone(scheduler._task)
            status = store.get_state("paper_scheduler")
            self.assertEqual(status["status"], "disabled")

    async def test_heartbeat_runs_tick_delivery_and_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "sched.db"))
            tick = AsyncMock(return_value={"created_count": 1, "status": "created"})
            settle = AsyncMock(return_value={"settled": 0, "pending": 0})
            deliver = AsyncMock(return_value={"sent": 1, "failed": 0, "pending": 1})
            scheduler = PaperScheduler(
                store=store,
                tick_sport=tick,
                settle_open=settle,
                deliver_pending=deliver,
                sports=["mlb"],
                heartbeat_seconds=300,
                enabled=True,
            )
            result = await scheduler.heartbeat_once()
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["created_count"], 1)
            tick.assert_awaited_once_with("mlb")
            deliver.assert_awaited_once()
            settle.assert_awaited_once()

    async def test_after_cycle_hook_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "after.db"))
            seen = {}

            async def after(result):
                seen["ok"] = True
                seen["created"] = result.get("created_count")

            tick = AsyncMock(
                return_value={
                    "status": "waiting",
                    "message": "no_events_within_scan_horizon",
                    "created_count": 0,
                }
            )
            settle = AsyncMock(return_value={"settled": 0, "pending": 0})
            deliver = AsyncMock(return_value={"sent": 0, "failed": 0, "pending": 0})
            scheduler = PaperScheduler(
                store=store,
                tick_sport=tick,
                settle_open=settle,
                deliver_pending=deliver,
                sports=["mlb"],
                enabled=True,
                after_cycle=after,
            )
            result = await scheduler.heartbeat_once()
            self.assertEqual(result["status"], "ok")
            self.assertTrue(seen.get("ok"))
            self.assertEqual(seen.get("created"), 0)


class MlbSettlementPendingTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_lock_stays_pending(self):
        now = datetime.now(timezone.utc)
        entries = [
            {
                "id": "paper-recent",
                "status": "open",
                "sport": "MLB",
                "stake": 10,
                "potential_payout": 30,
                "lock_time": (now - timedelta(minutes=10)).isoformat(),
                "legs": [
                    {
                        "player_name": "Shohei Ohtani",
                        "market_key": "batter_hits",
                        "side": "OVER",
                        "entry_line": 0.5,
                    }
                ],
            }
        ]
        actions = await settle_mlb_entries(object(), entries, now=now)
        self.assertEqual(actions, [])


class DeliveryPersistenceTests(unittest.TestCase):
    def test_mark_delivery_is_idempotent_for_sent_status(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "delivery.db"))
            entry = {
                "id": "paper-delivery",
                "fingerprint": "fp-delivery",
                "platform": "prizepicks",
                "sport": "MLB",
                "tier": "excellent",
                "stake": 10,
                "expected_roi": 12,
                "potential_payout": 30,
                "lock_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "legs": [],
            }
            store.create_paper_entry(entry)
            store.mark_delivery("paper-delivery", status="sent")
            store.mark_delivery("paper-delivery", status="sent")
            listed = store.list_paper_entries()[0]
            self.assertEqual(listed["delivery_status"], "sent")
            self.assertEqual(listed["delivery_attempts"], 2)
            self.assertEqual(store.list_pending_delivery(), [])


class StrongNearLockTests(unittest.TestCase):
    def test_strong_entry_created_near_lock(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        plays = [
            paper_play("one", "Player One", "event-1", 60, 2, 4, (now + timedelta(minutes=20)).isoformat()),
            paper_play("two", "Player Two", "event-2", 60, 2, 4, (now + timedelta(minutes=20)).isoformat()),
        ]
        result = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(
                min_leg_win=56,
                min_leg_books=2,
                max_leg_dispersion=5,
                require_line_stability=True,
                excellent_roi=10,
                strong_roi=5,
            ),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["tier"], "strong")


class EspnSettlementTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_nfl_lock_stays_pending(self):
        now = datetime.now(timezone.utc)
        entries = [
            {
                "id": "paper-nfl-recent",
                "status": "open",
                "sport": "NFL",
                "stake": 10,
                "potential_payout": 30,
                "lock_time": (now - timedelta(hours=1)).isoformat(),
                "legs": [
                    {
                        "player_name": "Joe Burrow",
                        "market_key": "player_pass_tds",
                        "side": "OVER",
                        "entry_line": 1.5,
                    }
                ],
            }
        ]
        actions = await settle_espn_entries(object(), entries, now=now)
        self.assertEqual(actions, [])

    async def test_nfl_two_leg_slip_grades_from_espn_boxscore(self):
        now = datetime(2026, 10, 5, 1, tzinfo=timezone.utc)
        lock = datetime(2026, 10, 4, 17, tzinfo=timezone.utc)
        scoreboard = {
            "events": [
                {
                    "id": "401",
                    "date": "2026-10-04T17:00:00Z",
                    "competitions": [{"status": {"type": {"completed": True, "name": "STATUS_FINAL"}}}],
                }
            ]
        }
        summary = {
            "boxscore": {
                "players": [
                    {
                        "statistics": [
                            {
                                "name": "passing",
                                "keys": ["passingTouchdowns", "passingYards"],
                                "athletes": [
                                    {
                                        "athlete": {"displayName": "Joe Burrow"},
                                        "stats": ["1", "428"],
                                    }
                                ],
                            },
                            {
                                "name": "receiving",
                                "keys": ["receptions", "receivingYards"],
                                "athletes": [
                                    {
                                        "athlete": {"displayName": "Jeremiyah Love"},
                                        "stats": ["1", "12"],
                                    }
                                ],
                            },
                        ]
                    }
                ]
            }
        }

        async def fake_fetch(session, url):
            if "scoreboard" in url:
                return scoreboard
            if "summary" in url:
                return summary
            return None

        entries = [
            {
                "id": "paper-nfl-hit",
                "status": "open",
                "sport": "NFL",
                "stake": 10,
                "potential_payout": 30,
                "lock_time": lock.isoformat(),
                "legs": [
                    {
                        "player_name": "Jalon Daniels",
                        "market_key": "player_pass_tds",
                        "side": "OVER",
                        "entry_line": 0.5,
                    },
                    {
                        "player_name": "Jeremiyah Love",
                        "market_key": "player_receptions",
                        "side": "UNDER",
                        "entry_line": 3.5,
                    },
                ],
            },
            {
                "id": "paper-nfl-miss",
                "status": "open",
                "sport": "NFL",
                "stake": 10,
                "potential_payout": 30,
                "lock_time": lock.isoformat(),
                "legs": [
                    {
                        "player_name": "Joe Burrow",
                        "market_key": "player_pass_tds",
                        "side": "OVER",
                        "entry_line": 1.5,
                    },
                    {
                        "player_name": "Jeremiyah Love",
                        "market_key": "player_receptions",
                        "side": "UNDER",
                        "entry_line": 3.5,
                    },
                ],
            },
        ]
        # First slip needs Daniels O0.5 — add him to the same boxscore via extra fetch data.
        summary["boxscore"]["players"][0]["statistics"][0]["athletes"].append(
            {"athlete": {"displayName": "Jalon Daniels"}, "stats": ["1", "148"]}
        )

        with patch("automation.settlement._fetch_json", new=fake_fetch):
            actions = await settle_espn_entries(object(), entries, now=now)

        by_id = {action["entry_id"]: action for action in actions}
        self.assertEqual(by_id["paper-nfl-hit"]["status"], "settled")
        self.assertEqual(by_id["paper-nfl-hit"]["result"], "win")
        self.assertEqual(by_id["paper-nfl-hit"]["payout"], 30)
        self.assertEqual(by_id["paper-nfl-hit"]["provenance"], "espn_boxscore")
        self.assertEqual(by_id["paper-nfl-miss"]["result"], "loss")
        self.assertEqual(by_id["paper-nfl-miss"]["payout"], 0)


if __name__ == "__main__":
    unittest.main()

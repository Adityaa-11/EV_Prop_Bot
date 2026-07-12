"""Tests for paper scheduler, delivery, settlement, and leases."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from automation.delivery import format_paper_slip
from automation.paper import PaperPolicy, build_paper_entries
from automation.scheduler import PaperScheduler
from automation.settlement import evaluate_leg, settle_mlb_entries
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
        self.assertIn("paper-1", description)


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
            policy=PaperPolicy(),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["tier"], "strong")


if __name__ == "__main__":
    unittest.main()

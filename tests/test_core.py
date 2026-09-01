import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from automation import PaperPolicy, build_paper_entries, void_stale_open_entries
from api import (
    DataCache,
    Prop,
    build_consensus,
    calculate_entry_ev,
    canonical_market_key,
    fetch_dfs_props_from_odds_api,
)
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


class CoreScoringTests(unittest.TestCase):
    def test_alternate_market_normalization(self):
        self.assertEqual(canonical_market_key("batter_hits_alternate"), "batter_hits")
        self.assertEqual(canonical_market_key("batter_hits"), "batter_hits")

    def test_consensus_uses_only_exact_line_and_event(self):
        prop = Prop(
            id="prop-1",
            player_name="Example Player",
            team="AAA",
            sport="MLB",
            stat_type="Hits",
            platform="prizepicks",
            line=0.5,
            event_id="event-1",
            market_key="batter_hits",
        )
        rows = [
            {
                "player": "Example Player",
                "line": 0.5,
                "over_odds": -130,
                "under_odds": 100,
                "bookmaker": "draftkings",
                "event_id": "event-1",
            },
            {
                "player": "Example Player",
                "line": 0.5,
                "over_odds": -120,
                "under_odds": -105,
                "bookmaker": "fanduel",
                "event_id": "event-1",
            },
            {
                "player": "Example Player",
                "line": 1.5,
                "over_odds": 200,
                "under_odds": -250,
                "bookmaker": "bovada",
                "event_id": "event-1",
            },
            {
                "player": "Example Player",
                "line": 0.5,
                "over_odds": 200,
                "under_odds": -250,
                "bookmaker": "bovada",
                "event_id": "event-2",
            },
        ]

        consensus = build_consensus(prop, rows)

        self.assertIsNotNone(consensus)
        self.assertEqual(consensus["book_count"], 2)
        self.assertEqual(len(consensus["exact_line_odds"]), 2)
        self.assertEqual(consensus["recommended_play"], "OVER")

    def test_power_entry_break_even(self):
        result = calculate_entry_ev([57.735, 57.735], {2: 3.0})
        self.assertAlmostEqual(result["expected_roi_percentage"], 0, delta=0.1)


class CacheTests(unittest.TestCase):
    def test_expired_data_not_served_by_default(self):
        cache = DataCache(default_ttl=1)
        cache.set("key", {"value": 1})
        data, timestamp, ttl = cache.cache["key"]
        cache.cache["key"] = (data, timestamp - 2, ttl)

        self.assertEqual(cache.get("key"), (None, False))
        self.assertEqual(cache.get("key", allow_stale=True), ({"value": 1}, False))


class PaperEntryTests(unittest.TestCase):
    def test_excellent_entry_is_created_after_stable_observations(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        game_time = (now + timedelta(hours=2)).isoformat()
        plays = [
            paper_play("one", "Player One", "event-1", 62, 3, 2, game_time),
            paper_play("two", "Player Two", "event-2", 62, 3, 2, game_time),
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
        self.assertEqual(result["entries"][0]["tier"], "excellent")
        self.assertGreater(result["entries"][0]["expected_roi"], 10)

    def test_strong_entry_waits_until_near_lock(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        plays = [
            paper_play("one", "Player One", "event-1", 60, 2, 4, (now + timedelta(hours=2)).isoformat()),
            paper_play("two", "Player Two", "event-2", 60, 2, 4, (now + timedelta(hours=2)).isoformat()),
        ]
        result = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["reason"], "no_qualifying_entry")

    def test_risk_capacity_never_forces_an_entry(self):
        result = build_paper_entries(
            [],
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(),
            daily_staked=30,
            open_entries=0,
        )
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["reason"], "risk_capacity_reached")


class SettlementTests(unittest.TestCase):
    def test_void_stale_non_mlb_entry(self):
        now = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
        lock_time = (now - timedelta(hours=24)).isoformat()
        entries = [
            {
                "id": "paper-wnba",
                "status": "open",
                "sport": "WNBA",
                "stake": 10,
                "lock_time": lock_time,
            }
        ]
        actions = void_stale_open_entries(entries, now=now, stale_hours=12)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["result"], "void")
        self.assertEqual(actions[0]["payout"], 10)

    def test_stale_void_frees_capacity_for_new_entries(self):
        now = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
        lock_time = (now - timedelta(hours=24)).isoformat()
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            for index in range(4):
                store.create_paper_entry(
                    {
                        "id": f"paper-{index}",
                        "fingerprint": f"fp-{index}",
                        "platform": "underdog",
                        "sport": "WNBA",
                        "tier": "excellent",
                        "stake": 10,
                        "expected_roi": 12,
                        "potential_payout": 30,
                        "lock_time": lock_time,
                        "created_at": lock_time,
                        "legs": [],
                    }
                )
            self.assertEqual(store.paper_summary(200)["open_entries"], 4)
            for action in void_stale_open_entries(store.list_open_paper_entries(), now=now, stale_hours=12):
                store.apply_settlement(
                    action["entry_id"],
                    result=action["result"],
                    payout=action["payout"],
                    provenance=action.get("provenance"),
                )
            self.assertEqual(store.paper_summary(200)["open_entries"], 0)
            game_time = (now + timedelta(hours=2)).isoformat()
            plays = [
                paper_play("one", "Player One", "event-1", 62, 3, 2, game_time),
                paper_play("two", "Player Two", "event-2", 62, 3, 2, game_time),
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


class ExecutionQueueTests(unittest.TestCase):
    def _live_entry(self, entry_id: str, fingerprint: str) -> dict:
        lock_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        return {
            "id": entry_id,
            "fingerprint": fingerprint,
            "platform": "prizepicks",
            "sport": "NFL",
            "tier": "excellent",
            "stake": 5,
            "expected_roi": 12,
            "potential_payout": 15,
            "lock_time": lock_time,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "legs": [
                {
                    "candidate_id": f"candidate-{entry_id}",
                    "player_name": "Example Player",
                    "stat_type": "Pass Yds",
                    "event_id": "event-1",
                    "market_key": "player_pass_yds",
                    "side": "OVER",
                    "line": 249.5,
                    "entry_line": 249.5,
                    "win_probability": 62,
                },
                {
                    "candidate_id": f"candidate-{entry_id}-2",
                    "player_name": "Other Player",
                    "stat_type": "Rec Yds",
                    "event_id": "event-2",
                    "market_key": "player_rec_yds",
                    "side": "UNDER",
                    "line": 54.5,
                    "entry_line": 54.5,
                    "win_probability": 61,
                },
            ],
        }

    def test_claim_is_idempotent_for_same_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            self.assertTrue(
                store.create_paper_entry(self._live_entry("live-1", "fp-live-1"), execution_mode="live")
            )
            pending = store.list_pending_execution_entries()
            self.assertEqual(len(pending), 1)
            first = store.claim_execution_entry("live-1", worker_id="worker-a")
            second = store.claim_execution_entry("live-1", worker_id="worker-a")
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(store.list_pending_execution_entries(), [])

    def test_complete_execution_marks_submitted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            store.create_paper_entry(self._live_entry("live-2", "fp-live-2"), execution_mode="live")
            store.claim_execution_entry("live-2", worker_id="worker-a")
            self.assertTrue(
                store.complete_execution_entry(
                    "live-2",
                    status="submitted",
                    external_ticket_id="ticket-123",
                )
            )
            entry = store.list_paper_entries()[0]
            self.assertEqual(entry["execution_status"], "submitted")
            self.assertEqual(entry["external_ticket_id"], "ticket-123")

    def test_create_paper_entry_duplicate_fingerprint_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            payload = self._live_entry("live-dup", "fp-dup")
            self.assertTrue(store.create_paper_entry(payload, execution_mode="live"))
            self.assertFalse(store.create_paper_entry(payload, execution_mode="live"))
            self.assertEqual(len(store.list_pending_execution_entries()), 1)


class StorageTests(unittest.TestCase):
    def test_run_and_outcome_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            run_id = store.save_run(
                "ev",
                "mlb",
                "ok",
                {"count": 1, "plays": [{"candidate_id": "candidate-1"}]},
                {"props": 10},
            )
            latest = store.latest_run("ev", "mlb")
            self.assertEqual(latest["id"], run_id)
            self.assertEqual(latest["payload"]["count"], 1)

            store.record_outcome(
                "candidate-1",
                status="settled",
                result="win",
                stake=2,
                payout=6,
                notes="fixture",
            )

    def test_paper_entry_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            created_at = datetime.now(timezone.utc).isoformat()
            entry = {
                "id": "paper-1",
                "fingerprint": "fingerprint-1",
                "platform": "prizepicks",
                "sport": "MLB",
                "tier": "excellent",
                "stake": 10,
                "expected_roi": 12,
                "potential_payout": 30,
                "lock_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "created_at": created_at,
                "legs": [],
            }
            self.assertTrue(store.create_paper_entry(entry))
            self.assertFalse(store.create_paper_entry(entry))
            self.assertEqual(store.paper_summary(200)["exposure"], 10)
            self.assertTrue(store.settle_paper_entry("paper-1", result="win", payout=30))
            summary = store.paper_summary(200)
            self.assertEqual(summary["bankroll"], 220)
            self.assertEqual(summary["wins"], 1)

    def test_over_line_drop_records_negative_clv(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            entry = {
                "id": "paper-clv",
                "fingerprint": "fingerprint-clv",
                "platform": "prizepicks",
                "sport": "MLB",
                "tier": "excellent",
                "stake": 10,
                "expected_roi": 12,
                "potential_payout": 30,
                "lock_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "legs": [
                    {
                        "candidate_id": "candidate-entry",
                        "player_name": "Example Player",
                        "stat_type": "Points",
                        "event_id": "event-1",
                        "market_key": "player_points",
                        "side": "OVER",
                        "line": 16.5,
                        "entry_line": 16.5,
                        "win_probability": 60,
                    }
                ],
            }
            store.create_paper_entry(entry)
            store.update_open_entry_closing_lines(
                [
                    {
                        "prop": {
                            "platform": "prizepicks",
                            "player_name": "Example Player",
                            "event_id": "event-1",
                            "market_key": "player_points",
                            "line": 14.5,
                        },
                        "sharp_odds": {
                            "over_probability": 65,
                            "under_probability": 35,
                        },
                    }
                ]
            )
            leg = store.list_paper_entries()[0]["legs"][0]
            self.assertEqual(leg["closing_line"], 14.5)
            self.assertEqual(leg["line_clv"], -2.0)
            self.assertIsNone(leg["probability_clv"])


class PrizePicksIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovers_supported_markets_before_odds_request(self):
        event = {
            "id": "event-1",
            "commence_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "home_team": "Home",
            "away_team": "Away",
        }
        discovery = {
            "bookmakers": [
                {
                    "key": "prizepicks",
                    "markets": [{"key": "batter_hits"}],
                }
            ]
        }
        odds_payload = {
            **event,
            "bookmakers": [
                {
                    "key": "prizepicks",
                    "markets": [
                        {
                            "key": "batter_hits",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Example Batter",
                                    "point": 0.5,
                                    "price": -119,
                                },
                                {
                                    "name": "Under",
                                    "description": "Example Batter",
                                    "point": 0.5,
                                    "price": -111,
                                },
                            ],
                        }
                    ],
                }
            ],
        }

        async def fake_get(_session, url, params=None, timeout=20):
            if url.endswith("/events"):
                return 200, [event]
            if url.endswith("/markets"):
                return 200, discovery
            self.assertEqual(params["markets"], "batter_hits")
            return 200, odds_payload

        with (
            patch("api.get_odds_api_key", return_value="test-key"),
            patch("api._odds_api_get", new=AsyncMock(side_effect=fake_get)),
        ):
            props = await fetch_dfs_props_from_odds_api(
                object(),
                "mlb",
                "prizepicks",
            )

        self.assertEqual(len(props), 1)
        self.assertEqual(props[0].market_key, "batter_hits")
        self.assertEqual(props[0].event_id, "event-1")


if __name__ == "__main__":
    unittest.main()


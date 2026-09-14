import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from automation import PaperPolicy, build_paper_entries, compute_paper_capacity, void_stale_open_entries
from api import (
    DataCache,
    Prop,
    _parse_prizepicks_board,
    _paper_version_for_created_at,
    _prizepicks_payload_blocked,
    build_consensus,
    calculate_entry_ev,
    canonical_market_key,
    fetch_dfs_props_from_odds_api,
    fetch_prizepicks,
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

    def test_mlb_market_priority_fetches_batter_props_before_cap(self):
        from api import DFS_MARKETS_BY_SPORT, SHARP_MARKET_LIMIT

        mlb = DFS_MARKETS_BY_SPORT["mlb"]
        capped = mlb[:SHARP_MARKET_LIMIT]
        self.assertIn("batter_total_bases", capped)
        self.assertIn("batter_hits", capped)
        self.assertLess(mlb.index("batter_total_bases"), mlb.index("pitcher_strikeouts"))

    def test_paper_version_eras(self):
        self.assertEqual(_paper_version_for_created_at("2026-09-03T12:00:00+00:00"), "v1")
        self.assertEqual(_paper_version_for_created_at("2026-09-04T00:00:00+00:00"), "v2")
        self.assertEqual(_paper_version_for_created_at("2026-09-10T19:57:54+00:00"), "v2")
        self.assertEqual(_paper_version_for_created_at("2026-09-11T00:00:00+00:00"), "v3")
        self.assertEqual(_paper_version_for_created_at("2026-09-12T15:00:00+00:00"), "v3")

    def test_scan_budget_reset_clears_counters(self):
        from api import reset_paper_scan_budget, _paper_scan_budget, store as api_store
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).date().isoformat()
        api_store.set_state("paper_scan_budget", {"date": today, "count": 200})
        result = reset_paper_scan_budget(reason="unit_test")
        self.assertTrue(result["reset"])
        budget = _paper_scan_budget()
        self.assertEqual(budget["scans_today"], 0)
        self.assertFalse(budget["cap_reached"])

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
    def test_spray_52_percent_legs_are_rejected(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        game_time = (now + timedelta(hours=2)).isoformat()
        plays = [
            paper_play("one", "Player One", "event-1", 52, 2, 6, game_time),
            paper_play("two", "Player Two", "event-2", 52, 2, 6, game_time),
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

    def test_excellent_entry_fires_on_first_scan_without_stability(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        game_time = (now + timedelta(hours=2)).isoformat()
        plays = [
            paper_play("one", "Player One", "event-1", 62, 3, 2, game_time),
            paper_play("two", "Player Two", "event-2", 62, 3, 2, game_time),
        ]
        result = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": False},
            policy=PaperPolicy(),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["tier"], "excellent")
        # 62/62 @ 3x ≈ 15.3% ROI; must clear the V3.1 ~1% gate.
        self.assertGreaterEqual(result["entries"][0]["expected_roi"], 1)

    def test_v31_allows_break_even_pairs_that_old_8pct_gate_blocked(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        game_time = (now + timedelta(hours=2)).isoformat()
        plays = [
            paper_play("one", "Player One", "event-1", 58, 3, 2, game_time),
            paper_play("two", "Player Two", "event-2", 58, 3, 2, game_time),
        ]
        blocked = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(excellent_roi=8, strong_roi=8),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        allowed = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(blocked["entries"], [])
        self.assertEqual(len(allowed["entries"]), 1)
        self.assertGreaterEqual(allowed["entries"][0]["expected_roi"], 0.9)
        self.assertLess(allowed["entries"][0]["expected_roi"], 8)

    def test_prefers_higher_roi_and_excellent_before_weaker_slips(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        lock = (now + timedelta(minutes=20)).isoformat()
        plays = [
            # Weak strong-tier combo (~5.2% ROI at 59/59) if strong_roi were 5.
            paper_play("w1", "Weak One", "event-1", 59, 3, 2, lock),
            paper_play("w2", "Weak Two", "event-2", 59, 3, 2, lock),
            # Stronger excellent combo.
            paper_play("s1", "Strong One", "event-3", 65, 3, 2, lock),
            paper_play("s2", "Strong Two", "event-4", 65, 3, 2, lock),
        ]
        result = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(
                min_leg_win=55,
                strong_roi=5,
                excellent_roi=8,
                max_entries_per_lock_time=1,
            ),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(len(result["entries"]), 1)
        entry = result["entries"][0]
        self.assertEqual(entry["tier"], "excellent")
        names = {leg["player_name"] for leg in entry["legs"]}
        self.assertEqual(names, {"Strong One", "Strong Two"})

    def test_caps_entries_sharing_the_same_lock_time(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        lock = (now + timedelta(hours=2)).isoformat()
        plays = [
            paper_play("a1", "A One", "event-1", 65, 3, 2, lock),
            paper_play("a2", "A Two", "event-2", 65, 3, 2, lock),
            paper_play("b1", "B One", "event-3", 64, 3, 2, lock),
            paper_play("b2", "B Two", "event-4", 64, 3, 2, lock),
            paper_play("c1", "C One", "event-5", 63, 3, 2, lock),
            paper_play("c2", "C Two", "event-6", 63, 3, 2, lock),
        ]
        result = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(max_entries_per_lock_time=2),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(len(result["entries"]), 2)
        rois = [entry["expected_roi"] for entry in result["entries"]]
        self.assertEqual(rois, sorted(rois, reverse=True))


    def test_underdog_juiced_side_scales_payout_and_roi(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        game_time = (now + timedelta(hours=2)).isoformat()
        fair = paper_play("one", "Player One", "event-1", 65, 3, 2, game_time)
        juiced = paper_play("two", "Player Two", "event-2", 65, 3, 2, game_time)
        fair["prop"]["platform"] = "underdog"
        juiced["prop"]["platform"] = "underdog"
        juiced["recommended_play"] = "UNDER"
        juiced["prop"]["under_payout_multiplier"] = 0.9
        juiced["prop"]["over_payout_multiplier"] = 1.15

        flat = build_paper_entries(
            [
                paper_play("one", "Player One", "event-1", 65, 3, 2, game_time)
                | {"prop": {**fair["prop"], "under_payout_multiplier": 1.0, "over_payout_multiplier": 1.0}},
                paper_play("two", "Player Two", "event-2", 65, 3, 2, game_time)
                | {
                    "prop": {
                        **juiced["prop"],
                        "under_payout_multiplier": 1.0,
                        "over_payout_multiplier": 1.0,
                    },
                    "recommended_play": "UNDER",
                },
            ],
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        result = build_paper_entries(
            [fair, juiced],
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(len(flat["entries"]), 1)
        entry = result["entries"][0]
        # Base 3x * 1.0 * 0.9 = 2.7x payout.
        self.assertAlmostEqual(entry["payout_multiplier"], 2.7, places=3)
        self.assertAlmostEqual(entry["potential_payout"], 27.0, places=2)
        self.assertLess(entry["expected_roi"], flat["entries"][0]["expected_roi"])
        under_leg = next(leg for leg in entry["legs"] if leg["side"] == "UNDER")
        self.assertEqual(under_leg["payout_multiplier"], 0.9)

    def test_optional_stability_flag_still_blocks_unstable_lines(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        game_time = (now + timedelta(hours=2)).isoformat()
        plays = [
            paper_play("one", "Player One", "event-1", 62, 3, 2, game_time),
            paper_play("two", "Player Two", "event-2", 62, 3, 2, game_time),
        ]
        result = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": False},
            policy=PaperPolicy(require_line_stability=True),
            daily_staked=0,
            open_entries=0,
            now=now,
        )
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["reason"], "no_qualifying_entry")

    def test_sub_minimum_win_probability_is_rejected(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        plays = [
            paper_play("one", "Player One", "event-1", 51, 2, 4, (now + timedelta(hours=2)).isoformat()),
            paper_play("two", "Player Two", "event-2", 52, 2, 4, (now + timedelta(hours=2)).isoformat()),
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

    def test_far_entries_use_separate_open_bucket(self):
        now = datetime(2026, 7, 12, 16, tzinfo=timezone.utc)
        far_time = (now + timedelta(hours=72)).isoformat()
        plays = [
            paper_play("one", "Player One", "event-1", 62, 3, 2, far_time),
            paper_play("two", "Player Two", "event-2", 62, 3, 2, far_time),
        ]
        result = build_paper_entries(
            plays,
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(max_open_entries=20, max_far_open_entries=5),
            daily_staked=0,
            open_near=20,
            open_far=0,
            now=now,
        )
        self.assertEqual(len(result["entries"]), 1)

    def test_scan_blocked_when_near_full_even_with_far_room(self):
        capacity = compute_paper_capacity(
            PaperPolicy(max_open_entries=20, max_far_open_entries=5),
            daily_staked=0,
            daily_profit=0,
            open_near=20,
            open_far=0,
        )
        self.assertFalse(capacity["can_scan"])
        self.assertTrue(capacity["can_create"])
        self.assertEqual(capacity["reason"], "max_near_open_entries_reached")

    def test_scan_blocked_when_daily_stake_cap_hit(self):
        capacity = compute_paper_capacity(
            PaperPolicy(daily_stake_cap=200),
            daily_staked=200,
            daily_profit=0,
            open_near=0,
            open_far=0,
        )
        self.assertFalse(capacity["can_scan"])
        self.assertEqual(capacity["reason"], "daily_stake_cap_reached")

    def test_risk_capacity_never_forces_an_entry(self):
        result = build_paper_entries(
            [],
            stability_for=lambda _: {"stable": True},
            policy=PaperPolicy(daily_stake_cap=30),
            daily_staked=30,
            open_entries=0,
        )
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["reason"], "daily_stake_cap_reached")


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
            self.assertEqual(entry["status"], "open")

    def test_complete_execution_requires_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            store.create_paper_entry(self._live_entry("live-pending", "fp-pending"), execution_mode="live")
            self.assertFalse(
                store.complete_execution_entry("live-pending", status="submitted", external_ticket_id="x")
            )

    def test_failed_execution_voids_entry_to_free_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            store.create_paper_entry(self._live_entry("live-fail", "fp-fail"), execution_mode="live")
            store.claim_execution_entry("live-fail", worker_id="worker-a")
            self.assertTrue(store.complete_execution_entry("live-fail", status="failed", error="captcha"))
            entry = store.list_paper_entries()[0]
            self.assertEqual(entry["execution_status"], "failed")
            self.assertEqual(entry["status"], "settled")
            self.assertEqual(entry["result"], "void")
            self.assertEqual(store.paper_summary(200)["open_entries"], 0)

    def test_claim_rejects_second_worker_while_lease_active(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            store.create_paper_entry(self._live_entry("live-lease", "fp-lease"), execution_mode="live")
            self.assertIsNotNone(store.claim_execution_entry("live-lease", worker_id="worker-a", claim_ttl_seconds=900))
            self.assertIsNone(store.claim_execution_entry("live-lease", worker_id="worker-b", claim_ttl_seconds=900))

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

    def test_freeze_backfills_closing_line_from_entry_when_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            entry = {
                "id": "paper-close-fallback",
                "fingerprint": "fingerprint-close-fallback",
                "platform": "underdog",
                "sport": "MLB",
                "tier": "excellent",
                "stake": 10,
                "expected_roi": 12,
                "potential_payout": 30,
                "lock_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "legs": [
                    {
                        "candidate_id": "candidate-fallback",
                        "player_name": "Fallback Player",
                        "stat_type": "Total Bases",
                        "market_key": "batter_total_bases",
                        "side": "UNDER",
                        "line": 1.5,
                        "entry_line": 1.5,
                        "win_probability": 58,
                        "closing_line": None,
                        "line_clv": None,
                    }
                ],
            }
            store.create_paper_entry(entry)
            store.freeze_closing_lines_past_lock()
            leg = store.list_paper_entries()[0]["legs"][0]
            self.assertEqual(leg["closing_line"], 1.5)
            self.assertEqual(leg["line_clv"], 0.0)
            self.assertTrue(leg["closing_frozen"])
            self.assertEqual(leg["closing_source"], "entry_line_fallback")

    def test_backfill_closing_line_from_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(str(Path(directory) / "test.db"))
            lock_time = datetime.now(timezone.utc) + timedelta(hours=2)
            entry = {
                "id": "paper-obs-close",
                "fingerprint": "fingerprint-obs-close",
                "platform": "underdog",
                "sport": "MLB",
                "tier": "excellent",
                "stake": 10,
                "expected_roi": 12,
                "potential_payout": 30,
                "lock_time": lock_time.isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "legs": [
                    {
                        "candidate_id": "candidate-obs",
                        "player_name": "Obs Player",
                        "stat_type": "Hits",
                        "market_key": "batter_hits",
                        "side": "OVER",
                        "line": 0.5,
                        "entry_line": 0.5,
                        "win_probability": 56,
                        "closing_line": None,
                        "line_clv": None,
                    }
                ],
            }
            store.create_paper_entry(entry)
            store.record_candidate_observations(
                [
                    {
                        "candidate_id": "candidate-obs",
                        "recommended_play": "OVER",
                        "win_probability": 57,
                        "prop": {
                            "platform": "underdog",
                            "sport": "MLB",
                            "event_id": "evt",
                            "player_name": "Obs Player",
                            "market_key": "batter_hits",
                            "line": 1.5,
                            "game_time": lock_time.isoformat(),
                        },
                        "consensus": {"book_count": 4, "dispersion": 1},
                        "sharp_odds": {"market": "batter_hits"},
                    }
                ]
            )
            self.assertEqual(store.backfill_closing_lines_from_observations(), 1)
            leg = store.list_paper_entries()[0]["legs"][0]
            self.assertEqual(leg["closing_line"], 1.5)
            self.assertEqual(leg["line_clv"], 1.0)
            self.assertEqual(leg["closing_source"], "candidate_observation")


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


class PrizePicksDirectFeedTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_board_keeps_standard_only(self):
        payload = {
            "data": [
                {
                    "id": "1",
                    "attributes": {
                        "stat_type": "Hits",
                        "line_score": 0.5,
                        "odds_type": "standard",
                        "start_time": "2026-09-10T20:00:00Z",
                        "is_live": False,
                    },
                    "relationships": {"new_player": {"data": {"id": "p1"}}},
                },
                {
                    "id": "2",
                    "attributes": {
                        "stat_type": "Hits",
                        "line_score": 1.5,
                        "odds_type": "demon",
                        "start_time": "2026-09-10T20:00:00Z",
                        "is_live": False,
                    },
                    "relationships": {"new_player": {"data": {"id": "p1"}}},
                },
            ],
            "included": [
                {
                    "id": "p1",
                    "type": "new_player",
                    "attributes": {"display_name": "Sample Batter", "team": "NYY"},
                }
            ],
        }
        props = _parse_prizepicks_board(payload, "mlb")
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0].player_name, "Sample Batter")
        self.assertEqual(props[0].line, 0.5)
        self.assertEqual(props[0].platform, "prizepicks")

    def test_captcha_payload_detected(self):
        self.assertTrue(
            _prizepicks_payload_blocked(
                {"url": "https://geo.captcha-delivery.com/interstitial/?cid=abc"}
            )
        )
        self.assertFalse(_prizepicks_payload_blocked({"data": [], "included": []}))

    async def test_fetch_prizepicks_prefers_partner_api(self):
        board = {
            "data": [
                {
                    "id": "99",
                    "attributes": {
                        "stat_type": "Points",
                        "line_score": 22.5,
                        "odds_type": "standard",
                        "start_time": "2026-10-20T19:00:00Z",
                        "is_live": False,
                    },
                    "relationships": {"new_player": {"data": {"id": "np1"}}},
                }
            ],
            "included": [
                {
                    "id": "np1",
                    "type": "new_player",
                    "attributes": {"display_name": "Jalen Brunson", "team": "NYK"},
                }
            ],
        }

        class FakeResp:
            def __init__(self, status, payload):
                self.status = status
                self._payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def json(self, content_type=None):
                return self._payload

        class FakeSession:
            def get(self, url, headers=None, timeout=None):
                self.last_url = url
                if "partner-api.prizepicks.com" in url:
                    return FakeResp(200, board)
                return FakeResp(403, {"url": "https://geo.captcha-delivery.com/x"})

        odds_fallback = AsyncMock(return_value=[])
        with patch("api.fetch_dfs_props_from_odds_api", new=odds_fallback):
            props = await fetch_prizepicks(FakeSession(), "nba")

        self.assertEqual(len(props), 1)
        self.assertEqual(props[0].player_name, "Jalen Brunson")
        odds_fallback.assert_not_called()

    async def test_fetch_prizepicks_falls_back_when_direct_blocked(self):
        class FakeResp:
            status = 403

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def json(self, content_type=None):
                return {"url": "https://geo.captcha-delivery.com/interstitial/"}

        class FakeSession:
            def get(self, url, headers=None, timeout=None):
                return FakeResp()

        fallback_prop = Prop(
            id="pp_odds",
            player_name="Fallback Player",
            team="AAA",
            sport="MLB",
            stat_type="Hits",
            platform="prizepicks",
            line=0.5,
        )
        with patch(
            "api.fetch_dfs_props_from_odds_api",
            new=AsyncMock(return_value=[fallback_prop]),
        ):
            props = await fetch_prizepicks(FakeSession(), "mlb")

        self.assertEqual(len(props), 1)
        self.assertEqual(props[0].player_name, "Fallback Player")


if __name__ == "__main__":
    unittest.main()


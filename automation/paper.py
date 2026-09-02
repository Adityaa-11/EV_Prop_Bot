"""Deterministic entry construction for paper trading."""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class PaperPolicy:
    starting_bankroll: float = 200.0
    stake: float = 10.0
    daily_stake_cap: float = 200.0
    daily_loss_stop: float = 200.0
    max_open_entries: int = 20
    min_leg_win: float = 52.0
    min_leg_books: int = 2
    max_leg_dispersion: float = 8.0
    require_line_stability: bool = False
    excellent_roi: float = -25.0
    strong_roi: float = -30.0
    strong_lock_minutes: int = 30


PAYOUTS = {
    "prizepicks": {2: 3.0},
    "underdog": {2: 3.0},
}


def _utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _entry_roi(probabilities: list[float], payout_multiplier: float) -> float:
    win_probability = 1.0
    for probability in probabilities:
        win_probability *= probability / 100
    return (win_probability * payout_multiplier - 1) * 100


def _leg_tier(play: dict[str, Any], policy: PaperPolicy) -> str | None:
    consensus = play.get("consensus", {})
    probability = float(play.get("win_probability", 0))
    books = int(consensus.get("book_count", 0))
    dispersion = float(consensus.get("dispersion", 100))
    if (
        probability >= policy.min_leg_win
        and books >= policy.min_leg_books
        and dispersion <= policy.max_leg_dispersion
    ):
        return "playable"
    return None


def _compatible(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_prop = first.get("prop", {})
    second_prop = second.get("prop", {})
    if first.get("candidate_id") == second.get("candidate_id"):
        return False
    if first_prop.get("player_name") == second_prop.get("player_name"):
        return False
    first_event = first_prop.get("event_id")
    second_event = second_prop.get("event_id")
    if first_event and second_event and first_event == second_event:
        return False
    return True


def build_paper_entries(
    plays: list[dict[str, Any]],
    *,
    stability_for: Callable[[str], dict[str, Any]],
    policy: PaperPolicy,
    daily_staked: float,
    daily_profit: float = 0,
    open_entries: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the best non-overlapping slips while allowing complete abstention."""
    now = now or datetime.now(timezone.utc)
    if daily_profit <= -policy.daily_loss_stop:
        return {"entries": [], "watch_count": len(plays), "reason": "daily_loss_stop_reached"}
    available_by_stake = max(
        0,
        int((policy.daily_stake_cap - daily_staked) // policy.stake),
    )
    available_by_open = max(0, policy.max_open_entries - open_entries)
    available_slots = min(available_by_stake, available_by_open)
    if available_slots == 0:
        if available_by_open == 0:
            reason = "max_open_entries_reached"
        elif available_by_stake == 0:
            reason = "daily_stake_cap_reached"
        else:
            reason = "risk_capacity_reached"
        return {"entries": [], "watch_count": len(plays), "reason": reason}

    eligible_plays = []
    for play in plays:
        candidate_id = play.get("candidate_id")
        if not candidate_id or _leg_tier(play, policy) is None:
            continue
        if policy.require_line_stability:
            stability = stability_for(candidate_id)
            if not stability.get("stable"):
                continue
        eligible_plays.append(play)

    combinations = []
    for platform, payout_table in PAYOUTS.items():
        platform_plays = [
            play
            for play in eligible_plays
            if play.get("prop", {}).get("platform") == platform
        ][:30]
        multiplier = payout_table[2]
        for legs in itertools.combinations(platform_plays, 2):
            if not _compatible(*legs):
                continue
            probabilities = [float(leg["win_probability"]) for leg in legs]
            expected_roi = _entry_roi(probabilities, multiplier)
            lock_times = [
                parsed
                for parsed in (_utc_datetime(leg.get("prop", {}).get("game_time")) for leg in legs)
                if parsed is not None
            ]
            if not lock_times:
                continue
            lock_time = min(lock_times)
            minutes_to_lock = (lock_time - now).total_seconds() / 60
            if minutes_to_lock <= 5:
                continue

            all_playable = all(_leg_tier(leg, policy) == "playable" for leg in legs)
            if not all_playable:
                continue
            if expected_roi >= policy.excellent_roi:
                tier = "excellent"
            elif (
                expected_roi >= policy.strong_roi
                and minutes_to_lock <= policy.strong_lock_minutes
            ):
                tier = "strong"
            else:
                continue

            fingerprint_source = "|".join(
                [platform, *sorted(str(leg["candidate_id"]) for leg in legs)]
            )
            fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
            entry_id = f"paper-{fingerprint[:16]}"
            combinations.append(
                {
                    "id": entry_id,
                    "fingerprint": fingerprint,
                    "platform": platform,
                    "sport": legs[0]["prop"]["sport"],
                    "tier": tier,
                    "stake": policy.stake,
                    "expected_roi": round(expected_roi, 2),
                    "potential_payout": round(policy.stake * multiplier, 2),
                    "payout_multiplier": multiplier,
                    "lock_time": lock_time.isoformat(),
                    "created_at": now.isoformat(),
                    "legs": [
                        {
                            "candidate_id": leg["candidate_id"],
                            "player_name": leg["prop"]["player_name"],
                            "stat_type": leg["prop"]["stat_type"],
                            "event_id": leg["prop"].get("event_id"),
                            "market_key": leg["prop"].get("market_key"),
                            "side": leg["recommended_play"],
                            "line": leg["prop"]["line"],
                            "game_time": leg["prop"].get("game_time"),
                            "win_probability": leg["win_probability"],
                            "book_count": leg.get("consensus", {}).get("book_count", 0),
                            "entry_line": leg["prop"]["line"],
                            "closing_line": None,
                            "line_clv": None,
                            "closing_probability": None,
                            "probability_clv": None,
                        }
                        for leg in legs
                    ],
                }
            )

    combinations.sort(
        key=lambda entry: (
            entry["tier"] == "excellent",
            entry["expected_roi"],
        ),
        reverse=True,
    )
    selected = []
    used_candidates: set[str] = set()
    for entry in combinations:
        candidate_ids = {leg["candidate_id"] for leg in entry["legs"]}
        if candidate_ids & used_candidates:
            continue
        selected.append(entry)
        used_candidates.update(candidate_ids)
        if len(selected) >= available_slots:
            break

    return {
        "entries": selected,
        "watch_count": max(0, len(plays) - len(selected) * 2),
        "reason": None if selected else "no_qualifying_entry",
    }

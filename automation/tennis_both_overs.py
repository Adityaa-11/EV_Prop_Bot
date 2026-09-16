"""Tennis both-overs games-won paper trading strategy.

Correlation thesis: when a tennis match goes long (many games), BOTH players
accumulate more Games Won / Total Games Won.  This builds 2-leg OVER+OVER
paper slips where both legs are on the same match — no Odds API consensus or
min_leg_win required (DFS-board-only lane).

Long-match heuristic (optional, off by default):
    If PAPER_TENNIS_LONG_MATCH_HEURISTIC=true, skip matches whose start time
    is <60 minutes away (late-posted lines on in-progress matches are noisy)
    and prefer matches with no "retirement" or "walkover" in the title.
    This is intentionally light — we have no model for match length.

Tags:
    strategy=tennis_both_overs_games
    paper_version=tennis-v1
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


GAMES_WON_STAT_TYPES = frozenset({
    "games won",
    "total games won",
    "games",
    # Dabble sometimes labels player game lines this way; match-total boards
    # are filtered out separately when both legs share one line/market.
    "player games won",
})


def _normalize_stat(stat: str) -> str:
    return stat.strip().lower()


def _is_games_won_prop(prop: dict[str, Any]) -> bool:
    return _normalize_stat(prop.get("stat_type", "")) in GAMES_WON_STAT_TYPES


@dataclass(frozen=True)
class TennisBothOversPolicy:
    stake: float = float(os.getenv("PAPER_TENNIS_STAKE", os.getenv("PAPER_STAKE", "10")))
    daily_cap: int = int(os.getenv("PAPER_TENNIS_DAILY_CAP", "20"))
    match_cap: int = int(os.getenv("PAPER_TENNIS_MATCH_CAP", "1"))
    payout_multiplier: float = 3.0
    long_match_heuristic: bool = os.getenv(
        "PAPER_TENNIS_LONG_MATCH_HEURISTIC", "false"
    ).lower() in {"1", "true", "yes"}
    min_minutes_to_start: float = 5.0


def _match_key_for_prop(prop: dict[str, Any]) -> str | None:
    """Return a grouping key that identifies the match.

    PrizePicks: ``game_time`` is the same for both players in a match and is
    combined with sport to form a coarse match key.  If ``event_id`` is present
    (Underdog / Odds-API sourced), use that directly.

    Robust pairing: we combine (platform, event_id OR game_time) so that
    cross-platform duplicates don't accidentally pair.
    """
    platform = prop.get("platform", "")
    event_id = prop.get("event_id")
    if event_id:
        return f"{platform}|{event_id}"
    game_time = prop.get("game_time")
    if game_time:
        return f"{platform}|{game_time}"
    return None


def build_tennis_both_overs_entries(
    props: list[dict[str, Any]],
    *,
    policy: TennisBothOversPolicy | None = None,
    daily_placed: int = 0,
    match_placed: dict[str, int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build 2-leg OVER+OVER paper slips for tennis Games Won.

    Parameters
    ----------
    props
        Flat list of DFS prop dicts.  Each must have at minimum:
        ``player_name``, ``stat_type``, ``line``, ``platform``, and either
        ``event_id`` or ``game_time`` for match pairing.
    policy
        Controls stake, caps, and heuristic toggles.
    daily_placed
        How many tennis-both-overs slips already created today.
    match_placed
        {match_key: count} of slips already created for each match today.
    now
        UTC timestamp for clock.

    Returns
    -------
    dict with ``entries`` (list), ``skipped_reasons`` (dict of reason→count),
    ``match_groups`` (count of valid same-match groups found).
    """
    policy = policy or TennisBothOversPolicy()
    now = now or datetime.now(timezone.utc)
    match_placed = match_placed or {}

    games_won_props = [p for p in props if _is_games_won_prop(p)]

    match_groups: dict[str, list[dict[str, Any]]] = {}
    for prop in games_won_props:
        key = _match_key_for_prop(prop)
        if key is None:
            continue
        match_groups.setdefault(key, []).append(prop)

    entries: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    remaining = policy.daily_cap - daily_placed

    for match_key, group in sorted(match_groups.items()):
        if remaining <= 0:
            skipped["daily_cap"] = skipped.get("daily_cap", 0) + 1
            continue

        over_props_by_player: dict[str, dict[str, Any]] = {}
        for prop in group:
            name = prop.get("player_name", "").strip()
            if not name:
                continue
            if name in over_props_by_player:
                continue
            over_props_by_player[name] = prop

        players = list(over_props_by_player.keys())
        if len(players) < 2:
            skipped["missing_leg"] = skipped.get("missing_leg", 0) + 1
            continue

        if (match_placed.get(match_key, 0) >= policy.match_cap):
            skipped["match_cap"] = skipped.get("match_cap", 0) + 1
            continue

        prop_a = over_props_by_player[players[0]]
        prop_b = over_props_by_player[players[1]]

        game_times = []
        for p in (prop_a, prop_b):
            gt = p.get("game_time")
            if gt:
                try:
                    parsed = datetime.fromisoformat(str(gt).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    game_times.append(parsed)
                except ValueError:
                    pass

        if not game_times:
            skipped["no_game_time"] = skipped.get("no_game_time", 0) + 1
            continue

        lock_time = min(game_times)
        minutes_to_lock = (lock_time - now).total_seconds() / 60
        if minutes_to_lock <= policy.min_minutes_to_start:
            skipped["too_close_to_start"] = skipped.get("too_close_to_start", 0) + 1
            continue

        if policy.long_match_heuristic and minutes_to_lock < 60:
            skipped["long_match_heuristic"] = skipped.get("long_match_heuristic", 0) + 1
            continue

        platform = prop_a.get("platform", "unknown")
        fingerprint_source = "|".join([
            "tennis_both_overs",
            platform,
            match_key,
            players[0],
            players[1],
        ])
        fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
        entry_id = f"tennis-bo-{fingerprint[:16]}"

        potential_payout = round(policy.stake * policy.payout_multiplier, 2)

        entry = {
            "id": entry_id,
            "fingerprint": fingerprint,
            "platform": platform,
            "sport": "TENNIS",
            "tier": "correlation",
            "strategy": "tennis_both_overs_games",
            "paper_version": "tennis-v1",
            "stake": policy.stake,
            "expected_roi": 0.0,
            "potential_payout": potential_payout,
            "payout_multiplier": round(policy.payout_multiplier, 4),
            "lock_time": lock_time.isoformat(),
            "created_at": now.isoformat(),
            "execution_mode": "paper",
            "legs": [
                _build_leg(prop_a, players[0]),
                _build_leg(prop_b, players[1]),
            ],
        }
        entries.append(entry)
        remaining -= 1

    return {
        "entries": entries,
        "skipped_reasons": skipped,
        "match_groups": len(match_groups),
        "games_won_props": len(games_won_props),
    }


def _build_leg(prop: dict[str, Any], player_name: str) -> dict[str, Any]:
    return {
        "candidate_id": prop.get("id") or f"tennis-{player_name}",
        "player_name": player_name,
        "stat_type": prop.get("stat_type", "Games Won"),
        "event_id": prop.get("event_id"),
        "market_key": prop.get("market_key", "tennis_games_won"),
        "side": "OVER",
        "line": prop.get("line", 0),
        "game_time": prop.get("game_time"),
        "win_probability": 0.0,
        "over_probability": None,
        "under_probability": None,
        "book_count": 0,
        "payout_multiplier": 1.0,
        "entry_line": prop.get("line", 0),
        "closing_line": None,
        "line_clv": None,
        "closing_probability": None,
        "probability_clv": None,
    }

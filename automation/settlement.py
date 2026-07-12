"""Deterministic MLB paper-settlement using the free MLB Stats API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from fuzzywuzzy import fuzz


SUPPORTED_MLB_MARKETS = {
    "batter_hits": "hits",
    "batter_home_runs": "homeRuns",
    "batter_rbis": "rbi",
    "batter_runs": "runs",
    "batter_stolen_bases": "stolenBases",
    "batter_total_bases": "totalBases",
    "pitcher_strikeouts": "strikeOuts",
    "pitcher_hits_allowed": "hits",
    "pitcher_walks": "baseOnBalls",
}


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def evaluate_leg(side: str, line: float, actual: float | None) -> str | None:
    if actual is None:
        return None
    if abs(actual - line) < 1e-9:
        return "push"
    if side.upper() == "OVER":
        return "win" if actual > line else "loss"
    return "win" if actual < line else "loss"


def _player_stat_from_boxscore(
    boxscore: dict[str, Any],
    player_name: str,
    market_key: str,
) -> float | None:
    field = SUPPORTED_MLB_MARKETS.get(market_key)
    if not field:
        return None

    best_score = 0
    best_value: float | None = None
    for side in ("home", "away"):
        players = boxscore.get("teams", {}).get(side, {}).get("players", {})
        for player in players.values():
            person = player.get("person", {})
            name = person.get("fullName") or ""
            score = fuzz.token_sort_ratio(player_name.lower(), name.lower())
            if score < 85 or score < best_score:
                continue
            stats = player.get("stats", {})
            batting = stats.get("batting", {})
            pitching = stats.get("pitching", {})
            if market_key.startswith("pitcher_"):
                raw = pitching.get(field)
            elif market_key == "batter_total_bases":
                singles = int(batting.get("hits", 0) or 0) - int(batting.get("doubles", 0) or 0) - int(
                    batting.get("triples", 0) or 0
                ) - int(batting.get("homeRuns", 0) or 0)
                raw = (
                    singles
                    + 2 * int(batting.get("doubles", 0) or 0)
                    + 3 * int(batting.get("triples", 0) or 0)
                    + 4 * int(batting.get("homeRuns", 0) or 0)
                )
            else:
                raw = batting.get(field)
            if raw is None or raw == "":
                continue
            best_score = score
            best_value = float(raw)
    return best_value


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict[str, Any] | None:
    try:
        async with session.get(url, timeout=30) as response:
            if response.status != 200:
                return None
            payload = await response.json()
            return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        return None


async def settle_mlb_entries(
    session: aiohttp.ClientSession,
    entries: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Settle open MLB paper slips whose lock time has passed.

    Returns a list of settlement actions. Unsupported or ambiguous legs stay pending.
    """
    now = now or datetime.now(timezone.utc)
    actions: list[dict[str, Any]] = []
    boxscore_cache: dict[int, dict[str, Any]] = {}
    schedule_cache: dict[str, list[dict[str, Any]]] = {}

    for entry in entries:
        if entry.get("status") != "open":
            continue
        if entry.get("sport", "").upper() != "MLB":
            continue
        lock_time = _parse_utc(entry.get("lock_time"))
        if lock_time is None or lock_time > now - timedelta(hours=3):
            # Wait until games are likely final before settling.
            continue

        date_key = lock_time.date().isoformat()
        if date_key not in schedule_cache:
            url = (
                "https://statsapi.mlb.com/api/v1/schedule"
                f"?sportId=1&date={lock_time.strftime('%m/%d/%Y')}&hydrate=linescore"
            )
            payload = await _fetch_json(session, url)
            games = []
            for date_block in (payload or {}).get("dates", []):
                games.extend(date_block.get("games", []))
            schedule_cache[date_key] = games

        games = schedule_cache[date_key]
        final_games = [
            game
            for game in games
            if game.get("status", {}).get("abstractGameState") == "Final"
        ]
        if not final_games:
            actions.append(
                {
                    "entry_id": entry["id"],
                    "status": "pending",
                    "reason": "no_final_mlb_games",
                }
            )
            continue

        leg_results = []
        unresolved = False
        for leg in entry.get("legs", []):
            market_key = leg.get("market_key")
            if market_key not in SUPPORTED_MLB_MARKETS:
                unresolved = True
                leg_results.append({**leg, "result": None, "actual": None, "reason": "unsupported_market"})
                continue

            matched_value = None
            matched_game_pk = None
            for game in final_games:
                game_pk = game.get("gamePk")
                if game_pk is None:
                    continue
                if game_pk not in boxscore_cache:
                    box = await _fetch_json(
                        session,
                        f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live",
                    )
                    boxscore_cache[game_pk] = (
                        (box or {}).get("liveData", {}).get("boxscore", {}) if box else {}
                    )
                value = _player_stat_from_boxscore(
                    boxscore_cache[game_pk],
                    leg.get("player_name", ""),
                    market_key,
                )
                if value is not None:
                    matched_value = value
                    matched_game_pk = game_pk
                    break

            if matched_value is None:
                unresolved = True
                leg_results.append({**leg, "result": None, "actual": None, "reason": "player_not_found"})
                continue

            result = evaluate_leg(leg.get("side", ""), float(leg.get("entry_line", leg.get("line", 0))), matched_value)
            leg_results.append(
                {
                    **leg,
                    "result": result,
                    "actual": matched_value,
                    "game_pk": matched_game_pk,
                    "reason": None,
                }
            )

        if unresolved or any(item.get("result") is None for item in leg_results):
            actions.append(
                {
                    "entry_id": entry["id"],
                    "status": "pending",
                    "reason": "ambiguous_or_unsupported_legs",
                    "legs": leg_results,
                }
            )
            continue

        results = [item["result"] for item in leg_results]
        if any(result == "void" for result in results):
            slip_result = "void"
            payout = float(entry["stake"])
        elif any(result == "push" for result in results) and all(
            result in {"win", "push"} for result in results
        ):
            # Conservative: any push voids the 2-leg power slip stake return.
            slip_result = "push"
            payout = float(entry["stake"])
        elif all(result == "win" for result in results):
            slip_result = "win"
            payout = float(entry.get("potential_payout", entry["stake"] * 3))
        else:
            slip_result = "loss"
            payout = 0.0

        actions.append(
            {
                "entry_id": entry["id"],
                "status": "settled",
                "result": slip_result,
                "payout": payout,
                "legs": leg_results,
                "provenance": "mlb_statsapi",
            }
        )

    return actions

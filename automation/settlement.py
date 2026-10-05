"""Deterministic paper-settlement from free public box-score APIs.

MLB uses the MLB Stats API. NFL, NCAAF, NBA, WNBA, NCAAB, NHL, MLS, and EPL
use ESPN's public scoreboard/summary endpoints (no API key). Sports with no
provider still auto-void after STALE_ENTRY_VOID_HOURS so capacity cannot jam.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from fuzzywuzzy import fuzz


EASTERN = ZoneInfo("America/New_York")
STALE_ENTRY_VOID_HOURS = float(os.getenv("STALE_ENTRY_VOID_HOURS", "12"))
SETTLEMENT_TIMEOUT_HOURS = float(os.getenv("SETTLEMENT_TIMEOUT_HOURS", "36"))
NAME_MATCH_MIN = 85

SUPPORTED_MLB_MARKETS = {
    "batter_hits": "hits",
    "batter_singles": "singles",
    "batter_home_runs": "homeRuns",
    "batter_rbis": "rbi",
    "batter_runs": "runs",
    "batter_stolen_bases": "stolenBases",
    "batter_total_bases": "totalBases",
    "batter_hits_runs_rbis": "hitsRunsRbis",
    "pitcher_strikeouts": "strikeOuts",
    "pitcher_hits_allowed": "hits",
    "pitcher_walks": "baseOnBalls",
    "pitcher_earned_runs": "earnedRuns",
}

# sport -> ESPN site API path
ESPN_LEAGUES = {
    "NFL": "football/nfl",
    "NCAAF": "football/college-football",
    "CFL": "football/cfl",
    "NBA": "basketball/nba",
    "WNBA": "basketball/wnba",
    "NCAAB": "basketball/mens-college-basketball",
    "NHL": "hockey/nhl",
    "MLS": "soccer/usa.1",
    "EPL": "soccer/eng.1",
}

SETTLEMENT_SUPPORTED_SPORTS = {"MLB", *ESPN_LEAGUES}
# TODO: tennis still has no reliable free stats API.

SETTLE_DELAY_HOURS = {
    "MLB": 3.0,
    "NFL": 4.0,
    "NCAAF": 4.0,
    "CFL": 4.0,
    "NBA": 3.0,
    "WNBA": 3.0,
    "NCAAB": 3.0,
    "NHL": 3.5,
    "MLS": 2.5,
    "EPL": 2.5,
}

ESPN_MARKET_KEYS = frozenset(
    {
        "player_pass_tds",
        "player_pass_yds",
        "player_pass_interceptions",
        "player_completions",
        "player_pass_attempts",
        "player_rush_yds",
        "player_rush_tds",
        "player_receptions",
        "player_reception_yds",
        "player_reception_tds",
        "player_longest_reception",
        "player_longest_rush",
        "player_sacks",
        "player_interceptions",
        "player_rush_reception_yds",
        "player_rush_reception_tds",
        "player_anytime_td",
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_steals",
        "player_blocks",
        "player_turnovers",
        "player_points_rebounds_assists",
        "player_points_rebounds",
        "player_points_assists",
        "player_rebounds_assists",
        "player_blocks_steals",
        "player_double_double",
        "player_goals",
        "player_shots_on_goal",
        "player_shots",
        "player_shots_on_target",
        "player_goals_scored",
        "player_goals_assists",
        "goalie_saves",
        "goalie_goals_against",
        "player_power_play_points",
    }
)

_FETCH_HEADERS = {
    "User-Agent": "ev-dashboard-paper-settlement/1.0",
    "Accept": "application/json",
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


def _calendar_dates_for_lock(lock_time: datetime) -> list[date]:
    """US-Eastern slate dates around lock, including UTC-midnight spillover."""
    local = lock_time.astimezone(EASTERN).date()
    return [local + timedelta(days=delta) for delta in (-1, 0, 1)]


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if "/" in text:
        text = text.split("/", 1)[0]
    if "-" in text and not text.startswith("-"):
        text = text.split("-", 1)[0]
    try:
        return float(text)
    except ValueError:
        return None


def _slash_parts(value: Any) -> tuple[float | None, float | None]:
    text = str(value or "").strip()
    if "/" not in text:
        return _to_float(text), None
    left, right = text.split("/", 1)
    return _to_float(left), _to_float(right)


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
            if score < NAME_MATCH_MIN or score < best_score:
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
            elif market_key == "batter_hits_runs_rbis":
                raw = (
                    int(batting.get("hits", 0) or 0)
                    + int(batting.get("runs", 0) or 0)
                    + int(batting.get("rbi", 0) or 0)
                )
            elif market_key == "batter_singles":
                raw = (
                    int(batting.get("hits", 0) or 0)
                    - int(batting.get("doubles", 0) or 0)
                    - int(batting.get("triples", 0) or 0)
                    - int(batting.get("homeRuns", 0) or 0)
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
        async with session.get(url, timeout=30, headers=_FETCH_HEADERS) as response:
            if response.status != 200:
                return None
            payload = await response.json()
            return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        return None


def void_stale_open_entries(
    entries: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stale_hours: float | None = None,
) -> list[dict[str, Any]]:
    """Close open entries that are past lock with no settlement result.

    Sports with a box-score provider get a longer grace window. Everything else
    voids after ``stale_hours`` so capacity cannot jam indefinitely.
    """
    now = now or datetime.now(timezone.utc)
    stale_hours = STALE_ENTRY_VOID_HOURS if stale_hours is None else stale_hours
    timeout_hours = max(stale_hours, SETTLEMENT_TIMEOUT_HOURS)
    actions: list[dict[str, Any]] = []

    for entry in entries:
        if entry.get("status") != "open":
            continue
        lock_time = _parse_utc(entry.get("lock_time"))
        if lock_time is None:
            continue

        sport = str(entry.get("sport", "")).upper()
        hours_past_lock = (now - lock_time).total_seconds() / 3600
        if sport in SETTLEMENT_SUPPORTED_SPORTS:
            if hours_past_lock < timeout_hours:
                continue
            reason = "mlb_settlement_timeout" if sport == "MLB" else "settlement_timeout"
        else:
            if hours_past_lock < stale_hours:
                continue
            reason = "no_settlement_provider"

        actions.append(
            {
                "entry_id": entry["id"],
                "status": "settled",
                "result": "void",
                "payout": float(entry.get("stake", 0)),
                "provenance": reason,
            }
        )

    return actions


def _grade_completed_legs(entry: dict[str, Any], leg_results: list[dict[str, Any]], provenance: str) -> dict[str, Any]:
    results = [item["result"] for item in leg_results]
    if any(result == "void" for result in results):
        slip_result = "void"
        payout = float(entry["stake"])
    elif any(result == "push" for result in results) and all(
        result in {"win", "push"} for result in results
    ):
        slip_result = "push"
        payout = float(entry["stake"])
    elif all(result == "win" for result in results):
        slip_result = "win"
        payout = float(entry.get("potential_payout", entry["stake"] * 3))
    else:
        slip_result = "loss"
        payout = 0.0
    return {
        "entry_id": entry["id"],
        "status": "settled",
        "result": slip_result,
        "payout": payout,
        "legs": leg_results,
        "provenance": provenance,
    }


def _espn_stat_value(market_key: str, bags: dict[str, dict[str, Any]]) -> float | None:
    passing = bags.get("passing", {})
    rushing = bags.get("rushing", {})
    receiving = bags.get("receiving", {})
    defensive = bags.get("defensive", {})
    interceptions = bags.get("interceptions", {})
    merged: dict[str, Any] = {}
    for bag in bags.values():
        merged.update(bag)

    def g(*keys: str) -> float | None:
        for key in keys:
            for source in (merged, passing, rushing, receiving, defensive):
                if key in source:
                    parsed = _to_float(source[key])
                    if parsed is not None:
                        return parsed
        return None

    completions, attempts = _slash_parts(passing.get("completions/passingAttempts"))

    mapping: dict[str, float | None] = {
        "player_pass_tds": g("passingTouchdowns"),
        "player_pass_yds": g("passingYards"),
        "player_pass_interceptions": _to_float(passing.get("interceptions")),
        "player_completions": completions,
        "player_pass_attempts": attempts,
        "player_rush_yds": g("rushingYards"),
        "player_rush_tds": g("rushingTouchdowns"),
        "player_receptions": g("receptions"),
        "player_reception_yds": g("receivingYards"),
        "player_reception_tds": g("receivingTouchdowns"),
        "player_longest_reception": g("longReception"),
        "player_longest_rush": g("longRushing"),
        "player_sacks": g("sacks"),
        "player_interceptions": _to_float(interceptions.get("interceptions")) or _to_float(defensive.get("interceptions")),
        "player_points": g("points"),
        "player_rebounds": g("rebounds", "totalRebounds"),
        "player_assists": g("assists"),
        "player_threes": g("threePointFieldGoalsMade", "threepointfieldgoalsmade"),
        "player_steals": g("steals"),
        "player_blocks": g("blocks"),
        "player_turnovers": g("turnovers"),
        "player_goals": g("goals"),
        "player_shots_on_goal": g("shotsOnGoal", "shots"),
        "player_shots": g("shots", "totalShots"),
        "player_shots_on_target": g("shotsOnTarget"),
        "player_goals_scored": g("goals"),
        "goalie_saves": g("saves"),
        "goalie_goals_against": g("goalsAgainst"),
        "player_power_play_points": g("powerPlayPoints"),
    }
    if market_key in mapping:
        return mapping[market_key]

    rush_yds = g("rushingYards") or 0.0
    rec_yds = g("receivingYards") or 0.0
    rush_tds = g("rushingTouchdowns") or 0.0
    rec_tds = g("receivingTouchdowns") or 0.0
    pts = g("points") or 0.0
    reb = g("rebounds", "totalRebounds") or 0.0
    ast = g("assists") or 0.0
    stl = g("steals") or 0.0
    blk = g("blocks") or 0.0
    goals = g("goals") or 0.0

    combos = {
        "player_rush_reception_yds": rush_yds + rec_yds,
        "player_rush_reception_tds": rush_tds + rec_tds,
        "player_anytime_td": rush_tds + rec_tds,
        "player_points_rebounds_assists": pts + reb + ast,
        "player_points_rebounds": pts + reb,
        "player_points_assists": pts + ast,
        "player_rebounds_assists": reb + ast,
        "player_blocks_steals": blk + stl,
        "player_goals_assists": goals + ast,
        "player_double_double": 1.0 if sum(1 for val in (pts, reb, ast, stl, blk) if val >= 10) >= 2 else 0.0,
    }
    if market_key in combos:
        return combos[market_key]
    # NHL "points" vs NBA "points" share the key; hockey points = G+A when
    # the boxscore has goals but no basketball points line.
    if market_key == "player_points" and g("points") is None and (g("goals") is not None or g("assists") is not None):
        return (g("goals") or 0.0) + (g("assists") or 0.0)
    return None


def _bags_from_espn_boxscore(boxscore: dict[str, Any]) -> list[tuple[str, dict[str, dict[str, Any]]]]:
    players: list[tuple[str, dict[str, dict[str, Any]]]] = []
    for team in boxscore.get("players") or []:
        bags_by_name: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
        for category in team.get("statistics") or []:
            cat_name = str(category.get("name") or "unknown")
            keys = category.get("keys") or category.get("labels") or []
            for athlete in category.get("athletes") or []:
                name = ((athlete.get("athlete") or {}).get("displayName") or "").strip()
                if not name:
                    continue
                stats = athlete.get("stats") or []
                bags_by_name[name][cat_name].update(
                    {str(key): value for key, value in zip(keys, stats)}
                )
        players.extend(bags_by_name.items())
    return players


def _best_espn_stat(
    players: list[tuple[str, dict[str, dict[str, Any]]]],
    player_name: str,
    market_key: str,
) -> tuple[float | None, int]:
    best_score = 0
    best_value: float | None = None
    for name, bags in players:
        score = fuzz.token_sort_ratio(player_name.lower(), name.lower())
        if score < NAME_MATCH_MIN or score < best_score:
            continue
        value = _espn_stat_value(market_key, bags)
        if value is None:
            continue
        best_score = score
        best_value = value
    return best_value, best_score


def _game_commence(event: dict[str, Any]) -> datetime | None:
    return _parse_utc(event.get("date"))


def _event_is_final(event: dict[str, Any]) -> bool:
    competitions = event.get("competitions") or []
    if not competitions:
        return False
    status = (competitions[0].get("status") or {}).get("type") or {}
    return bool(status.get("completed")) or str(status.get("name") or "").upper() == "STATUS_FINAL"


def _within_lock_window(lock_time: datetime, commence: datetime | None) -> bool:
    if commence is None:
        return False
    return lock_time - timedelta(hours=3) <= commence <= lock_time + timedelta(hours=16)


def _is_better_match(
    *,
    lock_time: datetime,
    commence: datetime | None,
    name_score: int,
    best_score: int,
    best_commence: datetime | None,
    has_match: bool,
) -> bool:
    if name_score < NAME_MATCH_MIN:
        return False
    if not has_match:
        return True
    if name_score != best_score:
        return name_score > best_score
    if commence is None:
        return False
    if best_commence is None:
        return True
    return abs((commence - lock_time).total_seconds()) < abs((best_commence - lock_time).total_seconds())


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
        delay = SETTLE_DELAY_HOURS["MLB"]
        if lock_time is None or lock_time > now - timedelta(hours=delay):
            continue

        games: list[dict[str, Any]] = []
        for slate_date in _calendar_dates_for_lock(lock_time):
            date_key = slate_date.isoformat()
            if date_key not in schedule_cache:
                url = (
                    "https://statsapi.mlb.com/api/v1/schedule"
                    f"?sportId=1&date={slate_date.strftime('%m/%d/%Y')}&hydrate=linescore"
                )
                payload = await _fetch_json(session, url)
                day_games = []
                for date_block in (payload or {}).get("dates", []):
                    day_games.extend(date_block.get("games", []))
                schedule_cache[date_key] = day_games
            games.extend(schedule_cache[date_key])

        final_games = [
            game
            for game in games
            if game.get("status", {}).get("abstractGameState") == "Final"
            and _within_lock_window(lock_time, _parse_utc(game.get("gameDate")))
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
            best_score = 0
            best_commence: datetime | None = None
            for game in final_games:
                game_pk = game.get("gamePk")
                commence = _parse_utc(game.get("gameDate"))
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
                if value is None:
                    continue
                score = NAME_MATCH_MIN
                if not _is_better_match(
                    lock_time=lock_time,
                    commence=commence,
                    name_score=score,
                    best_score=best_score,
                    best_commence=best_commence,
                    has_match=matched_value is not None,
                ):
                    continue
                best_score = score
                best_commence = commence
                matched_value = value
                matched_game_pk = game_pk

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

        actions.append(_grade_completed_legs(entry, leg_results, "mlb_statsapi"))

    return actions


async def _espn_events_for_dates(
    session: aiohttp.ClientSession,
    league_path: str,
    dates: list[date],
    cache: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for slate_date in dates:
        cache_key = f"{league_path}:{slate_date.isoformat()}"
        if cache_key not in cache:
            url = (
                "https://site.api.espn.com/apis/site/v2/sports/"
                f"{league_path}/scoreboard?dates={slate_date.strftime('%Y%m%d')}&limit=300"
            )
            payload = await _fetch_json(session, url)
            cache[cache_key] = list(payload.get("events") or []) if payload else []
        for event in cache[cache_key]:
            event_id = str(event.get("id") or "")
            if event_id and event_id in seen_ids:
                continue
            if event_id:
                seen_ids.add(event_id)
            events.append(event)
    return events


async def settle_espn_entries(
    session: aiohttp.ClientSession,
    entries: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Settle non-MLB paper slips from ESPN public box scores."""
    now = now or datetime.now(timezone.utc)
    actions: list[dict[str, Any]] = []
    scoreboard_cache: dict[str, list[dict[str, Any]]] = {}
    boxscore_cache: dict[str, list[tuple[str, dict[str, dict[str, Any]]]]] = {}

    for entry in entries:
        if entry.get("status") != "open":
            continue
        sport = str(entry.get("sport", "")).upper()
        league_path = ESPN_LEAGUES.get(sport)
        lock_time = _parse_utc(entry.get("lock_time"))
        delay = SETTLE_DELAY_HOURS.get(sport, 3.5)
        if league_path is None or lock_time is None or lock_time > now - timedelta(hours=delay):
            continue

        events = await _espn_events_for_dates(
            session,
            league_path,
            _calendar_dates_for_lock(lock_time),
            scoreboard_cache,
        )
        slate = [
            event
            for event in events
            if _within_lock_window(lock_time, _game_commence(event))
        ]
        final_events = [event for event in slate if _event_is_final(event)]
        if not final_events:
            actions.append(
                {
                    "entry_id": entry["id"],
                    "status": "pending",
                    "reason": "no_final_espn_games",
                }
            )
            continue

        leg_results = []
        unresolved = False
        for leg in entry.get("legs", []):
            market_key = str(leg.get("market_key") or "")
            matched_value = None
            matched_event = None
            best_score = 0
            best_commence: datetime | None = None
            for event in final_events:
                event_id = str(event.get("id") or "")
                commence = _game_commence(event)
                if not event_id:
                    continue
                if event_id not in boxscore_cache:
                    summary = await _fetch_json(
                        session,
                        f"https://site.api.espn.com/apis/site/v2/sports/{league_path}/summary?event={event_id}",
                    )
                    boxscore_cache[event_id] = _bags_from_espn_boxscore(
                        (summary or {}).get("boxscore") or {}
                    )
                value, score = _best_espn_stat(
                    boxscore_cache[event_id],
                    str(leg.get("player_name") or ""),
                    market_key,
                )
                if value is None or not _is_better_match(
                    lock_time=lock_time,
                    commence=commence,
                    name_score=score,
                    best_score=best_score,
                    best_commence=best_commence,
                    has_match=matched_value is not None,
                ):
                    continue
                best_score = score
                best_commence = commence
                matched_value = value
                matched_event = event_id

            if matched_value is None:
                unresolved = True
                reason = "unsupported_market" if market_key not in ESPN_MARKET_KEYS else "player_not_found"
                leg_results.append({**leg, "result": None, "actual": None, "reason": reason})
                continue

            result = evaluate_leg(
                leg.get("side", ""),
                float(leg.get("entry_line", leg.get("line", 0))),
                matched_value,
            )
            leg_results.append(
                {
                    **leg,
                    "result": result,
                    "actual": matched_value,
                    "event_id": matched_event,
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

        actions.append(_grade_completed_legs(entry, leg_results, "espn_boxscore"))

    return actions


async def settle_open_entries(
    session: aiohttp.ClientSession,
    entries: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Settle every open paper slip that has a free box-score provider."""
    now = now or datetime.now(timezone.utc)
    mlb = [entry for entry in entries if str(entry.get("sport", "")).upper() == "MLB"]
    espn = [entry for entry in entries if str(entry.get("sport", "")).upper() in ESPN_LEAGUES]
    actions = await settle_mlb_entries(session, mlb, now=now)
    actions.extend(await settle_espn_entries(session, espn, now=now))
    return actions

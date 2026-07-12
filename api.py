"""
EV Dashboard - FastAPI Backend
Aggregates player props from multiple DFS pick'em platforms and calculates +EV opportunities.

Supported Platforms:
- PrizePicks (working)
- Underdog Fantasy (working)
- Sleeper Picks (needs research - separate API from fantasy)
- Betr Picks (needs research)
- ParlayPlay (needs research)

Run with: uvicorn api:app --reload
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import aiohttp
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fuzzywuzzy import fuzz
import os
import hashlib
import hmac
import time
from dotenv import load_dotenv
from storage import PipelineStore
from automation import (
    PaperPolicy,
    PaperScheduler,
    build_paper_entries,
    deliver_paper_entry,
    settle_mlb_entries,
)

load_dotenv()

# =============================================================================
# CACHING SYSTEM - Saves API quota by caching data
# =============================================================================

class DataCache:
    """Simple in-memory cache with TTL (time-to-live)."""
    
    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self.cache = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str, allow_stale: bool = False) -> tuple[Any, bool]:
        """Get cached data without serving expired betting data by default."""
        if key not in self.cache:
            return None, False
        
        data, timestamp, ttl = self.cache[key]
        age = time.time() - timestamp
        
        if age > ttl:
            return (data, False) if allow_stale else (None, False)
        
        return data, True
    
    def set(self, key: str, data: Any, ttl: int = None):
        """Cache data with optional custom TTL."""
        self.cache[key] = (data, time.time(), ttl or self.default_ttl)
    
    def invalidate(self, key: str = None):
        """Clear specific key or all cache."""
        if key:
            self.cache.pop(key, None)
        else:
            self.cache.clear()
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        now = time.time()
        stats = {
            "total_keys": len(self.cache),
            "keys": {}
        }
        for key, (data, timestamp, ttl) in self.cache.items():
            age = now - timestamp
            stats["keys"][key] = {
                "age_seconds": round(age, 1),
                "ttl_seconds": ttl,
                "is_fresh": age <= ttl,
                "expires_in": max(0, round(ttl - age, 1)),
            }
        return stats

# Initialize cache (5 minute default TTL)
cache = DataCache(default_ttl=300)
refresh_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
store = PipelineStore()

# =============================================================================
# CONFIGURATION
# =============================================================================

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
HERMES_API_KEY = os.getenv("HERMES_API_KEY")
PAPER_POLICY = PaperPolicy(
    starting_bankroll=float(os.getenv("PAPER_STARTING_BANKROLL", "200")),
    stake=float(os.getenv("PAPER_STAKE", "10")),
    daily_stake_cap=float(os.getenv("PAPER_DAILY_STAKE_CAP", "30")),
    daily_loss_stop=float(os.getenv("PAPER_DAILY_LOSS_STOP", "30")),
    max_open_entries=int(os.getenv("PAPER_MAX_OPEN_ENTRIES", "4")),
)
PAPER_DAILY_SCAN_CAP = int(os.getenv("PAPER_DAILY_SCAN_CAP", "24"))
PAPER_SCHEDULER_ENABLED = os.getenv("PAPER_SCHEDULER_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}
PAPER_SPORTS = [
    sport.strip().lower()
    for sport in os.getenv("PAPER_SPORTS", "mlb,nba,nfl,nhl").split(",")
    if sport.strip()
]
paper_scheduler: PaperScheduler | None = None


def _require_secret(configured: str | None, provided: str | None, name: str) -> None:
    if not configured:
        raise HTTPException(status_code=503, detail=f"{name} is not configured")
    if not provided or not hmac.compare_digest(configured, provided):
        raise HTTPException(status_code=401, detail="Invalid API key")


async def require_admin_key(x_admin_key: Optional[str] = Header(None)) -> None:
    _require_secret(ADMIN_API_KEY, x_admin_key, "ADMIN_API_KEY")


async def require_hermes_key(x_hermes_key: Optional[str] = Header(None)) -> None:
    _require_secret(HERMES_API_KEY, x_hermes_key, "HERMES_API_KEY")


def require_refresh_authorization(
    refresh: bool,
    admin_key: str | None,
    hermes_key: str | None,
) -> None:
    if not refresh:
        return
    admin_valid = bool(
        ADMIN_API_KEY
        and admin_key
        and hmac.compare_digest(ADMIN_API_KEY, admin_key)
    )
    hermes_valid = bool(
        HERMES_API_KEY
        and hermes_key
        and hmac.compare_digest(HERMES_API_KEY, hermes_key)
    )
    if not admin_valid and not hermes_valid:
        raise HTTPException(
            status_code=401,
            detail="A protected key is required for quota-consuming refreshes",
        )

# =============================================================================
# API KEY MANAGER - Automatic rotation when quota runs out
# =============================================================================

class OddsAPIKeyManager:
    """Manages multiple Odds API keys with automatic rotation."""
    
    def __init__(self):
        self.keys = []
        self.current_index = 0
        self.key_usage = {}  # Track usage per key
        self.disabled_indices: set[int] = set()
        
        # Load keys from environment
        # Supports: ODDS_API_KEY, ODDS_API_KEY_1, ODDS_API_KEY_2, etc.
        primary_key = os.getenv("ODDS_API_KEY")
        if primary_key:
            self.keys.append(primary_key.strip())
        
        # Load numbered backup keys
        for i in range(1, 10):  # Support up to 9 backup keys
            key = os.getenv(f"ODDS_API_KEY_{i}")
            if key:
                key = key.strip()  # Remove any whitespace/newlines
                if key not in self.keys:
                    self.keys.append(key)
        
        print(f"[API Keys] Loaded {len(self.keys)} Odds API key(s)")
    
    @property
    def current_key(self) -> str | None:
        """Get the current active API key."""
        if not self.keys:
            return None
        return self.keys[self.current_index]
    
    def rotate_key(self) -> bool:
        """Rotate to the next available key. Returns True if successful."""
        if len(self.keys) <= 1:
            return False
        
        old_index = self.current_index
        for offset in range(1, len(self.keys) + 1):
            candidate = (old_index + offset) % len(self.keys)
            if candidate not in self.disabled_indices:
                self.current_index = candidate
                print(f"[API Keys] Rotated from key {old_index + 1} to key {self.current_index + 1}")
                return self.current_index != old_index
        
        return False
    
    def update_usage(self, remaining: int, used: int):
        """Update usage tracking for current key."""
        if self.current_key:
            self.key_usage[self.current_key[:8]] = {
                "remaining": remaining,
                "used": used,
            }
            
            # Auto-rotate if depleted or running low (less than 5 requests)
            if remaining <= 5 and len(self.keys) > 1:
                self.disabled_indices.add(self.current_index)
                print(f"[API Keys] Key {self.current_index + 1} running low ({remaining} remaining), rotating...")
                self.rotate_key()
    
    def mark_key_exhausted(self):
        """Mark current key as exhausted and rotate."""
        if self.current_key:
            exhausted_index = self.current_index
            self.key_usage[self.current_key[:8]] = {
                "remaining": 0,
                "used": 500,
                "exhausted": True,
            }
            self.disabled_indices.add(exhausted_index)
            print(f"[API Keys] Key {exhausted_index + 1} exhausted, rotating...")
            self.rotate_key()
    
    def get_status(self) -> dict:
        """Get status of all keys."""
        return {
            "total_keys": len(self.keys),
            "current_key_index": self.current_index + 1,
            "current_key_preview": f"{self.current_key[:8]}..." if self.current_key else None,
            "usage": self.key_usage,
        }
    
    def reload_keys(self):
        """Reload keys from environment (useful after adding new keys)."""
        self.keys = []
        self.current_index = 0
        self.disabled_indices = set()
        
        primary_key = os.getenv("ODDS_API_KEY")
        if primary_key:
            self.keys.append(primary_key.strip())
        
        for i in range(1, 10):
            key = os.getenv(f"ODDS_API_KEY_{i}")
            if key:
                key = key.strip()  # Remove whitespace
                if key not in self.keys:
                    self.keys.append(key)
        
        print(f"[API Keys] Reloaded {len(self.keys)} Odds API key(s)")
        return len(self.keys)

# Initialize the key manager
api_key_manager = OddsAPIKeyManager()

# Helper function to get current key (always fresh)
def get_odds_api_key() -> str | None:
    return api_key_manager.current_key

app = FastAPI(
    title="EV Dashboard API",
    description="Find +EV plays across DFS pick'em platforms",
    version="1.0.0"
)

# Allow frontend to access API
# More permissive CORS for development and Vercel preview deployments
allowed_origins = [
    FRONTEND_URL,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# CONSTANTS
# =============================================================================

# PrizePicks League IDs
PP_LEAGUE_IDS = {
    "nba": 7, "nfl": 2, "mlb": 3, "nhl": 8, 
    "ncaab": 10, "ncaaf": 4, "soccer": 17
}

# Underdog Sport mappings
UD_SPORTS = {"nba": "NBA", "nfl": "NFL", "mlb": "MLB", "nhl": "NHL"}

# Main sports for "all" queries
MAIN_SPORTS = ["nba", "nfl", "mlb", "nhl"]

# The Odds API sport keys
ODDS_API_SPORTS = {
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "ncaab": "basketball_ncaab",
    "ncaaf": "americanfootball_ncaaf",
}

# Prop type mappings (platform stat -> Odds API market)
# More comprehensive mappings for better coverage
PROP_MAPPINGS = {
    # NBA - Standard
    "Points": "player_points",
    "Rebounds": "player_rebounds",
    "Assists": "player_assists",
    "3-Point Made": "player_threes",
    "3-Pointers Made": "player_threes",
    "Three Pointers Made": "player_threes",
    "Pts+Rebs+Asts": "player_points_rebounds_assists",
    "Pts + Reb + Ast": "player_points_rebounds_assists",
    "Points + Rebounds + Assists": "player_points_rebounds_assists",
    "Steals": "player_steals",
    "Blocks": "player_blocks",
    "Turnovers": "player_turnovers",
    "Pts+Rebs": "player_points_rebounds",
    "Points + Rebounds": "player_points_rebounds",
    "Pts+Asts": "player_points_assists",
    "Points + Assists": "player_points_assists",
    "Rebs+Asts": "player_rebounds_assists",
    "Rebounds + Assists": "player_rebounds_assists",
    "Blks+Stls": "player_blocks_steals",
    "Blocks + Steals": "player_blocks_steals",
    "Fantasy Score": "player_points_rebounds_assists",  # Close approximation
    
    # NFL
    "Pass Yards": "player_pass_yds",
    "Passing Yards": "player_pass_yds",
    "Rush Yards": "player_rush_yds",
    "Rushing Yards": "player_rush_yds",
    "Receiving Yards": "player_reception_yds",
    "Rec Yards": "player_reception_yds",
    "Receptions": "player_receptions",
    "Pass TDs": "player_pass_tds",
    "Passing Touchdowns": "player_pass_tds",
    "Rush+Rec Yards": "player_rush_reception_yds",
    "Rushing + Receiving Yards": "player_rush_reception_yds",
    "Interceptions": "player_interceptions",
    "Completions": "player_completions",
    "Pass Attempts": "player_pass_attempts",
    "Longest Reception": "player_longest_reception",
    "Longest Rush": "player_longest_rush",
    
    # MLB
    "Strikeouts": "pitcher_strikeouts",
    "Pitcher Strikeouts": "pitcher_strikeouts",
    "Hits Allowed": "pitcher_hits_allowed",
    "Earned Runs": "pitcher_earned_runs",
    "Walks Allowed": "pitcher_walks",
    "Total Bases": "batter_total_bases",
    "Hits": "batter_hits",
    "RBIs": "batter_rbis",
    "Runs": "batter_runs",
    "Home Runs": "batter_home_runs",
    "Stolen Bases": "batter_stolen_bases",
    
    # NHL
    "Shots On Goal": "player_shots_on_goal",
    "Shots": "player_shots_on_goal",
    "Goals": "player_goals",
    "Points": "player_points",  # NHL points = goals + assists
    "Assists": "player_assists",
    "Saves": "goalie_saves",
    "Goals Against": "goalie_goals_against",
    "Power Play Points": "player_power_play_points",
    
    # Soccer
    "Shots": "player_shots",
    "Shots On Target": "player_shots_on_target",
    "Goals": "player_goals_scored",
    "Assists": "player_assists",
    "Tackles": "player_tackles",
    "Passes": "player_passes",
    
    # Underdog stat names (lowercase variations)
    "points": "player_points",
    "rebounds": "player_rebounds",
    "assists": "player_assists",
    "pts_rebs_asts": "player_points_rebounds_assists",
    "three_pointers_made": "player_threes",
    "threes": "player_threes",
    "steals": "player_steals",
    "blocks": "player_blocks",
    "turnovers": "player_turnovers",
    "passing_yards": "player_pass_yds",
    "rushing_yards": "player_rush_yds",
    "receiving_yards": "player_reception_yds",
    "receptions": "player_receptions",
    "shots_on_goal": "player_shots_on_goal",
}

# Ambiguous labels such as Points, Assists, Goals, and Shots must be resolved
# in the context of a sport rather than by one global dictionary.
SPORT_MARKET_MAPPINGS: dict[str, dict[str, str]] = {
    "nba": {
        "Points": "player_points",
        "Rebounds": "player_rebounds",
        "Assists": "player_assists",
        "Shots": "player_shots",
    },
    "nhl": {
        "Points": "player_points",
        "Assists": "player_assists",
        "Goals": "player_goals",
        "Shots": "player_shots_on_goal",
        "Shots On Goal": "player_shots_on_goal",
    },
    "soccer": {
        "Goals": "player_goals_scored",
        "Assists": "player_assists",
        "Shots": "player_shots",
        "Shots On Target": "player_shots_on_target",
    },
}


def market_for_stat(stat_type: str, sport: str) -> str | None:
    sport_map = SPORT_MARKET_MAPPINGS.get(sport.lower(), {})
    return sport_map.get(stat_type) or PROP_MAPPINGS.get(stat_type)


def canonical_market_key(market_key: str) -> str:
    return market_key.removesuffix("_alternate")

# Break-even percentages by platform and slip type
BREAKEVEN = {
    "prizepicks": {
        "5_flex": 54.34,
        "6_flex": 54.34,
        "4_power": 56.23,
        "2_power": 57.74,
        "default": 54.34,
    },
    "underdog": {
        "5_leg": 52.38,
        "4_leg": 53.57,
        "3_leg": 55.56,
        "2_leg": 60.00,
        "default": 52.38,
    },
    "sleeper": {
        "default": 54.00,  # Approximate, needs verification
    },
    "betr": {
        "default": 54.00,  # Approximate, needs verification
    },
}

# =============================================================================
# DATA MODELS
# =============================================================================

class Prop(BaseModel):
    id: str
    player_name: str
    team: str
    opponent: Optional[str] = None
    sport: str
    stat_type: str
    platform: str
    line: float
    game_time: Optional[str] = None
    event_id: Optional[str] = None
    market_key: Optional[str] = None
    is_alternate: bool = False
    captured_at: str = ""

class SharpOdds(BaseModel):
    bookmaker: str
    line: float
    over_odds: int
    under_odds: int
    over_probability: float
    under_probability: float

class EVPlay(BaseModel):
    prop: Prop
    sharp_odds: Optional[SharpOdds] = None
    recommended_play: str  # "OVER" or "UNDER"
    win_probability: float
    ev_percentage: float
    best_for: list[str]  # ["5_flex", "4_power", etc.]


class OutcomeUpdate(BaseModel):
    status: str
    result: Optional[str] = None
    stake: Optional[float] = None
    payout: Optional[float] = None
    closing_line: Optional[float] = None
    notes: Optional[str] = None


class EntryEVRequest(BaseModel):
    probabilities: list[float]
    payouts: dict[int, float]


class PaperSettlement(BaseModel):
    result: str
    payout: float


class MiddleOpportunity(BaseModel):
    player_name: str
    stat_type: str
    sport: str
    platform_a: dict
    platform_b: dict
    spread: float
    middle_zone: list[float]

class GameSummary(BaseModel):
    id: str
    sport: str
    home_team: str
    away_team: str
    start_time: str
    prop_count: int
    ev_play_count: int
    top_ev_play: Optional[dict] = None

# =============================================================================
# PLATFORM FETCHERS
# =============================================================================

async def fetch_prizepicks_direct(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """Fetch props from PrizePicks API."""
    league_id = PP_LEAGUE_IDS.get(sport.lower())
    if not league_id:
        print(f"[PrizePicks Direct] Unknown sport: {sport}")
        return []
    
    url = f"https://api.prizepicks.com/projections?league_id={league_id}&per_page=250&single_stat=true"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Referer": "https://app.prizepicks.com/",
        "Origin": "https://app.prizepicks.com",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors", 
        "sec-fetch-site": "same-site",
    }
    
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            print(f"[PrizePicks Direct] API response status: {resp.status} for {sport.upper()}")
            if resp.status != 200:
                print(f"[PrizePicks Direct] Failed - status {resp.status}")
                return []
            
            data = await resp.json()
            included = {i["id"]: i for i in data.get("included", [])}
            props = []
            
            for proj in data.get("data", []):
                attrs = proj.get("attributes", {})
                player_id = proj.get("relationships", {}).get("new_player", {}).get("data", {}).get("id")
                player_data = included.get(player_id, {}).get("attributes", {})
                
                props.append(Prop(
                    id=f"pp_{proj.get('id', '')}",
                    player_name=player_data.get("name", "Unknown"),
                    team=player_data.get("team", ""),
                    sport=sport.upper(),
                    stat_type=attrs.get("stat_type", ""),
                    platform="prizepicks",
                    line=float(attrs.get("line_score", 0)),
                    game_time=attrs.get("start_time", ""),
                ))
            
            print(f"[PrizePicks Direct] Got {len(props)} props for {sport.upper()}")
            return props
    except Exception as e:
        print(f"[PrizePicks Direct] Error: {e}")
        import traceback
        traceback.print_exc()
        return []



# -------------------------------
# DFS via The Odds API (us_dfs)
# -------------------------------

DFS_BOOKMAKER_KEYS = {
    "prizepicks": "prizepicks",
    "betr": "betr_us_dfs",
}

DFS_MARKETS_BY_SPORT: dict[str, list[str]] = {
    "nba": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_points_rebounds_assists",
        "player_points_rebounds",
        "player_points_assists",
        "player_rebounds_assists",
        "player_steals",
        "player_blocks",
        "player_blocks_steals",
        "player_turnovers",
        "player_double_double",
        "player_first_basket",
    ],
    "nfl": [
        "player_pass_yds",
        "player_rush_yds",
        "player_reception_yds",
        "player_receptions",
        "player_pass_tds",
        "player_rush_tds",
        "player_reception_tds",
        "player_rush_reception_yds",
        "player_interceptions",
        "player_completions",
        "player_pass_attempts",
        "player_anytime_td",
    ],
    "mlb": [
        "pitcher_strikeouts",
        "pitcher_hits_allowed",
        "pitcher_earned_runs",
        "pitcher_walks",
        "batter_total_bases",
        "batter_hits",
        "batter_rbis",
        "batter_runs",
        "batter_home_runs",
        "batter_stolen_bases",
    ],
    "nhl": [
        "player_shots_on_goal",
        "player_goals",
        "player_assists",
        "player_points",
        "player_power_play_points",
        "goalie_saves",
    ],
    "soccer": [
        "player_shots",
        "player_shots_on_target",
        "player_goals_scored",
        "player_assists",
    ],
}

def market_to_stat(market_key: str, sport: str) -> str:
    """Return a stable display label for standard and alternate markets."""
    canonical = canonical_market_key(market_key)
    sport_map = SPORT_MARKET_MAPPINGS.get(sport.lower(), {})
    for stat_label, mapped_market in sport_map.items():
        if mapped_market == canonical:
            return stat_label
    for stat_label, mapped_market in PROP_MAPPINGS.items():
        if (
            isinstance(stat_label, str)
            and stat_label
            and stat_label[0].isupper()
            and mapped_market == canonical
        ):
            return stat_label
    return canonical

def _safe_id(*parts: str) -> str:
    raw = "|".join([p or "" for p in parts])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


async def _odds_api_get(
    session: aiohttp.ClientSession,
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = 20,
) -> tuple[int, Any]:
    """GET The Odds API with quota tracking and bounded key rotation."""
    request_params = dict(params or {})
    attempts = max(1, len(api_key_manager.keys))

    for _ in range(attempts):
        request_params["apiKey"] = get_odds_api_key()
        try:
            async with session.get(url, params=request_params, timeout=timeout) as response:
                remaining = response.headers.get("x-requests-remaining")
                used = response.headers.get("x-requests-used")
                if (
                    response.status not in {401, 403, 429}
                    and remaining
                    and used
                    and remaining.isdigit()
                    and used.isdigit()
                ):
                    api_key_manager.update_usage(int(remaining), int(used))

                try:
                    payload = await response.json(content_type=None)
                except Exception:
                    payload = {"message": (await response.text())[:500]}

                if response.status not in {401, 403, 429}:
                    return response.status, payload

                api_key_manager.mark_key_exhausted()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return 599, {"message": str(exc)}

    return 429, {"message": "No Odds API key with remaining quota"}


async def fetch_dfs_props_from_odds_api(
    session: aiohttp.ClientSession,
    sport: str,
    platform_key: str,
) -> list[Prop]:
    """Fetch DFS props using only markets advertised for each event.

    The event-markets discovery call prevents a single unsupported market from
    invalidating the entire request with HTTP 422.
    """
    if not get_odds_api_key():
        return []

    sport_l = sport.lower()
    sport_key = ODDS_API_SPORTS.get(sport_l)
    if not sport_key:
        return []

    bookmaker_key = DFS_BOOKMAKER_KEYS.get(platform_key.lower())
    if not bookmaker_key:
        return []

    markets = DFS_MARKETS_BY_SPORT.get(sport_l, [])
    if not markets:
        return []

    events_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
    event_status, events = await _odds_api_get(
        session,
        events_url,
        {"dateFormat": "iso"},
        timeout=15,
    )
    if event_status != 200 or not isinstance(events, list):
        print(f"[DFS Props] Events fetch failed ({platform_key}): {event_status} {events}")
        return []

    now = datetime.now(timezone.utc)
    lookahead = now + timedelta(hours=int(os.getenv("DFS_LOOKAHEAD_HOURS", "36")))
    upcoming_events = []
    for event in events:
        try:
            commence = datetime.fromisoformat(event.get("commence_time", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if now - timedelta(hours=2) <= commence <= lookahead:
            upcoming_events.append(event)

    event_limit = max(1, int(os.getenv("DFS_EVENT_LIMIT", "8")))
    market_limit = max(1, int(os.getenv("DFS_MARKET_LIMIT", "4")))
    sem = asyncio.Semaphore(4)

    async def _fetch_event_odds(event: dict) -> list[dict]:
        event_id = event.get("id")
        if not event_id:
            return []

        base_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event_id}"
        discovery_params = {
            "regions": "us_dfs",
            "bookmakers": bookmaker_key,
            "dateFormat": "iso",
        }
        async with sem:
            discovery_status, discovery = await _odds_api_get(
                session,
                f"{base_url}/markets",
                discovery_params,
            )
        if discovery_status != 200 or not isinstance(discovery, dict):
            print(f"[DFS Props] Market discovery failed for {event_id}: {discovery_status}")
            return []

        desired_bases = set(markets)
        available = {
            market.get("key")
            for bookmaker in discovery.get("bookmakers", [])
            if bookmaker.get("key") == bookmaker_key
            for market in bookmaker.get("markets", [])
            if market.get("key")
        }
        selected = []
        for desired_market in markets:
            if desired_market not in desired_bases:
                continue
            if desired_market in available:
                selected.append(desired_market)
            alternate = f"{desired_market}_alternate"
            if alternate in available:
                selected.append(alternate)
            if len(selected) >= market_limit:
                break
        selected = selected[:market_limit]
        if not selected:
            return []

        odds_params = {
            "regions": "us_dfs",
            "markets": ",".join(selected),
            "bookmakers": bookmaker_key,
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        async with sem:
            odds_status, odds_payload = await _odds_api_get(
                session,
                f"{base_url}/odds",
                odds_params,
            )
        if odds_status == 200 and isinstance(odds_payload, dict):
            return [odds_payload]

        # Defensive fallback: isolate a provider-side market failure.
        if odds_status == 422:
            payloads = []
            for selected_market in selected:
                single_params = dict(odds_params, markets=selected_market)
                async with sem:
                    single_status, single_payload = await _odds_api_get(
                        session,
                        f"{base_url}/odds",
                        single_params,
                    )
                if single_status == 200 and isinstance(single_payload, dict):
                    payloads.append(single_payload)
            return payloads

        print(f"[DFS Props] Odds fetch failed for {event_id}: {odds_status}")
        return []

    payload_groups = await asyncio.gather(
        *[_fetch_event_odds(event) for event in upcoming_events[:event_limit]]
    )
    odds_payloads = [payload for group in payload_groups for payload in group]

    props: list[Prop] = []
    platform_norm = platform_key.lower()
    sport_norm = sport_l.upper()
    captured_at = datetime.now(timezone.utc).isoformat()
    seen_props: set[tuple[str, str, float, str]] = set()

    for payload in odds_payloads:
        commence_time = payload.get("commence_time") or payload.get("commenceTime")
        event_id = payload.get("id") or ""
        home = payload.get("home_team") or ""
        away = payload.get("away_team") or ""
        opponent_label = f"{away} @ {home}" if home and away else None

        for bookmaker in payload.get("bookmakers", []) or []:
            for mkt in bookmaker.get("markets", []) or []:
                market_key = mkt.get("key") or ""
                stat_type = market_to_stat(market_key, sport_l)
                for outcome in mkt.get("outcomes", []) or []:
                    player = outcome.get("description") or outcome.get("participant") or ""
                    point = outcome.get("point")
                    if not player or point is None:
                        continue

                    dedupe_key = (player, market_key, float(point), str(event_id))
                    if dedupe_key in seen_props:
                        continue
                    seen_props.add(dedupe_key)

                    prop_id = _safe_id(platform_norm, sport_norm, market_key, player, str(point), str(event_id))
                    props.append(Prop(
                        id=prop_id,
                        player_name=player,
                        team="",
                        opponent=opponent_label,
                        sport=sport_norm,
                        stat_type=stat_type,
                        platform=platform_norm,
                        line=float(point),
                        game_time=commence_time,
                        event_id=str(event_id),
                        market_key=canonical_market_key(market_key),
                        is_alternate=market_key.endswith("_alternate"),
                        captured_at=captured_at,
                    ))

    return props

async def fetch_prizepicks(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """Fetch PrizePicks props via Odds API (direct API is blocked by captcha)."""
    # NOTE: PrizePicks direct API is blocked by PerimeterX captcha on server requests
    # Must use Odds API with us_dfs region instead (costs API quota)
    
    props = await fetch_dfs_props_from_odds_api(session, sport, "prizepicks")
    if props:
        print(f"[PrizePicks] Got {len(props)} props from Odds API for {sport.upper()}")
    else:
        print(f"[PrizePicks] No props found for {sport.upper()} (Odds API may not have data)")
    return props


async def fetch_underdog(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """Fetch props from Underdog Fantasy API - TESTED AND WORKING."""
    # Underdog uses sport_id as a string like "NBA", "NFL", etc.
    target_sport = sport.upper()
    
    url = "https://api.underdogfantasy.com/beta/v6/over_under_lines"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Origin": "https://underdogfantasy.com",
        "Referer": "https://underdogfantasy.com/",
    }
    
    try:
        async with session.get(url, headers=headers, timeout=30) as resp:
            print(f"[Underdog] API response status: {resp.status}")
            if resp.status != 200:
                print(f"[Underdog] Failed to fetch - status {resp.status}")
                return []
            
            data = await resp.json()
            
            # Build lookup dictionaries
            # games[].id is numeric, sport_id is string like "NBA"
            games = {g["id"]: g for g in data.get("games", [])}
            # appearances[].id is UUID string, has match_id (numeric) and player_id (UUID)
            appearances = {a["id"]: a for a in data.get("appearances", [])}
            # players[].id is UUID string
            players = {p["id"]: p for p in data.get("players", [])}
            
            print(f"[Underdog] Found {len(games)} games, {len(appearances)} appearances, {len(players)} players")
            
            # Get all over_under_lines
            lines = data.get("over_under_lines", [])
            print(f"[Underdog] Found {len(lines)} over_under_lines")
            
            props = []
            for line in lines:
                try:
                    # Get the over_under object which contains appearance_stat
                    ou = line.get("over_under", {})
                    app_stat = ou.get("appearance_stat", {})
                    
                    # Get appearance_id from appearance_stat (it's like "uuid-uuid")
                    app_id = app_stat.get("appearance_id")
                    app = appearances.get(app_id, {})
                    
                    # Get game via match_id from appearance
                    match_id = app.get("match_id")
                    game = games.get(match_id, {})
                    
                    # Filter by sport - game.sport_id is a string like "NBA"
                    game_sport = game.get("sport_id", "")
                    if game_sport != target_sport:
                        continue
                    
                    # Get player info via player_id from appearance
                    player_id = app.get("player_id")
                    player = players.get(player_id, {})
                    
                    # Get stat type from appearance_stat
                    stat_type = app_stat.get("display_stat") or app_stat.get("stat") or ""
                    
                    # Get line value - it's a STRING in the API!
                    stat_value = line.get("stat_value")
                    
                    if stat_value is not None and player:
                        name = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
                        
                        if name:
                            # Get team from game title (e.g., "MIL @ BOS" -> "MIL")
                            game_title = game.get("title", "") or game.get("abbreviated_title", "")
                            team = game_title.split(" @ ")[0] if " @ " in game_title else ""
                            
                            props.append(Prop(
                                id=f"ud_{line.get('id', '')}",
                                player_name=name,
                                team=team,
                                sport=target_sport,
                                stat_type=stat_type,
                                platform="underdog",
                                line=float(stat_value),  # Convert string to float
                                game_time=game.get("scheduled_at", ""),
                            ))
                except Exception as e:
                    # Skip this line if there's an error parsing it
                    continue
            
            print(f"[Underdog] Returning {len(props)} props for {target_sport}")
            return props
    except Exception as e:
        print(f"[Underdog] Error: {e}")
        import traceback
        traceback.print_exc()
        return []


async def fetch_sleeper_picks(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """
    Fetch props from Sleeper Picks.
    
    NOTE: Sleeper Picks (the pick'em product) uses a DIFFERENT API than the 
    fantasy football API documented at docs.sleeper.com. The pick'em API 
    endpoints need to be discovered through browser network inspection.
    
    Known info:
    - Sleeper Picks is at sleeper.com/picks
    - May use api.sleeper.com or a different subdomain
    - Requires further research to find endpoints
    """
    # TODO: Research Sleeper Picks API
    # The documented Sleeper API (api.sleeper.app) is for fantasy leagues,
    # not their pick'em product. Need to inspect network traffic on sleeper.com/picks
    return []



async def fetch_betr_picks(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """Fetch Betr Picks props via The Odds API `us_dfs`."""
    # Temporarily disabled to save API calls
    return []
    # return await fetch_dfs_props_from_odds_api(session, sport, "betr")

async def fetch_chalkboard(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """
    Fetch props from Chalkboard.
    
    Since you mentioned you already have Chalkboard working, you can add
    your implementation here. The structure should be similar to PrizePicks/Underdog.
    """
    # TODO: Add your Chalkboard implementation here
    # Return format should match other fetch functions:
    # return [Prop(id=..., player_name=..., team=..., sport=..., stat_type=..., platform="chalkboard", line=...)]
    return []


async def collect_props(
    session: aiohttp.ClientSession,
    sport: str,
    *,
    refresh: bool = False,
) -> tuple[list[Prop], bool]:
    """Canonical, single-flight prop collection used by every client."""
    cache_key = f"props_{sport.lower()}"
    if not refresh:
        cached, fresh = cache.get(cache_key)
        if cached is not None:
            return cached, fresh
        latest = store.latest_run("props", sport)
        if latest is not None:
            captured_at = datetime.fromisoformat(latest["captured_at"])
            max_age = int(os.getenv("PUBLIC_PROP_MAX_AGE_MINUTES", "60")) * 60
            if (datetime.now(timezone.utc) - captured_at).total_seconds() <= max_age:
                restored = [
                    Prop(**payload)
                    for payload in latest["payload"].get("props", [])
                ]
                cache.set(cache_key, restored)
                return restored, False
        return [], False

    async with refresh_locks[cache_key]:
        sports_to_fetch = MAIN_SPORTS if sport.lower() == "all" else [sport.lower()]
        tasks = []
        for current_sport in sports_to_fetch:
            tasks.extend(
                [
                    fetch_prizepicks(session, current_sport),
                    fetch_underdog(session, current_sport),
                    fetch_betr_picks(session, current_sport),
                    fetch_chalkboard(session, current_sport),
                ]
            )
        results = await asyncio.gather(*tasks)
        props = [prop for result in results for prop in result]
        captured_at = datetime.now(timezone.utc).isoformat()
        for prop in props:
            if not prop.market_key:
                prop.market_key = market_for_stat(prop.stat_type, prop.sport)
            if not prop.captured_at:
                prop.captured_at = captured_at
        cache.set(cache_key, props)
        store.save_run(
            "props",
            sport,
            "ok" if props else "empty",
            {"props": [prop.model_dump() for prop in props]},
            {
                "count": len(props),
                "platforms": {
                    platform: sum(1 for prop in props if prop.platform == platform)
                    for platform in sorted({prop.platform for prop in props})
                },
            },
        )
        return props, True

# =============================================================================
# SHARP ODDS FETCHER
# =============================================================================

# Preferred sharp books in order of priority
# Pinnacle is the sharpest (from EU region), then major US books
SHARP_BOOKS = [
    "pinnacle",      # Sharpest book in the world (EU region)
    "draftkings",    # Sharp US book
    "fanduel",       # Sharp US book
    "betmgm",        # Major US book
    "bovada",        # Good for player props
    "betonlineag",   # BetOnline - good prop coverage
    "caesars",       # Major US book
    "betrivers",     # US regional
    "lowvig",        # Low vig book
    "mybookieag",    # MyBookie
    "espnbet",       # ESPN Bet
    "hardrockbet",   # Hard Rock
    "betparx",       # betPARX
    "betus",         # BetUS
    "fliff",         # Fliff
]

# Market priority for EV (fetch these first to maximize matches)
MARKET_PRIORITY_BY_SPORT = {
    "nba": DFS_MARKETS_BY_SPORT["nba"],
    "nfl": DFS_MARKETS_BY_SPORT["nfl"],
    "mlb": DFS_MARKETS_BY_SPORT["mlb"],
    "nhl": DFS_MARKETS_BY_SPORT["nhl"],
}

# Reduce calls to keep EV endpoint responsive
SHARP_EVENT_LIMIT = int(os.getenv("SHARP_EVENT_LIMIT", "8"))
SHARP_MARKET_LIMIT = int(os.getenv("SHARP_MARKET_LIMIT", "4"))

async def fetch_sharp_odds(
    session: aiohttp.ClientSession,
    sport: str,
    market: str,
    event_ids: set[str] | None = None,
    commence_times: set[str] | None = None,
) -> list[dict]:
    """Fetch sportsbook prices for a market and relevant event IDs."""
    if not get_odds_api_key():
        return []
    
    sport_key = ODDS_API_SPORTS.get(sport.lower())
    if not sport_key:
        return []
    
    try:
        events: list[dict] = [
            {"id": event_id}
            for event_id in sorted(event_ids or set())
        ]
        events_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
        if commence_times or not events:
            status, payload = await _odds_api_get(session, events_url, timeout=15)
            if status != 200 or not isinstance(payload, list):
                return []
            if commence_times:
                target_times = []
                for value in commence_times:
                    try:
                        target_times.append(
                            datetime.fromisoformat(value.replace("Z", "+00:00"))
                        )
                    except ValueError:
                        continue
                matching_events = []
                for event in payload:
                    try:
                        event_time = datetime.fromisoformat(
                            event.get("commence_time", "").replace("Z", "+00:00")
                        )
                    except ValueError:
                        continue
                    if any(
                        abs((event_time - target).total_seconds()) <= 15 * 60
                        for target in target_times
                    ):
                        matching_events.append(event)
                known_ids = {event["id"] for event in events}
                events.extend(
                    event
                    for event in matching_events
                    if event.get("id") not in known_ids
                )
            elif not events:
                events = payload
        
        all_odds = []
        
        sem = asyncio.Semaphore(4)

        async def _fetch_event(event: dict) -> list[dict]:
            odds_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event['id']}/odds"
            params = {
                "regions": "us,us2,eu",  # US + EU to get Pinnacle (sharpest book)
                "markets": market,
                "oddsFormat": "american",
                # Request sharp books - Pinnacle is sharpest, then US books
                "bookmakers": "pinnacle,draftkings,fanduel,betmgm,bovada,betonlineag,caesars,betrivers,lowvig,mybookieag",
            }

            async with sem:
                status, data = await _odds_api_get(session, odds_url, params)
            if status != 200 or not isinstance(data, dict):
                print(f"[Sharp Odds] Event {event['id']} returned status {status}")
                return []

            # Sort bookmakers by our preference order (Pinnacle first = sharpest)
            bookmakers = data.get("bookmakers", [])
            bookmakers.sort(key=lambda b: SHARP_BOOKS.index(b["key"]) if b["key"] in SHARP_BOOKS else 999)

            event_odds: list[dict] = []
            for bookmaker in bookmakers:
                for mkt in bookmaker.get("markets", []):
                    if mkt["key"] != market:
                        continue

                    # Group outcomes by player
                    player_outcomes = {}
                    for outcome in mkt.get("outcomes", []):
                        player = outcome.get("description", "")
                        if player not in player_outcomes:
                            player_outcomes[player] = {}

                        name = outcome.get("name", "").lower()
                        if "over" in name:
                            player_outcomes[player]["over"] = outcome
                        elif "under" in name:
                            player_outcomes[player]["under"] = outcome

                    for player, outcomes in player_outcomes.items():
                        if "over" in outcomes and "under" in outcomes:
                            # Determine if this is a sharp book
                            # Pinnacle is sharpest, then DK/FD
                            is_sharp = bookmaker["key"] in ["pinnacle", "draftkings", "fanduel", "lowvig"]

                            event_odds.append({
                                "player": player,
                                "line": outcomes["over"].get("point", 0),
                                "over_odds": outcomes["over"].get("price", -110),
                                "under_odds": outcomes["under"].get("price", -110),
                                "bookmaker": bookmaker["key"],
                                "market": market,
                                "is_sharp": is_sharp,
                                "event_id": str(event["id"]),
                                "commence_time": data.get("commence_time"),
                                "home_team": data.get("home_team"),
                                "away_team": data.get("away_team"),
                                "last_update": mkt.get("last_update"),
                            })

            return event_odds

        events = events[:SHARP_EVENT_LIMIT]
        results = await asyncio.gather(*[_fetch_event(e) for e in events])
        for event_odds in results:
            all_odds.extend(event_odds)
        
        print(f"[Sharp Odds] Found {len(all_odds)} odds entries for {market} in {sport}")
        return all_odds
    except Exception as e:
        print(f"Odds API error: {e}")
        import traceback
        traceback.print_exc()
        return []

# =============================================================================
# CALCULATIONS
# =============================================================================

def calculate_no_vig(over_odds: int, under_odds: int) -> tuple[float, float]:
    """Calculate true probabilities by removing the vig."""
    def implied_prob(odds: int) -> float:
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    
    over_implied = implied_prob(over_odds)
    under_implied = implied_prob(under_odds)
    total = over_implied + under_implied
    
    over_true = (over_implied / total) * 100
    under_true = (under_implied / total) * 100
    
    return over_true, under_true


BOOK_WEIGHTS = {
    "pinnacle": 3.0,
    "lowvig": 2.5,
    "draftkings": 2.0,
    "fanduel": 2.0,
    "betonlineag": 1.5,
    "bovada": 1.5,
}


def probability_to_american(probability: float) -> int:
    probability = min(max(probability / 100, 0.0001), 0.9999)
    if probability >= 0.5:
        return round(-100 * probability / (1 - probability))
    return round(100 * (1 - probability) / probability)


def calculate_entry_ev(
    probabilities: list[float],
    payouts: dict[int, float],
) -> dict[str, Any]:
    """Calculate payout-aware entry EV under an independence assumption.

    ``payouts`` maps the number of winning legs to total return multiplier,
    including returned stake. This supports power and flex payout tables
    without hardcoding platform offers that can change.
    """
    if not 2 <= len(probabilities) <= 8:
        raise ValueError("Entry must contain between 2 and 8 legs")
    if any(probability <= 0 or probability >= 100 for probability in probabilities):
        raise ValueError("Probabilities must be percentages strictly between 0 and 100")

    distribution = [1.0]
    for percentage in probabilities:
        probability = percentage / 100
        next_distribution = [0.0] * (len(distribution) + 1)
        for wins, current_probability in enumerate(distribution):
            next_distribution[wins] += current_probability * (1 - probability)
            next_distribution[wins + 1] += current_probability * probability
        distribution = next_distribution

    expected_return = sum(
        distribution[wins] * float(payouts.get(wins, 0))
        for wins in range(len(distribution))
    )
    return {
        "legs": len(probabilities),
        "expected_return_multiplier": round(expected_return, 4),
        "expected_roi_percentage": round((expected_return - 1) * 100, 2),
        "outcome_probabilities": {
            wins: round(probability * 100, 4)
            for wins, probability in enumerate(distribution)
        },
        "assumption": "independent_legs",
    }


def build_consensus(prop: Prop, odds_rows: list[dict]) -> dict[str, Any] | None:
    """Build a weighted exact-line consensus for one prop.

    Different sportsbook lines remain visible for comparison but are never
    used to infer the probability at the PrizePicks line.
    """
    player_rows = []
    for row in odds_rows:
        if prop.event_id and row.get("event_id") and row["event_id"] != prop.event_id:
            continue
        if abs(float(row["line"]) - prop.line) > 0.001:
            continue
        player_rows.append(row)

    if not player_rows:
        return None

    weighted_over = 0.0
    weighted_under = 0.0
    total_weight = 0.0
    probabilities = []
    for row in player_rows:
        over_probability, under_probability = calculate_no_vig(
            row["over_odds"],
            row["under_odds"],
        )
        weight = BOOK_WEIGHTS.get(row["bookmaker"], 1.0)
        weighted_over += over_probability * weight
        weighted_under += under_probability * weight
        total_weight += weight
        probabilities.append(
            {
                "bookmaker": row["bookmaker"],
                "over_probability": round(over_probability, 2),
                "under_probability": round(under_probability, 2),
                "weight": weight,
            }
        )

    consensus_over = weighted_over / total_weight
    consensus_under = weighted_under / total_weight
    recommended = "OVER" if consensus_over > consensus_under else "UNDER"
    win_probability = max(consensus_over, consensus_under)
    supporting_probabilities = [
        item["over_probability"] if recommended == "OVER" else item["under_probability"]
        for item in probabilities
    ]
    dispersion = (
        max(supporting_probabilities) - min(supporting_probabilities)
        if len(supporting_probabilities) > 1
        else 0.0
    )
    confidence = "high" if len(player_rows) >= 3 and dispersion <= 3 else "medium" if len(player_rows) >= 2 else "low"

    return {
        "recommended_play": recommended,
        "win_probability": win_probability,
        "over_probability": consensus_over,
        "under_probability": consensus_under,
        "fair_odds": probability_to_american(win_probability),
        "book_count": len(player_rows),
        "dispersion": round(dispersion, 2),
        "confidence": confidence,
        "book_probabilities": probabilities,
        "exact_line_odds": player_rows,
    }


def match_player(name: str, candidates: list[str], threshold: int = 80) -> Optional[str]:
    """Fuzzy match a player name to a list of candidates."""
    def normalize(n: str) -> str:
        n = n.lower().strip()
        for suffix in [" jr.", " sr.", " iii", " ii", " iv"]:
            n = n.replace(suffix, "")
        return n
    
    name_norm = normalize(name)
    best_match = None
    best_score = 0
    
    for candidate in candidates:
        cand_norm = normalize(candidate)
        score = max(
            fuzz.ratio(name_norm, cand_norm),
            fuzz.partial_ratio(name_norm, cand_norm),
            fuzz.token_sort_ratio(name_norm, cand_norm),
        )
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate
    
    return best_match


def get_best_slip_types(win_prob: float, platform: str) -> list[str]:
    """Get which slip types are +EV for a given win probability."""
    breakevens = BREAKEVEN.get(platform, BREAKEVEN["prizepicks"])
    result = []
    
    for slip_type, be in breakevens.items():
        if slip_type != "default" and win_prob >= be:
            result.append(slip_type)
    
    return result

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    return {"message": "EV Dashboard API", "version": "1.0.0"}


@app.get("/api/hermes/candidates", dependencies=[Depends(require_hermes_key)])
async def hermes_candidates(
    sport: str = Query("mlb"),
    platform: str = Query("all"),
    max_age_minutes: int = Query(15, ge=1, le=1440),
):
    """Return the latest durable candidate snapshot without spending API quota."""
    run = store.latest_run("ev", sport)
    if run is None:
        raise HTTPException(status_code=404, detail="No candidate snapshot available")

    captured_at = datetime.fromisoformat(run["captured_at"])
    age_seconds = (datetime.now(timezone.utc) - captured_at).total_seconds()
    if age_seconds > max_age_minutes * 60:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Candidate snapshot is stale",
                "captured_at": run["captured_at"],
                "age_seconds": round(age_seconds),
            },
        )

    payload = run["payload"]
    plays = payload.get("plays", [])
    if platform.lower() != "all":
        plays = [
            play
            for play in plays
            if play.get("prop", {}).get("platform") == platform.lower()
        ]
    return {
        "run_id": run["id"],
        "captured_at": run["captured_at"],
        "age_seconds": round(age_seconds, 1),
        "sport": sport.upper(),
        "count": len(plays),
        "plays": plays,
        "metrics": run["metrics"],
    }


@app.get("/api/hermes/runs", dependencies=[Depends(require_hermes_key)])
async def hermes_runs(limit: int = Query(25, ge=1, le=100)):
    """Return pipeline health history for Hermes monitoring."""
    return {"runs": store.recent_runs(limit)}


@app.post("/api/hermes/scan", dependencies=[Depends(require_hermes_key)])
async def hermes_scan(
    sport: str = Query("mlb"),
    platform: str = Query("all"),
    min_ev: float = Query(0),
    min_win: float = Query(54),
    min_books: int = Query(2, ge=1, le=5),
):
    """Run one explicit, quota-consuming scan for Hermes."""
    normalized_sport = sport.lower()
    if normalized_sport not in MAIN_SPORTS:
        raise HTTPException(
            status_code=422,
            detail=f"sport must be one of {MAIN_SPORTS}; scan sports separately",
        )
    normalized_platform = platform.lower()
    if normalized_platform not in {"all", "prizepicks", "underdog"}:
        raise HTTPException(
            status_code=422,
            detail="platform must be all, prizepicks, or underdog",
        )
    return await get_ev_plays(
        sport=normalized_sport,
        platform=None if normalized_platform == "all" else normalized_platform,
        min_ev=min_ev,
        min_win=min_win,
        min_books=min_books,
        refresh=True,
        x_admin_key=None,
        x_hermes_key=HERMES_API_KEY,
    )


@app.post("/api/hermes/outcomes/{candidate_id}", dependencies=[Depends(require_hermes_key)])
async def hermes_record_outcome(candidate_id: str, update: OutcomeUpdate):
    """Record settlement and closing-line data for the learning loop."""
    allowed_statuses = {"open", "submitted", "settled", "void", "rejected"}
    if update.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(allowed_statuses)}")
    store.record_outcome(
        candidate_id,
        status=update.status,
        result=update.result,
        stake=update.stake,
        payout=update.payout,
        closing_line=update.closing_line,
        notes=update.notes,
    )
    return {"success": True, "candidate_id": candidate_id, "status": update.status}


async def _paper_slate_gate(
    session: aiohttp.ClientSession,
    sport: str,
) -> dict[str, Any]:
    sport_key = ODDS_API_SPORTS.get(sport)
    if not sport_key:
        raise HTTPException(status_code=422, detail=f"Unsupported sport: {sport}")
    events_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
    status, payload = await _odds_api_get(session, events_url, timeout=15)
    if status != 200 or not isinstance(payload, list):
        return {"due": False, "reason": "schedule_unavailable", "events": []}

    now = datetime.now(timezone.utc)
    eligible = []
    for event in payload:
        try:
            commence_time = datetime.fromisoformat(
                event.get("commence_time", "").replace("Z", "+00:00")
            )
        except ValueError:
            continue
        minutes_to_start = (commence_time - now).total_seconds() / 60
        if 5 < minutes_to_start <= 360:
            eligible.append(
                {
                    "id": event.get("id"),
                    "commence_time": event.get("commence_time"),
                    "home_team": event.get("home_team"),
                    "away_team": event.get("away_team"),
                    "minutes_to_start": round(minutes_to_start, 1),
                }
            )
    if not eligible:
        return {"due": False, "reason": "no_events_within_six_hours", "events": []}

    nearest_minutes = min(event["minutes_to_start"] for event in eligible)
    interval_seconds = 900 if nearest_minutes <= 30 else 1800 if nearest_minutes <= 120 else 3600
    state = store.get_state(f"paper_scan:{sport}") or {}
    last_scan_value = state.get("last_scan_at")
    seconds_since_scan = None
    if last_scan_value:
        try:
            last_scan = datetime.fromisoformat(last_scan_value)
            seconds_since_scan = (now - last_scan).total_seconds()
        except ValueError:
            pass
    due = seconds_since_scan is None or seconds_since_scan >= interval_seconds
    return {
        "due": due,
        "reason": None if due else "cadence_not_due",
        "events": eligible,
        "interval_seconds": interval_seconds,
        "seconds_since_scan": round(seconds_since_scan, 1) if seconds_since_scan is not None else None,
        "nearest_minutes": nearest_minutes,
    }


def _paper_scheduler_status() -> dict[str, Any]:
    if paper_scheduler is None:
        return {
            "enabled": PAPER_SCHEDULER_ENABLED,
            "running": False,
            "message": "scheduler_not_started",
        }
    return paper_scheduler.status()


async def run_paper_delivery() -> dict[str, Any]:
    pending = store.list_pending_delivery()
    sent = 0
    failed = 0
    async with aiohttp.ClientSession() as session:
        for entry in pending:
            result = await deliver_paper_entry(session, entry)
            store.mark_delivery(
                entry["id"],
                status=result["status"],
                error=result.get("error"),
            )
            if result["success"]:
                sent += 1
            else:
                failed += 1
    return {"pending": len(pending), "sent": sent, "failed": failed}


async def run_paper_settlement() -> dict[str, Any]:
    store.freeze_closing_lines_past_lock()
    open_entries = store.list_open_paper_entries()
    async with aiohttp.ClientSession() as session:
        actions = await settle_mlb_entries(session, open_entries)
    settled = 0
    pending = 0
    for action in actions:
        if action.get("status") == "settled":
            if store.apply_settlement(
                action["entry_id"],
                result=action["result"],
                payout=action["payout"],
                legs=action.get("legs"),
                provenance=action.get("provenance"),
            ):
                settled += 1
        else:
            pending += 1
    return {"settled": settled, "pending": pending, "actions": len(actions)}


async def run_paper_tick(sport: str) -> dict[str, Any]:
    """Quota-gated paper scan used by Hermes and the Railway scheduler."""
    normalized_sport = sport.lower()
    if normalized_sport not in MAIN_SPORTS:
        raise HTTPException(status_code=422, detail=f"sport must be one of {MAIN_SPORTS}")

    async with refresh_locks[f"paper_tick:{normalized_sport}"]:
        async with aiohttp.ClientSession() as session:
            gate = await _paper_slate_gate(session, normalized_sport)
        if not gate["due"]:
            latest = {
                "status": "waiting",
                "sport": normalized_sport.upper(),
                "message": gate["reason"],
                "gate": gate,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            store.set_state("paper_latest", latest)
            return {**latest, "created_entries": [], "created_count": 0}

        today = datetime.now(timezone.utc).date().isoformat()
        budget_state = store.get_state("paper_scan_budget") or {}
        scans_today = (
            int(budget_state.get("count", 0))
            if budget_state.get("date") == today
            else 0
        )
        if scans_today >= PAPER_DAILY_SCAN_CAP:
            latest = {
                "status": "waiting",
                "sport": normalized_sport.upper(),
                "message": "daily_scan_cap_reached",
                "scan_cap": PAPER_DAILY_SCAN_CAP,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            store.set_state("paper_latest", latest)
            return {**latest, "created_entries": [], "created_count": 0}

        scan = await hermes_scan(
            sport=normalized_sport,
            platform="all",
            min_ev=0,
            min_win=54,
            min_books=2,
        )
        plays = scan.get("plays", [])
        store.record_candidate_observations(plays)
        updated_closing_lines = store.update_open_entry_closing_lines(plays)
        store.freeze_closing_lines_past_lock()
        summary = store.paper_summary(PAPER_POLICY.starting_bankroll)
        build = build_paper_entries(
            plays,
            stability_for=store.candidate_stability,
            policy=PAPER_POLICY,
            daily_staked=summary["daily_staked"],
            daily_profit=summary["daily_profit"],
            open_entries=summary["open_entries"],
        )
        created_entries = []
        for entry in build["entries"]:
            if store.create_paper_entry(entry):
                created_entries.append(entry)

        if created_entries:
            await run_paper_delivery()

        checked_at = datetime.now(timezone.utc).isoformat()
        store.set_state(
            "paper_scan_budget",
            {"date": today, "count": scans_today + 1},
        )
        store.set_state(
            f"paper_scan:{normalized_sport}",
            {
                "last_scan_at": checked_at,
                "candidate_count": len(plays),
                "next_interval_seconds": gate.get("interval_seconds"),
            },
        )
        latest = {
            "status": "created" if created_entries else "watching",
            "sport": normalized_sport.upper(),
            "message": build["reason"],
            "candidate_count": len(plays),
            "watch_count": build["watch_count"],
            "created_count": len(created_entries),
            "updated_closing_lines": updated_closing_lines,
            "gate": gate,
            "checked_at": checked_at,
            "scans_today": scans_today + 1,
            "scan_cap": PAPER_DAILY_SCAN_CAP,
        }
        store.set_state("paper_latest", latest)
        return {**latest, "created_entries": created_entries}


@app.get("/api/paper")
async def paper_dashboard(limit: int = Query(100, ge=1, le=500)):
    """Public, read-only paper portfolio used by the live dashboard."""
    budget = store.get_state("paper_scan_budget") or {}
    today = datetime.now(timezone.utc).date().isoformat()
    scans_today = int(budget.get("count", 0)) if budget.get("date") == today else 0
    return {
        "mode": "paper",
        "summary": store.paper_summary(PAPER_POLICY.starting_bankroll),
        "entries": store.list_paper_entries(limit),
        "automation": store.get_state("paper_latest") or {
            "status": "waiting",
            "message": "Paper automation has not run yet",
        },
        "scheduler": _paper_scheduler_status(),
        "quota": {
            "scans_today": scans_today,
            "scan_cap": PAPER_DAILY_SCAN_CAP,
            "remaining_scans": max(0, PAPER_DAILY_SCAN_CAP - scans_today),
        },
        "delivery_failures": store.delivery_failure_count(),
        "settlement_backlog": store.settlement_backlog_count(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/paper/line-history")
async def paper_line_history(
    limit: int = Query(100, ge=1, le=500),
    sport: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    player: Optional[str] = Query(None),
):
    """Persisted candidate observation history for the line-movement page."""
    observations = store.observation_history(
        limit=limit,
        sport=sport,
        platform=platform,
        player=player,
    )
    return {
        "count": len(observations),
        "observations": observations,
    }


@app.post("/api/hermes/paper/tick", dependencies=[Depends(require_hermes_key)])
async def hermes_paper_tick(sport: str = Query("mlb")):
    """Run a quota-gated paper scan and create only deterministic slips."""
    return await run_paper_tick(sport)


@app.post("/api/hermes/paper/deliver", dependencies=[Depends(require_hermes_key)])
async def hermes_paper_deliver():
    return await run_paper_delivery()


@app.post("/api/hermes/paper/settle", dependencies=[Depends(require_hermes_key)])
async def hermes_paper_settle():
    return await run_paper_settlement()


@app.post(
    "/api/hermes/paper/entries/{entry_id}/settle",
    dependencies=[Depends(require_hermes_key)],
)
async def hermes_settle_paper_entry(entry_id: str, settlement: PaperSettlement):
    allowed_results = {"win", "loss", "push", "void"}
    result = settlement.result.lower()
    if result not in allowed_results:
        raise HTTPException(status_code=422, detail=f"result must be one of {sorted(allowed_results)}")
    if settlement.payout < 0:
        raise HTTPException(status_code=422, detail="payout cannot be negative")
    if not store.apply_settlement(entry_id, result=result, payout=settlement.payout):
        raise HTTPException(status_code=404, detail="Open paper entry not found")
    return {"success": True, "entry_id": entry_id, "result": result}


@app.on_event("startup")
async def start_paper_scheduler() -> None:
    global paper_scheduler
    paper_scheduler = PaperScheduler(
        store=store,
        tick_sport=run_paper_tick,
        settle_open=run_paper_settlement,
        deliver_pending=run_paper_delivery,
        sports=PAPER_SPORTS,
        enabled=PAPER_SCHEDULER_ENABLED,
    )
    await paper_scheduler.start()
    print(
        f"[PaperScheduler] enabled={PAPER_SCHEDULER_ENABLED} sports={PAPER_SPORTS}"
    )


@app.on_event("shutdown")
async def stop_paper_scheduler() -> None:
    if paper_scheduler is not None:
        await paper_scheduler.stop()


@app.get("/api/debug/sharp-odds", dependencies=[Depends(require_admin_key)])
async def debug_sharp_odds(
    sport: str = Query("nba"),
    market: str = Query("player_points"),
):
    """Debug endpoint to test sharp odds fetching directly."""
    async with aiohttp.ClientSession() as session:
        try:
            sport_key = ODDS_API_SPORTS.get(sport.lower())
            if not sport_key:
                return {"error": f"Unknown sport: {sport}", "available": list(ODDS_API_SPORTS.keys())}
            
            api_key = get_odds_api_key()
            if not api_key:
                return {"error": "No API key configured"}
            
            # Get events
            events_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
            async with session.get(events_url, params={"apiKey": api_key}, timeout=15) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"error": f"Events fetch failed: {resp.status}", "detail": text[:500]}
                events = await resp.json()
            
            if not events:
                return {"error": "No events found", "sport_key": sport_key}
            
            # Get odds for first event
            event = events[0]
            odds_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event['id']}/odds"
            params = {
                "apiKey": api_key,
                "regions": "us,us2,eu",
                "markets": market,
                "oddsFormat": "american",
                "bookmakers": "pinnacle,draftkings,fanduel,betmgm,bovada",
            }
            
            async with session.get(odds_url, params=params, timeout=15) as resp:
                remaining = resp.headers.get("x-requests-remaining", "unknown")
                used = resp.headers.get("x-requests-used", "unknown")
                
                if resp.status != 200:
                    text = await resp.text()
                    return {
                        "error": f"Odds fetch failed: {resp.status}",
                        "detail": text[:500],
                        "url": str(resp.url),
                        "remaining": remaining,
                        "used": used,
                    }
                
                data = await resp.json()
            
            return {
                "success": True,
                "event": event,
                "bookmakers_count": len(data.get("bookmakers", [])),
                "bookmakers": [b["key"] for b in data.get("bookmakers", [])],
                "sample_data": data,
                "api_remaining": remaining,
                "api_used": used,
            }
        except Exception as e:
            import traceback
            return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/api/debug/ev-calc", dependencies=[Depends(require_admin_key)])
async def debug_ev_calc(sport: str = Query("nba")):
    """Debug endpoint to show EV calculations for all matched props."""
    async with aiohttp.ClientSession() as session:
        try:
            # Get props
            pp_props = await fetch_prizepicks(session, sport)
            all_props = pp_props
            
            if not all_props:
                return {"error": "No props found"}
            
            # Get first market
            markets_needed = set()
            for prop in all_props:
                market = prop.market_key or market_for_stat(prop.stat_type, prop.sport)
                if market:
                    markets_needed.add(market)
            
            if not markets_needed:
                return {"error": "No mappable markets"}
            
            # Get sharp odds for prioritized markets
            all_odds = []
            priority = MARKET_PRIORITY_BY_SPORT.get(sport.lower(), [])
            ordered_markets = [m for m in priority if m in markets_needed]
            ordered_markets.extend([m for m in markets_needed if m not in ordered_markets])
            for market in ordered_markets[:4]:
                odds = await fetch_sharp_odds(session, sport, market)
                all_odds.extend(odds)
            
            if not all_odds:
                return {"error": "No sharp odds found"}
            
            # Calculate EV for each matched prop
            results = []
            for prop in all_props[:50]:  # Limit to first 50
                market = prop.market_key or market_for_stat(prop.stat_type, prop.sport)
                if not market:
                    continue
                
                relevant_odds = [o for o in all_odds if o["market"] == market]
                matched_name = match_player(prop.player_name, [o["player"] for o in relevant_odds])
                
                if not matched_name:
                    continue
                
                for odds in relevant_odds:
                    if odds["player"] != matched_name:
                        continue
                    if abs(odds["line"] - prop.line) > 0.5:
                        continue
                    
                    over_prob, under_prob = calculate_no_vig(odds["over_odds"], odds["under_odds"])
                    win_prob = max(over_prob, under_prob)
                    recommended = "OVER" if over_prob > under_prob else "UNDER"
                    
                    default_be = BREAKEVEN.get(prop.platform, {}).get("default", 54.34)
                    ev_pct = win_prob - default_be
                    
                    results.append({
                        "player": prop.player_name,
                        "stat": prop.stat_type,
                        "prop_line": prop.line,
                        "book_line": odds["line"],
                        "over_odds": odds["over_odds"],
                        "under_odds": odds["under_odds"],
                        "over_prob": round(over_prob, 2),
                        "under_prob": round(under_prob, 2),
                        "win_prob": round(win_prob, 2),
                        "ev_pct": round(ev_pct, 2),
                        "recommended": recommended,
                        "would_pass_54": win_prob >= 54,
                        "would_pass_52": win_prob >= 52,
                    })
                    break
            
            # Sort by EV descending
            results.sort(key=lambda x: x["ev_pct"], reverse=True)
            
            return {
                "total_props": len(all_props),
                "total_calculated": len(results),
                "passing_54": len([r for r in results if r["would_pass_54"]]),
                "passing_52": len([r for r in results if r["would_pass_52"]]),
                "best_plays": results[:15],
            }
        except Exception as e:
            import traceback
            return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/api/debug/ev-matching", dependencies=[Depends(require_admin_key)])
async def debug_ev_matching(sport: str = Query("nba")):
    """Debug endpoint to test EV matching logic."""
    async with aiohttp.ClientSession() as session:
        try:
            # Get props
            pp_props = await fetch_prizepicks(session, sport)
            ud_props = await fetch_underdog(session, sport)
            all_props = pp_props + ud_props
            
            if not all_props:
                return {"error": "No props found", "prizepicks": len(pp_props), "underdog": len(ud_props)}
            
            # Get markets needed
            markets_needed = {}
            for prop in all_props:
                market = prop.market_key or market_for_stat(prop.stat_type, prop.sport)
                if market:
                    if market not in markets_needed:
                        markets_needed[market] = []
                    markets_needed[market].append({
                        "player": prop.player_name,
                        "line": prop.line,
                        "stat": prop.stat_type,
                        "platform": prop.platform,
                    })
            
            # Get sharp odds for first market
            first_market = list(markets_needed.keys())[0] if markets_needed else None
            if not first_market:
                return {"error": "No mappable markets found", "stat_types": [p.stat_type for p in all_props[:10]]}
            
            all_odds = await fetch_sharp_odds(session, sport, first_market)
            
            # Try to match
            matches = []
            no_matches = []
            
            for prop in all_props:
                market = prop.market_key or market_for_stat(prop.stat_type, prop.sport)
                if market != first_market:
                    continue
                
                relevant_odds = [o for o in all_odds if o["market"] == market]
                odds_players = [o["player"] for o in relevant_odds]
                matched_name = match_player(prop.player_name, odds_players)
                
                if matched_name:
                    # Find the matching odds
                    for odds in relevant_odds:
                        if odds["player"] == matched_name:
                            line_diff = abs(odds["line"] - prop.line)
                            matches.append({
                                "prop_player": prop.player_name,
                                "prop_line": prop.line,
                                "odds_player": matched_name,
                                "odds_line": odds["line"],
                                "line_diff": line_diff,
                                "would_match": line_diff <= 0.5,
                            })
                            break
                else:
                    no_matches.append({
                        "prop_player": prop.player_name,
                        "prop_line": prop.line,
                        "available_odds_players": odds_players[:10],
                    })
            
            return {
                "total_props": len(all_props),
                "market_tested": first_market,
                "sharp_odds_count": len(all_odds),
                "matches": matches[:15],
                "no_matches": no_matches[:10],
                "markets_needed": {k: len(v) for k, v in markets_needed.items()},
            }
        except Exception as e:
            import traceback
            return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/api/cache")
async def get_cache_status():
    """Get cache statistics."""
    return cache.get_stats()


@app.post("/api/cache/clear", dependencies=[Depends(require_admin_key)])
async def clear_cache():
    """Clear all cached data."""
    cache.invalidate()
    return {"success": True, "message": "Cache cleared"}


@app.post("/api/reload-keys", dependencies=[Depends(require_admin_key)])
async def reload_api_keys():
    """Reload API keys from environment variables."""
    count = api_key_manager.reload_keys()
    return {
        "success": True,
        "keys_loaded": count,
        "message": f"Reloaded {count} API key(s) from environment"
    }


@app.get("/api/health")
async def health():
    """Check API health and platform connectivity."""
    budget = store.get_state("paper_scan_budget") or {}
    today = datetime.now(timezone.utc).date().isoformat()
    scans_today = int(budget.get("count", 0)) if budget.get("date") == today else 0
    return {
        "status": "ok",
        "odds_api_configured": bool(get_odds_api_key()),
        "api_keys_loaded": api_key_manager.get_status()["total_keys"],
        "sharp_books": SHARP_BOOKS,
        "admin_api_configured": bool(ADMIN_API_KEY),
        "hermes_api_configured": bool(HERMES_API_KEY),
        "storage": "sqlite",
        "paper_scheduler": _paper_scheduler_status(),
        "paper_quota": {
            "scans_today": scans_today,
            "scan_cap": PAPER_DAILY_SCAN_CAP,
        },
        "delivery_failures": store.delivery_failure_count(),
        "settlement_backlog": store.settlement_backlog_count(),
        "platforms": {
            "prizepicks": bool(get_odds_api_key()),
            "underdog": True,
            "chalkboard": False,
            "betr": False,
        }
    }


@app.post("/api/rotate-key", dependencies=[Depends(require_admin_key)])
async def force_rotate_key():
    """Force rotation to the next API key."""
    old_index = api_key_manager.current_index
    success = api_key_manager.rotate_key()
    new_index = api_key_manager.current_index
    
    return {
        "success": success,
        "previous_key": old_index + 1,
        "current_key": new_index + 1,
        "total_keys": len(api_key_manager.keys),
        "message": f"Rotated from key {old_index + 1} to key {new_index + 1}" if success else "No backup keys available"
    }


@app.post("/api/set-key/{key_index}", dependencies=[Depends(require_admin_key)])
async def set_specific_key(key_index: int):
    """Switch to a specific API key by index (1-based)."""
    if key_index < 1 or key_index > len(api_key_manager.keys):
        return {"success": False, "error": f"Invalid key index. Must be 1-{len(api_key_manager.keys)}"}
    
    api_key_manager.current_index = key_index - 1
    return {
        "success": True,
        "current_key": key_index,
        "total_keys": len(api_key_manager.keys),
    }


@app.get("/api/all-keys-usage", dependencies=[Depends(require_admin_key)])
async def get_all_keys_usage():
    """Check usage for ALL API keys."""
    results = []
    
    async with aiohttp.ClientSession() as session:
        for i, key in enumerate(api_key_manager.keys):
            try:
                url = "https://api.the-odds-api.com/v4/sports"
                async with session.get(url, params={"apiKey": key}, timeout=10) as resp:
                    if resp.status == 401:
                        results.append({
                            "key_number": i + 1,
                            "key_preview": f"{key[:6]}...{key[-4:]}",
                            "status": "invalid",
                            "requests_used": 0,
                            "requests_remaining": 0,
                        })
                    else:
                        remaining = resp.headers.get("x-requests-remaining", "0")
                        used = resp.headers.get("x-requests-used", "0")
                        results.append({
                            "key_number": i + 1,
                            "key_preview": f"{key[:6]}...{key[-4:]}",
                            "status": "active" if int(remaining) > 0 else "depleted",
                            "requests_used": int(used) if str(used).isdigit() else 0,
                            "requests_remaining": int(remaining) if str(remaining).isdigit() else 0,
                        })
            except Exception as e:
                results.append({
                    "key_number": i + 1,
                    "key_preview": f"{key[:6]}...{key[-4:]}",
                    "status": "error",
                    "error": str(e),
                    "requests_used": 0,
                    "requests_remaining": 0,
                })
    
    return {
        "current_key": api_key_manager.current_index + 1,
        "total_keys": len(api_key_manager.keys),
        "keys": results,
        "total_remaining": sum(k.get("requests_remaining", 0) for k in results),
    }


@app.get("/api/odds-usage")
async def get_odds_api_usage():
    """Check The Odds API usage/remaining requests."""
    if not get_odds_api_key():
        return {"error": "ODDS_API_KEY not configured", "configured": False}
    
    # Make a lightweight request to check usage (sports list is free and returns headers)
    async with aiohttp.ClientSession() as session:
        try:
            url = "https://api.the-odds-api.com/v4/sports"
            async with session.get(url, params={"apiKey": get_odds_api_key()}) as resp:
                if resp.status == 401:
                    # Try rotating to next key
                    if api_key_manager.rotate_key():
                        return {"error": "Invalid API key, rotated to next key. Refresh to check.", "configured": True}
                    return {"error": "Invalid API key", "configured": True}
                
                # Extract usage from headers
                requests_remaining = resp.headers.get("x-requests-remaining", "unknown")
                requests_used = resp.headers.get("x-requests-used", "unknown")
                
                remaining = int(requests_remaining) if str(requests_remaining).isdigit() else 0
                used = int(requests_used) if str(requests_used).isdigit() else 0
                
                # Update the key manager with usage info (triggers auto-rotation if low)
                api_key_manager.update_usage(remaining, used)
                
                key_status = api_key_manager.get_status()
                
                return {
                    "configured": True,
                    "requests_used": used,
                    "requests_remaining": remaining,
                    "requests_total": 500,  # Free tier limit per key
                    "auto_rotation": {
                        "enabled": key_status["total_keys"] > 1,
                        "total_keys": key_status["total_keys"],
                        "current_key": key_status["current_key_index"],
                    }
                }
        except Exception as e:
            return {"error": str(e), "configured": True}


@app.get("/api/props")
async def get_props(
    sport: str = Query("nba", description="Sport to fetch (nba, nfl, mlb, nhl, all)"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    stat: Optional[str] = Query(None, description="Filter by stat type"),
    min_ev: Optional[float] = Query(None, description="Minimum EV percentage"),
    player: Optional[str] = Query(None, description="Search by player name"),
    refresh: bool = Query(False, description="Force refresh (bypass cache)"),
    x_admin_key: Optional[str] = Header(None),
    x_hermes_key: Optional[str] = Header(None),
):
    """Get all props across platforms with optional filters."""
    require_refresh_authorization(refresh, x_admin_key, x_hermes_key)
    async with aiohttp.ClientSession() as session:
        all_props, cache_fresh = await collect_props(session, sport, refresh=refresh)

    if platform:
        all_props = [prop for prop in all_props if prop.platform == platform.lower()]
    if stat:
        all_props = [prop for prop in all_props if stat.lower() in prop.stat_type.lower()]
    if player:
        all_props = [
            prop
            for prop in all_props
            if fuzz.partial_ratio(player.lower(), prop.player_name.lower()) >= 70
        ]

    return {
        "count": len(all_props),
        "sport": sport.upper(),
        "cached": not refresh,
        "cache_fresh": cache_fresh,
        "props": [prop.model_dump() for prop in all_props],
    }


@app.get("/api/ev")
async def get_ev_plays(
    sport: str = Query("nba", description="Sport to analyze (nba, nfl, mlb, nhl, all)"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    min_ev: float = Query(0, description="Minimum EV percentage"),
    min_win: float = Query(54, description="Minimum win probability"),
    min_books: int = Query(1, ge=1, le=5, description="Minimum exact-line sportsbook quotes"),
    refresh: bool = Query(False, description="Force refresh (bypass cache)"),
    x_admin_key: Optional[str] = Header(None),
    x_hermes_key: Optional[str] = Header(None),
):
    """Get +EV plays with sharp odds analysis. Prioritizes DraftKings/FanDuel lines."""
    require_refresh_authorization(refresh, x_admin_key, x_hermes_key)
    cache_key = f"ev_{sport.lower()}"
    
    # Check cache first (unless refresh requested)
    if not refresh:
        cached_data, is_fresh = cache.get(cache_key)
        if cached_data is not None:
            # Apply filters to cached data
            ev_plays = cached_data
            if platform:
                ev_plays = [p for p in ev_plays if p["prop"]["platform"] == platform.lower()]
            ev_plays = [
                p
                for p in ev_plays
                if p["ev_percentage"] >= min_ev
                and p["win_probability"] >= min_win
                and p.get("consensus", {}).get("book_count", 1) >= min_books
            ]
            
            return {
                "count": len(ev_plays),
                "sport": "ALL" if sport.lower() == "all" else sport.upper(),
                "sharp_books_used": list(set(p["sharp_odds"]["bookmaker"] for p in ev_plays)) if ev_plays else [],
                "plays": ev_plays,
                "cached": True,
                "cache_fresh": is_fresh,
            }

        latest = store.latest_run("ev", sport)
        if latest is not None:
            captured_at = datetime.fromisoformat(latest["captured_at"])
            max_age = int(os.getenv("PUBLIC_EV_MAX_AGE_MINUTES", "15")) * 60
            if (datetime.now(timezone.utc) - captured_at).total_seconds() <= max_age:
                ev_plays = latest["payload"].get("plays", [])
                cache.set(cache_key, ev_plays)
                if platform:
                    ev_plays = [p for p in ev_plays if p["prop"]["platform"] == platform.lower()]
                ev_plays = [
                    p
                    for p in ev_plays
                    if p["ev_percentage"] >= min_ev
                    and p["win_probability"] >= min_win
                    and p.get("consensus", {}).get("book_count", 1) >= min_books
                ]
                return {
                    "count": len(ev_plays),
                    "sport": "ALL" if sport.lower() == "all" else sport.upper(),
                    "sharp_books_used": sorted(
                        {p["sharp_odds"]["bookmaker"] for p in ev_plays}
                    ),
                    "plays": ev_plays,
                    "cached": True,
                    "cache_fresh": False,
                    "captured_at": latest["captured_at"],
                }

        return {
            "count": 0,
            "sport": "ALL" if sport.lower() == "all" else sport.upper(),
            "sharp_books_used": [],
            "plays": [],
            "cached": True,
            "cache_fresh": False,
            "message": "No scan snapshot is available yet",
        }
    
    async with aiohttp.ClientSession() as session:
        # Determine which sports to fetch
        sports_to_fetch = MAIN_SPORTS if sport.lower() == "all" else [sport.lower()]
        
        # Reuse the canonical prop snapshot. A forced EV refresh also refreshes props.
        all_props, _ = await collect_props(session, sport, refresh=refresh)
        
        if platform:
            all_props = [p for p in all_props if p.platform == platform.lower()]
        
        if not all_props:
            return {"count": 0, "plays": [], "sharp_books_used": []}
        
        # Get exact market/event pairs needed by the fetched props.
        markets_by_sport: dict[str, set[str]] = {}
        events_by_sport_market: dict[tuple[str, str], set[str]] = defaultdict(set)
        times_by_sport_market: dict[tuple[str, str], set[str]] = defaultdict(set)
        for prop in all_props:
            market = prop.market_key or market_for_stat(prop.stat_type, prop.sport)
            if market:
                if prop.sport not in markets_by_sport:
                    markets_by_sport[prop.sport] = set()
                markets_by_sport[prop.sport].add(market)
                if prop.event_id:
                    events_by_sport_market[(prop.sport, market)].add(prop.event_id)
                elif prop.game_time:
                    times_by_sport_market[(prop.sport, market)].add(prop.game_time)
        
        # Fetch only markets and events represented by platform props.
        all_odds = []
        for s in sports_to_fetch:
            sport_markets = markets_by_sport.get(s.upper(), set())
            priority = MARKET_PRIORITY_BY_SPORT.get(s.lower(), [])
            ordered_markets = [m for m in priority if m in sport_markets]
            ordered_markets.extend([m for m in sport_markets if m not in ordered_markets])
            tasks = [
                fetch_sharp_odds(
                    session,
                    s,
                    market,
                    events_by_sport_market.get((s.upper(), market)) or None,
                    times_by_sport_market.get((s.upper(), market)) or None,
                )
                for market in ordered_markets[:SHARP_MARKET_LIMIT]
            ]
            for odds in await asyncio.gather(*tasks):
                all_odds.extend(odds)
        
        if not all_odds:
            response = {
                "count": 0,
                "sport": "ALL" if sport.lower() == "all" else sport.upper(),
                "plays": [],
                "sharp_books_used": [],
                "error": "Could not fetch sportsbook odds",
            }
            store.save_run(
                "ev",
                sport,
                "error",
                response,
                {"props": len(all_props), "odds": 0},
                response["error"],
            )
            return response
        
        # Analyze each prop
        ev_plays = []
        
        for prop in all_props:
            market = prop.market_key or market_for_stat(prop.stat_type, prop.sport)
            if not market:
                continue
            
            relevant_odds = [
                row
                for row in all_odds
                if row["market"] == market
                and (not prop.event_id or row.get("event_id") == prop.event_id)
            ]
            relevant_odds.sort(key=lambda x: 0 if x.get("is_sharp") else 1)
            
            matched_name = match_player(prop.player_name, [o["player"] for o in relevant_odds])
            
            if not matched_name:
                continue
            
            player_odds = [row for row in relevant_odds if row["player"] == matched_name]
            consensus = build_consensus(prop, player_odds)
            if consensus is None:
                continue

            exact_line_odds = consensus["exact_line_odds"]
            representative = exact_line_odds[0]
            recommended = consensus["recommended_play"]
            win_prob = consensus["win_probability"]
            
            default_be = BREAKEVEN.get(prop.platform, {}).get("default", 54.34)
            ev_pct = win_prob - default_be
            
            candidate_id = _safe_id(
                prop.id,
                recommended,
                f"{prop.line:.3f}",
                market,
            )
            ev_plays.append({
                "candidate_id": candidate_id,
                "prop": prop.model_dump(),
                "sharp_odds": {
                    "bookmaker": representative["bookmaker"],
                    "line": representative["line"],
                    "over_odds": representative["over_odds"],
                    "under_odds": representative["under_odds"],
                    "over_probability": round(consensus["over_probability"], 2),
                    "under_probability": round(consensus["under_probability"], 2),
                    "is_sharp": representative.get("is_sharp", False),
                },
                "all_book_odds": [
                    {
                        "bookmaker": row["bookmaker"],
                        "line": row["line"],
                        "over_odds": row["over_odds"],
                        "under_odds": row["under_odds"],
                        "used_in_consensus": abs(float(row["line"]) - prop.line) <= 0.001,
                    }
                    for row in player_odds
                ],
                "consensus": {
                    "method": "weighted_exact_line_no_vig",
                    "book_count": consensus["book_count"],
                    "dispersion": consensus["dispersion"],
                    "confidence": consensus["confidence"],
                    "fair_odds": consensus["fair_odds"],
                    "book_probabilities": consensus["book_probabilities"],
                },
                "recommended_play": recommended,
                "win_probability": round(win_prob, 2),
                "ev_percentage": round(ev_pct, 2),
                "probability_edge": round(ev_pct, 2),
                "ev_method": "probability_edge_vs_platform_breakeven",
                "best_for": get_best_slip_types(win_prob, prop.platform),
            })
        
        # Sort by EV
        ev_plays.sort(key=lambda x: x["ev_percentage"], reverse=True)
        
        # Cache the unfiltered results
        cache.set(cache_key, ev_plays)
        
        # Apply filters for response
        filtered_plays = ev_plays
        if platform:
            filtered_plays = [p for p in filtered_plays if p["prop"]["platform"] == platform.lower()]
        filtered_plays = [
            p
            for p in filtered_plays
            if p["ev_percentage"] >= min_ev
            and p["win_probability"] >= min_win
            and p.get("consensus", {}).get("book_count", 1) >= min_books
        ]
        
        response = {
            "count": len(filtered_plays),
            "sport": "ALL" if sport.lower() == "all" else sport.upper(),
            "sharp_books_used": list(set(p["sharp_odds"]["bookmaker"] for p in filtered_plays)) if filtered_plays else [],
            "plays": filtered_plays,
            "cached": False,
        }
        store.save_run(
            "ev",
            sport,
            "ok",
            response,
            {
                "props": len(all_props),
                "sportsbook_quotes": len(all_odds),
                "candidates_scored": len(ev_plays),
                "candidates_returned": len(filtered_plays),
            },
        )
        return response


@app.get("/api/middles")
async def get_middles(
    sport: str = Query("nba", description="Sport to analyze (nba, nfl, mlb, nhl, all)"),
    min_spread: float = Query(0.5, description="Minimum spread between lines"),
    refresh: bool = Query(False, description="Force refresh (bypass cache)"),
    x_admin_key: Optional[str] = Header(None),
    x_hermes_key: Optional[str] = Header(None),
):
    """Find middle/arbitrage opportunities across platforms."""
    require_refresh_authorization(refresh, x_admin_key, x_hermes_key)
    cache_key = f"middles_{sport.lower()}"
    
    # Check cache first (unless refresh requested)
    if not refresh:
        cached_data, is_fresh = cache.get(cache_key)
        if cached_data is not None:
            # Apply min_spread filter to cached data
            middles = [m for m in cached_data if m["spread"] >= min_spread]
            return {
                "count": len(middles),
                "sport": "ALL" if sport.lower() == "all" else sport.upper(),
                "middles": middles,
                "cached": True,
                "cache_fresh": is_fresh,
            }
    
    async with aiohttp.ClientSession() as session:
        all_props, _ = await collect_props(session, sport, refresh=refresh)
        pp_props = [prop for prop in all_props if prop.platform == "prizepicks"]
        ud_props = [prop for prop in all_props if prop.platform == "underdog"]
        middles = []

        # Match on sport + canonical market, then fuzzy-match the player name.
        for pp_prop in pp_props:
            pp_market = pp_prop.market_key or market_for_stat(pp_prop.stat_type, pp_prop.sport)
            candidates = [
                prop
                for prop in ud_props
                if prop.sport == pp_prop.sport
                and (prop.market_key or market_for_stat(prop.stat_type, prop.sport)) == pp_market
            ]
            matched_name = match_player(pp_prop.player_name, [prop.player_name for prop in candidates])
            if not matched_name:
                continue
            ud_prop = next(prop for prop in candidates if prop.player_name == matched_name)
            spread = abs(pp_prop.line - ud_prop.line)
            if spread <= 0:
                continue

            if pp_prop.line > ud_prop.line:
                high_platform, high_line = "prizepicks", pp_prop.line
                low_platform, low_line = "underdog", ud_prop.line
            else:
                high_platform, high_line = "underdog", ud_prop.line
                low_platform, low_line = "prizepicks", pp_prop.line

            middle_zone = []
            current = low_line + 0.5
            while current < high_line:
                middle_zone.append(round(current, 2))
                current += 0.5

            middles.append({
                "player_name": pp_prop.player_name,
                "stat_type": pp_prop.stat_type,
                "sport": pp_prop.sport,
                "platform_a": {
                    "name": high_platform,
                    "line": high_line,
                    "recommended": "UNDER",
                },
                "platform_b": {
                    "name": low_platform,
                    "line": low_line,
                    "recommended": "OVER",
                },
                "spread": spread,
                "middle_zone": middle_zone,
            })
        
        middles.sort(key=lambda x: x["spread"], reverse=True)
        
        # Cache the unfiltered results (with min_spread=0)
        cache.set(cache_key, middles)
        
        # Apply min_spread filter for response
        filtered_middles = [m for m in middles if m["spread"] >= min_spread]
        
        return {
            "count": len(filtered_middles),
            "sport": "ALL" if sport.lower() == "all" else sport.upper(),
            "middles": filtered_middles,
            "cached": False,
        }


@app.get("/api/compare/{player_name}")
async def compare_player(
    player_name: str,
    sport: str = Query("nba", description="Sport"),
):
    """Compare a player's lines across all platforms."""
    async with aiohttp.ClientSession() as session:
        all_props, _ = await collect_props(session, sport)
        
        # Find matching player
        matches = [p for p in all_props if fuzz.partial_ratio(player_name.lower(), p.player_name.lower()) >= 80]
        
        if not matches:
            return {"found": False, "player": player_name, "props": []}
        
        # Group by stat type
        by_stat = {}
        for p in matches:
            if p.stat_type not in by_stat:
                by_stat[p.stat_type] = {}
            by_stat[p.stat_type][p.platform] = p.line
        
        return {
            "found": True,
            "player": matches[0].player_name,
            "team": matches[0].team,
            "sport": sport.upper(),
            "by_stat": by_stat,
            "props": [p.model_dump() for p in matches]
        }


@app.get("/api/games")
async def get_games(
    sport: Optional[str] = Query(None, description="Sport (nba, nfl, mlb, nhl) or omit for all"),
    refresh: bool = Query(False, description="Force refresh (bypass cache)"),
    x_admin_key: Optional[str] = Header(None),
    x_hermes_key: Optional[str] = Header(None),
):
    """Get today's games with prop counts (simplified for now)."""
    require_refresh_authorization(refresh, x_admin_key, x_hermes_key)
    cache_key = f"games_{sport.lower() if sport else 'all'}"
    
    # Check cache first (unless refresh requested)
    if not refresh:
        cached_data, is_fresh = cache.get(cache_key)
        if cached_data is not None:
            cached_data["cached"] = True
            cached_data["cache_fresh"] = is_fresh
            return cached_data
    
    async with aiohttp.ClientSession() as session:
        normalized_sport = sport or "all"
        all_props, _ = await collect_props(session, normalized_sport, refresh=refresh)
        teams = set()
        games_by_key: dict[str, dict[str, Any]] = {}
        for prop in all_props:
            if prop.team:
                teams.add(prop.team)
            game_key = prop.event_id or f"{prop.sport}|{prop.opponent}|{prop.game_time}"
            game = games_by_key.setdefault(
                game_key,
                {
                    "id": game_key,
                    "sport": prop.sport,
                    "matchup": prop.opponent,
                    "start_time": prop.game_time,
                    "prop_count": 0,
                    "platforms": {},
                },
            )
            game["prop_count"] += 1
            game["platforms"][prop.platform] = game["platforms"].get(prop.platform, 0) + 1
        
        result = {
            "sport": normalized_sport.upper(),
            "teams_with_props": sorted(list(teams)),
            "total_props": len(all_props),
            "platforms": {
                "prizepicks": sum(1 for prop in all_props if prop.platform == "prizepicks"),
                "underdog": sum(1 for prop in all_props if prop.platform == "underdog"),
            },
            "games": sorted(
                games_by_key.values(),
                key=lambda game: game.get("start_time") or "",
            ),
            "cached": False,
        }
        
        # Cache the result
        cache.set(cache_key, result)
        
        return result


@app.post("/api/calc")
async def calculate_ev(over_odds: int, under_odds: int):
    """Calculate no-vig probabilities from odds."""
    over_prob, under_prob = calculate_no_vig(over_odds, under_odds)
    
    return {
        "over_odds": over_odds,
        "under_odds": under_odds,
        "over_probability": round(over_prob, 2),
        "under_probability": round(under_prob, 2),
        "vig_percentage": round((over_prob + under_prob - 100) * -1, 2),
        "ev_analysis": {
            "prizepicks": {
                "5_flex": over_prob >= 54.34 or under_prob >= 54.34,
                "4_power": over_prob >= 56.23 or under_prob >= 56.23,
                "2_power": over_prob >= 57.74 or under_prob >= 57.74,
            },
            "underdog": {
                "5_leg": over_prob >= 52.38 or under_prob >= 52.38,
                "4_leg": over_prob >= 53.57 or under_prob >= 53.57,
                "3_leg": over_prob >= 55.56 or under_prob >= 55.56,
            }
        }
    }


@app.post("/api/calc-entry-ev")
async def calculate_entry_expected_value(request: EntryEVRequest):
    """Calculate true expected ROI for a caller-supplied payout table."""
    try:
        return calculate_entry_ev(request.probabilities, request.payouts)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

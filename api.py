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

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import aiohttp
import asyncio
from datetime import datetime, timedelta
from fuzzywuzzy import fuzz
import os
import hashlib
import time
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CACHING SYSTEM - Saves API quota by caching data
# =============================================================================

class DataCache:
    """Simple in-memory cache with TTL (time-to-live)."""
    
    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self.cache = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> tuple[any, bool]:
        """Get cached data. Returns (data, is_fresh) or (None, False) if expired/missing."""
        if key not in self.cache:
            return None, False
        
        data, timestamp, ttl = self.cache[key]
        age = time.time() - timestamp
        
        if age > ttl:
            # Expired but return stale data with is_fresh=False
            return data, False
        
        return data, True
    
    def set(self, key: str, data: any, ttl: int = None):
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

# =============================================================================
# CONFIGURATION
# =============================================================================

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# =============================================================================
# API KEY MANAGER - Automatic rotation when quota runs out
# =============================================================================

class OddsAPIKeyManager:
    """Manages multiple Odds API keys with automatic rotation."""
    
    def __init__(self):
        self.keys = []
        self.current_index = 0
        self.key_usage = {}  # Track usage per key
        
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
        self.current_index = (self.current_index + 1) % len(self.keys)
        
        # Skip back to original if we've cycled through all
        if self.current_index == old_index:
            return False
        
        print(f"[API Keys] Rotated from key {old_index + 1} to key {self.current_index + 1}")
        return True
    
    def update_usage(self, remaining: int, used: int):
        """Update usage tracking for current key."""
        if self.current_key:
            self.key_usage[self.current_key[:8]] = {
                "remaining": remaining,
                "used": used,
            }
            
            # Auto-rotate if running low (less than 10 requests)
            if remaining < 10 and len(self.keys) > 1:
                print(f"[API Keys] Key {self.current_index + 1} running low ({remaining} remaining), rotating...")
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
    allow_origins=["*"],  # Allow all origins (safe for public API)
    allow_credentials=True,
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
PROP_MAPPINGS = {
    # NBA
    "Points": "player_points",
    "Rebounds": "player_rebounds",
    "Assists": "player_assists",
    "3-Point Made": "player_threes",
    "Pts+Rebs+Asts": "player_points_rebounds_assists",
    "Steals": "player_steals",
    "Blocks": "player_blocks",
    "Turnovers": "player_turnovers",
    # NFL
    "Pass Yards": "player_pass_yds",
    "Rush Yards": "player_rush_yds",
    "Receiving Yards": "player_reception_yds",
    "Receptions": "player_receptions",
    "Pass TDs": "player_pass_tds",
    # MLB
    "Strikeouts": "pitcher_strikeouts",
    "Hits Allowed": "pitcher_hits_allowed",
    # NHL
    "Shots On Goal": "player_shots_on_goal",
    "Goals": "player_goals",
    # Underdog stat names (slightly different)
    "points": "player_points",
    "rebounds": "player_rebounds",
    "assists": "player_assists",
    "pts_rebs_asts": "player_points_rebounds_assists",
    "three_pointers_made": "player_threes",
    "passing_yards": "player_pass_yds",
    "rushing_yards": "player_rush_yds",
    "receiving_yards": "player_reception_yds",
}

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
        "Accept-Encoding": "gzip, deflate, br",
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
        "player_steals",
        "player_blocks",
        "player_turnovers",
    ],
    "nfl": [
        "player_pass_yds",
        "player_rush_yds",
        "player_reception_yds",
        "player_receptions",
        "player_pass_tds",
    ],
    "mlb": [
        "pitcher_strikeouts",
        "pitcher_hits_allowed",
    ],
    "nhl": [
        "player_shots_on_goal",
        "player_goals",
    ],
}

def _canonical_market_to_stat() -> dict[str, str]:
    """Reverse map Odds API market key -> canonical stat label used by PROP_MAPPINGS."""
    out: dict[str, str] = {}
    for stat_label, market_key in PROP_MAPPINGS.items():
        if isinstance(stat_label, str) and stat_label and stat_label[0].isupper():
            out[market_key] = stat_label
    return out

MARKET_TO_STAT = _canonical_market_to_stat()

def _safe_id(*parts: str) -> str:
    raw = "|".join([p or "" for p in parts])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

async def fetch_dfs_props_from_odds_api(
    session: aiohttp.ClientSession,
    sport: str,
    platform_key: str,
) -> list[Prop]:
    """Fetch DFS pick'em props from The Odds API using `regions=us_dfs`."""
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
    try:
        async with session.get(
            events_url,
            params={"apiKey": get_odds_api_key(), "dateFormat": "iso"},
            timeout=15,
        ) as resp:
            if resp.status != 200:
                return []
            events = await resp.json()
    except Exception as e:
        print(f"Odds API events error ({platform_key}): {e}")
        return []

    sem = asyncio.Semaphore(6)

    async def _fetch_event_odds(event: dict) -> dict | None:
        event_id = event.get("id")
        if not event_id:
            return None

        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event_id}/odds"
        params = {
            "apiKey": get_odds_api_key(),
            "regions": "us_dfs",
            "markets": ",".join(markets),
            "bookmakers": bookmaker_key,
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        try:
            async with sem:
                async with session.get(url, params=params, timeout=20) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.json()
        except Exception:
            return None

    odds_payloads = await asyncio.gather(*[_fetch_event_odds(e) for e in events[:40]])
    odds_payloads = [p for p in odds_payloads if p]

    props: list[Prop] = []
    platform_norm = platform_key.lower()
    sport_norm = sport_l.upper()

    for payload in odds_payloads:
        commence_time = payload.get("commence_time") or payload.get("commenceTime")
        event_id = payload.get("id") or ""
        home = payload.get("home_team") or ""
        away = payload.get("away_team") or ""
        opponent_label = f"{away} @ {home}" if home and away else None

        for bookmaker in payload.get("bookmakers", []) or []:
            for mkt in bookmaker.get("markets", []) or []:
                market_key = mkt.get("key") or ""
                stat_type = MARKET_TO_STAT.get(market_key, market_key)

                seen = set()
                for outcome in mkt.get("outcomes", []) or []:
                    player = outcome.get("description") or outcome.get("participant") or ""
                    point = outcome.get("point")
                    if not player or point is None:
                        continue

                    tup = (player, market_key, float(point), str(event_id))
                    if tup in seen:
                        continue
                    seen.add(tup)

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
                    ))

    return props

async def fetch_prizepicks(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """Fetch PrizePicks props. Try direct API first (free), fall back to Odds API if needed."""
    # Try direct PrizePicks API first (FREE - doesn't use Odds API quota)
    props = await fetch_prizepicks_direct(session, sport)
    if props:
        print(f"[PrizePicks] Got {len(props)} props from direct API for {sport.upper()}")
        return props
    
    # Fall back to Odds API if direct fails (uses quota)
    print(f"[PrizePicks] Direct API failed for {sport.upper()}, trying Odds API...")
    props = await fetch_dfs_props_from_odds_api(session, sport, "prizepicks")
    if props:
        print(f"[PrizePicks] Got {len(props)} props from Odds API for {sport.upper()}")
    return props


async def fetch_underdog(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """Fetch props from Underdog Fantasy API."""
    ud_sport = UD_SPORTS.get(sport.lower())
    if not ud_sport:
        print(f"[Underdog] Unknown sport: {sport}")
        return []
    
    url = "https://api.underdogfantasy.com/beta/v6/over_under_lines"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://underdogfantasy.com",
        "Referer": "https://underdogfantasy.com/",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }
    
    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            print(f"[Underdog] API response status: {resp.status}")
            if resp.status != 200:
                print(f"[Underdog] Failed to fetch - status {resp.status}")
                return []
            
            data = await resp.json()
            
            # Build lookup dictionaries
            games = {g["id"]: g for g in data.get("games", [])}
            appearances = {a["id"]: a for a in data.get("appearances", [])}
            players = {p["id"]: p for p in data.get("players", [])}
            
            print(f"[Underdog] Found {len(games)} games, {len(appearances)} appearances, {len(players)} players")
            
            # Debug: print unique sport_ids to see what format they're in
            sport_ids = set()
            for g in games.values():
                sport_ids.add(str(g.get("sport_id", "unknown")))
            print(f"[Underdog] Available sport_ids: {sport_ids}")
            
            props = []
            for line in data.get("over_under_lines", []):
                ou = line.get("over_under", {})
                app_stat = ou.get("appearance_stat", {})
                app_id = app_stat.get("appearance_id")
                app = appearances.get(app_id, {})
                
                # Get game info via match_id
                match_id = app.get("match_id")
                game = games.get(match_id, {})
                
                # Filter by sport - try multiple comparison methods
                game_sport = str(game.get("sport_id", "")).upper()
                if game_sport != ud_sport and game_sport != ud_sport.lower():
                    continue
                
                player_id = app.get("player_id")
                player = players.get(player_id, {})
                
                stat_type = app_stat.get("display_stat") or app_stat.get("stat", "")
                stat_value = line.get("stat_value")
                
                if player and stat_value:
                    name = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
                    props.append(Prop(
                        id=f"ud_{line.get('id', '')}",
                        player_name=name,
                        team=game.get("title", "").split(" @ ")[0] if " @ " in game.get("title", "") else "",
                        sport=sport.upper(),
                        stat_type=stat_type,
                        platform="underdog",
                        line=float(stat_value),
                        game_time=game.get("scheduled_at", ""),
                    ))
            
            print(f"[Underdog] Returning {len(props)} props for {sport.upper()}")
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
    return await fetch_dfs_props_from_odds_api(session, sport, "betr")

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

# =============================================================================
# SHARP ODDS FETCHER
# =============================================================================

# Preferred sharp books in order of priority
SHARP_BOOKS = ["draftkings", "fanduel", "betmgm", "caesars", "pointsbet"]

async def fetch_sharp_odds(session: aiohttp.ClientSession, sport: str, market: str) -> list[dict]:
    """Fetch odds from The Odds API for a specific market, prioritizing sharp books."""
    if not get_odds_api_key():
        return []
    
    sport_key = ODDS_API_SPORTS.get(sport.lower())
    if not sport_key:
        return []
    
    try:
        # Get events
        events_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
        async with session.get(events_url, params={"apiKey": get_odds_api_key()}) as resp:
            # Handle quota exceeded - rotate key and retry
            if resp.status == 403 or resp.status == 401:
                print(f"[API Keys] Quota exceeded or invalid key, rotating...")
                if api_key_manager.rotate_key():
                    # Retry with new key
                    async with session.get(events_url, params={"apiKey": get_odds_api_key()}) as retry_resp:
                        if retry_resp.status != 200:
                            return []
                        events = await retry_resp.json()
                else:
                    return []
            elif resp.status != 200:
                return []
            else:
                events = await resp.json()
        
        all_odds = []
        
        # Get odds for each event (limit to conserve API calls)
        for event in events[:8]:
            odds_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event['id']}/odds"
            params = {
                "apiKey": get_odds_api_key(),
                "regions": "us",
                "markets": market,
                "oddsFormat": "american",
                # Request specific bookmakers - prioritize sharp books
                "bookmakers": ",".join(SHARP_BOOKS),
            }
            
            async with session.get(odds_url, params=params) as resp:
                if resp.status != 200:
                    continue
                
                data = await resp.json()
                
                # Sort bookmakers by our preference order
                bookmakers = data.get("bookmakers", [])
                bookmakers.sort(key=lambda b: SHARP_BOOKS.index(b["key"]) if b["key"] in SHARP_BOOKS else 999)
                
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
                                all_odds.append({
                                    "player": player,
                                    "line": outcomes["over"].get("point", 0),
                                    "over_odds": outcomes["over"].get("price", -110),
                                    "under_odds": outcomes["under"].get("price", -110),
                                    "bookmaker": bookmaker["key"],
                                    "market": market,
                                    "is_sharp": bookmaker["key"] in SHARP_BOOKS[:2],  # DK/FD are sharpest
                                })
            
            await asyncio.sleep(0.3)  # Rate limiting
        
        return all_odds
    except Exception as e:
        print(f"Odds API error: {e}")
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


@app.get("/api/cache")
async def get_cache_status():
    """Get cache statistics."""
    return cache.get_stats()


@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all cached data."""
    cache.invalidate()
    return {"success": True, "message": "Cache cleared"}


@app.post("/api/reload-keys")
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
    return {
        "status": "ok",
        "odds_api_configured": bool(get_odds_api_key()),
        "api_keys_loaded": api_key_manager.get_status()["total_keys"],
        "sharp_books": SHARP_BOOKS[:2],  # DraftKings, FanDuel
        "platforms": {
            "prizepicks": True,      # Working
            "underdog": True,        # Working
            "chalkboard": False,     # Add your implementation
            "betr": False,           # Needs API research
        }
    }


@app.post("/api/rotate-key")
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


@app.post("/api/set-key/{key_index}")
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


@app.get("/api/all-keys-usage")
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
):
    """Get all props across platforms with optional filters."""
    cache_key = f"props_{sport.lower()}"
    
    # Check cache first (unless refresh requested)
    if not refresh:
        cached_data, is_fresh = cache.get(cache_key)
        if cached_data is not None:
            all_props = cached_data
            # Apply filters to cached data
            if platform:
                all_props = [p for p in all_props if p.platform == platform.lower()]
            if stat:
                all_props = [p for p in all_props if stat.lower() in p.stat_type.lower()]
            if player:
                all_props = [p for p in all_props if fuzz.partial_ratio(player.lower(), p.player_name.lower()) >= 70]
            
            return {
                "count": len(all_props),
                "sport": sport.upper(),
                "cached": True,
                "cache_fresh": is_fresh,
                "props": [p.dict() for p in all_props]
            }
    
    # Fetch fresh data
    async with aiohttp.ClientSession() as session:
        # Determine which sports to fetch
        sports_to_fetch = MAIN_SPORTS if sport.lower() == "all" else [sport.lower()]
        
        # Fetch from all platforms concurrently for all sports
        tasks = []
        for s in sports_to_fetch:
            tasks.extend([
                fetch_prizepicks(session, s),
                fetch_underdog(session, s),
                fetch_betr_picks(session, s),
                fetch_chalkboard(session, s),
            ])
        results = await asyncio.gather(*tasks)
        
        # Combine all props
        all_props = []
        for props in results:
            all_props.extend(props)
        
        # Cache the unfiltered data
        cache.set(cache_key, all_props)
        
        # Apply filters
        if platform:
            all_props = [p for p in all_props if p.platform == platform.lower()]
        
        if stat:
            all_props = [p for p in all_props if stat.lower() in p.stat_type.lower()]
        
        if player:
            all_props = [p for p in all_props if fuzz.partial_ratio(player.lower(), p.player_name.lower()) >= 70]
        
        return {
            "count": len(all_props),
            "sport": sport.upper(),
            "props": [p.dict() for p in all_props]
        }


@app.get("/api/ev")
async def get_ev_plays(
    sport: str = Query("nba", description="Sport to analyze (nba, nfl, mlb, nhl, all)"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    min_ev: float = Query(0, description="Minimum EV percentage"),
    min_win: float = Query(54, description="Minimum win probability"),
    refresh: bool = Query(False, description="Force refresh (bypass cache)"),
):
    """Get +EV plays with sharp odds analysis. Prioritizes DraftKings/FanDuel lines."""
    cache_key = f"ev_{sport.lower()}"
    
    # Check cache first (unless refresh requested)
    if not refresh:
        cached_data, is_fresh = cache.get(cache_key)
        if cached_data is not None:
            # Apply filters to cached data
            ev_plays = cached_data
            if platform:
                ev_plays = [p for p in ev_plays if p["prop"]["platform"] == platform.lower()]
            if min_ev > 0:
                ev_plays = [p for p in ev_plays if p["ev_percentage"] >= min_ev]
            if min_win > 54:
                ev_plays = [p for p in ev_plays if p["win_probability"] >= min_win]
            
            return {
                "count": len(ev_plays),
                "sport": "ALL" if sport.lower() == "all" else sport.upper(),
                "sharp_books_used": list(set(p["sharp_odds"]["bookmaker"] for p in ev_plays)) if ev_plays else [],
                "plays": ev_plays,
                "cached": True,
                "cache_fresh": is_fresh,
            }
    
    async with aiohttp.ClientSession() as session:
        # Determine which sports to fetch
        sports_to_fetch = MAIN_SPORTS if sport.lower() == "all" else [sport.lower()]
        
        # Fetch props from all platforms for all sports
        all_props = []
        for s in sports_to_fetch:
            pp_props = await fetch_prizepicks(session, s)
            ud_props = await fetch_underdog(session, s)
            betr_props = await fetch_betr_picks(session, s)
            chalk_props = await fetch_chalkboard(session, s)
            all_props.extend(pp_props + ud_props + betr_props + chalk_props)
        
        if platform:
            all_props = [p for p in all_props if p.platform == platform.lower()]
        
        if not all_props:
            return {"count": 0, "plays": [], "sharp_books_used": []}
        
        # Get unique markets needed per sport
        markets_by_sport = {}
        for prop in all_props:
            market = PROP_MAPPINGS.get(prop.stat_type)
            if market:
                if prop.sport not in markets_by_sport:
                    markets_by_sport[prop.sport] = set()
                markets_by_sport[prop.sport].add(market)
        
        # Fetch sharp odds for each sport and market (prioritizes DraftKings/FanDuel)
        all_odds = []
        for s in sports_to_fetch:
            sport_markets = markets_by_sport.get(s.upper(), set())
            for market in list(sport_markets)[:3]:  # Limit API calls per sport
                odds = await fetch_sharp_odds(session, s, market)
                all_odds.extend(odds)
        
        if not all_odds:
            return {"count": 0, "plays": [], "sharp_books_used": [], "error": "Could not fetch sharp odds"}
        
        # Analyze each prop
        ev_plays = []
        
        for prop in all_props:
            market = PROP_MAPPINGS.get(prop.stat_type)
            if not market:
                continue
            
            # Find matching odds - prefer sharp books
            relevant_odds = [o for o in all_odds if o["market"] == market]
            # Sort to prioritize sharp books
            relevant_odds.sort(key=lambda x: 0 if x.get("is_sharp") else 1)
            
            matched_name = match_player(prop.player_name, [o["player"] for o in relevant_odds])
            
            if not matched_name:
                continue
            
            for odds in relevant_odds:
                if odds["player"] != matched_name:
                    continue
                if abs(odds["line"] - prop.line) > 0.5:
                    continue
                
                over_prob, under_prob = calculate_no_vig(odds["over_odds"], odds["under_odds"])
                
                if over_prob > under_prob:
                    recommended = "OVER"
                    win_prob = over_prob
                else:
                    recommended = "UNDER"
                    win_prob = under_prob
                
                default_be = BREAKEVEN.get(prop.platform, {}).get("default", 54.34)
                ev_pct = win_prob - default_be
                
                if win_prob >= min_win and ev_pct >= min_ev:
                    ev_plays.append({
                        "prop": prop.dict(),
                        "sharp_odds": {
                            "bookmaker": odds["bookmaker"],
                            "line": odds["line"],
                            "over_odds": odds["over_odds"],
                            "under_odds": odds["under_odds"],
                            "over_probability": round(over_prob, 2),
                            "under_probability": round(under_prob, 2),
                            "is_sharp": odds.get("is_sharp", False),
                        },
                        "recommended_play": recommended,
                        "win_probability": round(win_prob, 2),
                        "ev_percentage": round(ev_pct, 2),
                        "best_for": get_best_slip_types(win_prob, prop.platform),
                    })
                break
        
        # Sort by EV
        ev_plays.sort(key=lambda x: x["ev_percentage"], reverse=True)
        
        # Cache the unfiltered results
        cache.set(cache_key, ev_plays)
        
        # Apply filters for response
        filtered_plays = ev_plays
        if platform:
            filtered_plays = [p for p in filtered_plays if p["prop"]["platform"] == platform.lower()]
        if min_ev > 0:
            filtered_plays = [p for p in filtered_plays if p["ev_percentage"] >= min_ev]
        if min_win > 54:
            filtered_plays = [p for p in filtered_plays if p["win_probability"] >= min_win]
        
        return {
            "count": len(filtered_plays),
            "sport": "ALL" if sport.lower() == "all" else sport.upper(),
            "sharp_books_used": list(set(p["sharp_odds"]["bookmaker"] for p in filtered_plays)) if filtered_plays else [],
            "plays": filtered_plays,
            "cached": False,
        }


@app.get("/api/middles")
async def get_middles(
    sport: str = Query("nba", description="Sport to analyze (nba, nfl, mlb, nhl, all)"),
    min_spread: float = Query(0.5, description="Minimum spread between lines"),
    refresh: bool = Query(False, description="Force refresh (bypass cache)"),
):
    """Find middle/arbitrage opportunities across platforms."""
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
        # Determine which sports to fetch
        sports_to_fetch = MAIN_SPORTS if sport.lower() == "all" else [sport.lower()]
        
        # Fetch from all platforms for all sports
        pp_props = []
        ud_props = []
        for s in sports_to_fetch:
            pp_props.extend(await fetch_prizepicks(session, s))
            ud_props.extend(await fetch_underdog(session, s))
        
        # Group props by player + stat + sport
        def key(p):
            return (p.player_name.lower().strip(), p.stat_type.lower(), p.sport.lower())
        
        pp_by_key = {key(p): p for p in pp_props}
        ud_by_key = {key(p): p for p in ud_props}
        
        middles = []
        
        # Find matching props with different lines
        for k, pp_prop in pp_by_key.items():
            if k not in ud_by_key:
                continue
            
            ud_prop = ud_by_key[k]
            spread = abs(pp_prop.line - ud_prop.line)
            
            if spread >= min_spread:
                # Determine which platform has higher/lower line
                if pp_prop.line > ud_prop.line:
                    high_platform = "prizepicks"
                    low_platform = "underdog"
                    high_line = pp_prop.line
                    low_line = ud_prop.line
                else:
                    high_platform = "underdog"
                    low_platform = "prizepicks"
                    high_line = ud_prop.line
                    low_line = pp_prop.line
                
                # Middle zone is between the lines
                middle_zone = list(range(int(low_line) + 1, int(high_line) + 1))
                if not middle_zone:
                    middle_zone = [low_line + 0.5]
                
                middles.append({
                    "player_name": pp_prop.player_name,
                    "stat_type": pp_prop.stat_type,
                    "sport": sport.upper(),
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
        pp_props = await fetch_prizepicks(session, sport)
        ud_props = await fetch_underdog(session, sport)
        
        all_props = pp_props + ud_props
        
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
            "props": [p.dict() for p in matches]
        }


@app.get("/api/games")
async def get_games(
    sport: Optional[str] = Query(None, description="Sport (nba, nfl, mlb, nhl) or omit for all"),
    refresh: bool = Query(False, description="Force refresh (bypass cache)"),
):
    """Get today's games with prop counts (simplified for now)."""
    cache_key = f"games_{sport.lower() if sport else 'all'}"
    
    # Check cache first (unless refresh requested)
    if not refresh:
        cached_data, is_fresh = cache.get(cache_key)
        if cached_data is not None:
            cached_data["cached"] = True
            cached_data["cache_fresh"] = is_fresh
            return cached_data
    
    async with aiohttp.ClientSession() as session:
        # If no sport specified or "all", fetch from all sports
        if not sport or sport.lower() == "all":
            sports_to_fetch = ["nba", "nfl", "mlb", "nhl"]
        else:
            sports_to_fetch = [sport.lower()]
        
        all_pp_props = []
        all_ud_props = []
        teams = set()
        
        for s in sports_to_fetch:
            pp_props = await fetch_prizepicks(session, s)
            ud_props = await fetch_underdog(session, s)
            all_pp_props.extend(pp_props)
            all_ud_props.extend(ud_props)
            
            for p in pp_props + ud_props:
                if p.team:
                    teams.add(f"{p.team} ({s.upper()})" if len(sports_to_fetch) > 1 else p.team)
        
        result = {
            "sport": "ALL" if len(sports_to_fetch) > 1 else sports_to_fetch[0].upper(),
            "teams_with_props": sorted(list(teams)),
            "total_props": len(all_pp_props) + len(all_ud_props),
            "platforms": {
                "prizepicks": len(all_pp_props),
                "underdog": len(all_ud_props),
            },
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


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

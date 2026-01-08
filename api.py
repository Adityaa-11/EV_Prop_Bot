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
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

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

async def fetch_prizepicks(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """Fetch props from PrizePicks API."""
    league_id = PP_LEAGUE_IDS.get(sport.lower())
    if not league_id:
        return []
    
    url = f"https://api.prizepicks.com/projections?league_id={league_id}&per_page=250&single_stat=true"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status != 200:
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
            
            return props
    except Exception as e:
        print(f"PrizePicks error: {e}")
        return []


async def fetch_underdog(session: aiohttp.ClientSession, sport: str) -> list[Prop]:
    """Fetch props from Underdog Fantasy API."""
    ud_sport = UD_SPORTS.get(sport.lower())
    if not ud_sport:
        return []
    
    url = "https://api.underdogfantasy.com/beta/v6/over_under_lines"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    
    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                return []
            
            data = await resp.json()
            
            # Build lookup dictionaries
            games = {g["id"]: g for g in data.get("games", [])}
            appearances = {a["id"]: a for a in data.get("appearances", [])}
            players = {p["id"]: p for p in data.get("players", [])}
            
            props = []
            for line in data.get("over_under_lines", []):
                ou = line.get("over_under", {})
                app_stat = ou.get("appearance_stat", {})
                app_id = app_stat.get("appearance_id")
                app = appearances.get(app_id, {})
                
                # Get game info via match_id
                match_id = app.get("match_id")
                game = games.get(match_id, {})
                
                # Filter by sport
                if game.get("sport_id", "").upper() != ud_sport:
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
            
            return props
    except Exception as e:
        print(f"Underdog error: {e}")
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
    """
    Fetch props from Betr Picks.
    
    RESEARCH NOTES:
    - Betr Picks URL: picks.betr.app/picks/fantasy-pick-slip
    - API endpoint likely at: api.betr.app or similar
    
    TO FIND THE API:
    1. Open picks.betr.app in Chrome
    2. Open DevTools (F12) → Network tab
    3. Filter by "XHR" or "Fetch"
    4. Browse the props and watch for API calls
    5. Look for endpoints returning JSON with player props
    
    Expected endpoints might be:
    - https://api.betr.app/v1/picks
    - https://api.betr.app/v1/props
    - https://picks.betr.app/api/lines
    """
    # Attempt to fetch from likely Betr API endpoints
    possible_urls = [
        "https://api.betr.app/v1/over-under-lines",
        "https://api.betr.app/v1/picks/lines",
        "https://picks.betr.app/api/v1/lines",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://picks.betr.app",
        "Referer": "https://picks.betr.app/",
    }
    
    for url in possible_urls:
        try:
            async with session.get(url, headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # If we get data, parse it
                    # Structure will need to be discovered
                    print(f"Betr API found at: {url}")
                    print(f"Response keys: {data.keys() if isinstance(data, dict) else 'list'}")
                    # TODO: Parse actual response once structure is known
                    return []
        except Exception as e:
            continue
    
    # API not found yet - needs manual research
    return []


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
    if not ODDS_API_KEY:
        return []
    
    sport_key = ODDS_API_SPORTS.get(sport.lower())
    if not sport_key:
        return []
    
    try:
        # Get events
        events_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
        async with session.get(events_url, params={"apiKey": ODDS_API_KEY}) as resp:
            if resp.status != 200:
                return []
            events = await resp.json()
        
        all_odds = []
        
        # Get odds for each event (limit to conserve API calls)
        for event in events[:8]:
            odds_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event['id']}/odds"
            params = {
                "apiKey": ODDS_API_KEY,
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


@app.get("/api/health")
async def health():
    """Check API health and platform connectivity."""
    return {
        "status": "ok",
        "odds_api_configured": bool(ODDS_API_KEY),
        "sharp_books": SHARP_BOOKS[:2],  # DraftKings, FanDuel
        "platforms": {
            "prizepicks": True,      # Working
            "underdog": True,        # Working
            "chalkboard": False,     # Add your implementation
            "betr": False,           # Needs API research
        }
    }


@app.get("/api/odds-usage")
async def get_odds_api_usage():
    """Check The Odds API usage/remaining requests."""
    if not ODDS_API_KEY:
        return {"error": "ODDS_API_KEY not configured", "configured": False}
    
    # Make a lightweight request to check usage (sports list is free and returns headers)
    async with aiohttp.ClientSession() as session:
        try:
            url = "https://api.the-odds-api.com/v4/sports"
            async with session.get(url, params={"apiKey": ODDS_API_KEY}) as resp:
                if resp.status == 401:
                    return {"error": "Invalid API key", "configured": True}
                
                # Extract usage from headers
                requests_remaining = resp.headers.get("x-requests-remaining", "unknown")
                requests_used = resp.headers.get("x-requests-used", "unknown")
                
                return {
                    "configured": True,
                    "requests_used": int(requests_used) if requests_used.isdigit() else requests_used,
                    "requests_remaining": int(requests_remaining) if requests_remaining.isdigit() else requests_remaining,
                    "requests_total": 500,  # Free tier limit
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
):
    """Get all props across platforms with optional filters."""
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
):
    """Get +EV plays with sharp odds analysis. Prioritizes DraftKings/FanDuel lines."""
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
        
        return {
            "count": len(ev_plays),
            "sport": "ALL" if sport.lower() == "all" else sport.upper(),
            "sharp_books_used": list(set(p["sharp_odds"]["bookmaker"] for p in ev_plays)),
            "plays": ev_plays
        }


@app.get("/api/middles")
async def get_middles(
    sport: str = Query("nba", description="Sport to analyze (nba, nfl, mlb, nhl, all)"),
    min_spread: float = Query(0.5, description="Minimum spread between lines"),
):
    """Find middle/arbitrage opportunities across platforms."""
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
        
        return {
            "count": len(middles),
            "sport": sport.upper(),
            "middles": middles
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
):
    """Get today's games with prop counts (simplified for now)."""
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
        
        return {
            "sport": "ALL" if len(sports_to_fetch) > 1 else sports_to_fetch[0].upper(),
            "teams_with_props": sorted(list(teams)),
            "total_props": len(all_pp_props) + len(all_ud_props),
            "platforms": {
                "prizepicks": len(all_pp_props),
                "underdog": len(all_ud_props),
            }
        }


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

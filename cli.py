#!/usr/bin/env python3
"""
PrizePicks +EV Finder - CLI Version
Standalone script to find +EV plays without Discord.

Usage:
    python cli.py nba          # Get NBA +EV props
    python cli.py nfl          # Get NFL +EV props
    python cli.py --player "LeBron James"  # Search specific player
    python cli.py --calc -140 +110  # Calculate no-vig odds
"""

import asyncio
import aiohttp
import argparse
from dataclasses import dataclass
from typing import Optional
import os
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
import json

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

ODDS_API_KEY = os.getenv("ODDS_API_KEY")

LEAGUE_IDS = {
    "nba": 7,
    "nfl": 2,
    "mlb": 3,
    "nhl": 8,
    "ncaab": 10,
    "ncaaf": 4,
}

ODDS_API_SPORTS = {
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
}

PROP_MAPPINGS = {
    "Points": "player_points",
    "Rebounds": "player_rebounds", 
    "Assists": "player_assists",
    "3-Point Made": "player_threes",
    "Pts+Rebs+Asts": "player_points_rebounds_assists",
    "Pts+Rebs": "player_points_rebounds",
    "Pts+Asts": "player_points_assists",
    "Rebs+Asts": "player_rebounds_assists",
    "Steals": "player_steals",
    "Blocks": "player_blocks",
    "Turnovers": "player_turnovers",
    "Pass Yards": "player_pass_yds",
    "Rush Yards": "player_rush_yds",
    "Receiving Yards": "player_reception_yds",
    "Pass TDs": "player_pass_tds",
    "Receptions": "player_receptions",
    "Strikeouts": "pitcher_strikeouts",
    "Shots On Goal": "player_shots_on_goal",
}

BREAKEVEN_ODDS = {
    "5_flex": 54.34,
    "6_flex": 54.34,
    "4_power": 56.23,
    "2_power": 57.74,
}

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PrizePicksProp:
    player_name: str
    team: str
    stat_type: str
    line: float
    league: str
    game_time: str

@dataclass
class OddsBookLine:
    player_name: str
    stat_type: str
    line: float
    over_odds: int
    under_odds: int
    bookmaker: str

# =============================================================================
# API FUNCTIONS
# =============================================================================

async def fetch_prizepicks_props(session: aiohttp.ClientSession, league: str) -> list[PrizePicksProp]:
    """Fetch all props from PrizePicks for a given league."""
    league_id = LEAGUE_IDS.get(league.lower())
    if not league_id:
        return []
    
    url = f"https://api.prizepicks.com/projections?league_id={league_id}&per_page=250&single_stat=true"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                print(f"❌ PrizePicks API error: {resp.status}")
                return []
            
            data = await resp.json()
            props = []
            
            projections = data.get("data", [])
            included = {item["id"]: item for item in data.get("included", [])}
            
            for proj in projections:
                attrs = proj.get("attributes", {})
                player_id = proj.get("relationships", {}).get("new_player", {}).get("data", {}).get("id")
                player_data = included.get(player_id, {}).get("attributes", {})
                
                props.append(PrizePicksProp(
                    player_name=player_data.get("name", "Unknown"),
                    team=player_data.get("team", ""),
                    stat_type=attrs.get("stat_type", ""),
                    line=float(attrs.get("line_score", 0)),
                    league=league.upper(),
                    game_time=attrs.get("start_time", ""),
                ))
            
            return props
            
    except Exception as e:
        print(f"❌ Error fetching PrizePicks: {e}")
        return []

async def fetch_odds_api_props(session: aiohttp.ClientSession, sport: str, market: str) -> list[OddsBookLine]:
    """Fetch player props from The Odds API."""
    if not ODDS_API_KEY:
        return []
    
    sport_key = ODDS_API_SPORTS.get(sport.lower())
    if not sport_key:
        return []
    
    events_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
    params = {"apiKey": ODDS_API_KEY}
    
    try:
        async with session.get(events_url, params=params) as resp:
            if resp.status != 200:
                return []
            events = await resp.json()
        
        all_props = []
        
        for event in events[:8]:
            event_id = event["id"]
            odds_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event_id}/odds"
            
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": market,
                "oddsFormat": "american",
            }
            
            async with session.get(odds_url, params=params) as resp:
                if resp.status != 200:
                    continue
                
                odds_data = await resp.json()
                
                for bookmaker in odds_data.get("bookmakers", []):
                    book_name = bookmaker["key"]
                    
                    for mkt in bookmaker.get("markets", []):
                        if mkt["key"] != market:
                            continue
                        
                        outcomes = mkt.get("outcomes", [])
                        player_outcomes = {}
                        
                        for outcome in outcomes:
                            player = outcome.get("description", "")
                            if player not in player_outcomes:
                                player_outcomes[player] = {}
                            
                            name = outcome.get("name", "").lower()
                            if "over" in name:
                                player_outcomes[player]["over"] = outcome
                            elif "under" in name:
                                player_outcomes[player]["under"] = outcome
                        
                        for player, outs in player_outcomes.items():
                            if "over" in outs and "under" in outs:
                                all_props.append(OddsBookLine(
                                    player_name=player,
                                    stat_type=market,
                                    line=outs["over"].get("point", 0),
                                    over_odds=outs["over"].get("price", -110),
                                    under_odds=outs["under"].get("price", -110),
                                    bookmaker=book_name,
                                ))
            
            await asyncio.sleep(0.3)
        
        return all_props
        
    except Exception as e:
        print(f"❌ Error fetching Odds API: {e}")
        return []

# =============================================================================
# CALCULATIONS
# =============================================================================

def american_to_implied(odds: int) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def calculate_no_vig(over_odds: int, under_odds: int) -> tuple[float, float]:
    over_implied = american_to_implied(over_odds)
    under_implied = american_to_implied(under_odds)
    total = over_implied + under_implied
    return (over_implied / total) * 100, (under_implied / total) * 100

def normalize_name(name: str) -> str:
    name = name.lower().strip()
    for suffix in [" jr.", " sr.", " iii", " ii", " iv"]:
        name = name.replace(suffix, "")
    return name

def match_players(pp_name: str, odds_names: list[str], threshold: int = 80) -> Optional[str]:
    pp_normalized = normalize_name(pp_name)
    best_match, best_score = None, 0
    
    for odds_name in odds_names:
        score = max(
            fuzz.ratio(pp_normalized, normalize_name(odds_name)),
            fuzz.partial_ratio(pp_normalized, normalize_name(odds_name)),
            fuzz.token_sort_ratio(pp_normalized, normalize_name(odds_name)),
        )
        if score > best_score and score >= threshold:
            best_score, best_match = score, odds_name
    
    return best_match

# =============================================================================
# MAIN ANALYSIS
# =============================================================================

async def find_ev_props(sport: str):
    """Find all +EV props for a sport."""
    print(f"\n🔍 Fetching {sport.upper()} props from PrizePicks...")
    
    async with aiohttp.ClientSession() as session:
        pp_props = await fetch_prizepicks_props(session, sport)
        
        if not pp_props:
            print(f"❌ No {sport.upper()} props found on PrizePicks")
            return
        
        print(f"✅ Found {len(pp_props)} PrizePicks props")
        
        # Group props by stat type
        prop_by_stat = {}
        for prop in pp_props:
            if prop.stat_type not in prop_by_stat:
                prop_by_stat[prop.stat_type] = []
            prop_by_stat[prop.stat_type].append(prop)
        
        print(f"📊 Stat types: {', '.join(prop_by_stat.keys())}")
        
        if not ODDS_API_KEY:
            print("\n⚠️  No ODDS_API_KEY set - showing PrizePicks props only:")
            print("-" * 60)
            for prop in pp_props[:20]:
                print(f"{prop.player_name} ({prop.team}) - {prop.stat_type}: {prop.line}")
            return
        
        print(f"\n📡 Fetching sportsbook odds...")
        
        # Fetch odds for common markets
        all_odds = []
        markets = set()
        for stat_type in prop_by_stat.keys():
            if stat_type in PROP_MAPPINGS:
                markets.add(PROP_MAPPINGS[stat_type])
        
        for market in list(markets)[:5]:
            print(f"   Fetching {market}...")
            odds = await fetch_odds_api_props(session, sport, market)
            all_odds.extend(odds)
            print(f"   Found {len(odds)} odds lines")
        
        if not all_odds:
            print("❌ Could not fetch sportsbook odds")
            return
        
        # Find +EV props
        print(f"\n🎯 Analyzing for +EV plays...")
        print("=" * 70)
        
        ev_plays = []
        
        for prop in pp_props:
            market = PROP_MAPPINGS.get(prop.stat_type)
            if not market:
                continue
            
            relevant_odds = [o for o in all_odds if o.stat_type == market]
            if not relevant_odds:
                continue
            
            matched_name = match_players(prop.player_name, [o.player_name for o in relevant_odds])
            if not matched_name:
                continue
            
            for odds_line in relevant_odds:
                if odds_line.player_name != matched_name:
                    continue
                if abs(odds_line.line - prop.line) > 0.5:
                    continue
                
                over_prob, under_prob = calculate_no_vig(odds_line.over_odds, odds_line.under_odds)
                
                if over_prob > under_prob:
                    play, prob = "OVER", over_prob
                else:
                    play, prob = "UNDER", under_prob
                
                if prob >= BREAKEVEN_ODDS["5_flex"]:
                    ev_plays.append({
                        "player": prop.player_name,
                        "team": prop.team,
                        "stat": prop.stat_type,
                        "line": prop.line,
                        "play": play,
                        "prob": prob,
                        "book": odds_line.bookmaker,
                        "over_odds": odds_line.over_odds,
                        "under_odds": odds_line.under_odds,
                    })
                break
        
        # Sort and display in spreadsheet format
        ev_plays.sort(key=lambda x: x["prob"], reverse=True)
        
        if not ev_plays:
            print("😔 No +EV plays found")
            return
        
        # Print spreadsheet header
        print(f"\n{'='*80}")
        print(f"🎯 PRIZEPICKS +EV FINDER | {sport.upper()} | {len(ev_plays)} Plays Found")
        print(f"{'='*80}\n")
        
        # Column headers
        print(f"{'Game Info':<20} {'Bet Details':<32} {'Win%':>8} {'EV%':>8}")
        print(f"{'-'*20} {'-'*32} {'-'*8} {'-'*8}")
        
        for play in ev_plays:
            # Calculate EV% above break-even
            ev_above = play["prob"] - BREAKEVEN_ODDS["5_flex"]
            
            # Format columns
            game_info = f"{play['team']}"[:18]
            
            # Format bet details like "[NBA] [Rebounds] Player Under 6.5"
            stat_short = play['stat'][:10]
            bet_details = f"[{stat_short}] {play['player'][:12]} {play['play'][0]} {play['line']}"
            bet_details = bet_details[:30]
            
            # Color indicator based on EV
            if play["prob"] >= 60:
                indicator = "🟢"
            elif play["prob"] >= 57:
                indicator = "🟡"  
            else:
                indicator = "🟠"
            
            print(f"{game_info:<20} {bet_details:<32} {play['prob']:>6.1f}% {ev_above:>6.2f}%  {indicator}")
        
        # Footer
        print(f"\n{'-'*80}")
        print("Break-Even: 5/6-Flex=54.34% | 4-Power=56.23% | 2-Power=57.74%")
        print("EV% = Edge above 5/6-Flex break-even")
        print(f"{'='*80}\n")
        
        # Detailed view option
        print("\n📋 DETAILED VIEW:\n")
        for i, play in enumerate(ev_plays[:10], 1):
            ev_above = play["prob"] - BREAKEVEN_ODDS["5_flex"]
            
            if play["prob"] >= 57.74:
                slip = "2-Power, 4-Power, 5/6-Flex"
            elif play["prob"] >= 56.23:
                slip = "4-Power, 5/6-Flex"
            else:
                slip = "5/6-Flex only"
            
            print(f"{i}. {play['player']} ({play['team']})")
            print(f"   {play['play']} {play['line']} {play['stat']}")
            print(f"   Win%: {play['prob']:.1f}% | EV%: +{ev_above:.2f}% | Book: {play['book']}")
            print(f"   Odds: Over {play['over_odds']:+d} / Under {play['under_odds']:+d}")
            print(f"   ✅ Best Slip: {slip}")
            print()

async def search_player(name: str):
    """Search for a specific player's props."""
    print(f"\n🔍 Searching for '{name}'...")
    
    async with aiohttp.ClientSession() as session:
        for sport in ["nba", "nfl", "mlb", "nhl"]:
            props = await fetch_prizepicks_props(session, sport)
            
            matches = [p for p in props if fuzz.partial_ratio(name.lower(), p.player_name.lower()) >= 75]
            
            if matches:
                print(f"\n✅ Found in {sport.upper()}:")
                for prop in matches:
                    print(f"   {prop.player_name} ({prop.team}) - {prop.stat_type}: {prop.line}")

def calc_no_vig(over: int, under: int):
    """Calculate and display no-vig odds."""
    over_prob, under_prob = calculate_no_vig(over, under)
    
    print(f"\n🧮 No-Vig Calculator")
    print(f"   Over ({over:+d}):  {over_prob:.2f}%")
    print(f"   Under ({under:+d}): {under_prob:.2f}%")
    
    best = max(over_prob, under_prob)
    if best >= 57.74:
        print(f"   ✅ +EV for 2-man Power and all Flex")
    elif best >= 56.23:
        print(f"   ✅ +EV for 4-man Power and 5/6 Flex")
    elif best >= 54.34:
        print(f"   ✅ +EV for 5/6-man Flex only")
    else:
        print(f"   ❌ Not +EV (need >54.34%)")

# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="PrizePicks +EV Finder")
    parser.add_argument("sport", nargs="?", help="Sport to analyze (nba, nfl, mlb, nhl)")
    parser.add_argument("--player", "-p", help="Search for a specific player")
    parser.add_argument("--calc", "-c", nargs=2, type=int, metavar=("OVER", "UNDER"),
                        help="Calculate no-vig odds")
    
    args = parser.parse_args()
    
    if args.calc:
        calc_no_vig(args.calc[0], args.calc[1])
    elif args.player:
        asyncio.run(search_player(args.player))
    elif args.sport:
        asyncio.run(find_ev_props(args.sport))
    else:
        print("PrizePicks +EV Finder")
        print("=" * 40)
        print("\nUsage:")
        print("  python cli.py nba              # Get NBA +EV props")
        print("  python cli.py nfl              # Get NFL +EV props")
        print("  python cli.py --player 'LeBron'  # Search player")
        print("  python cli.py --calc -140 +110   # Calculate no-vig")
        print("\nSet ODDS_API_KEY in .env for full functionality")
        print("Get free key at: https://the-odds-api.com")

if __name__ == "__main__":
    main()

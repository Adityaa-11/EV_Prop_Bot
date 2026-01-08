"""
PrizePicks & Underdog +EV Discord Bot
"""

import discord
from discord.ext import commands
import aiohttp
import asyncio
from dataclasses import dataclass
from typing import Optional
import os
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
from datetime import datetime
import json

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
WEBHOOK_PRIZEPICKS = os.getenv("DISCORD_WEBHOOK_PRIZEPICKS")
WEBHOOK_UNDERDOG = os.getenv("DISCORD_WEBHOOK_UNDERDOG")

# League mappings
LEAGUE_IDS = {"nba": 7, "nfl": 2, "mlb": 3, "nhl": 8, "ncaab": 10, "ncaaf": 4, "soccer": 17}
ODDS_API_SPORTS = {"nba": "basketball_nba", "nfl": "americanfootball_nfl", "mlb": "baseball_mlb", "nhl": "icehockey_nhl", "ncaab": "basketball_ncaab", "ncaaf": "americanfootball_ncaaf", "soccer": "soccer_epl"}

# Underdog sport mappings
UD_SPORTS = {"nba": "NBA", "nfl": "NFL", "mlb": "MLB", "nhl": "NHL"}

PROP_MAPPINGS = {
    "Points": "player_points", "Rebounds": "player_rebounds", "Assists": "player_assists",
    "3-Point Made": "player_threes", "Pts+Rebs+Asts": "player_points_rebounds_assists",
    "Steals": "player_steals", "Blocks": "player_blocks", "Turnovers": "player_turnovers",
    "Pass Yards": "player_pass_yds", "Rush Yards": "player_rush_yds", "Receiving Yards": "player_reception_yds",
    "Receptions": "player_receptions", "Strikeouts": "pitcher_strikeouts",
    "Shots On Goal": "player_shots_on_goal", "Shots": "player_shots",
}

# Breakeven percentages
BREAKEVEN_PP = {"5_flex": 54.34, "4_power": 56.23, "2_power": 57.74}
BREAKEVEN_UD = {"5_leg": 52.38, "4_leg": 53.57, "3_leg": 55.56, "2_leg": 60.00}  # Underdog payouts differ

@dataclass
class Prop:
    player: str
    team: str
    stat: str
    line: float
    league: str
    source: str = "prizepicks"

@dataclass
class Odds:
    player: str
    line: float
    over: int
    under: int
    book: str

# =============================================================================
# API FETCHING
# =============================================================================

async def fetch_pp(session, league):
    """Fetch PrizePicks props"""
    league_id = LEAGUE_IDS.get(league.lower())
    if not league_id: return []
    url = f"https://api.prizepicks.com/projections?league_id={league_id}&per_page=250&single_stat=true"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}
    try:
        async with session.get(url, headers=headers) as r:
            if r.status != 200: return []
            data = await r.json()
            included = {i["id"]: i for i in data.get("included", [])}
            props = []
            for p in data.get("data", []):
                a = p.get("attributes", {})
                pid = p.get("relationships", {}).get("new_player", {}).get("data", {}).get("id")
                pl = included.get(pid, {}).get("attributes", {})
                props.append(Prop(pl.get("name", "?"), pl.get("team", ""), a.get("stat_type", ""), float(a.get("line_score", 0)), league.upper(), "prizepicks"))
            return props
    except: return []

async def fetch_ud(session, league):
    """Fetch Underdog Fantasy props"""
    sport = UD_SPORTS.get(league.lower())
    if not sport: return []
    
    url = "https://api.underdogfantasy.com/beta/v5/over_under_lines"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    try:
        async with session.get(url, headers=headers) as r:
            if r.status != 200: return []
            data = await r.json()
            
            props = []
            appearances = {a["id"]: a for a in data.get("appearances", [])}
            players = {p["id"]: p for p in data.get("players", [])}
            
            for line in data.get("over_under_lines", []):
                app_id = line.get("over_under", {}).get("appearance_stat", {}).get("appearance_id")
                app = appearances.get(app_id, {})
                
                # Filter by sport
                if app.get("match", {}).get("sport_id", "").upper() != sport:
                    continue
                
                player_id = app.get("player_id")
                player = players.get(player_id, {})
                
                stat_type = line.get("over_under", {}).get("appearance_stat", {}).get("stat")
                stat_value = line.get("stat_value")
                
                if player and stat_value:
                    props.append(Prop(
                        player=f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
                        team=app.get("match", {}).get("home_team_abbr", "") or "",
                        stat=stat_type or "",
                        line=float(stat_value),
                        league=league.upper(),
                        source="underdog"
                    ))
            return props
    except Exception as e:
        print(f"Underdog fetch error: {e}")
        return []

async def fetch_odds(session, sport, market):
    """Fetch sportsbook odds from The Odds API"""
    if not ODDS_API_KEY: return []
    sport_key = ODDS_API_SPORTS.get(sport.lower())
    if not sport_key: return []
    try:
        async with session.get(f"https://api.the-odds-api.com/v4/sports/{sport_key}/events", params={"apiKey": ODDS_API_KEY}) as r:
            if r.status != 200: return []
            events = await r.json()
        all_odds = []
        for e in events[:8]:
            async with session.get(f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{e['id']}/odds", params={"apiKey": ODDS_API_KEY, "regions": "us", "markets": market, "oddsFormat": "american"}) as r:
                if r.status != 200: continue
                data = await r.json()
                for bk in data.get("bookmakers", []):
                    for m in bk.get("markets", []):
                        if m["key"] != market: continue
                        po = {}
                        for o in m.get("outcomes", []):
                            pl = o.get("description", "")
                            if pl not in po: po[pl] = {}
                            if "over" in o.get("name", "").lower(): po[pl]["over"] = o
                            elif "under" in o.get("name", "").lower(): po[pl]["under"] = o
                        for pl, oo in po.items():
                            if "over" in oo and "under" in oo:
                                all_odds.append(Odds(pl, oo["over"].get("point", 0), oo["over"].get("price", -110), oo["under"].get("price", -110), bk["key"]))
            await asyncio.sleep(0.3)
        return all_odds
    except: return []

# =============================================================================
# CALCULATIONS
# =============================================================================

def no_vig(over, under):
    oi = 100/(over+100) if over > 0 else abs(over)/(abs(over)+100)
    ui = 100/(under+100) if under > 0 else abs(under)/(abs(under)+100)
    t = oi + ui
    return (oi/t)*100, (ui/t)*100

def match(pp_name, odds_names):
    pp = pp_name.lower().replace(" jr.", "").replace(" sr.", "").strip()
    best, score = None, 0
    for on in odds_names:
        o = on.lower().replace(" jr.", "").replace(" sr.", "").strip()
        s = max(fuzz.ratio(pp, o), fuzz.partial_ratio(pp, o), fuzz.token_sort_ratio(pp, o))
        if s > score and s >= 80: best, score = on, s
    return best

# =============================================================================
# WEBHOOK POSTING
# =============================================================================

async def post_to_webhook(session, webhook_url, content=None, embeds=None):
    """Post message to Discord webhook"""
    if not webhook_url: return False
    payload = {}
    if content: payload["content"] = content
    if embeds: payload["embeds"] = embeds
    try:
        async with session.post(webhook_url, json=payload) as r:
            return r.status in [200, 204]
    except:
        return False

async def send_plays_to_webhook(session, plays, sport, source, breakeven):
    """Send +EV plays to appropriate webhook"""
    webhook = WEBHOOK_PRIZEPICKS if source == "prizepicks" else WEBHOOK_UNDERDOG
    if not webhook or not plays:
        return
    
    platform = "PRIZEPICKS" if source == "prizepicks" else "UNDERDOG"
    color = 0x00ff00 if source == "prizepicks" else 0x7c3aed  # Green for PP, Purple for UD
    
    # Header embed
    header = {
        "title": f"🎯 {platform} +EV PLAYS | {sport.upper()}",
        "description": f"**{len(plays)} plays found** • {datetime.now().strftime('%I:%M %p')}",
        "color": color
    }
    await post_to_webhook(session, webhook, embeds=[header])
    await asyncio.sleep(0.5)
    
    # Individual play embeds
    for p in plays[:15]:
        ev = p["win"] - breakeven
        play_color = 0x22c55e if p["win"] >= 60 else 0xeab308 if p["win"] >= 57 else 0xf97316
        
        embed = {
            "title": f"{p['player']} {p['play']} {p['line']}",
            "color": play_color,
            "fields": [
                {"name": "Stat", "value": f"`{p['stat']}`", "inline": True},
                {"name": "Team", "value": f"`{p['team']}`", "inline": True},
                {"name": "Win%", "value": f"**{p['win']:.1f}%**", "inline": True},
                {"name": "EV%", "value": f"**+{ev:.2f}%**", "inline": True},
                {"name": "Book", "value": f"`{p['book']}`", "inline": True},
                {"name": "Odds", "value": f"O:`{p['ov']:+d}` U:`{p['un']:+d}`", "inline": True},
            ]
        }
        await post_to_webhook(session, webhook, embeds=[embed])
        await asyncio.sleep(0.3)

# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

async def analyze_platform(session, sport, source, fetch_func, breakeven_key):
    """Analyze props from a platform and find +EV plays"""
    props = await fetch_func(session, sport)
    if not props:
        return [], f"No {source} props found"
    
    markets = set(PROP_MAPPINGS.get(p.stat) for p in props if p.stat in PROP_MAPPINGS)
    all_odds = []
    for m in list(markets)[:5]:
        all_odds.extend(await fetch_odds(session, sport, m))
    
    if not all_odds:
        return [], "No odds found"
    
    breakeven = BREAKEVEN_PP[breakeven_key] if source == "prizepicks" else BREAKEVEN_UD.get(breakeven_key, 52.38)
    
    plays = []
    for p in props:
        m = match(p.player, [o.player for o in all_odds])
        if not m: continue
        for o in all_odds:
            if o.player != m or abs(o.line - p.line) > 0.5: continue
            op, up = no_vig(o.over, o.under)
            if max(op, up) >= breakeven:
                play = "OVER" if op > up else "UNDER"
                plays.append({"player": p.player, "team": p.team, "stat": p.stat, "line": p.line, "play": play, "win": max(op, up), "book": o.book, "ov": o.over, "un": o.under})
            break
    
    plays.sort(key=lambda x: x["win"], reverse=True)
    return plays, None

# =============================================================================
# DISCORD BOT
# =============================================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user}")
    print(f"PrizePicks webhook: {'✓' if WEBHOOK_PRIZEPICKS else '✗'}")
    print(f"Underdog webhook: {'✓' if WEBHOOK_UNDERDOG else '✗'}")

@bot.command(name="ev")
async def ev(ctx, sport: str = "nba"):
    """Get PrizePicks +EV plays"""
    sport = sport.lower()
    if sport not in LEAGUE_IDS:
        await ctx.send(f"Sports: {', '.join(LEAGUE_IDS.keys())}"); return
    await ctx.send(f"Fetching PrizePicks {sport.upper()}...")
    
    async with aiohttp.ClientSession() as s:
        plays, error = await analyze_platform(s, sport, "prizepicks", fetch_pp, "5_flex")
        if error:
            await ctx.send(error); return
        if not plays:
            await ctx.send("No +EV plays found"); return
        
        # Send to channel
        h = f"```\n{'='*72}\nPRIZEPICKS +EV | {sport.upper()} | {len(plays)} Plays\n{'='*72}\n```"
        await ctx.send(h)
        
        t = "```\n"
        t += f"{'Team':<12} {'Bet Details':<32} {'Win%':>7} {'EV%':>7}\n"
        t += f"{'-'*12} {'-'*32} {'-'*7} {'-'*7}\n"
        
        for p in plays[:15]:
            ev_pct = p["win"] - BREAKEVEN_PP["5_flex"]
            team = p["team"][:10]
            det = f"[{p['stat'][:8]}] {p['player'][:14]} {p['play'][0]} {p['line']}"[:30]
            t += f"{team:<12} {det:<32} {p['win']:>5.1f}% {ev_pct:>5.2f}%\n"
        
        t += "```"
        await ctx.send(t)
        
        # Also post to webhook
        await send_plays_to_webhook(s, plays, sport, "prizepicks", BREAKEVEN_PP["5_flex"])

@bot.command(name="ud")
async def ud(ctx, sport: str = "nba"):
    """Get Underdog +EV plays"""
    sport = sport.lower()
    if sport not in UD_SPORTS:
        await ctx.send(f"Sports: {', '.join(UD_SPORTS.keys())}"); return
    await ctx.send(f"Fetching Underdog {sport.upper()}...")
    
    async with aiohttp.ClientSession() as s:
        plays, error = await analyze_platform(s, sport, "underdog", fetch_ud, "5_leg")
        if error:
            await ctx.send(error); return
        if not plays:
            await ctx.send("No +EV plays found"); return
        
        # Send to channel
        h = f"```\n{'='*72}\nUNDERDOG +EV | {sport.upper()} | {len(plays)} Plays\n{'='*72}\n```"
        await ctx.send(h)
        
        t = "```\n"
        t += f"{'Team':<12} {'Bet Details':<32} {'Win%':>7} {'EV%':>7}\n"
        t += f"{'-'*12} {'-'*32} {'-'*7} {'-'*7}\n"
        
        for p in plays[:15]:
            ev_pct = p["win"] - BREAKEVEN_UD["5_leg"]
            team = p["team"][:10]
            det = f"[{p['stat'][:8]}] {p['player'][:14]} {p['play'][0]} {p['line']}"[:30]
            t += f"{team:<12} {det:<32} {p['win']:>5.1f}% {ev_pct:>5.2f}%\n"
        
        t += "```"
        await ctx.send(t)
        
        # Also post to webhook
        await send_plays_to_webhook(s, plays, sport, "underdog", BREAKEVEN_UD["5_leg"])

@bot.command(name="both")
async def both(ctx, sport: str = "nba"):
    """Get +EV plays from both platforms"""
    await ctx.send(f"Fetching {sport.upper()} from PrizePicks & Underdog...")
    
    async with aiohttp.ClientSession() as s:
        pp_plays, pp_err = await analyze_platform(s, sport, "prizepicks", fetch_pp, "5_flex")
        ud_plays, ud_err = await analyze_platform(s, sport, "underdog", fetch_ud, "5_leg")
        
        if pp_plays:
            await ctx.send(f"**PrizePicks:** {len(pp_plays)} +EV plays")
            await send_plays_to_webhook(s, pp_plays, sport, "prizepicks", BREAKEVEN_PP["5_flex"])
        else:
            await ctx.send(f"**PrizePicks:** {pp_err or 'No +EV plays'}")
        
        if ud_plays:
            await ctx.send(f"**Underdog:** {len(ud_plays)} +EV plays")
            await send_plays_to_webhook(s, ud_plays, sport, "underdog", BREAKEVEN_UD["5_leg"])
        else:
            await ctx.send(f"**Underdog:** {ud_err or 'No +EV plays'}")

@bot.command(name="webhook")
async def webhook_post(ctx, platform: str = "both", sport: str = "nba"):
    """Post +EV plays directly to webhooks"""
    await ctx.send(f"Posting {sport.upper()} to webhooks...")
    
    async with aiohttp.ClientSession() as s:
        if platform in ["pp", "prizepicks", "both"]:
            plays, _ = await analyze_platform(s, sport, "prizepicks", fetch_pp, "5_flex")
            if plays:
                await send_plays_to_webhook(s, plays, sport, "prizepicks", BREAKEVEN_PP["5_flex"])
                await ctx.send(f"✅ Posted {len(plays)} PrizePicks plays to webhook")
            else:
                await ctx.send("❌ No PrizePicks +EV plays")
        
        if platform in ["ud", "underdog", "both"]:
            plays, _ = await analyze_platform(s, sport, "underdog", fetch_ud, "5_leg")
            if plays:
                await send_plays_to_webhook(s, plays, sport, "underdog", BREAKEVEN_UD["5_leg"])
                await ctx.send(f"✅ Posted {len(plays)} Underdog plays to webhook")
            else:
                await ctx.send("❌ No Underdog +EV plays")

@bot.command(name="player")
async def player(ctx, *, name: str):
    await ctx.send(f"Searching {name}...")
    async with aiohttp.ClientSession() as s:
        found = []
        for sp in ["nba", "nfl", "mlb", "nhl"]:
            for p in await fetch_pp(s, sp):
                if fuzz.partial_ratio(name.lower(), p.player.lower()) >= 80: found.append(p)
            for p in await fetch_ud(s, sp):
                if fuzz.partial_ratio(name.lower(), p.player.lower()) >= 80: found.append(p)
        if not found: await ctx.send("Not found"); return
        e = discord.Embed(title=f"Props: {name}", color=discord.Color.blue())
        for p in found[:15]: e.add_field(name=f"{p.stat} ({p.source})", value=f"Line: {p.line}\nTeam: {p.team}", inline=True)
        await ctx.send(embed=e)

@bot.command(name="calc")
async def calc(ctx, over: int, under: int):
    op, up = no_vig(over, under)
    e = discord.Embed(title="No-Vig Calculator", color=discord.Color.purple())
    e.add_field(name=f"Over ({over:+d})", value=f"{op:.2f}%", inline=True)
    e.add_field(name=f"Under ({under:+d})", value=f"{up:.2f}%", inline=True)
    b = max(op, up)
    rec = "+EV for 2-Power+" if b >= 57.74 else "+EV for 4-Power+" if b >= 56.23 else "+EV for 5/6-Flex" if b >= 54.34 else "Not +EV"
    e.add_field(name="Result", value=rec, inline=False)
    await ctx.send(embed=e)

@bot.command(name="help_ev")
async def help_ev(ctx):
    e = discord.Embed(title="🎯 +EV Bot Commands", color=discord.Color.gold())
    e.add_field(name="PrizePicks", value="`!ev nba` - Get PP +EV plays", inline=False)
    e.add_field(name="Underdog", value="`!ud nba` - Get UD +EV plays", inline=False)
    e.add_field(name="Both Platforms", value="`!both nba` - Get from both", inline=False)
    e.add_field(name="Webhook Post", value="`!webhook pp nba` - Post to webhooks\n`!webhook ud nba`\n`!webhook both nba`", inline=False)
    e.add_field(name="Other", value="`!player Name` - Search\n`!calc -140 +110` - Calc", inline=False)
    e.add_field(name="Sports", value="`nba nfl mlb nhl`", inline=False)
    await ctx.send(embed=e)

if __name__ == "__main__":
    if not DISCORD_TOKEN: print("Set DISCORD_TOKEN in .env"); exit(1)
    if not ODDS_API_KEY: print("Warning: No ODDS_API_KEY")
    bot.run(DISCORD_TOKEN)

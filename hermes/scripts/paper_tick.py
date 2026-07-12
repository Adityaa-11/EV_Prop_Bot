"""Silent cron heartbeat; prints only new slips or actionable errors."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


def tick(base_url: str, key: str, sport: str) -> dict:
    query = urllib.parse.urlencode({"sport": sport})
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/hermes/paper/tick?{query}",
        method="POST",
        headers={"Accept": "application/json", "X-Hermes-Key": key},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def slip_message(entry: dict) -> str:
    legs = "\n".join(
        (
            f"• {leg['player_name']} — {leg['side']} {leg['line']} "
            f"{leg['stat_type']} ({leg['win_probability']:.2f}%, {leg['book_count']} books)"
        )
        for leg in entry["legs"]
    )
    return (
        "**PAPER — NO REAL WAGER**\n"
        f"Platform: **{entry['platform'].title()}** | Tier: **{entry['tier'].title()}**\n"
        f"Stake: **${entry['stake']:.2f}** | Return: **${entry['potential_payout']:.2f}** "
        f"| Expected ROI: **{entry['expected_roi']:.2f}%**\n"
        f"{legs}\n"
        f"Locks: {entry['lock_time']}\n"
        f"Slip ID: `{entry['id']}`"
    )


def main() -> int:
    base_url = os.getenv("EV_BACKEND_URL")
    key = os.getenv("HERMES_API_KEY")
    if not base_url or not key:
        print("Paper automation error: EV_BACKEND_URL or HERMES_API_KEY is missing.")
        return 2

    sports = [
        sport.strip().lower()
        for sport in os.getenv(
            "PAPER_SPORTS",
            "mlb,nba,nfl,nhl,wnba,ncaab,ncaaf,cfl,mls,epl,summer",
        ).split(",")
        if sport.strip()
    ]
    messages = []
    errors = []
    for sport in sports:
        try:
            result = tick(base_url, key, sport)
        except urllib.error.HTTPError as error:
            errors.append(f"{sport.upper()}: backend returned HTTP {error.code}")
            continue
        except urllib.error.URLError:
            errors.append(f"{sport.upper()}: backend unavailable")
            continue
        messages.extend(slip_message(entry) for entry in result.get("created_entries", []))

    if messages:
        print("\n\n".join(messages))
    elif errors:
        print("Paper automation error: " + "; ".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

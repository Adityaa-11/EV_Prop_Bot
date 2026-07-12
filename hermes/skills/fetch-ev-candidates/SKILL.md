---
name: fetch-ev-candidates
description: Use when the paper-betting scheduler checks a supported sports slate. Calls the deterministic EV backend once and reports only backend-created paper slips.
version: 1.0.0
author: EV Dashboard
license: MIT
metadata:
  hermes:
    tags: [paper-trading, ev, sportsbook, discord]
    related_skills: []
---

# Fetch EV Candidates

## Purpose

Run the deterministic paper tick. The backend decides whether games are near
enough to scan, whether quota may be spent, and whether any slip qualifies.

## Procedure

1. Run `python /opt/data/skills/fetch-ev-candidates/scripts/paper_tick.py --sport mlb`.
2. Parse the JSON response.
3. If `created_count` is zero, do not invent a recommendation. A short waiting
   status is sufficient.
4. For every item in `created_entries`, send one Discord message containing:
   - `PAPER — NO REAL WAGER`
   - platform, stake, potential payout, tier, expected ROI, and lock time
   - every player, stat, side, line, probability, and exact-line book count
   - the internal paper slip ID
5. Never recalculate EV, combine different legs, lower a threshold, or navigate
   to PrizePicks or Underdog.

## Fail Closed

- Missing `EV_BACKEND_URL` or `HERMES_API_KEY`: report configuration error.
- HTTP/auth/backend failure: report the error once; do not retry a paid scan.
- `waiting`, `watching`, `no_qualifying_entry`, or no games: success with no slip.
- Never print the Hermes key.

## Verification

- Every delivered slip ID exists in `GET /api/paper`.
- Every message is visibly marked as a simulation.
- Zero backend-created entries means zero recommended slips.

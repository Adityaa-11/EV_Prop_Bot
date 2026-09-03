---
name: place-dfs-entry
description: Use when live execution is enabled and the backend has pending approved DFS entries. Poll the execution queue, place exact slips on PrizePicks or Underdog with Playwright, and report submitted or failed results.
version: 1.0.0
author: EV Dashboard
license: MIT
metadata:
  hermes:
    tags: [live-execution, prizepicks, underdog, playwright]
    related_skills: [fetch-ev-candidates]
    requires_toolsets: [terminal]
---

# Place DFS Entry

## Purpose

Execute backend-approved live entries. The FastAPI backend alone decides eligibility.

## Procedure

1. Verify `EV_BACKEND_URL` and `HERMES_API_KEY` are set.
2. Run `python scripts/run_executor.py` from this skill directory.
3. For each pending entry returned by the backend:
   - Claim via `POST /api/hermes/execution/{id}/claim`
- If `shadow_mode` is true: open the platform, verify both legs exist, screenshot, report `skipped`
- If `shadow_mode` is false: select exact legs, set stake, click Submit, capture ticket id
   - Report via `POST /api/hermes/execution/{id}/result`
4. Send a short Discord summary if configured (backend also alerts).

## Fail closed

- Missing player or line on platform → `failed`, do not substitute
- Login/captcha failure → `failed`, pause and alert user
- Never modify legs, stake, tier, or platform from the payload
- Never recalculate EV or add extra picks
- One claim per entry; always POST a result

## Playwright

Use `scripts/place_prizepicks.py` or `scripts/place_underdog.py` with persistent browser profiles:

- `PP_BROWSER_PROFILE` for PrizePicks
- `UD_BROWSER_PROFILE` for Underdog

## Verification

- Every `submitted` entry has matching slip ID in `GET /api/live`
- Shadow runs never click Submit

---
name: place-dfs-entry
description: Use when live execution is enabled and the backend has pending approved DFS entries. Poll the execution queue, place exact slips on PrizePicks or Underdog with Playwright, or shadow/place Dabble on a Georgia Android via Appium, and report submitted or failed results.
version: 1.1.0
author: EV Dashboard
license: MIT
metadata:
  hermes:
    tags: [live-execution, prizepicks, underdog, dabble, playwright, appium]
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
- `platform=dabble` must run `place_dabble.py`, never Underdog

## Playwright (PrizePicks / Underdog)

Use `scripts/place_prizepicks.py` or `scripts/place_underdog.py` with persistent browser profiles:

- `PP_BROWSER_PROFILE` for PrizePicks
- `UD_BROWSER_PROFILE` for Underdog

## Appium (Dabble Android)

Dabble is app-only. A real Android 7+ must stay USB-plugged into the Atlanta Mac Mini with GPS on.

1. `python scripts/check_android.py` must report `ok: true`
2. Log into Dabble once on the phone (All-In visible in Georgia)
3. `appium --port 4723`
4. `EXECUTION_SHADOW_MODE=true python scripts/run_executor.py`

Shadow screenshots both legs and does **not** tap Submit. Do not enable `LIVE_EXECUTION_ENABLED` until that pass works. Do not call Dabble's private submit API.

## Verification

- Every `submitted` entry has matching slip ID in `GET /api/live`
- Shadow runs never click Submit

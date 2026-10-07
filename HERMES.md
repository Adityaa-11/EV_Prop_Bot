# EV Bot Automation Contract

Hermes orchestrates this project; it does not calculate betting eligibility.

## Brain vs hands

| Component | Location | Responsibility |
|-----------|----------|----------------|
| FastAPI backend | Railway | EV, tiers, bankroll, approve/reject, ledger, settlement |
| Hermes + Playwright | Mac Mini | Poll approved live entries, submit on PP/UD, report result |
| Hermes + Appium | Mac Mini + Android in Georgia | Shadow/place Dabble in the official app only |
| Grok (Hermes model) | Mac Mini | Navigate UI, handle errors, format alerts — **not** EV math |

## Paper mode (default)

- Call `POST /api/hermes/paper/tick?sport=<sport>` with `X-Hermes-Key` only if Railway scheduler is off.
- A `waiting` or `watching` response is successful. Never lower thresholds or force a daily play.
- New slips in `created_entries` are simulations. Label every Discord message `PAPER — NO REAL WAGER`.
- Read portfolio state from `GET /api/paper`.
- Skill: `fetch-ev-candidates` — **must not** open PrizePicks or Underdog.

## Live mode (when enabled)

Env on Railway:

```bash
EXECUTION_MODE=live
LIVE_EXECUTION_ENABLED=true
EXECUTION_SHADOW_MODE=true   # start true — navigate only, no submit
LIVE_STAKE=1
LIVE_EXCELLENT_ONLY=true
```

Hermes executor loop (Mac Mini):

1. `GET /api/hermes/execution/pending` with `X-Hermes-Key`
2. `POST /api/hermes/execution/{id}/claim` — idempotent lease
3. Run Playwright skill `place-dfs-entry` with **exact** legs/stake from payload
4. `POST /api/hermes/execution/{id}/result` — `{status: submitted|failed|skipped, external_ticket_id?, error?}`
5. `POST /api/hermes/execution/heartbeat` every few minutes

Skill: `place-dfs-entry` — may navigate PP/UD (Playwright) or Dabble Android (Appium); **must not** change legs, stake, or EV logic.

Kill switches:

- `LIVE_EXECUTION_ENABLED=false` on Railway — stops new live queue entries
- `PAPER_SCHEDULER_ENABLED=false` — stops scanning
- `EXECUTION_SHADOW_MODE=true` — Hermes must not click Submit

## Mac Mini setup

```bash
export EV_BACKEND_URL=https://web-production-f7afc.up.railway.app
export HERMES_API_KEY=your_key
export PP_BROWSER_PROFILE=$HOME/.ev-bot/prizepicks-profile
export UD_BROWSER_PROFILE=$HOME/.ev-bot/underdog-profile
export EV_BOT_ARTIFACTS=$HOME/.ev-bot/artifacts

cd hermes/skills/place-dfs-entry/scripts
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium

# Log in once manually (non-headless):
#   PP_HEADLESS=false python3 -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); c=p.chromium.launch_persistent_context('$PP_BROWSER_PROFILE', headless=False); pg=c.new_page(); pg.goto('https://app.prizepicks.com/board'); input('Log in, then press Enter...'); c.close()"
# Repeat for Underdog profile at https://underdogfantasy.com/pick-em/higher-lower/all

# Copy skills to Hermes
cp -R hermes/skills/* ~/.hermes/skills/
```

### Test one executor pass (shadow — no submit)

```bash
export EXECUTION_SHADOW_MODE=true
python3 hermes/skills/place-dfs-entry/scripts/run_executor.py
```

### Live submit (real entries)

Railway:

```bash
EXECUTION_MODE=live
LIVE_EXECUTION_ENABLED=true
EXECUTION_SHADOW_MODE=false
LIVE_STAKE=1
```

Mac Mini:

```bash
export EXECUTION_SHADOW_MODE=false
python3 hermes/skills/place-dfs-entry/scripts/run_executor.py
```

Screenshots on failure/success: `$EV_BOT_ARTIFACTS`.

Schedule (launchd or cron every 2–5 min):

```bash
python hermes/skills/place-dfs-entry/scripts/run_executor.py
```

Credentials stay in env or browser profile — never commit to git.

## Dabble Android (Georgia GPS)

Dabble has no desktop board. Playwright cannot place it. Grok Bot's cloud computer is not in Georgia.

Hardware gate (spare **Android 7+** at the Mini — not a Kindle Fire, not an iPhone 4s):

1. Play Store installs Dabble (`com.dabblesports.us_fantasy`)
2. In Atlanta, real-money **All-In 2-pick** is visible
3. USB debugging on, stay awake while charging, **no lock PIN**
4. Location high accuracy; Dabble location allowed
5. Phone left plugged into the Mini

```bash
export EV_BACKEND_URL=https://web-production-f7afc.up.railway.app
export HERMES_API_KEY=your_key
export EXECUTION_SHADOW_MODE=true
export APPIUM_SERVER_URL=http://127.0.0.1:4723
export EV_BOT_ARTIFACTS=$HOME/.ev-bot/artifacts

cd hermes/skills/place-dfs-entry/scripts
chmod +x setup_android.sh
./setup_android.sh          # adb + pip + Appium driver; runs check_android.py
python3 check_android.py    # must print "ok": true

# Log into Dabble once on the phone.
appium --port 4723

# Shadow pass — screenshots both legs, does not tap Submit
python3 run_executor.py
```

`place_dabble.py` fails closed if ADB/Appium/Dabble/login/player/line is missing. It never posts to Dabble's private submit API.

Keep `LIVE_EXECUTION_ENABLED=false` until a shadow screenshot shows both legs.

Paper floor for Dabble (and all V3 paper): `PAPER_MIN_LEG_WIN=57.7`, ROI ≥ 0, `PAPER_MAX_ENTRIES_PER_PLAYER=1`. Discord `DISCORD_WEBHOOK_DABBLE` is tap-card backup only — no PP/UD fallback.

## Dashboard

- Paper: `GET /api/paper` → Vercel `/paper-trading`
- Live: `GET /api/live`

## Rules

- Never recalculate EV, combine legs differently, or override a rejected risk decision.
- Never print `HERMES_API_KEY` or platform passwords in logs or Discord.
- Real execution only after paper validation and shadow mode pass.

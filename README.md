# 🎯 EV Dashboard - PrizePicks & Underdog

A full-stack application to find profitable (+EV) plays on **PrizePicks** and **Underdog Fantasy** by comparing their lines to sharp sportsbook odds (DraftKings, FanDuel).

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│   FastAPI API   │────▶│  External APIs  │
│  (Vercel/Next)  │     │    (Railway)    │     │  (UD, Odds API) │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │ SQLite + Bot +  │
                        │ Hermes API      │
                        └─────────────────┘
```

- **Frontend**: Next.js dashboard hosted on Vercel
- **Backend**: FastAPI + Discord bot hosted on Railway
- **Data Sources**: PrizePicks through The Odds API `us_dfs`, Underdog direct API, sportsbook prices through The Odds API
- **Scoring**: exact-line, same-event, weighted no-vig sportsbook consensus
- **Storage**: durable SQLite snapshots and settlement history

---

## 📋 Commands (Discord Bot)

| Command | Description |
|---------|-------------|
| `!ev nba` | Get PrizePicks +EV plays |
| `!ud nba` | Get Underdog +EV plays |
| `!both nba` | Get from both platforms |
| `!webhook pp nba` | Post PrizePicks to webhook |
| `!webhook ud nba` | Post Underdog to webhook |
| `!player LeBron` | Search player props |
| `!calc -140 +110` | Calculate no-vig odds |
| `!help_ev` | Show all commands |

**Supported Sports**: `nba`, `nfl`, `mlb`, `nhl`

---

## 🚀 Deployment

### Prerequisites

1. **The Odds API Key** (free): https://the-odds-api.com
2. **Discord Bot Token**: https://discord.com/developers/applications
3. **Discord Webhooks**: Create in your Discord server
4. **GitHub Account**: For deployment
5. **Railway Account**: https://railway.app (free tier available)
6. **Vercel Account**: https://vercel.com (free tier available)

### Step 1: Push to GitHub

```bash
cd "Prizepicks odds bot"
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/ev-dashboard.git
git push -u origin main
```

### Step 2: Deploy Backend to Railway

1. Go to [Railway](https://railway.app) and sign in with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository
4. Railway will auto-detect Python and use the `Procfile`
5. Go to **Settings** → **Variables** and add:

```
DISCORD_TOKEN=your_discord_bot_token
DISCORD_WEBHOOK_PRIZEPICKS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_UNDERDOG=https://discord.com/api/webhooks/...
ODDS_API_KEY=your_odds_api_key
ADMIN_API_KEY=generate_a_long_random_secret
HERMES_API_KEY=generate_a_different_long_random_secret
DATABASE_PATH=/data/ev_bot.db
FRONTEND_URL=https://your-app.vercel.app
BACKEND_URL=https://your-app.up.railway.app
PORT=8000
RUN_MODE=both
```

6. Attach a Railway volume at `/data` so snapshots survive deploys.
7. Copy your Railway URL (e.g., `https://your-app.up.railway.app`)

### Step 3: Deploy Frontend to Vercel

1. Go to [Vercel](https://vercel.com) and sign in with GitHub
2. Click **"New Project"** → Import your repository
3. Set **Root Directory** to `frontend`
4. Add environment variable:

```
NEXT_PUBLIC_API_URL=https://your-app.up.railway.app
```

5. Click **Deploy**

### Step 4: Update CORS

After Vercel deploys, go back to Railway and update:

```
FRONTEND_URL=https://your-actual-vercel-url.vercel.app
```

---

## 💻 Local Development

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file
cp env.example .env
# Edit .env with your keys

# Run API only
RUN_MODE=api python main.py

# Run bot only
RUN_MODE=bot python main.py

# Run both
python main.py
```

### Frontend

```bash
cd frontend

# Install dependencies
pnpm install

# Create .env.local
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Run dev server
pnpm dev
```

Open http://localhost:3000

---

## 📡 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Check API status |
| `GET /api/props?sport=nba` | Get all props |
| `GET /api/ev?sport=nba` | Get +EV plays |
| `GET /api/middles?sport=nba` | Get middle opportunities |
| `GET /api/games?sport=nba` | Get games summary |
| `GET /api/compare/{player}` | Compare player across platforms |
| `POST /api/calc` | Calculate no-vig odds |
| `POST /api/calc-entry-ev` | Calculate payout-aware entry EV |
| `POST /api/hermes/scan` | Protected quota-consuming scan (`X-Hermes-Key`) |
| `GET /api/hermes/candidates` | Protected latest candidate snapshot |
| `GET /api/hermes/runs` | Protected pipeline run history |
| `POST /api/hermes/outcomes/{id}` | Protected settlement/CLV recording |
| `GET /api/paper` | Public read-only paper bankroll, slips, and live status |
| `GET /api/paper/line-history` | Public persisted observation history |
| `POST /api/hermes/paper/tick` | Protected event-gated paper automation heartbeat |
| `POST /api/hermes/paper/deliver` | Protected Discord paper-slip delivery retry |
| `POST /api/hermes/paper/settle` | Protected MLB settlement pass |
| `POST /api/hermes/paper/entries/{id}/settle` | Protected manual paper settlement |

Public dashboard routes only read snapshots. Upstream refreshes, key rotation,
debugging, and cache administration require `X-Hermes-Key` or `X-Admin-Key`.

Paper automation runs inside the Railway API process when
`PAPER_SCHEDULER_ENABLED=true`. It checks the free events endpoint before a paid
scan, adapts cadence as lock approaches, requires two stable candidate
observations, posts Discord slips labeled `PAPER — NO REAL WAGER`, records CLV,
and settles supported MLB markets. Creating zero slips is a successful outcome.

Kill switch / rollback:

```bash
# Railway variable
PAPER_SCHEDULER_ENABLED=false
```

Also require `DATABASE_PATH=/data/ev_bot.db` with a Railway volume mounted at
`/data` before enabling the scheduler.

The `/paper-trading` dashboard polls the paper ledger every ten seconds.

Production smoke test:

```bash
HERMES_API_KEY=... python scripts/smoke_test.py https://your-api.up.railway.app --scan --sport mlb
```

---

## 💰 Candidate Edge and Entry EV

Candidate `ev_percentage` is retained for frontend compatibility and represents
probability edge over the configured platform break-even—not guaranteed dollar
profit. Use `POST /api/calc-entry-ev` with the current platform payout table to
calculate entry-level expected ROI. That calculation assumes independent legs.

### Break-Even Percentages

### PrizePicks

| Slip Type | Break-Even |
|-----------|------------|
| 5/6-Flex | 54.34% |
| 4-Power | 56.23% |
| 2-Power | 57.74% |

### Underdog

| Slip Type | Break-Even |
|-----------|------------|
| 5-Leg | 52.38% |
| 4-Leg | 53.57% |
| 3-Leg | 55.56% |
| 2-Leg | 60.00% |

---

## 📁 Project Structure

```
├── api.py              # FastAPI backend
├── bot.py              # Discord bot
├── main.py             # Unified runner for Railway
├── storage.py          # SQLite snapshots and outcome history
├── tests/              # Deterministic scoring/storage tests
├── Procfile            # Railway deployment config
├── requirements.txt    # Python dependencies
├── env.example         # Environment template
│
└── frontend/           # Next.js frontend
    ├── app/            # App router pages
    ├── components/     # React components
    ├── lib/            # Utilities & API client
    ├── vercel.json     # Vercel config
    └── package.json
```

---

## ⚠️ API Rate Limits

| Service | Free Tier |
|---------|-----------|
| The Odds API | 500 requests/month |
| PrizePicks | No official limit (be respectful) |
| Underdog | No official limit (be respectful) |

**Tip**: The Odds API charges per event/market. Keep public refresh disabled and
let one authenticated scheduler trigger sport-specific scans within a fixed
quota budget.

---

## 🔧 Troubleshooting

### "No props found"
- Games may not be scheduled today
- Props appear 2-3 hours before game time
- Check back during game days

### "No odds found"
- Sportsbooks post player props 12-24 hours before games
- Check if your ODDS_API_KEY is valid
- You may have exceeded your monthly quota

### Frontend can't connect to API
- Check NEXT_PUBLIC_API_URL is set correctly
- Ensure Railway backend is running
- Check CORS - FRONTEND_URL must match your Vercel URL

### Bot not responding
- Verify DISCORD_TOKEN is correct
- Make sure bot has MESSAGE CONTENT INTENT enabled
- Check bot is invited to server with correct permissions

---

## 📄 License

MIT License - Use at your own risk. Sports betting involves risk.
# Poker

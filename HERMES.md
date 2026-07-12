# EV Bot Automation Contract

Hermes orchestrates this project; it does not calculate betting eligibility.

- The FastAPI backend is the only authority for EV, quality tiers, bankroll limits, paper-slip construction, settlement, and CLV.
- Call `POST /api/hermes/paper/tick?sport=<sport>` with `X-Hermes-Key`. Do not call paid upstream APIs directly.
- A `waiting` or `watching` response is successful. Never lower thresholds or force a daily play.
- New slips in `created_entries` are simulations. Label every Discord message `PAPER — NO REAL WAGER`.
- Read portfolio state from `GET /api/paper`.
- Never navigate PrizePicks or Underdog, submit an entry, expose credentials, or reinterpret a rejected risk decision.
- Real-money execution is outside the current implementation.
- Always-on scanning belongs to Railway (`PAPER_SCHEDULER_ENABLED`). Local Hermes is optional.
- Kill switch: set `PAPER_SCHEDULER_ENABLED=false` on Railway and redeploy/restart.

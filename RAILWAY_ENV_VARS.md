# Railway Environment Variables

Copy these to your Railway service settings.

## Required - Database
- `DATABASE_URL` — PostgreSQL connection string (Neon)

## Required - APIs
- `API_FOOTBALL_KEY` — API-Football key for injuries/lineups/stats
- `THE_ODDS_API_KEY` — The Odds API key for live odds

## Required - Discord Webhooks
- `DISCORD_WEBHOOK_URL` — Main predictions channel
- `DISCORD_FREE_PICKS_WEBHOOK_URL` — Public free picks channel
- `DISCORD_PROPS_WEBHOOK_URL` — Props/corners/cards channel
- `DISCORD_RESULTS_WEBHOOK` — Results notifications
- `DISCORD_REDDIT_WEBHOOK_URL` — Reddit-style recap
- `WEBHOOK_PARLAYS` — Parlay predictions

## Required - Admin
- `ADMIN_API_KEY` — API authentication key

## Optional - GitHub
- `GITHUB_TOKEN` — GitHub access token

## Railway Service Setup

### Main Service: Worker (Required - 24/7)
This is the core service. Uses the Dockerfile which runs `combined_sports_runner.py`.

**Start command:** `python3 combined_sports_runner.py`

This handles everything:
- Value Singles predictions (every 1 hour)
- ML Parlays (every 3 hours)
- College Basketball (every 2 hours)
- Result verification (every 5 minutes)
- Discord distribution (daily at 10:00 UTC)
- Daily/weekly recaps

**Important:** This is a background worker — disable health checks in Railway
(Settings → Deploy → Health Check Path → leave empty).

### Optional: Add More Services (same repo)
Create separate Railway services pointing to the same GitHub repo.
Override the start command per service:

1. **Dashboard**: `streamlit run pgr_dashboard.py --server.port $PORT --server.address 0.0.0.0`
2. **API**: `python3 -m uvicorn api:app --host 0.0.0.0 --port $PORT`

These are web services — Railway assigns $PORT automatically.

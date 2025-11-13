# Railway Deployment Guide - Football Predictions Platform

## Quick Start

### 1. Create Railway Project
```bash
# Install Railway CLI (optional)
npm install -g @railway/cli

# Or use Railway web interface: https://railway.app/
```

### 2. Set Up PostgreSQL Database

**In Railway Dashboard:**
1. Click "New Project"
2. Add "PostgreSQL" service
3. Copy the `DATABASE_URL` connection string

### 3. Configure Environment Variables

**Required Secrets** (Add in Railway → Variables tab):

```bash
# Database (auto-provided by Railway PostgreSQL)
DATABASE_URL=postgresql://...
PGHOST=...
PGPORT=5432
PGUSER=...
PGPASSWORD=...
PGDATABASE=...

# API Keys
API_FOOTBALL_KEY=your_api_football_key
THE_ODDS_API_KEY=your_odds_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Python Configuration
PYTHONUNBUFFERED=1
TF_ENABLE_ONEDNN_OPTS=0
```

### 4. Deploy Code

**Option A: GitHub Integration (Recommended)**
1. Push your code to GitHub
2. In Railway: "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Railway auto-detects Python and installs dependencies

**Option B: Railway CLI**
```bash
railway login
railway init
railway up
```

### 5. Configure Services

Railway doesn't use Procfile directly. Create separate services:

**Service 1: Web Dashboard**
- Name: `dashboard`
- Start Command: `streamlit run pgr_dashboard.py --server.port $PORT --server.address 0.0.0.0`
- Port: Railway auto-assigns (uses $PORT)

**Service 2: Prediction Generator**
- Name: `prediction-generator`
- Start Command: `python3 real_football_champion.py`

**Service 3: SGP Champion**
- Name: `sgp-champion`
- Start Command: `python3 sgp_champion.py`

**Service 4: Women 1X2**
- Name: `women-1x2`
- Start Command: `python3 women_1x2_champion.py`

**Service 5: Auto Bet Logger**
- Name: `auto-bet-logger`
- Start Command: `python3 auto_bet_logger.py`

**Service 6: Daily Categorizer**
- Name: `daily-categorizer`
- Start Command: `python3 daily_bet_categorizer.py`

**Service 7: Daily Reminder**
- Name: `daily-reminder`
- Start Command: `python3 daily_games_reminder.py`

**Service 8: Performance Updates**
- Name: `performance-updates`
- Start Command: `python3 schedule_performance_updates.py`

### 6. Database Migration

**Initialize Database Schema:**
```bash
# Railway CLI method
railway run python3 -c "from db_connection import get_db_connection; conn = get_db_connection(); print('Database connected')"

# Or run initialization scripts
railway run python3 check_db.py
```

**The database tables will auto-create** when workflows first run.

### 7. Export Existing Data from Replit

**On Replit, run:**
```bash
# Export predictions
python3 -c "
import psycopg2
import os
import json

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Export football_opportunities
cur.execute('SELECT * FROM football_opportunities')
data = cur.fetchall()
columns = [desc[0] for desc in cur.description]

with open('export_predictions.json', 'w') as f:
    json.dump([dict(zip(columns, row)) for row in data], f, default=str, indent=2)

print(f'Exported {len(data)} predictions')
"
```

**Then import on Railway:**
```bash
railway run python3 import_predictions.py
```

## Important Notes

### Python Version
Railway auto-detects Python 3.11+ from `pyproject.toml`

### Dependencies
Railway uses `railway_requirements.txt` (included in this export)

### Port Binding
- Streamlit dashboard must use `$PORT` environment variable
- Already configured in start command above

### Service Resources
Each service runs independently. Monitor in Railway dashboard.

### Logs
Access logs via Railway dashboard or CLI:
```bash
railway logs
```

### Database Backups
Railway PostgreSQL includes automatic backups on paid plans.

## Cost Estimate

**Railway Pricing (as of 2025):**
- Hobby Plan: $5/month (includes 512MB RAM per service, PostgreSQL)
- Estimated cost for 8 services: $5-10/month
- PostgreSQL: Included in Hobby plan

**Total: ~$10/month** vs Replit's higher costs

## Troubleshooting

### Issue: "Module not found"
```bash
# Rebuild dependencies
railway run pip install -r railway_requirements.txt
```

### Issue: Database connection errors
```bash
# Check DATABASE_URL is set
railway variables

# Test connection
railway run python3 -c "import psycopg2; print(psycopg2.connect('$DATABASE_URL'))"
```

### Issue: Services not starting
- Check logs: `railway logs --service <service-name>`
- Verify environment variables are set
- Ensure start commands are correct

## Performance Optimization

### Reduce Service Count
You can combine some workflows into one service:

**Combined Scheduler Service:**
```python
# Create combined_scheduler.py
import schedule
import time
from real_football_champion import main as predictions
from sgp_champion import main as sgp
from women_1x2_champion import main as women

schedule.every(1).hours.do(predictions)
schedule.every(1).hours.do(sgp)
schedule.every(1).hours.do(women)

while True:
    schedule.run_pending()
    time.sleep(60)
```

This reduces from 8 services to 2-3 services (Dashboard + Combined Scheduler + Auto Logger).

## Next Steps

1. ✅ Create Railway account
2. ✅ Set up PostgreSQL database
3. ✅ Configure environment variables
4. ✅ Deploy via GitHub or CLI
5. ✅ Create services with start commands above
6. ✅ Export data from Replit
7. ✅ Import data to Railway
8. ✅ Monitor logs and verify predictions generating

## Support

Railway Docs: https://docs.railway.app/
Railway Discord: https://discord.gg/railway

Good luck with your migration! 🚀

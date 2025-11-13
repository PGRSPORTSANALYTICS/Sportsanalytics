# Railway Migration - Complete Package

## What's Included

### Deployment Files
1. ✅ **railway_requirements.txt** - All Python dependencies
2. ✅ **Procfile** - Service definitions for Railway
3. ✅ **RAILWAY_DEPLOYMENT.md** - Complete deployment guide
4. ✅ **RAILWAY_CHECKLIST.md** - Step-by-step migration checklist

### Migration Scripts
5. ✅ **export_database_to_railway.py** - Export Replit database
6. ✅ **import_database_from_replit.py** - Import to Railway database

### Cost Optimization
7. ✅ **combined_scheduler.py** - Single service for all predictions (saves $$$)

## Quick Start (5 Steps)

### 1. Export Data (On Replit)
```bash
python3 export_database_to_railway.py
# Download the railway_export/ folder
```

### 2. Create Railway Project
- Go to https://railway.app/
- Sign up and create new project
- Add PostgreSQL database

### 3. Deploy Code
- Push code to GitHub
- Connect GitHub to Railway
- Railway auto-deploys

### 4. Configure Services
Choose your deployment:

**Simple (Recommended - $5-10/month):**
- Service 1: Dashboard (`streamlit run pgr_dashboard.py --server.port $PORT --server.address 0.0.0.0`)
- Service 2: Combined Scheduler (`python3 combined_scheduler.py`)

**Full (Advanced - $10-20/month):**
- 8 separate services (see RAILWAY_DEPLOYMENT.md)

### 5. Import Data
```bash
railway run python3 import_database_from_replit.py
```

## Environment Variables Needed

Copy these from Replit → Secrets to Railway → Variables:

```
DATABASE_URL=<auto-filled>
API_FOOTBALL_KEY=<your-key>
THE_ODDS_API_KEY=<your-key>
TELEGRAM_BOT_TOKEN=<your-key>
PYTHONUNBUFFERED=1
TF_ENABLE_ONEDNN_OPTS=0
```

## Cost Comparison

| Platform | Monthly Cost | Notes |
|----------|-------------|-------|
| Replit | $20-50+ | Higher for complex projects |
| Railway (Simple) | $5-10 | 2 services + PostgreSQL |
| Railway (Full) | $10-20 | 8 services + PostgreSQL |

**Savings: 50-75%** 💰

## Why Railway?

✅ **Simpler Infrastructure** - No complex workflow management
✅ **Better Performance** - Dedicated resources per service
✅ **Lower Cost** - Pay only for what you use
✅ **Easy Scaling** - Auto-scales with traffic
✅ **Better Monitoring** - Clean logs and metrics
✅ **PostgreSQL Included** - No database locks like Replit

## What Stays the Same

✅ All prediction logic (exact scores, SGP, women's 1X2)
✅ Telegram bot functionality
✅ Dashboard features
✅ Database structure
✅ API integrations

## What Changes

- ❌ No more workflow restarts
- ❌ No more database locking issues
- ❌ No more SSL connection drops
- ✅ Services run independently
- ✅ Better resource allocation
- ✅ Cleaner logs

## Migration Timeline

| Step | Time | 
|------|------|
| Export data | 5 min |
| Setup Railway | 10 min |
| Deploy code | 15 min |
| Configure services | 20 min |
| Import data | 10 min |
| Testing | 30 min |
| **Total** | **1.5 hours** |

## Support

If you need help:
1. Check RAILWAY_DEPLOYMENT.md for detailed instructions
2. Use RAILWAY_CHECKLIST.md to track progress
3. Railway Discord: https://discord.gg/railway
4. Railway Docs: https://docs.railway.app/

## Success Metrics

After migration, you should see:
- ✅ Dashboard live at Railway URL
- ✅ Predictions generating every hour
- ✅ Telegram bot responding
- ✅ Database queries working
- ✅ Monthly costs under $15

## Your Current System

**16 Quality Leagues:**
- Premier League, La Liga, Serie A, Bundesliga, Ligue 1
- Championship, Eredivisie, Primeira Liga, Belgian Pro
- Norway Eliteserien, Brazil Serie A, J1 League
- Argentina Liga, Colombia Liga, Champions League, Europa

**3 Products:**
1. Exact Score Predictions (499-999 SEK/month)
2. SGP/Same Game Parlay (999-1,499 SEK/month)
3. Women's 1X2 Match Winner

**Everything migrates perfectly to Railway.**

## Next Steps

1. Read RAILWAY_CHECKLIST.md
2. Follow step-by-step
3. Export your data
4. Deploy to Railway
5. Import your data
6. Start generating predictions

Good luck with your migration! 🚀

---

*Created: November 13, 2025*
*Ready for Railway deployment*

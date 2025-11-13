# 🚀 START HERE - Railway Migration Guide

## Your Code is Ready for Railway!

I've prepared everything you need for tonight's migration. All files are ready to go.

---

## Quick Start (Tonight's Plan)

### Option 1: Automated Setup (Recommended - 5 minutes)
```bash
./railway_setup.sh
```

This script will:
1. Export your database automatically
2. Prepare Git repository
3. Show you next steps

### Option 2: Manual Setup (10 minutes)

**Step 1: Export Data**
```bash
python3 export_database_to_railway.py
```
Downloads the `railway_export/` folder to your computer.

**Step 2: Push to GitHub**
```bash
git init
git add .
git commit -m "Initial commit for Railway"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

**Step 3: Deploy to Railway**
1. Go to https://railway.app/ and sign up
2. "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Add PostgreSQL database
5. Set environment variables (see below)

**Step 4: Configure Services**

Choose **Simple Deployment** (saves money):

Service 1 - **Dashboard**:
```
Name: dashboard
Start Command: streamlit run pgr_dashboard.py --server.port $PORT --server.address 0.0.0.0
Public: Yes ✅
```

Service 2 - **Combined Scheduler**:
```
Name: scheduler  
Start Command: python3 combined_scheduler.py
Public: No ❌
```

**Step 5: Set Environment Variables**

In Railway → Settings → Variables, add these:

```bash
# API Keys (copy from Replit Secrets)
API_FOOTBALL_KEY=your_key_here
THE_ODDS_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_token_here

# Python Config
PYTHONUNBUFFERED=1
TF_ENABLE_ONEDNN_OPTS=0

# DATABASE_URL is auto-set by Railway PostgreSQL
```

**Step 6: Import Data**
```bash
railway run python3 import_database_from_replit.py
```

**Done!** 🎉

---

## Files Created for You

### Essential Files
1. ✅ **MIGRATION_SUMMARY.md** - Overview and cost comparison
2. ✅ **RAILWAY_DEPLOYMENT.md** - Complete deployment guide  
3. ✅ **RAILWAY_CHECKLIST.md** - Step-by-step checklist
4. ✅ **railway_requirements.txt** - All Python dependencies
5. ✅ **Procfile** - Service definitions

### Migration Scripts
6. ✅ **export_database_to_railway.py** - Export Replit DB
7. ✅ **import_database_from_replit.py** - Import to Railway
8. ✅ **combined_scheduler.py** - All predictions in one service

### Setup Helpers
9. ✅ **railway_setup.sh** - Automated setup script
10. ✅ **.gitignore** - Git ignore rules

---

## Cost Savings

| What | Replit | Railway | Savings |
|------|--------|---------|---------|
| Monthly | $20-50+ | $5-10 | **60-80%** 💰 |

Railway Simple Deployment:
- 1 Dashboard service
- 1 Scheduler service  
- 1 PostgreSQL database
- **Total: $5-10/month**

---

## What's Included

Your complete football predictions platform:

**16 Quality Leagues:**
✅ Premier League, La Liga, Serie A, Bundesliga, Ligue 1
✅ Championship, Eredivisie, Primeira Liga, Belgian Pro
✅ Norway, Brazil Serie A, J1 League, Argentina, Colombia
✅ Champions League, Europa League

**3 Products:**
1. Exact Score Predictions
2. SGP/Same Game Parlay
3. Women's 1X2 Match Winner

**All Features:**
✅ AI ensemble predictions
✅ Expected Value (EV) filtering
✅ Telegram bot delivery
✅ Web dashboard analytics
✅ Automatic result verification
✅ Performance tracking

---

## Why Railway Fixes Your Issues

**Current Replit Problems:**
❌ Workflows restart every 2-3 minutes
❌ Database locking issues
❌ SSL connection drops
❌ Complex workflow management
❌ High costs

**Railway Solutions:**
✅ Services run independently (no restarts)
✅ Dedicated PostgreSQL (no locks)
✅ Stable connections
✅ Simple service management
✅ 60-80% cheaper

---

## Timeline

| Task | Time |
|------|------|
| Export data | 5 min |
| Push to GitHub | 5 min |
| Setup Railway | 10 min |
| Configure services | 15 min |
| Import data | 10 min |
| Test & verify | 15 min |
| **Total** | **60 minutes** |

---

## Environment Variables Checklist

Copy these from **Replit → Secrets** to **Railway → Variables**:

- [ ] API_FOOTBALL_KEY
- [ ] THE_ODDS_API_KEY  
- [ ] TELEGRAM_BOT_TOKEN
- [ ] PYTHONUNBUFFERED=1
- [ ] TF_ENABLE_ONEDNN_OPTS=0

**DATABASE_URL** is auto-set when you add PostgreSQL ✅

---

## Support Resources

📖 **Detailed Guides:**
- RAILWAY_DEPLOYMENT.md (complete reference)
- RAILWAY_CHECKLIST.md (step-by-step)
- MIGRATION_SUMMARY.md (overview)

🆘 **Help:**
- Railway Docs: https://docs.railway.app/
- Railway Discord: https://discord.gg/railway

---

## Verification Steps

After deployment, check:

1. ✅ Dashboard accessible at Railway URL
2. ✅ Predictions generating (check Railway logs)
3. ✅ Telegram bot responding to /status
4. ✅ Database has your historical data
5. ✅ Costs showing $5-10/month

---

## Quick Commands Reference

**Export data:**
```bash
python3 export_database_to_railway.py
```

**Run setup:**
```bash
./railway_setup.sh
```

**Check Railway logs:**
```bash
railway logs
railway logs --service dashboard
railway logs --service scheduler
```

**Import data:**
```bash
railway run python3 import_database_from_replit.py
```

---

## Success Checklist

Tonight's Migration Goals:

- [ ] Database exported from Replit
- [ ] Code pushed to GitHub
- [ ] Railway project created
- [ ] PostgreSQL database added
- [ ] Environment variables set
- [ ] Services deployed (dashboard + scheduler)
- [ ] Data imported successfully
- [ ] Dashboard accessible
- [ ] Predictions generating
- [ ] Telegram bot working

---

## What to Do Right Now

1. **Read this file** (you're doing it! ✅)
2. **Run setup:** `./railway_setup.sh`
3. **Follow prompts** in terminal
4. **Deploy to Railway** (follow on-screen instructions)
5. **Test everything**
6. **Done!** 🎉

---

## Emergency Rollback

If something goes wrong:
- Your Replit project is **unchanged**
- All data is still in Replit
- You can continue using Replit
- Railway is a **copy**, not a migration

---

## Final Notes

- ⏰ Estimated time: **1 hour total**
- 💰 Monthly savings: **$10-40**
- 🎯 Goal: Stable, affordable platform
- 📊 All features preserved
- 🔒 Data safely exported

---

**You're ready to migrate!** 🚀

Start with: `./railway_setup.sh`

Good luck tonight! The code is prepared and ready.

---

*Generated: November 13, 2025*
*All files verified and ready for Railway deployment*

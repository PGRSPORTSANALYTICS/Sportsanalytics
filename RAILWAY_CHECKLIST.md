# Railway Migration Checklist

## Pre-Migration (On Replit)

- [ ] **Export Database**
  ```bash
  python3 export_database_to_railway.py
  ```
  This creates `railway_export/` folder with all data

- [ ] **Download railway_export folder**
  - Download the entire `railway_export/` folder to your computer
  - You'll upload this to Railway after deployment

- [ ] **Document your environment variables**
  - API_FOOTBALL_KEY: `___________`
  - THE_ODDS_API_KEY: `___________`
  - TELEGRAM_BOT_TOKEN: `___________`

## Railway Setup

### Step 1: Create Account
- [ ] Sign up at https://railway.app/
- [ ] Connect your GitHub account

### Step 2: Create PostgreSQL Database
- [ ] New Project → "Provision PostgreSQL"
- [ ] Copy the `DATABASE_URL` from Variables tab

### Step 3: Push Code to GitHub
- [ ] Create new GitHub repository
- [ ] Push all files from Replit to GitHub
  ```bash
  git init
  git add .
  git commit -m "Initial commit for Railway deployment"
  git remote add origin <your-github-repo>
  git push -u origin main
  ```

### Step 4: Deploy to Railway
- [ ] Railway Dashboard → "New Project"
- [ ] Select "Deploy from GitHub repo"
- [ ] Choose your repository
- [ ] Wait for initial build (5-10 minutes)

### Step 5: Configure Environment Variables
In Railway → Variables tab, add:

```
DATABASE_URL=<auto-filled-by-railway>
API_FOOTBALL_KEY=<your-key>
THE_ODDS_API_KEY=<your-key>
TELEGRAM_BOT_TOKEN=<your-key>
PYTHONUNBUFFERED=1
TF_ENABLE_ONEDNN_OPTS=0
```

### Step 6: Set Up Services

**Option A: Simple (3 services total)**
1. **Dashboard Service**
   - Start Command: `streamlit run pgr_dashboard.py --server.port $PORT --server.address 0.0.0.0`
   - Public Domain: Enabled ✅

2. **Combined Scheduler Service**
   - Start Command: `python3 combined_scheduler.py`
   - Public Domain: Disabled ❌

3. **PostgreSQL Database**
   - (Already created in Step 2)

**Option B: Full (8+ services)**
See RAILWAY_DEPLOYMENT.md for individual service configuration

### Step 7: Import Data
- [ ] Upload `railway_export/` folder to your Railway project
- [ ] Run import script:
  ```bash
  railway run python3 import_database_from_replit.py
  ```

### Step 8: Verify Deployment
- [ ] Check Dashboard URL (Railway provides this)
- [ ] Verify predictions are generating (check logs)
- [ ] Test Telegram bot commands
- [ ] Confirm database has data

## Post-Migration

### Monitor Services
- [ ] Check Railway logs daily for first week
- [ ] Monitor prediction generation
- [ ] Verify Telegram broadcasts working

### Cost Monitoring
- [ ] Enable billing alerts in Railway
- [ ] Expected cost: $5-15/month (vs Replit's higher pricing)

### Backup Strategy
- [ ] Railway PostgreSQL includes automatic backups (paid plans)
- [ ] Export data weekly using `export_database_to_railway.py`

## Troubleshooting

### "Module not found" errors
```bash
railway run pip install -r railway_requirements.txt
```

### Dashboard not accessible
- Verify Public Domain is enabled for dashboard service
- Check port is set to `$PORT` in start command

### Predictions not generating
- Check scheduler logs: `railway logs --service combined-scheduler`
- Verify API keys are set correctly
- Check PostgreSQL connection

### Database connection errors
- Verify `DATABASE_URL` is set
- Check PostgreSQL service is running
- Test connection: `railway run python3 check_db.py`

## Rollback Plan (If needed)

If Railway doesn't work:
1. Your Replit project is still intact
2. Re-import data to Replit PostgreSQL
3. Restart Replit workflows

## Success Criteria

✅ Dashboard accessible via Railway URL
✅ Predictions generating every hour
✅ Telegram bot responding to commands
✅ Database queries working
✅ Costs under $15/month

## Estimated Timeline

- Setup Railway account: 10 minutes
- Deploy code: 15 minutes
- Configure services: 20 minutes
- Import data: 10 minutes
- Testing: 30 minutes

**Total: ~1.5 hours**

## Support Resources

- Railway Docs: https://docs.railway.app/
- Railway Discord: https://discord.gg/railway
- Your deployment guide: See RAILWAY_DEPLOYMENT.md

Good luck! 🚀

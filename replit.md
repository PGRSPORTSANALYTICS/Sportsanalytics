# Sports Betting Analytics Platform

## Overview
This project is an AI-powered sports betting analytics platform, leveraging Monte Carlo simulation and ensemble modeling for profitable predictions. The platform focuses on Value Singles as the core product (1X2, Over/Under, BTTS, Double Chance markets) with Multi-Match Parlays and College Basketball as secondary products. The goal is to achieve a 15-20% realistic ROI with strict EV filtering (5%+ edge required). Key features include a premium Streamlit dashboard, a Telegram bot for prediction delivery, and automatic result verification, all driven by data-driven AI analysis based on xG, form, H2H, injuries, and standings.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### UI/UX Decisions
The platform utilizes a Streamlit web application with a wide layout, Plotly for interactive charts, auto-refresh functionality, and consistent color coding. Interactive elements and multi-chart support enhance data visualization.

### Technical Implementations
The system employs advanced prediction features including:
- **Comprehensive Analysis:** Team form, Head-to-Head history, league standings, odds movement tracking, and venue-specific form (xG).
- **Data Sourcing:** Dual-source system for injury and lineup data (API-Football with Transfermarkt fallback) and a triple-layer fallback for data resilience (API-Football, web scrapers, safe defaults).
- **Prediction Models:** Neural Networks for exact scores (removed), an Ensemble Prediction System combining Poisson distribution, neural network probabilities, and H2H patterns, and Similar Matches Technology for confidence adjustment. Full integration of Monte Carlo simulation across all prediction engines.
- **Value-Based Betting:** Expected Value (EV) Filtering with Kelly Criterion Bet Sizing ensures betting only when a genuine edge exists.
- **Multi-Market Expansion:** Dedicated engines for various market types including Value Singles (1X2, AH), Totals (Over/Under), Both Teams To Score (BTTS), Corners (match, team, handicap), Shots (team, match), and Cards (match, team).
- **Bet Monitoring & Delivery:** Hybrid bet monitoring with a `BetStatusService`, Live Bet Control Center, extended Telegram bot commands, and dual Telegram channels for different prediction types with smart volume control. Automated Discord result notifications.
- **Intelligent Result Verification:** Production-ready caching and cooldown system with multi-source fallback (Flashscore, API-Football, The Odds API, Sofascore) ensures fast and reliable result settlement.
- **Bankroll & Analytics:** Centralized `BankrollManager` for tracking bankroll and exposure (legacy dynamic staking option). Primary analytics now use a unit-based system for ROI, profit (units), and hit rate, decoupled from real money.
- **AI Training & Learning:** Comprehensive pipeline to collect 40+ features for future AI model training, including `training_data` PostgreSQL table and a `DataCollector`. Includes a Learning System Track Record dashboard section and Trust Level Learning.
- **ML Parlay Engine:** New low/medium risk product for Moneyline/1X2/DNB parlays, with 2-4 legs, specific odds ranges, EV, and stake percentages. Multi-Match Parlay System builds parlays from approved Value Singles across different matches.
- **Prediction Filtering:** H2H BTTS filter, AI-learned SGP odds filter, Realistic SGP Margin Calibration, and PGR Final Score Strategy.
- **3-Tier Trust Level Classification:** Predictions classified into High (L1), Medium (L2), and Soft (L3) Trust levels based on simulation approval, EV, confidence, and disagreement.
- **Central Market Router:** Portfolio balancing system using a two-pass selection algorithm with per-market caps, prioritization by trust level and EV, and a global daily pick cap to ensure diversified daily cards.
- **Odds Drift Module:** Real-time odds movement tracking and drift scoring to indicate market agreement with the model and block bets if drift is unfavorable.
- **Syndicate Engine Suite (v1.0):** Three specialized engines that work in sequence to enhance prediction quality:
  - **Profile Boost Engine:** Adjusts EV (alpha=0.15) and confidence (beta=0.12) based on contextual factors: tempo, rivalry, referee profile, wing play, formation aggression, weather, and form momentum. Config: `profile_boost_config.py`.
  - **Market Weight Engine:** Learns from 30-day rolling historical ROI data to bias towards high-performing markets. Weights range 0.6-1.4 with shrinkage for small samples. Config: `market_weight_config.py`.
  - **Hidden Value Scanner:** Identifies "soft edge" picks with EV between -1% and +2% using composite scoring (EV proximity, confidence, boost score, market weight). Max 5 picks/day, min score 40/100. Config: `hidden_value_config.py`.
  - API endpoints: `/api/syndicate/status`, `/api/syndicate/boost`, `/api/syndicate/market_weights`
- **LIVE LEARNING MODE (v1.0 - ACTIVE):** Full data capture system for model calibration:
  - Captures ALL trust tiers (L1, L2, L3, Hidden Value) without filtering
  - CLV tracking: stores opening_odds, closing_odds, clv_delta for every pick
  - Unit-based P/L tracking (no monetary staking applied)
  - Stores raw_ev, boosted_ev, weighted_ev for every pick
  - Profile boost details and market weight saved with each pick
  - Market Weight Engine learns from live results automatically
  - API endpoints: `/api/live_learning/status`, `/api/live_learning/progress`, `/api/live_learning/picks`, `/api/live_learning/settle`
  - Config: `live_learning_config.py`, Tracker: `live_learning_tracker.py`

### System Design Choices
- **Data Layer:** PostgreSQL (Replit's Neon database) with connection pooling, TCP keepalives, and retry logic for stability.
- **Date Standardization:** Use of `recommended_date` and `match_date`, with `match_date` as primary for queries.
- **Persistent API Caching:** PostgreSQL-based caching with a 24h TTL and smart validation.
- **Emergency Fixture Fallback:** SofaScore web scraper as a third-layer fallback.
- **Data Processing:** Pandas DataFrames for data manipulation and financial calculations.
- **Legal Framework:** Comprehensive legal documentation in Swedish and English, compliant with GDPR and Swedish law.

## External Dependencies

### Core Libraries
- `streamlit`: Web application framework.
- `plotly`: Interactive charting.
- `pandas`: Data manipulation.
- `numpy`: Numerical computations.
- `scipy`: Statistical functions.

### Communication & Distribution
- `python-telegram-bot`: Telegram Bot API integration.
- `telegram.ext`: Command handlers.
- `asyncio`: Asynchronous operations.

### Data Storage
- `sqlite3`: Local database operations. (Note: Migration to PostgreSQL is underway/complete for primary storage).

### Web Scraping & Verification
- `trafilatura`: Web content extraction.
- `requests`: HTTP client.
- `selenium`: Browser automation.

### External APIs
- **The Odds API**: Real-time odds and match availability.
- **API-Football**: Injuries, lineups, and match statistics.

## Recent Changes (December 21, 2025)

### Dashboard Updates
- **Value Singles Categorization Fix:** The dashboard now correctly categorizes picks by checking BOTH the `product` column (CARDS/CORNERS) AND the `selection` text. Previously, bets like "Over 1.5 Cards" were incorrectly appearing under "Goals & BTTS" because the categorization only checked selection text.
- **Bookmaker Odds Display:** Added bookmaker odds columns (odds_by_bookmaker, best_odds_value, best_odds_bookmaker) to database views and dashboard queries.

### Dashboard Categories
The Value Singles tab now displays picks in 3 sections:
1. **Match Result (1X2)** - Home Win, Away Win, Draw
2. **Goals & BTTS** - Over/Under goals, Both Teams To Score
3. **Cards & Corners** - All cards and corners markets (identified by product='CARDS' or product='CORNERS')

### Settlement & Data Integrity Policy (December 22, 2025)
**Objective:** Ensure full transparency, statistical integrity, and professional-grade reporting.

**Policy:**
- All bets are settled only when official match data is available via verified data providers (API-Football, Odds API, or equivalent)
- For Corners and Cards markets, historical data from smaller competitions or matches older than 2 days may not be retrievable
- Any bet that cannot be verified after the cutoff period is automatically marked as **VOID (Data Unavailable)**
- Cutoff periods: Corners/Cards = 2 days, Other Football/SGP = 3 days

**Key Principles:**
- No assumptions, estimations, or inferred results are ever used
- Unverifiable data is excluded rather than guessed
- ROI, hit rate, and profit calculations include only verified results (VOID bets excluded from stats)
- This approach ensures all published results are honest, reproducible, and auditable

### Result Verification Status
- **Verification system working correctly** - Multi-source fallback (The Odds API, API-Football, Sofascore, Flashscore) settling bets automatically every 5 minutes
- **Auto-void enabled** - Old unverifiable bets are automatically voided with "Data Unavailable" reason
- **335 old corners/cards voided** - December 22, 2025 cleanup of older unverifiable bets

### Current Performance (All-Time)
- **Total Settled:** 1,290+ bets (excluding voided)
- Performance metrics exclude VOID bets for statistical accuracy
- **Pending:** Only recent bets (< 2-3 days old) remain pending until matches complete

### Discord Integration (December 22, 2025)
- **Discord ROI Webhook** - Automated performance updates to Discord channel
- **Trigger:** Auto-sends after football verification settles any bets
- **Manual Trigger:** GET /api/discord/stats
- **Stats Endpoint:** GET /api/stats/roi returns all-time, monthly, weekly, daily stats as JSON
- **Embed Format:** Color-coded by ROI (green positive, orange warning, red negative)
- **Metrics Included:** ROI%, units profit, hit rate, record, pending bets, recent results

### Manual Settlement System (December 25, 2025)
**Purpose:** Bulletproof verification for corners/cards when API-Football lacks data.

**Components:**
- `manual_results` table - Stores operator overrides with full audit trail
- `verification_metrics` table - Tracks success rates by market and source
- `flashscore_stats_scraper.py` - ManualResultsManager, VerificationMetrics classes

**API Endpoints (Authenticated with X-API-Key header):**
- POST /api/manual/settle - Manually settle a bet with corners/cards/goals data
- GET /api/manual/pending - Get bets needing manual review
- GET /api/verification/metrics - View success rates by market/source
- GET /api/manual/audit - View audit log of all manual settlements

**Security:** Requires ADMIN_API_KEY environment variable to be set.

**Flow:**
1. Results engine checks for manual overrides before auto-verification
2. API-Football is primary source, then database cache
3. Unverifiable corners/cards can be settled via manual API
4. All manual settlements logged with operator, reason, timestamp

### Discord Scheduled Notifications (December 25, 2025)
- **Daily Recap:** Every day at 22:30 - Day's results to Discord
- **Weekly Recap:** Every Sunday at 22:30 - Full week summary with ROI%
- **Config:** `daily_recap.py` with `send_daily_discord_recap()` and `send_weekly_discord_recap()`

### STABILITY & VERIFICATION MODE (December 25, 2025)
**Objective:** Verify edge via CLV (Closing Line Value) tracking, NOT via P/L. Reduce variance. Stabilize signals before scaling.

**Active Controls:**
- **Hard EV Cap:** 25% maximum (prevents overconfident predictions)
- **EV Deflator:** 0.4x applied globally (raw EV was averaging 74%, unrealistic)
- **Blocked EV Bands:** 50-100% structurally -EV (-47 units, -32.9% ROI on 143 bets)
- **SGP:** DISABLED (3-5x tier bleeding -29 units, 17.1% hit rate vs 24.1% required)
- **CORNERS Cap:** 30% of daily portfolio exposure (was 47%)
- **Flat Staking:** 1 unit per bet, no Kelly scaling during verification phase

**Files:**
- `ev_controller.py` - Central EV control module
- `live_learning_config.py` - Stability mode configuration
- `daily_card_builder.py` - Market exposure cap enforcement

**Exit Criteria (before scaling):**
- Average CLV > 1%
- 1500+ settled bets with verified CLV
- Daily variance SD < 40 units
- CORNERS concentration < 35%

**CLV Tracking:**
- Database columns: `open_odds`, `close_odds`, `clv_pct`
- CLV tracking every 10 minutes for closing odds capture
- Objective: If CLV is consistently positive, edge is verified regardless of short-term P/L variance

### Active Workflows
- **Real Football Dashboard** (port 5000) - Main UI
- **Combined Sports Engine** - Prediction engine with 1-hour Value Singles cycles (STABILITY MODE)
- **PGR API Server** (port 8000) - REST API
- **College Basketball Dashboard** (port 6000) - Basketball predictions
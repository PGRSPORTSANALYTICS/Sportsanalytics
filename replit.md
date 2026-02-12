# Sports Betting Analytics Platform

## Overview
This AI-powered sports betting analytics platform uses Monte Carlo simulation and ensemble modeling to generate profitable predictions, primarily focusing on Value Singles (1X2, Over/Under, BTTS, Double Chance). Secondary products include Multi-Match Parlays and College Basketball. The platform aims for a 15-20% ROI with strict EV filtering (5%+ edge). It features a premium Streamlit dashboard, a Telegram bot for prediction delivery, and automatic result verification, all driven by AI analysis incorporating xG, form, H2H, injuries, and standings. The business vision is to provide a reliable, data-driven tool for sports bettors, offering significant market potential by democratizing advanced analytics.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### UI/UX Decisions
The platform features a Streamlit web application with a wide layout, utilizing Plotly for interactive charts, auto-refresh functionality, and consistent color coding to enhance data visualization and user experience.

### Technical Implementations
The system incorporates advanced features such as:
- **Comprehensive Analysis:** Integrates team form, H2H, league standings, odds movement, and venue-specific xG.
- **Data Sourcing:** Employs a dual-source system for injury/lineup data (API-Football with Transfermarkt fallback) and a triple-layer fallback for general data resilience (API-Football, web scrapers, safe defaults).
- **Prediction Models:** Combines Poisson distribution, neural network probabilities, and H2H patterns within an Ensemble Prediction System, enhanced by Monte Carlo simulation and Similar Matches Technology.
- **Value-Based Betting:** Utilizes Expected Value (EV) Filtering with Kelly Criterion Bet Sizing, enhanced by Shrink-to-Market Probability Calibration (85% ensemble + 15% market-implied, Feb 12 2026).
- **Multi-Market Expansion:** Dedicated engines support various market types including Value Singles, Totals, BTTS, Corners, Shots, and Cards.
- **Bet Monitoring & Delivery:** Features a `BetStatusService`, Live Bet Control Center, an extended Telegram bot with dual channels for predictions, and automated Discord result notifications.
- **Intelligent Result Verification:** A production-ready caching and cooldown system with multi-source fallback (Flashscore, API-Football, The Odds API, Sofascore) ensures fast and reliable settlement. Manual settlement system for unverified corner/card markets.
- **Bankroll & Analytics:** A centralized `BankrollManager` tracks bankroll and exposure, with primary analytics using a unit-based system for ROI, profit, and hit rate.
- **AI Training & Learning:** A comprehensive pipeline collects 40+ features for future AI model training, supported by a `training_data` PostgreSQL table and a `DataCollector`, including a Learning System Track Record dashboard and Trust Level Learning.
- **Parlay Engine v2:** Builds 2-leg parlays from the best approved Value Singles (all markets: 1X2, Over/Under, BTTS, Double Chance). Max 3 parlays/day, max 5x total odds, calibrated probabilities, flat staking.
- **Prediction Filtering:** Includes H2H BTTS filter, AI-learned SGP odds filter, Realistic SGP Margin Calibration, and PGR Final Score Strategy.
- **3-Tier Trust Level Classification:** Predictions are classified into High (L1), Medium (L2), and Soft (L3) based on simulation approval, EV, confidence, and disagreement.
- **Central Market Router:** A portfolio balancing system with a two-pass selection algorithm, per-market caps, trust level/EV prioritization, and a global daily pick cap.
- **Odds Drift Module:** Tracks real-time odds movement to block bets with unfavorable drift.
- **Syndicate Engine Suite (v1.0):** Enhances prediction quality with:
    - **Profile Boost Engine:** Adjusts EV/confidence based on contextual factors (tempo, rivalry, referee, etc.).
    - **Market Weight Engine:** Learns from 30-day historical ROI to bias towards high-performing markets.
    - **Hidden Value Scanner:** Identifies "soft edge" picks (EV between -1% and +2%) using composite scoring.
- **PRODUCTION MODEL v1.0 (Jan 25, 2026 - ACTIVE):** Learning phase completed with verified edge. System now operates in production mode with optimized market configuration.
    - **Learning Phase Results (Dec 25, 2025 - Jan 25, 2026):**
        - 1909 bets settled | 59.5% hit rate | +23.5% ROI | +449.2 units profit
    - **PRODUCTION MARKETS (Live, full weight):**
        - CARDS: 88.4% hit rate, +127.70u
        - CORNERS: 60.6% hit rate, +146.53u
        - VALUE_SINGLE (Totals + BTTS only — no 1X2)
    - **LEARNING ONLY (Low weight, data collection):**
        - BASKETBALL: Breakeven, continued data collection
        - HOME_WIN + AWAY_WIN: All 1X2 excluded — bookmakers too sharp, AI training continues
    - **DISABLED:**
        - SGP: Permanently disabled (2.8% hit rate, -5065u)
    - **Post-Learning Rules:**
        - No stake increases
        - No new markets
        - No threshold changes
        - All changes logged as post-learning modifications
- **Historical Fixes (Learning Phase):**
    - CORNERS Volume Control (Jan 10): Max 20/day, 3 picks per match
    - Basketball Flat Staking (Jan 11): Fixed Kelly scaling to 1-unit flat stakes
- **Basketball Market Balancing (Jan 25, 2026):** Diversified market selection to reduce Away Win dominance.
    - Totals (Over/Under): 40% quota (~6 picks) - prioritized
    - Home Win: 30% quota (~4 picks)
    - Away Win: 20% quota (~3 picks) - reduced from previous dominance
    - Spread: 10% quota (~2 picks)
    - Fills remaining slots with best EV from any market
- **1X2 Market Disabled (Feb 6, 2026):** Moved all 1X2 (Home Win, Away Win, Draw) to learning-only.
    - Home Win: 36.6% hit rate, -12.5u (model overestimates by ~25pp)
    - Away Win: 31.6% hit rate, -10.1u (already learning-only since Jan 11)
    - Reason: Bookmakers price 1X2 too sharply — model can't find real edge
    - Production Value Singles now limited to: Totals (O/U) and BTTS markets
    - 1X2 data still collected for AI training
- **Parlay Engine Rework (Feb 6, 2026):** Simplified from ML-only to all-market parlays.
    - Sources: Best approved Value Singles from DB (real model probabilities)
    - Markets: 1X2, Over/Under, BTTS, Double Chance, DNB
    - Legs: 2-3 per parlay (was 2 only)
    - Max 3 parlays/day, flat staking (0.2u)
    - Verifier updated for all market types (TOTALS, BTTS, DC)
    - Removed: Odds API fetching, xG estimation, form checks (all now handled by Value Singles engine)
- **Daily Soft Stop-Loss (Jan 28, 2026):** Implemented -5u daily stop-loss for production.
    - Stops NEW bets when daily settled P/L reaches -5 units
    - Pending/running bets are NOT affected (soft stop-loss)
    - Applies to: VALUE_SINGLE, CARDS, CORNERS
    - Resets at midnight UTC
    - Module: `daily_stoploss.py`
- **Free Pick Limit (Jan 29, 2026):** Reduced to 1 free pick per day.
    - Value Singles: 5 picks/day @ 10:00 UTC (internal distribution)
    - Free Pick: 1 pick/day @ 11:00 UTC (public Discord channel)
- **Player Props Engine (Feb 11, 2026):** Internal learning mode for player prop markets.
    - **Football:** player_anytime_goalscorer, player_shots_on_goal (limited coverage from The Odds API)
    - **Basketball:** player_points, player_rebounds (strong coverage — NBA/NCAAB)
    - Mode: LEARNING ONLY — no real stakes, data collection for AI training
    - Schedule: Every 6 hours via combined_sports_runner.py
    - API budget: Max 15 credits per cycle (conserves 500/month quota)
    - DB table: `player_props` (separate from football_opportunities)
    - Discord: Top-edge props sent to DISCORD_PROPS_WEBHOOK_URL with learning mode badge
    - Auto-void: Props older than 3 days auto-voided by results_engine.py
    - Module: `player_props_engine.py`
- **Player Props Quality Filter (Feb 11, 2026):** Strict quality filtering for basketball props.
    - Module: `player_props_filter.py` + `nba_stats_provider.py`
    - NBA stats via `nba_api` (game logs: minutes, points, rebounds, assists) with 1hr in-memory cache
    - Markets: player_points, player_rebounds, player_assists, player_points_rebounds_assists (PRA)
    - Filter criteria (all must pass):
        1. Allowed markets only (4 basketball markets)
        2. Odds range: 1.70-2.20
        3. Deduplication: best odds per player+market+selection+line
        4. Min 10+ historical games this season
        5. Avg minutes >= 22 over last 10 games
        6. Played >= 5 of last 7 games
        7. Starter (25+ min) or rotation (15+ min) role
        8. Not returning from injury (<=2 of last 7 games)
        9. Not limited minutes last game (<15 min with 22+ avg)
        10. Projection requires 10+ recent game values
        11. Positive EV only (hit_rate × odds > 1)
    - Post-filter ranking (applied after quality pass):
        1. Rank by edge descending
        2. Max 2 props per player
        3. Max 3 props per match
        4. Remove projection diff < 1.0 stat unit
        5. Keep top 15 by edge
        6. Tag top 5 as Premium Picks
    - DB notes format: `PREMIUM|proj=X|diff=Y|hit=Z%|min=M|g7=N` (top 5) or `QUALITY|...` (rest)
    - Dashboard: "Quality Props" tab shows Premium Picks (gold accent) and Quality Picks separately
    - Typical yield: ~1579 raw → ~65 quality → ~15 ranked final (5 Premium + 10 Quality)

### System Design Choices
- **Data Layer:** PostgreSQL (Neon database) with connection pooling, TCP keepalives, and retry logic.
- **Date Standardization:** All kickoff times stored as UTC with epoch timestamps for consistency.
- **Persistent API Caching:** PostgreSQL-based caching with a 24h TTL.
- **Emergency Fixture Fallback:** SofaScore web scraper as a third-layer fallback.
- **Data Processing:** Pandas DataFrames for data manipulation.
- **Legal Framework:** GDPR and Swedish law compliant.

### Feature Specifications
- **Real Football Dashboard:** Main UI accessible via port 5000.
- **Combined Sports Engine:** Prediction engine in PRODUCTION MODE v1.0 with 1-hour Value Singles cycles.
- **PGR API Server:** REST API accessible via port 8000.
- **College Basketball Dashboard:** Dedicated dashboard for basketball predictions via port 6000.

## External Dependencies

### Core Libraries
- `streamlit`
- `plotly`
- `pandas`
- `numpy`
- `scipy`

### Communication & Distribution
- `python-telegram-bot`
- `telegram.ext`
- `asyncio`

### Data Storage
- `sqlite3` (for local operations, primary storage is PostgreSQL)

### Web Scraping & Verification
- `trafilatura`
- `requests`
- `selenium`

### External APIs
- **The Odds API**: Real-time odds and match availability.
- **API-Football**: Injuries, lineups, and match statistics.
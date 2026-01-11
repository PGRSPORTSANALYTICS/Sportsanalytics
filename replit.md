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
- **Value-Based Betting:** Utilizes Expected Value (EV) Filtering with Kelly Criterion Bet Sizing.
- **Multi-Market Expansion:** Dedicated engines support various market types including Value Singles, Totals, BTTS, Corners, Shots, and Cards.
- **Bet Monitoring & Delivery:** Features a `BetStatusService`, Live Bet Control Center, an extended Telegram bot with dual channels for predictions, and automated Discord result notifications.
- **Intelligent Result Verification:** A production-ready caching and cooldown system with multi-source fallback (Flashscore, API-Football, The Odds API, Sofascore) ensures fast and reliable settlement. Manual settlement system for unverified corner/card markets.
- **Bankroll & Analytics:** A centralized `BankrollManager` tracks bankroll and exposure, with primary analytics using a unit-based system for ROI, profit, and hit rate.
- **AI Training & Learning:** A comprehensive pipeline collects 40+ features for future AI model training, supported by a `training_data` PostgreSQL table and a `DataCollector`, including a Learning System Track Record dashboard and Trust Level Learning.
- **ML Parlay Engine:** Builds low/medium risk Moneyline/1X2/DNB parlays from approved Value Singles.
- **Prediction Filtering:** Includes H2H BTTS filter, AI-learned SGP odds filter, Realistic SGP Margin Calibration, and PGR Final Score Strategy.
- **3-Tier Trust Level Classification:** Predictions are classified into High (L1), Medium (L2), and Soft (L3) based on simulation approval, EV, confidence, and disagreement.
- **Central Market Router:** A portfolio balancing system with a two-pass selection algorithm, per-market caps, trust level/EV prioritization, and a global daily pick cap.
- **Odds Drift Module:** Tracks real-time odds movement to block bets with unfavorable drift.
- **Syndicate Engine Suite (v1.0):** Enhances prediction quality with:
    - **Profile Boost Engine:** Adjusts EV/confidence based on contextual factors (tempo, rivalry, referee, etc.).
    - **Market Weight Engine:** Learns from 30-day historical ROI to bias towards high-performing markets.
    - **Hidden Value Scanner:** Identifies "soft edge" picks (EV between -1% and +2%) using composite scoring.
- **LIVE LEARNING MODE (v1.0 - ACTIVE):** A full data capture system for model calibration, tracking all trust tiers, CLV, unit-based P/L, raw/boosted/weighted EV, profile boost details, and market weights.
- **Stability & Verification Mode:** Active controls like hard EV caps, EV deflators, blocked EV bands, disabled SGP, CORNERS exposure caps, and flat staking to verify edge via CLV tracking before scaling.
- **CORNERS Volume Control (Jan 10, 2026):** Fixed CORNERS explosion (69+/day → max 20). Implemented: (1) DB check for existing picks today before generating, (2) Hard global cap of 20/day with HARD STOP guard, (3) Max 3 picks per match enforced via shared dict across all sub-markets (match/team/handicap), (4) L3_SOFT_VALUE tier blocked from production.
- **Basketball Flat Staking Fix (Jan 11, 2026):** Basketball engine was using Kelly staking (~100u/bet) instead of Stability Mode flat 1-unit stakes. Fixed: (1) Added `STABILITY_MODE.unit_flat_staking` check at module level in `college_basket_value_engine.py`, (2) Updated `all_bets` view to use `stake=1` for basketball (targeted fix, other products unchanged).

### System Design Choices
- **Data Layer:** PostgreSQL (Neon database) with connection pooling, TCP keepalives, and retry logic.
- **Date Standardization:** All kickoff times stored as UTC with epoch timestamps for consistency.
- **Persistent API Caching:** PostgreSQL-based caching with a 24h TTL.
- **Emergency Fixture Fallback:** SofaScore web scraper as a third-layer fallback.
- **Data Processing:** Pandas DataFrames for data manipulation.
- **Legal Framework:** GDPR and Swedish law compliant.

### Feature Specifications
- **Real Football Dashboard:** Main UI accessible via port 5000.
- **Combined Sports Engine:** Prediction engine operating with 1-hour Value Singles cycles in STABILITY MODE.
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
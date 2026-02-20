# Sports Betting Analytics Platform

## Overview
This AI-powered sports betting analytics platform leverages Monte Carlo simulation and ensemble modeling to generate profitable predictions, primarily focusing on Value Singles (1X2, Over/Under, BTTS, Double Chance). Secondary offerings include Multi-Match Parlays and College Basketball analytics. The platform targets a 15-20% ROI with strict EV filtering (5%+ edge) and features a premium Streamlit dashboard, a Telegram bot for prediction delivery, and automatic result verification. AI analysis incorporates xG, form, H2H data, injuries, and standings. The project aims to provide a reliable, data-driven tool for sports bettors, democratizing advanced analytics for significant market potential.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### UI/UX Decisions
The platform features a Streamlit web application with a wide layout, utilizing Plotly for interactive charts, auto-refresh functionality, and consistent color coding to enhance data visualization and user experience. A dedicated PGR Edge Finder dashboard provides multi-book comparison and CLV analytics. A **Smart Picks** tab (first tab in the football dashboard) provides clean, conflict-free picks with one best pick per match, opposing market detection, and Core/High Value categorization (odds 1.70–2.10 core range). Powered by `smart_picks_filter.py` and `pgr_smart_picks_dashboard.py`.

### Technical Implementations
The system incorporates comprehensive analysis of team form, H2H, league standings, odds movement, and venue-specific xG. It employs a dual-source system for injury/lineup data and a triple-layer fallback for general data resilience. Prediction models combine Poisson distribution, neural network probabilities, H2H patterns, Monte Carlo simulation, and Similar Matches Technology. Value-based betting utilizes Expected Value (EV) Filtering with Kelly Criterion Bet Sizing and Shrink-to-Market Probability Calibration.

The system supports multi-market expansion for Value Singles, Totals, BTTS, Corners, Shots, and Cards. **Corners Engine** now uses real bookmaker odds from API-Football (parsing 64+ market lines from 15+ bookmakers per match). **Cards Engine** is paused from production as no API-Football bookmakers currently offer cards odds; it will auto-resume when real cards odds become available. It includes a `BetStatusService`, Live Bet Control Center, an extended Telegram bot, and automated Discord result notifications. Intelligent result verification uses a caching and cooldown system with multi-source fallback for reliable settlement. A `BankrollManager` tracks bankroll and exposure, with analytics using a unit-based system for ROI, profit, and hit rate.

An AI training pipeline collects 40+ features for future model training, supported by a `training_data` PostgreSQL table and a `DataCollector`. A Parlay Engine v2 builds 2-3 leg parlays from approved Value Singles across various markets. Prediction filtering includes H2H BTTS, AI-learned SGP odds, and PGR Final Score Strategy. A 3-Tier Trust Level Classification categorizes predictions based on simulation approval, EV, confidence, and disagreement. A Central Market Router provides portfolio balancing with a two-pass selection algorithm and per-market caps.

A Self-Learning Engine automates performance tracking across all leagues and markets, computing ROI, hit rate, CLV, and profit units with rolling windows. It employs a weighted scoring formula for league/market performance and automatically promotes/demotes markets between PRODUCTION, LEARNING_ONLY, and DISABLED statuses. Smart Bet Filtering uses combined confidence scores to reject low-confidence bets. An Odds Drift Module tracks real-time odds to block unfavorable bets. The Syndicate Engine Suite enhances prediction quality through a Profile Boost Engine, Market Weight Engine, and Hidden Value Scanner. The system operates in PRODUCTION MODE v1.0, with specific markets (CARDS, CORNERS, Value Singles - Totals + BTTS) live and others in learning or disabled states. It includes a daily soft stop-loss and a free pick limit. A Player Props Engine is in internal learning mode for football and basketball player prop markets, with strict quality filters for basketball. A PGR Analytics v2 module provides professional-grade odds intelligence, including multi-book normalization, a Fair Odds Engine, Edge/CLV intelligence, enhanced gating, and a bet lifecycle management system with full audit logging.

### System Design Choices
- **Data Layer:** PostgreSQL (Neon database) with connection pooling and retry logic.
- **Date Standardization:** All kickoff times stored as UTC with epoch timestamps.
- **Persistent API Caching:** PostgreSQL-based caching with a 24h TTL.
- **Emergency Fixture Fallback:** SofaScore web scraper.
- **Data Processing:** Pandas DataFrames.
- **Legal Framework:** GDPR and Swedish law compliant.
- **PGR Analytics v2:** Uses a modular design with dedicated database tables and modules for odds ingestion, fair odds calculation, edge/CLV intelligence, gating, and bet lifecycle management. It includes a vanilla HTML/CSS/JS dashboard.

### Feature Specifications
- **Real Football Dashboard:** Main UI accessible via port 5000.
- **Combined Sports Engine:** Prediction engine in PRODUCTION MODE v1.0 with 1-hour Value Singles cycles.
- **PGR API Server:** REST API accessible via port 8000. PGR Edge Finder dashboard at /pgr.
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
- `sqlite3`

### Web Scraping & Verification
- `trafilatura`
- `requests`
- `selenium`

### External APIs
- **The Odds API**: Real-time odds and match availability.
- **API-Football**: Injuries, lineups, and match statistics.
- **Flashscore**: For result verification.
- **SofaScore**: For result verification and emergency fixture fallback.
- **nba_api**: For NBA player statistics.
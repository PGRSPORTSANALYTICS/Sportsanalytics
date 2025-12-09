# Sports Betting Analytics Platform

## Overview
This project is an AI-powered sports betting analytics platform, leveraging Monte Carlo simulation and ensemble modeling for profitable predictions. The platform focuses on Value Singles as the core product (1X2, Over/Under, BTTS, Double Chance markets) with Multi-Match Parlays and College Basketball as secondary products. Features include a premium Streamlit dashboard and Telegram bot for prediction delivery, with automatic result verification. Uses data-driven AI analysis based on xG, form, H2H, injuries, and standings. Target: 15-20% realistic ROI with strict EV filtering (5%+ edge required).

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### UI/UX Decisions
The platform utilizes a Streamlit web application with a wide layout, Plotly for interactive charts, auto-refresh functionality, and consistent color coding. Interactive elements and multi-chart support enhance data visualization.

### Technical Implementations
The system employs advanced prediction features including:
- **Comprehensive Analysis:** Team form, Head-to-Head history, league standings, and odds movement tracking.
- **Data Sourcing:** Dual-source system for injury and lineup data (API-Football with Transfermarkt fallback).
- **Prediction Models:** Neural Networks for exact scores, an Ensemble Prediction System combining Poisson distribution, neural network probabilities, and H2H patterns, and Similar Matches Technology for confidence adjustment.
- **Value-Based Betting:** Expected Value (EV) Filtering with Kelly Criterion Bet Sizing ensures betting only when a genuine edge exists.
- **Data Resilience:** A triple-layer fallback system (API-Football, web scrapers, safe defaults) ensures continuous operation.
- **Dynamic Score Targeting:** Models predict any score from 0-0 through 9-9 based on ensemble analysis.
- **Venue-Specific Form:** xG calculation filtered by home/away performance.
- **Expanded League Coverage:** Integration of 16 quality leagues, including winter leagues.
- **SGP System:** Adaptive learning, live odds integration, player props, half-time & corners markets (corners currently disabled), and multi-leg parlay support with tiered EV filtering.
- **Hybrid Bet Monitoring:** Unified real-time tracking for Exact Score and SGP predictions via a central `BetStatusService`, Live Bet Control Center, and extended Telegram bot commands.
- **Telegram Channels:** Dual channels for different prediction types with smart volume control.
- **Intelligent Result Verification:** Production-ready caching and cooldown system with multi-source fallback (Flashscore, API-Football, The Odds API, Sofascore) ensures fast and reliable result settlement.
- **Non-Blocking Engine Architecture:** Combined Sports Engine uses non-blocking functions for sequential execution of all prediction cycles.
- **Dynamic Settlement:** `settlement.py` dynamically selects result columns for bet settlement.
- **Basketball Settings:** Specific confidence thresholds, odds ranges, and EV minimum edge for basketball predictions.
- **Bankroll Management:** Centralized `BankrollManager` tracks bankroll, exposure, and daily limits to prevent over-betting, capping daily exposure at 80% of bankroll.
- **Dynamic Staking:** Implemented 1.2% of bankroll per bet, with a daily loss protection stopping bets if daily loss exceeds 20% of bankroll.
- **AI Training Data Collection:** Comprehensive pipeline to collect 40+ features for future AI model training, including a `training_data` PostgreSQL table and a `DataCollector` singleton class.
- **Learning System Track Record:** Dashboard section showing AI prediction performance KPIs, breakdown by prediction type, accuracy by league, 30-day trend, and model calibration.
- **Fast Result Verification:** Reduced per-bet cooldown to 5 minutes, verification runs every 5 minutes, prioritizing The Odds API for result fetching.
- **ML Parlay Engine:** New low/medium risk product for Moneyline/1X2/DNB parlays, with 2-4 legs, specific odds ranges, EV, and stake percentages.
- **H2H BTTS Filter:** AI-learned pattern to block BTTS Yes when Head-to-Head data shows poor scoring history.
- **AI-Learned SGP Odds Filter:** Automated AI learning adjusts SGP MIN/MAX_ODDS based on performance analysis.
- **Realistic SGP Margin Calibration:** Updated SGP pricing to reflect real-world bookmaker margins (40% margin).
- **Discord Result Notifications:** Automated win/loss notifications to dedicated Discord channels for all prediction types.
- **PGR Final Score Strategy v1.0:** Data-driven odds filter based on analysis of settled bets, narrowing odds to a 10-12x sweet spot and adjusting EV minimum.
- **Monte Carlo Simulation:** Full integration across all prediction engines for generating score distributions and calculating EV.
- **3-Tier Trust Level Classification:** Implemented via `bet_filter.py` to classify predictions into High, Medium, and Soft Trust levels based on simulation approval, EV, confidence, and disagreement.
- **PostgreSQL SGP Settlement (Dec 8, 2025):** New `sgp_settlement.py` module handles automatic SGP bet settlement using team-name matching against `match_results_cache` table. Supports all common leg types (Over/Under goals, BTTS, 1H/2H goals, corners) with VOID fallback for unknown markets.
- **Increased Bet Volume (Dec 8, 2025):** SGP daily limit raised to 20, min EV lowered to 3% (6% EPL), min odds lowered to 3.5x. Value Singles daily limit raised to 8, max odds expanded to 2.10, min EV lowered to 4%.
- **Trust Level Learning (Dec 8, 2025):** Added `trust_level` field to training_data table. Data collector now captures L1/L2/L3 trust classifications from Monte Carlo simulations for future performance analysis.
- **Strategic Product Pivot (Dec 9, 2025):** Value Singles now core subscription product due to lower bookmaker margins (4-8% vs SGP's 28-45%). ML Parlays + College Basketball as secondary products. Target: 15-20% realistic ROI.
- **Multi-Match Parlay System (Dec 9, 2025):** Replaced old SGP (same-game parlay) with new multi-match parlay builder. New system builds parlays from approved L1/L2 Value Singles across different matches. Uses probability product from AI-calculated probabilities on each single bet.
- **Exact Score Removal (Dec 9, 2025):** Exact Score product completely removed from platform due to poor December performance (0/29 cold streak, $4,700+ losses). Platform now focuses exclusively on Value Singles (core product), Multi-Match Parlays, and College Basketball.
- **NOVA v2.0 Filter Retuning (Dec 9, 2025):** Complete filter overhaul for higher daily volume while maintaining safety. Changes:
  - **Value Singles:** EV 2% (was 5%), confidence 52% (was 56%), odds 1.50-3.00 (was 1.55-1.95), max 15/day (was 10), expanded to 29 leagues (was 9).
  - **3-Tier Trust System with Safety Guardrails:**
    - L1 (High Trust): Sim approved, EV >= 5%, confidence >= 55%, odds 1.50-3.00, max 3/day.
    - L2 (Medium Trust): Sim approved (SAFETY), EV >= 2%, confidence >= 52%, disagreement <= 15% (SAFETY, was 20%), odds 1.50-3.20.
    - L3 (Soft Value): EV >= 0%, confidence >= 50%, disagreement <= 25%, odds 1.40-3.50, used only when < 5 total picks.
  - **ML Parlays:** Per-leg EV 3%, total parlay EV >= 5% (SAFETY), leg odds 1.30-3.00, total odds 3.00-12.00, max 3/day.
  - **Multi-Match Parlays:** 2-3 legs (was 2-4), total odds 3.00-10.00 (was 4.00-20.00), EV 3% (was 5%), max 2/day (was 3).
  - **Basketball:** EV 1.5% (was 3%), confidence 52% (was 50%), max 12 singles (was 10).
  - Target: 5-15 Value Singles on typical match days.

### System Design Choices
- **Data Layer:** Migration from SQLite to PostgreSQL (Replit's Neon database) with connection pooling for concurrency.
- **Database Resilience:** TCP keepalives and retry logic for stable connections.
- **Date Standardization:** Use of `recommended_date` and `match_date`, with `match_date` as primary for queries.
- **Persistent API Caching:** PostgreSQL-based caching using `APICacheManager` to store API responses with a 24h TTL and smart validation.
- **Emergency Fixture Fallback:** SofaScore web scraper as a third-layer fallback.
- **Data Processing:** Pandas DataFrames for data manipulation, timestamp-based organization, and financial calculations.
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
- `sqlite3`: Local database operations.

### Web Scraping & Verification
- `trafilatura`: Web content extraction.
- `requests`: HTTP client.
- `selenium`: Browser automation.

### Utility Libraries
- `pathlib`: Path handling.
- `datetime`: Time and date manipulation.
- `typing`: Type hints.
- `schedule`: Task scheduling.

### External APIs
- **The Odds API**: Real-time odds and match availability.
- **API-Football**: Injuries, lineups, and match statistics.
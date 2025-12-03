# Exact Score Predictions Platform

## Overview
This project is an AI-powered platform for exact football score predictions, leveraging advanced machine learning and ensemble modeling for significant ROI. It features a premium Streamlit dashboard and Telegram bot for prediction delivery, with automatic result verification. The system uses data-driven AI analysis with ensemble models predicting ANY score based on xG, form, H2H, injuries, and standings. The platform targets a 20-25% hit rate across 16 quality leagues with odds 7-14x and a 12%+ EV edge. The January 2026 launch strategy focuses on Exact Score predictions, with SGP features to be introduced later once sufficient live-odds data is collected.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### UI/UX Decisions
The platform features a Streamlit web application with a wide layout, utilizing Plotly for interactive charts, auto-refresh functionality, and consistent color coding. Interactive elements with hover tooltips and multi-chart support enhance data visualization.

### Technical Implementations
The system employs advanced prediction features including:
- **Team Form Analysis:** Evaluates win/loss records, goals, clean sheets, and PPG from the last 5 matches.
- **Head-to-Head Historical Analysis:** Examines the last 10 H2H matches for score patterns, Over 2.5 goals, and BTTS rates.
- **League Standings Integration:** Incorporates current league position, points, goal difference, and rank difference.
- **Odds Movement Tracking:** Monitors opening vs. current odds, movement velocity, sharp money indicators, and closing line value.
- **Injury and Lineup Data:** Dual-source system prioritizing API-Football with automatic fallback to Transfermarkt web scraper.
- **Neural Network Predictions:** A deep learning model for exact scores, trained on 50+ features.
- **Ensemble Prediction System:** Combines Poisson distribution (xG-based), neural network probabilities, and H2H patterns with weighted averaging.
- **Similar Matches Technology:** Analyzes historical matches with similar characteristics to adjust prediction confidence.
- **Expected Value (EV) Filtering System:** Mathematical edge calculation replacing arbitrary confidence scores, betting only when model probability × odds provides genuine edge. Includes Kelly Criterion Bet Sizing.
- **Multi-Source Data Resilience:** Triple-layer fallback system (API-Football, web scrapers, safe defaults) ensures continuous operation during API outages.
- **Data-Driven Score Targeting:** Models predict ANY score based on ensemble analysis, allowing predictions for all scores 0-0 through 9-9.
- **Venue-Specific Form Analysis:** Implements venue-specific form filtering for xG calculation, using home games for home teams and away games for away teams.
- **League Coverage Expansion:** Expanded to 16 quality leagues, including full integration of winter leagues (Brazil Serie A, Japan J1 League) for year-round coverage.
- **Telegram Broadcast Fix:** Ensures only predictions for matches playing today are broadcasted.
- **SGP Self-Learning System:** Features adaptive learning capabilities for probability calibration, correlation learning, and dynamic Kelly sizing.
- **Live SGP Odds Integration:** Uses real bookmaker odds from The Odds API for SGP, with three pricing modes (Live, Hybrid, Simulated) and graceful fallback.
- **Player Props SGP System:** Expanded SGP to include player-based predictions (Anytime Goalscorer, Player Shots) using API-Football player statistics.
- **Half-Time & Corners SGP Markets:** Further expanded SGP with half-time goals and corners markets using adjusted Poisson distribution and correlation matrices.
- **Multi-Leg Parlay System:** Supports 3-7 leg parlays with a tiered EV filtering system (Jackpot Play, Premium Parlay, Value Parlay, Value Bet) balancing value and entertainment.
- **Hybrid Bet Monitoring System:** Unified real-time tracking for Exact Score and SGP predictions via a central `BetStatusService`, a Live Bet Control Center (Dashboard), and extended Telegram bot commands.
- **Dual Telegram Channels:** Separate broadcast channels for different prediction types with smart volume control.
- **Intelligent Result Verification System:** Production-ready caching and cooldown system to prevent API quota exhaustion with multi-source fallback (Flashscore, API-Football, The Odds API, Sofascore).
- **Non-Blocking Engine Architecture (Nov 26, 2025):** Combined Sports Engine uses `run_single_cycle()` function in real_football_champion.py and sgp_champion.py instead of blocking `main()` infinite loops, allowing proper sequential execution of all prediction cycles (Football → SGP → Women → Basketball).
- **Dynamic Settlement Column System:** settlement.py uses `RESULT_COLUMN_MAP` and `_update_result()` helper functions to dynamically select between "status" (basketball/women) and "result" (football) columns during bet settlement.
- **Separated Basketball Verification:** Basketball settlement handled exclusively by college_basket_result_verifier.py using The Odds API scores endpoint, not part of fixture-based settle_all_bets flow.
- **Bankroll Management System (Nov 29, 2025):** Centralized `BankrollManager` class prevents over-betting by tracking current bankroll, pending exposure, and daily limits. All prediction engines (SGP, Value Singles, Basketball) check available funds before placing bets. Maximum daily exposure capped at 80% of bankroll. System blocks new bets when limits are reached.
- **Dynamic Staking System (Nov 30, 2025):** Implemented 1.2% of bankroll per bet dynamic staking replacing fixed stakes. Features: (1) Unit system where 1 unit = 1% of bankroll, each bet = 1.2u, (2) Daily loss protection stops betting if daily loss ≥ 20% of bankroll, (3) Dashboard displays stakes as "$X (1.2u)" format. Stake scales automatically with bankroll growth/decline.
- **AI Training Data Collection System (Nov 30, 2025):** Comprehensive data collection pipeline for future AI model training without increasing bet volume. Features: (1) `training_data` PostgreSQL table with 40+ features capturing form, H2H, xG, odds, predictions and outcomes, (2) `DataCollector` singleton class using SQLAlchemy with proper auto-commit transactions via `engine.begin()`, (3) Integrated into all prediction engines (Exact Score, Value Singles, SGP), (4) `bet_placed` flag distinguishes actual bets vs. prediction-only records for expanded AI training, (5) Dashboard displays AI training stats in Overview tab.
- **Learning System Track Record (Nov 30, 2025):** Dashboard section showing AI prediction performance metrics. Features: (1) Overall accuracy KPIs comparing bets vs. predictions-only, (2) Performance breakdown by prediction type (Exact Score, Value Singles, SGP), (3) Accuracy by league with minimum sample gating, (4) 30-day accuracy trend chart with 7-day rolling average, (5) Model calibration chart comparing predicted probability vs. actual hit rate to monitor model quality.
- **SGP Corners Disabled (Nov 30, 2025):** Temporarily disabled all corners-based SGP legs due to low hit rate. SGP now focuses on goals-only markets: Over/Under Goals, BTTS, Half-Time Goals, Second-Half Goals.
- **Fast Result Verification System (Nov 30, 2025):** Major speed improvement - results now settle within 5 minutes of match ending (was up to 1 hour). Changes: (1) Reduced per-bet cooldown from 30 min to 5 min, (2) Verification runs every 5 minutes instead of 30 minutes, (3) Prioritized The Odds API scores endpoint (fastest) over API-Football for result fetching. Fallback order: The Odds API → Sofascore → API-Football.
- **ML Parlay Engine (Dec 2, 2025):** New LOW/MEDIUM risk product for Moneyline/1X2/DNB parlays. Features: (1) 2-4 legs per parlay, max 3 parlays per day, (2) Odds range 1.40-2.10 per leg, 4%+ EV per leg, (3) League whitelist (Top 5 European + major leagues), (4) 0.8% of bankroll stake per parlay, (5) Database tables: `ml_parlay_predictions` (parlay-level) and `ml_parlay_legs` (leg-level), (6) INTERNAL TEST MODE - no external posting yet, (7) Separate result verifier (`ml_parlay_verifier.py`), (8) Integrated into Combined Sports Engine running every 3 hours.
- **H2H BTTS Filter (Dec 3, 2025):** AI-learned pattern to skip BTTS Yes when Head-to-Head data shows poor scoring history. Features: (1) Fetches H2H BTTS rate from API-Football (last 10 matches), (2) Blends 60% Poisson model + 40% H2H historical rate, (3) Blocks BTTS Yes if blended rate < 30% (35% for Premier League), (4) Requires minimum 4 H2H matches for filtering to apply, (5) Example: Athletic Bilbao vs Real Madrid with 20% H2H BTTS rate correctly blocked. Triggered by user feedback on failed BTTS bet where Bilbao scored only 1 goal in 5 H2H meetings.

### System Design Choices
- **Data Layer:** Migrated from SQLite to PostgreSQL (Replit's built-in Neon database) to eliminate database locking issues during concurrent workflow access, using connection pooling.
- **Database Connection Resilience:** Implemented TCP keepalives and intelligent retry logic to prevent SSL connection drops.
- **Date Field Standardization:** System uses `recommended_date` (when prediction generated) and `match_date` (when match played), with `match_date` being the primary field for all queries.
- **Persistent API Caching:** PostgreSQL-based persistent caching using `APICacheManager` class to store API responses and track daily usage across all workflows. Cache tables created: `api_football_cache`, `odds_api_cache`, `api_request_counter`. Fixture fetching now uses `_fetch_with_cache()` method with 24h TTL and stable cache keys (league_id + date).
- **Cache Validation System:** Implemented smart cache validation that prevents storing empty/null responses, preventing quota exhaustion from caching error states (Nov 12, 2025 fix).
- **Emergency Fixture Fallback:** Added SofaScore web scraper as third-layer fallback when both The Odds API and API-Football quotas are exhausted, ensuring continuous operation.
- **Data Processing:** Pandas DataFrames are used for all data manipulation, with timestamp-based organization and financial calculations (Kelly criterion, edge calculation).
- **Legal Framework:** Comprehensive legal documentation (ToS, Risk Disclaimer, Privacy Policy) in Swedish and English, compliant with GDPR and Swedish law.

## External Dependencies

### Core Libraries
- **streamlit**: Web application framework.
- **plotly**: Interactive charting library.
- **pandas**: Data manipulation and analysis.
- **numpy**: Numerical computations.
- **scipy**: Statistical functions for Poisson probability calculations.

### Communication & Distribution
- **python-telegram-bot**: Telegram Bot API integration for prediction delivery.
- **telegram.ext**: Command handlers and subscriber management.
- **asyncio**: Asynchronous operations.

### Data Storage
- **sqlite3**: Python's built-in SQLite interface for local database operations.

### Web Scraping & Verification
- **trafilatura**: Web content extraction for result verification.
- **requests**: HTTP client for API calls and web scraping.
- **selenium**: Browser automation for complex scraping scenarios.

### Utility Libraries
- **pathlib**: Modern path handling.
- **datetime**: Time and date manipulation.
- **typing**: Type hints for code documentation.
- **schedule**: Task scheduling for automated processes.

### External APIs
- **The Odds API**: For real-time odds and match availability.
- **API-Football**: For injuries, lineups, and detailed match statistics.
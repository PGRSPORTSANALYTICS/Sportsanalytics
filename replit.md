# Exact Score Predictions Platform

## Overview
This project is an AI-powered platform for exact football score predictions, aiming for significant ROI through advanced machine learning and ensemble modeling. It features a premium Streamlit dashboard and Telegram bot delivery for predictions, coupled with automatic result verification. The system uses data-driven AI analysis (100% pattern-free) with ensemble models predicting ANY score based on xG, form, H2H, injuries, and standings. Targets 20-25% hit rate across 16 quality leagues (expanded Nov 2025) with odds 7-14x and 12%+ EV edge. Business goal: 500 settled predictions with 18%+ hit rate before January 2026 subscription launch (499-999 SEK/month) offering transparent, data-driven predictions with projected ROI of +100-200%.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### UI/UX Decisions
The platform utilizes a Streamlit web application with a wide layout for its dashboard, featuring Plotly for interactive charts and graphs. It includes auto-refresh functionality with 10-second intervals and built-in export capabilities for historical data. Consistent color coding, interactive elements with hover tooltips, and multi-chart support are used for data visualization.

### Technical Implementations
The system employs advanced prediction features including:
- **Team Form Analysis:** Evaluates win/loss records, goals, clean sheets, and PPG from the last 5 matches.
- **Head-to-Head Historical Analysis:** Examines the last 10 H2H matches for score patterns, Over 2.5 goals, and BTTS rates.
- **League Standings Integration:** Incorporates current league position, points, goal difference, and rank difference.
- **Odds Movement Tracking:** Monitors opening vs. current odds, movement velocity, sharp money indicators, and closing line value.
- **Injury and Lineup Data:** Dual-source system prioritizing API-Football for injuries and lineups, with automatic fallback to Transfermarkt web scraper when API unavailable. Scraper covers all Top 5 leagues + Champions League with 12-hour caching. Currently tracking 283 active injuries across major European leagues.
- **Neural Network Predictions:** A deep learning model for exact scores, trained on 50+ features.
- **Ensemble Prediction System:** Combines Poisson distribution (xG-based), neural network probabilities, and H2H patterns with weighted averaging.
- **Similar Matches Technology:** Analyzes historical matches with similar characteristics to adjust prediction confidence based on past outcomes. Uses league grouping (Top 5 leagues pooled together) for larger sample sizes. Adjusts confidence -30 to +30 points based on pattern strength.
- **Similar Matches Impact Tracker:** Automatically tracks every prediction to measure if Similar Matches is improving hit rate. Compares WITH vs WITHOUT Similar Matches adjustments, tracks predictions saved/blocked, and provides verdict after 20+ settled predictions. View with: `python3 view_sm_impact.py`
- **Expected Value (EV) Filtering System:** Mathematical edge calculation replacing arbitrary confidence scores. Only bets when model probability × odds provides genuine edge (EV > 15%). Includes:
  - **EV Calculator:** Combines Poisson, Neural Network, and Similar Matches probabilities with weighted averaging
  - **Model Agreement Checker:** Only bets when all models predict the same score
  - **Kelly Criterion Bet Sizing:** Optimal stake calculation based on edge and bankroll
  - **Model Calibration Tracker:** Validates if predicted probabilities match actual win rates across probability buckets
  - **Automatic Poisson Fallback:** Generates probabilities from xG data when model predictions unavailable
  - View calibration report: `python3 view_calibration.py`
- **Multi-Source Data Resilience:** Triple-layer fallback system ensures predictions continue even during API outages:
  - **Primary**: API-Football for injuries, lineups, H2H, form data, and standings
  - **Secondary**: Web scrapers (Transfermarkt for injuries, SofaScore for H2H/form/standings)
  - **Tertiary**: Safe default structures prevent crashes
  - All scrapers include 12-24 hour caching and rate limiting to minimize load
  - System automatically switches between sources without manual intervention
- **Odds Integration:** The Odds API provides real-time odds and match availability data.
- **Data-Driven Score Targeting:** System removed pattern filters (Nov 2025) to become 100% data-driven AI. Models now predict ANY score (1-0, 2-0, 2-1, 3-1, etc.) based on ensemble analysis. EV threshold lowered to 12% (from 15%) to enable predictions while maintaining quality edge.
- **League Coverage Expansion (Nov 3, 2025):** Expanded from 11 to 16 quality leagues to achieve 500 prediction volume goal by January 2026:
  - **Tier 1 (11 leagues):** Top 5 European (Premier, La Liga, Serie A, Bundesliga, Ligue 1), Elite European (Champions, Europa), Strong Second Tier (Eredivisie, Primeira, Belgian, Championship)
  - **Tier 2 (5 new leagues):** Scottish Premiership, Turkish Super League, Swedish Allsvenskan, Brazilian Serie A, Major League Soccer
  - **Target:** 30-40 predictions/week (up from 10-15/week) through different time zones and fixture schedules
  - **Per-League Tracking:** New monitoring script `view_league_performance.py` tracks hit rate, ROI, and volume per league. Underperforming leagues (< 15% hit rate after 20+ settled) can be removed.
- **Telegram Broadcast Fix (Nov 3, 2025):** Changed filter from unreliable bet_category to actual match_date check. Now only broadcasts predictions for matches playing TODAY, eliminating future prediction spam.
- **Player Props SGP System (Nov 6, 2025):** Expanded SGP (Same Game Parlay) system to include player-based predictions using API-Football player statistics:
  - **Player Statistics Fetcher:** Retrieves top scorers' goals per game, appearances, and shots per game from league data
  - **Anytime Goalscorer Probability:** Calculates player scoring probability using Poisson distribution adjusted for team's expected goals
  - **Player Shots Probability:** Estimates probability of player achieving 2+ shots on target
  - **6 New SGP Types:** Player to Score + Over/BTTS (both home/away), Player Shots 2+ + Over 2.5 + BTTS (3-leg premium parlays)
  - **Graceful Fallback:** System automatically falls back to basic parlays (Over/Under + BTTS) when player data unavailable or API-Football credentials missing
  - **Total SGP Offerings:** 9 combinations (3 basic goals + 6 player props) targeting 5-14% EV with odds 2-4.5x for basic, 5-12x for player props
- **Half-Time & Corners SGP Markets (Nov 6, 2025):** Further expanded SGP system with time-based and corners markets:
  - **Half-Time Goals Probability:** Calculates 1st half Over/Under using adjusted Poisson (45% of total xG)
  - **Second Half Goals Probability:** Calculates 2nd half Over/Under using adjusted Poisson (55% of total xG)
  - **Corners Probability:** Calibrated formula using xG correlation (total_corners = total_xG × 3.0 + 2.5, targeting 10-11 corner average). For typical xG 2.7: ~10.6 expected corners with Over 9.5 at ~62% probability
  - **6 New SGP Combinations:** 1H Over + 2H Over, 1H Over + BTTS, 2H Over + BTTS, Corners Over + Goals Over, Corners Over + BTTS, Premium 3-leg (Corners + 1H + Over 2.5)
  - **Correlation Matrix:** Updated with half-time, second half, and corners correlations for accurate joint probability pricing
  - **Total SGP Offerings:** 15 combinations (3 basic + 6 player props + 6 time/corners) targeting 5-15% EV
- **Hybrid Bet Monitoring System (Nov 6, 2025):** Unified real-time tracking solution for both Exact Score and SGP predictions:
  - **BetStatusService:** Centralized service querying both prediction products from single database with live status calculation (LIVE/UPCOMING/FINISHED based on 2-hour match window)
  - **Live Bet Control Center (Dashboard):** New Streamlit page with auto-refresh (45s), six-metric summary (Total Active, Exact Score, SGP, Today, Live, Total Stake), live bets section with countdown timers, today's bets grouped by status, all active bets with filters/sorting, settled today section with daily P&L, and CSV export
  - **Telegram Bot Commands:** Extended existing bot with `/active` (all bets summary), `/live` (matches in play), `/today` (today's bets grouped by status) for mobile monitoring
  - **Single Source of Truth:** Both dashboard and Telegram use shared BetStatusService ensuring data consistency

### System Design Choices
- **Data Layer:** SQLite database manages `suggestions`, `tickets`, and `pnl` tables, with a custom `DataLoader` for operations.
- **Data Processing:** Pandas DataFrames are used for all data manipulation, with timestamp-based organization. Financial calculations include Kelly criterion for bet sizing and edge calculation.
- **Database Design:** A single-file SQLite database is used for portability, with auto-creation of the database and tables, and timestamp indexing for efficient queries.
- **Legal Framework:** Comprehensive legal documentation (Terms of Service, Risk Disclaimer, Privacy Policy) in both Swedish and English, compliant with GDPR and Swedish law, is prepared for the subscription launch.

## External Dependencies

### Core Libraries
- **streamlit**: Web application framework.
- **plotly**: Interactive charting library.
- **pandas**: Data manipulation and analysis.
- **numpy**: Numerical computations.
- **scipy**: Statistical functions for Poisson probability calculations.

### Communication & Distribution
- **python-telegram-bot**: Telegram Bot API integration for prediction delivery.
- **telegram.ext**: Command handlers and subscriber management for the Telegram bot.
- **asyncio**: Asynchronous operations for bot performance.

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
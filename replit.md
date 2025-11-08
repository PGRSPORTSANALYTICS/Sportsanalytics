# Exact Score Predictions Platform

## Overview
This project is an AI-powered platform for exact football score predictions, leveraging advanced machine learning and ensemble modeling for significant ROI. It features a premium Streamlit dashboard and Telegram bot for prediction delivery, with automatic result verification. The system uses data-driven AI analysis (100% pattern-free) with ensemble models predicting ANY score based on xG, form, H2H, injuries, and standings. The platform targets a 20-25% hit rate across 16 quality leagues with odds 7-14x and a 12%+ EV edge. The January 2026 launch strategy focuses on Exact Score predictions, with SGP features to be introduced later once sufficient live-odds data is collected.

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
- **Expected Value (EV) Filtering System:** Mathematical edge calculation replacing arbitrary confidence scores, betting only when model probability × odds provides genuine edge. **Learning Mode (Nov 8, 2025):** Temporarily lowered from 12% to 8% EV threshold to accelerate data collection toward 500-prediction launch goal. This increases daily exact score volume from ~12-15 to ~20-25 predictions while maintaining quality filter. Includes Kelly Criterion Bet Sizing.
- **Multi-Source Data Resilience:** Triple-layer fallback system (API-Football, web scrapers, safe defaults) ensures continuous operation during API outages.
- **Data-Driven Score Targeting:** Models predict ANY score based on ensemble analysis, with EV threshold lowered to 12%.
- **League Coverage Expansion:** Expanded from 11 to 16 quality leagues to achieve higher prediction volume.
- **Telegram Broadcast Fix:** Ensures only predictions for matches playing today are broadcasted.
- **SGP Self-Learning System:** Features adaptive learning capabilities for probability calibration, correlation learning, and dynamic Kelly sizing.
- **Live SGP Odds Integration:** Uses real bookmaker odds from The Odds API for SGP, with three pricing modes (Live, Hybrid, Simulated) and graceful fallback.
- **Player Props SGP System:** Expanded SGP to include player-based predictions (Anytime Goalscorer, Player Shots) using API-Football player statistics.
- **Half-Time & Corners SGP Markets:** Further expanded SGP with half-time goals and corners markets using adjusted Poisson distribution and correlation matrices.
- **Multi-Leg Parlay System:** Supports 3-7 leg parlays with a tiered EV filtering system (Jackpot Play, Premium Parlay, Value Parlay, Value Bet) balancing value and entertainment.
- **Hybrid Bet Monitoring System:** Unified real-time tracking for Exact Score and SGP predictions via a central `BetStatusService`, a Live Bet Control Center (Dashboard), and extended Telegram bot commands.
- **Dual Telegram Channels (Nov 8, 2025):** Separate broadcast channels for different prediction types with smart volume control:
  - **Tips Channel (-1003269011722):** Dedicated to Exact Score predictions only (~20-25 per day during learning mode)
  - **SGP Channel (-1003233743568):** Dedicated to SGP/parlay predictions only
  - **Smart Volume Control:** System generates all possible SGPs (~300+) for analytics, but only broadcasts top 15 regular SGP + top 5 MonsterSGP (sorted by EV) to avoid channel spam
  - **Channel Routing:** `telegram_sender.py` routes predictions based on `prediction_type` parameter (exact_score/sgp) to appropriate channel
  - **Robust Date Parsing:** Multi-strategy date parser handles various ISO format variations from different data sources

### System Design Choices
- **Data Layer:** SQLite database manages `suggestions`, `tickets`, and `pnl` tables, with a custom `DataLoader`.
- **Data Processing:** Pandas DataFrames are used for all data manipulation, with timestamp-based organization and financial calculations (Kelly criterion, edge calculation).
- **Database Design:** A single-file SQLite database with auto-creation of tables and timestamp indexing.
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
- **API-Football**: For injuries, lineups, and detailed match statistics.- **MonsterSGP - Team-Specific Parlays (Nov 8, 2025):** Redesigned to use team-specific markets matching real bet builder offerings:
  - **Team-Specific Markets:** Home/Away Team Corners, Home/Away Team Shots, Match Result (1x2), 1H Goals, Full Match Corners
  - **New Probability Functions:**
    - **Team Corners:** Poisson(team_xG × 3.5 + 3.0) - calculates individual team corner expectations
    - **Team Shots:** Poisson(team_xG × 7.0 + 10.0) - calculates individual team shot totals
    - **Match Result:** Poisson-based 1x2 probabilities for home/draw/away outcomes
  - **Smart Filtering:** Only generates MonsterSGP when home_xG / away_xG >= 1.5 (ensures dominant home favorites)
  - **Calibrated Lines (targeting 30-60x odds):**
    - Home Team Corners 9.5+ (~48% hit rate for strong home team)
    - Away Team Corners U5.5 (~50% hit rate for weak away team)
    - Home Team Shots 24.5+ (~48% hit rate for strong home team)
    - Away Team Shots U15.5 (~50% hit rate for weak away team)
  - **MonsterSGP Combinations:**
    - **3-leg:** 1H Over 0.5 + Home Corners 9.5+ + Away Corners U5.5
    - **4-leg:** 3-leg + Home Shots 24.5+
    - **5-leg:** 4-leg + Away Shots U15.5
    - **6-leg:** 5-leg + Full Match Corners 10.5+
    - **7-leg BEAST:** 6-leg + Home Win (1x2)
  - **Correlation Matrix:** 11 new correlations for team-specific markets (e.g., HOME_TEAM_CORNERS ↔ HOME_TEAM_SHOTS: 0.45, MATCH_RESULT:HOME ↔ HOME_TEAM_SHOTS: 0.40)
  - **Target Performance:** 30-60x average odds with balanced 45-50% probability per leg

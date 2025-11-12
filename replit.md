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
- **Data-Driven Score Targeting:** Models predict ANY score based on ensemble analysis. **Expanded Score Diversity (Nov 8, 2025):** Removed hardcoded score biases and increased max_goals from 8 to 10, allowing predictions for all scores 0-0 through 9-9. System now predicts based purely on xG probability and EV, not historical patterns, to collect diverse training data including high-scoring games (3-2, 4-1, etc.).
- **Venue-Specific Form Analysis (Nov 8, 2025):** Fixed critical xG calculation bias by implementing venue-specific form filtering. Home teams now use only their last 5 HOME games for xG calculation, and away teams use only their last 5 AWAY games. This accurately captures teams that are strong at home but weak away (or vice versa), replacing the previous system that incorrectly averaged all games together. For example, a team with 2.5 xG at home and 1.2 xG away now correctly uses 2.5 when playing home, instead of the misleading 1.85 average.
- **League Coverage Expansion:** Expanded from 11 to 16 quality leagues to achieve higher prediction volume.
- **Winter Leagues Integration (Nov 12, 2025):** Full integration of year-round coverage with Brazil Serie A and Japan J1 League:
  - **Unified League Registry:** Created `league_config.py` as single source of truth mapping The Odds API keys to API-Football IDs for all 23 active leagues
  - **Dynamic League Loading:** Updated `real_football_champion.py` to auto-generate league lists from registry instead of hardcoded lists
  - **Auto-Verification Script:** `winter_leagues.py` validates API IDs and seasons using API-Football search (Brazil ID 71, Season 2025; Japan ID 98, Season 2025)
  - **Team Mappings:** Added 22 Brazilian teams (Flamengo, Palmeiras, Santos, etc.) and 20 Japanese teams (Kawasaki Frontale, Urawa Reds, Vissel Kobe, etc.) to `team_id_mappings.py`
  - **24/7 Coverage:** System now queries 7 winter leagues (Brazil, Argentina, Japan, Korea, Australia, USA, Mexico) ensuring continuous prediction generation during European off-season
  - **Files:** `league_config.py`, `winter_leagues.py`
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
  - **Smart Volume Control:** System generates all possible SGPs (~300+) for analytics, but only broadcasts top 15 regular SGP + top 10 MonsterSGP (sorted by EV) to avoid channel spam
  - **MonsterSGP Separation (Nov 10, 2025):** MonsterSGP is **entertainment-only** with extreme odds (30-200x) and excluded from official SGP performance statistics. Dashboard shows only regular SGP stats (158 predictions, 33.5% hit rate, +2,497 SEK profit).
  - **Channel Routing:** `telegram_sender.py` routes predictions based on `prediction_type` parameter (exact_score/sgp) to appropriate channel
  - **Robust Date Parsing:** Multi-strategy date parser handles various ISO format variations from different data sources
- **Intelligent Result Verification System (Nov 8, 2025):** Production-ready caching and cooldown system to prevent API quota exhaustion:
  - **Per-Match Result Caching (24h):** Individual match results cached for 24 hours, preventing redundant API calls while allowing fallback sources to fill gaps when primary source returns partial results
  - **30-Minute Verification Cooldown:** Each bet tracked with last verification timestamp, preventing redundant checks within 30 minutes. Cooldown marked AFTER successful verification (not before) to avoid waiting on upstream errors
  - **Multi-Source Fallback Strategy:** Flashscore (free) → API-Football → The Odds API → Sofascore, with smart caching at each layer
  - **API Quota Protection:** Reduces result verification API calls by 90% after initial check, ensuring sustainable operation within free API quotas
  - **Database Tables:** `match_results_cache` (per-match results with 24h TTL) and `verification_tracking` (bet-level cooldown timestamps)

### System Design Choices
- **Data Layer (Nov 9, 2025):** Migrated from SQLite to PostgreSQL (Replit's built-in Neon database) to eliminate database locking issues during concurrent workflow access. Uses connection pooling (5-20 connections) for 10+ simultaneous workflows. Created `db_helper.py` SQL compatibility layer and `pg_compat.py` for seamless migration of existing SQLite code.
- **Date Field Standardization (Nov 9, 2025):** System uses two date fields:
  - `recommended_date`: When prediction was generated (for tracking/analytics)
  - `match_date`: When the actual match is played (PRIMARY field for all queries)
  - **Critical Rule:** ALL date-based queries (dashboard display, daily summaries, "today's predictions", result verification) MUST use `match_date`, not `recommended_date`. This prevents confusion when predictions are generated days before the match.
- **Persistent API Caching (Nov 9, 2025):** CRITICAL FIX - Migrated from in-memory caching to PostgreSQL-based persistent caching to prevent API quota exhaustion:
  - **Problem:** Each of 10 concurrent workflows had separate in-memory caches that reset on restart, causing redundant API calls (10x multiplier)
  - **Solution:** `APICacheManager` class stores all API responses in PostgreSQL tables (`api_football_cache`, `odds_api_cache`) shared across ALL workflows
  - **Shared Quota Counter:** `api_request_counter` table tracks daily API usage across all workflows, preventing quota exhaustion
  - **Cache TTLs:** Team IDs (7 days), Fixtures (24h), Injuries (2h), Lineups (7 days), Live Odds (5min)
  - **Quota Limits:** API-Football (7000/day), The Odds API (450/day)
  - **Impact:** Reduces API calls by 90%+ by eliminating redundant calls across workflows
  - **Files:** `api_cache_manager.py`, `api_football_client.py`, `real_odds_api.py`
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

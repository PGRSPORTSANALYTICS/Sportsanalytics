# Exact Score Predictions Platform

## Overview
This project is an AI-powered platform for exact football score predictions, aiming for significant ROI through advanced machine learning and ensemble modeling. It features a premium Streamlit dashboard and Telegram bot delivery for predictions, coupled with automatic result verification. The system is highly optimized with "ULTRA-AGGRESSIVE filters," specifically targeting a 20-25% hit rate by focusing exclusively on 1-0 and 1-1 scores in top 5 leagues with odds between 7x and 11x. The business vision includes a paid subscription launch in January 2026, offering transparent, data-driven predictions with a focus on quality over quantity and projected ROI of +100-200%.

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
- **Dual API Integration:** Leverages The Odds API for real-time odds and API-Football for injuries, lineups, and statistics, cross-validating data for accuracy.
- **Data-Driven Score Targeting:** Based on analysis of 159 verified bets, system now exclusively targets winning score patterns: 2-0 (66.7% win rate, +3,941 SEK profit), 3-1 (28.6% win rate, +3,685 SEK profit), and 2-1 (16.1% win rate, +5,091 SEK profit). Top 5 leagues only, odds 7-14x range targeting 12x+ sweet spot. Previous targets (1-0, 1-1) removed due to poor performance (6.9% and 8.3% win rates respectively).

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
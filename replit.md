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
- **Injury and Lineup Data:** Tracks key player injuries and confirms lineups 1-2 hours before kickoff.
- **Neural Network Predictions:** A deep learning model for exact scores, trained on 50+ features.
- **Ensemble Prediction System:** Combines Poisson distribution (xG-based), neural network probabilities, and H2H patterns with weighted averaging.
- **Similar Matches Technology:** Analyzes historical matches with similar characteristics to adjust prediction confidence based on past outcomes. Uses league grouping (Top 5 leagues pooled together) for larger sample sizes. Adjusts confidence -30 to +30 points based on pattern strength.
- **Similar Matches Impact Tracker:** Automatically tracks every prediction to measure if Similar Matches is improving hit rate. Compares WITH vs WITHOUT Similar Matches adjustments, tracks predictions saved/blocked, and provides verdict after 20+ settled predictions. View with: `python3 view_sm_impact.py`
- **Confidence Scoring System:** Filters predictions with a threshold of 85+, using factors like proven score bonuses, odds sweet spot (11-13x), league quality, value score, match context, and injury impact.
- **Dual API Integration:** Leverages The Odds API for real-time odds and API-Football for injuries, lineups, and statistics, cross-validating data for accuracy.
- **Ultra-Aggressive Filters:** Targets 1-0 and 1-1 scores in Top 5 leagues with odds 7-11x, based on data-proven winning patterns (1-1 scores with 25% win rate, 2-1 with 16.7%, and 1-0 with 12.5%).

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
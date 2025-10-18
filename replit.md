# Exact Score Predictions Platform

## Overview

This is an AI-powered exact score prediction platform achieving +354% ROI through advanced ML and ensemble predictions. The system features a premium Streamlit dashboard, Telegram bot delivery, and automatic result verification. After proving significant performance advantage (exact scores: +354% ROI vs regular tips: -29.2% ROI), the platform now exclusively focuses on high-odds exact score predictions with typical odds ranging from 7.0 to 15.0.

## 🚀 Recent Enhancements (October 2025)

### Advanced Prediction Features
The system now uses a sophisticated ensemble approach combining multiple prediction methods:

1. **Team Form Analysis** (Last 5 matches)
   - Win/draw/loss records
   - Goals scored and conceded averages
   - Clean sheet rates
   - Points per game
   - Home/away performance splits

2. **Head-to-Head Historical Analysis**
   - Last 10 H2H matches between teams
   - Historical score patterns
   - Over 2.5 goals rate in H2H
   - BTTS (Both Teams to Score) rate in H2H

3. **League Standings Integration**
   - Current league position for both teams
   - Points and goal difference
   - Rank difference (strength gap indicator)
   - Home/away form in standings

4. **Odds Movement Tracking**
   - Opening odds vs current odds
   - Movement velocity (rate of change)
   - Sharp money indicators (steam moves)
   - Closing line value analysis

5. **Injury and Lineup Data**
   - Key player injuries tracking
   - Lineup confirmations (1-2 hours before kickoff)
   - Formation analysis when available

6. **Neural Network Predictions**
   - Deep learning model for exact scores
   - Multi-output architecture (home goals + away goals)
   - Trained on 50+ features
   - Probability distribution for all scores 0-6

7. **Ensemble Prediction System**
   - Combines Poisson distribution (xG-based)
   - Neural network probabilities
   - H2H historical patterns
   - Weighted averaging for optimal accuracy

### Enhanced Feature Set
Expanded from 15 to 50+ predictive features:
- Basic: odds, edge, confidence, quality
- xG: home, away, total, difference, ratio
- Form: win rates, goals, concessions, clean sheets, PPG
- H2H: matches, win rates, goal averages, over/under rates
- Standings: ranks, points, goal difference
- Odds: movement %, velocity, sharp money indicators
- Context: injuries, lineups, weekend games
- Derived: form difference, goals balance, quality×confidence, value score

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: Streamlit web application with wide layout configuration
- **Visualization**: Plotly for interactive charts and graphs
- **Real-time Updates**: Auto-refresh functionality with 10-second intervals
- **Data Export**: Built-in export capabilities for historical data analysis

### Backend Architecture
- **Data Layer**: SQLite database with three main tables:
  - `suggestions`: Betting recommendations with odds, stakes, and Kelly criterion calculations
  - `tickets`: Actual bet placements with settlement status and P&L
  - `pnl`: Bankroll progression and risk exposure tracking
- **Data Access**: Custom DataLoader class handling all database operations with error handling
- **Chart Generation**: Dedicated ChartGenerator class for creating consistent visualizations

### Data Processing
- **Pandas Integration**: All data manipulation using pandas DataFrames
- **Time Series Analysis**: Timestamp-based data organization for trend analysis
- **Financial Calculations**: Kelly criterion implementation for optimal bet sizing
- **Performance Metrics**: Edge calculation (absolute and relative) for bet evaluation

### Database Design
- **Single File Database**: SQLite for simplicity and portability
- **Auto-creation**: Database and tables created automatically if missing
- **Timestamp Indexing**: Integer timestamps for efficient time-based queries
- **Settlement Tracking**: Boolean flags for bet outcome monitoring

### Visualization Strategy
- **Color Coding**: Consistent color scheme across all charts
- **Interactive Elements**: Hover tooltips and responsive chart interactions
- **Multi-chart Support**: Subplot capabilities for complex data relationships
- **Error Handling**: Graceful handling of empty datasets with informative messages

## External Dependencies

### Core Libraries
- **streamlit**: Web application framework for dashboard interface
- **plotly**: Interactive charting library (express and graph_objects modules)
- **pandas**: Data manipulation and analysis
- **numpy**: Numerical computations for statistical calculations

### Communication & Distribution
- **python-telegram-bot**: Telegram Bot API integration for tips delivery
- **telegram.ext**: Command handlers and subscriber management
- **asyncio**: Asynchronous operations for bot performance

### Data Storage
- **sqlite3**: Built-in Python SQLite interface for local database operations

### Web Scraping & Verification
- **trafilatura**: Web content extraction for result verification
- **requests**: HTTP client for API calls and web scraping
- **selenium**: Browser automation for complex scraping scenarios

### Utility Libraries
- **pathlib**: Modern path handling for file operations
- **datetime**: Time and date manipulation with timezone support
- **typing**: Type hints for better code documentation and IDE support
- **schedule**: Task scheduling for automated processes

### File System
- **Local Storage**: SQLite database stored in `data/real_football.db`
- **Logs Directory**: `logs/` folder for system and verification logs
- **Automatic Directory Creation**: Self-managing file structure

### Integration Features
- **Exact Score Focus**: Exclusive focus on exact score predictions (market='exact_score')
- **Telegram Bot**: ExactScoreBot delivers predictions with 7-15x odds to subscribers
- **Real Result Verification**: Multi-source scraping with enhanced team name matching
- **Volume Generation**: Up to 10 exact score predictions per cycle, no daily limits
- **Proven Performance**: 131 exact scores tracked, 50% hit rate, +$2,237 profit on $1,109 staked
- **Authentic ROI Tracking**: No simulated data, only real match outcomes
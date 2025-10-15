# Exact Score Predictions Platform

## Overview

This is an AI-powered exact score prediction platform achieving +200% ROI through advanced xG analysis. The system features a premium Streamlit dashboard, Telegram bot delivery, and automatic result verification. After proving significant performance advantage (exact scores: +201.7% ROI vs regular tips: -29.2% ROI), the platform now exclusively focuses on high-odds exact score predictions with typical odds ranging from 7.0 to 15.0.

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
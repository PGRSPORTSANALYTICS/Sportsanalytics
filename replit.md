# E-Soccer Betting Bot Dashboard

## Overview

This is a Streamlit-based dashboard for monitoring an e-soccer betting bot's performance. The system provides real-time visualization of betting suggestions, ticket outcomes, and financial metrics including bankroll progression and P&L tracking. The dashboard connects to an SQLite database that stores betting data and presents it through interactive charts and tables.

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

### Data Storage
- **sqlite3**: Built-in Python SQLite interface for local database operations

### Utility Libraries
- **pathlib**: Modern path handling for file operations
- **datetime**: Time and date manipulation with timezone support
- **typing**: Type hints for better code documentation and IDE support

### File System
- **Local Storage**: SQLite database stored in `data/esoccer.db`
- **Export Directory**: `exports/` folder for data export functionality
- **Automatic Directory Creation**: Self-managing file structure
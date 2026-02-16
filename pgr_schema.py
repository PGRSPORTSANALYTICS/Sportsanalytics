"""
PGR Sports Analytics - Database Schema
=======================================
Creates all new tables for the 6-module system.
Preserves existing tables (football_opportunities, odds_snapshots, etc).
"""

import logging
from db_helper import db_helper

logger = logging.getLogger(__name__)

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS pgr_odds_snapshots (
        id SERIAL PRIMARY KEY,
        event_id VARCHAR(200) NOT NULL,
        sport VARCHAR(30) DEFAULT 'football',
        league_id VARCHAR(100) NOT NULL,
        league_name VARCHAR(200) DEFAULT '',
        start_time_utc TIMESTAMP NOT NULL,
        home_team VARCHAR(200) NOT NULL,
        away_team VARCHAR(200) NOT NULL,
        market_type VARCHAR(80) NOT NULL,
        selection VARCHAR(100) NOT NULL,
        line REAL,
        bookmaker VARCHAR(100) NOT NULL,
        odds_decimal REAL NOT NULL,
        timestamp_utc TIMESTAMP NOT NULL DEFAULT NOW(),
        fixture_id INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pgr_odds_event ON pgr_odds_snapshots(event_id)",
    "CREATE INDEX IF NOT EXISTS idx_pgr_odds_time ON pgr_odds_snapshots(timestamp_utc)",
    "CREATE INDEX IF NOT EXISTS idx_pgr_odds_market ON pgr_odds_snapshots(market_type, selection)",
    "CREATE INDEX IF NOT EXISTS idx_pgr_odds_kickoff ON pgr_odds_snapshots(start_time_utc)",
    """
    CREATE TABLE IF NOT EXISTS pgr_market_state (
        id SERIAL PRIMARY KEY,
        event_id VARCHAR(200) NOT NULL,
        market_type VARCHAR(80) NOT NULL,
        selection VARCHAR(100) NOT NULL,
        line REAL,
        best_price REAL NOT NULL,
        best_bookmaker VARCHAR(100) NOT NULL,
        market_avg REAL NOT NULL,
        market_median REAL NOT NULL,
        dispersion REAL DEFAULT 0,
        book_count INTEGER DEFAULT 0,
        prices JSONB DEFAULT '{}',
        is_stale BOOLEAN DEFAULT FALSE,
        stale_books TEXT[] DEFAULT '{}',
        timestamp_utc TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE(event_id, market_type, selection, line)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pgr_mkt_event ON pgr_market_state(event_id)",
    """
    CREATE TABLE IF NOT EXISTS pgr_fair_odds (
        id SERIAL PRIMARY KEY,
        event_id VARCHAR(200) NOT NULL,
        market_type VARCHAR(80) NOT NULL,
        selection VARCHAR(100) NOT NULL,
        line REAL,
        model_prob REAL NOT NULL,
        fair_odds REAL NOT NULL,
        calibrated_prob REAL,
        calibration_source VARCHAR(30) DEFAULT 'global',
        confidence REAL DEFAULT 0.5,
        confidence_badge VARCHAR(10) DEFAULT 'MEDIUM',
        uncertainty REAL DEFAULT 0,
        data_quality REAL DEFAULT 1.0,
        league_sample_size INTEGER DEFAULT 0,
        market_dispersion REAL DEFAULT 0,
        volatility REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(event_id, market_type, selection, line)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pgr_fair_event ON pgr_fair_odds(event_id)",
    """
    CREATE TABLE IF NOT EXISTS pgr_bet_lifecycle (
        id SERIAL PRIMARY KEY,
        event_id VARCHAR(200) NOT NULL,
        home_team VARCHAR(200) NOT NULL,
        away_team VARCHAR(200) NOT NULL,
        league_id VARCHAR(100) NOT NULL,
        league_name VARCHAR(200) DEFAULT '',
        sport VARCHAR(30) DEFAULT 'football',
        market_type VARCHAR(80) NOT NULL,
        selection VARCHAR(100) NOT NULL,
        line REAL,
        odds_decimal REAL NOT NULL,
        bookmaker VARCHAR(100) DEFAULT '',
        fair_odds REAL NOT NULL,
        model_prob REAL NOT NULL,
        edge_pct REAL NOT NULL,
        ev_pct REAL NOT NULL,
        confidence REAL DEFAULT 0.5,
        confidence_badge VARCHAR(10) DEFAULT 'MEDIUM',
        status VARCHAR(20) DEFAULT 'candidate',
        gating_status VARCHAR(20) DEFAULT 'LEARNING_ONLY',
        stake_units REAL DEFAULT 1.0,
        result VARCHAR(20),
        profit_loss REAL,
        closing_odds REAL,
        clv_pct REAL,
        start_time_utc TIMESTAMP,
        published_at TIMESTAMP,
        placed_at TIMESTAMP,
        settled_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        model_version VARCHAR(30) DEFAULT 'pgr_v2',
        request_id VARCHAR(60),
        tags TEXT[] DEFAULT '{}',
        notes TEXT DEFAULT '',
        expected_clv_pct REAL,
        volatility REAL DEFAULT 0,
        UNIQUE(event_id, market_type, selection, line, bookmaker)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pgr_bet_status ON pgr_bet_lifecycle(status)",
    "CREATE INDEX IF NOT EXISTS idx_pgr_bet_event ON pgr_bet_lifecycle(event_id)",
    "CREATE INDEX IF NOT EXISTS idx_pgr_bet_gating ON pgr_bet_lifecycle(gating_status)",
    "CREATE INDEX IF NOT EXISTS idx_pgr_bet_created ON pgr_bet_lifecycle(created_at)",
    """
    CREATE TABLE IF NOT EXISTS pgr_audit_log (
        id SERIAL PRIMARY KEY,
        bet_lifecycle_id INTEGER REFERENCES pgr_bet_lifecycle(id) ON DELETE CASCADE,
        action VARCHAR(50) NOT NULL,
        old_status VARCHAR(20),
        new_status VARCHAR(20),
        details JSONB DEFAULT '{}',
        timestamp_utc TIMESTAMP DEFAULT NOW(),
        source VARCHAR(30) DEFAULT 'system'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pgr_audit_bet ON pgr_audit_log(bet_lifecycle_id)",
    "CREATE INDEX IF NOT EXISTS idx_pgr_audit_time ON pgr_audit_log(timestamp_utc)",
    """
    CREATE TABLE IF NOT EXISTS pgr_clv_records (
        id SERIAL PRIMARY KEY,
        bet_lifecycle_id INTEGER REFERENCES pgr_bet_lifecycle(id) ON DELETE CASCADE,
        event_id VARCHAR(200) NOT NULL,
        market_type VARCHAR(80) NOT NULL,
        selection VARCHAR(100) NOT NULL,
        bet_odds REAL NOT NULL,
        closing_odds REAL NOT NULL,
        clv_pct REAL NOT NULL,
        close_window_minutes INTEGER DEFAULT 5,
        close_timestamp_utc TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pgr_clv_event ON pgr_clv_records(event_id)",
    """
    CREATE TABLE IF NOT EXISTS pgr_timing_stats (
        id SERIAL PRIMARY KEY,
        sport VARCHAR(30) DEFAULT 'football',
        league_id VARCHAR(100) NOT NULL,
        market_type VARCHAR(80) NOT NULL,
        time_bucket VARCHAR(30) NOT NULL,
        total_bets INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        roi_pct REAL DEFAULT 0,
        avg_clv REAL DEFAULT 0,
        avg_ev REAL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(sport, league_id, market_type, time_bucket)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pgr_weekly_reports (
        id SERIAL PRIMARY KEY,
        week_start DATE NOT NULL,
        week_end DATE NOT NULL,
        report_data JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(week_start)
    )
    """,
]


def create_pgr_schema():
    success = 0
    errors = 0
    for sql in SCHEMA_SQL:
        try:
            db_helper.execute(sql)
            success += 1
        except Exception as e:
            logger.error(f"Schema error: {e} | SQL: {sql[:80]}")
            errors += 1
    logger.info(f"PGR Schema: {success} statements OK, {errors} errors")
    return success, errors


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s, e = create_pgr_schema()
    print(f"Schema created: {s} OK, {e} errors")

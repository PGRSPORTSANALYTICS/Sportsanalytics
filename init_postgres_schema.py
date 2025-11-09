import psycopg2
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_schema():
    """Initialize PostgreSQL schema matching SQLite structure"""
    conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    cursor = conn.cursor()
    
    try:
        logger.info("🔧 Creating PostgreSQL schema...")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS football_opportunities (
                id SERIAL PRIMARY KEY,
                timestamp BIGINT,
                match_id TEXT,
                home_team TEXT,
                away_team TEXT,
                league TEXT,
                market TEXT,
                selection TEXT,
                odds REAL,
                edge_percentage REAL,
                confidence INTEGER,
                analysis TEXT,
                stake REAL,
                status TEXT DEFAULT 'pending',
                result TEXT,
                payout REAL DEFAULT 0,
                settled_timestamp BIGINT,
                roi_percentage REAL DEFAULT 0,
                match_date TEXT,
                kickoff_time TEXT,
                outcome TEXT,
                profit_loss REAL DEFAULT 0,
                updated_at TEXT,
                quality_score REAL DEFAULT 0,
                recommended_tier TEXT DEFAULT NULL,
                recommended_date TEXT DEFAULT NULL,
                daily_rank INTEGER DEFAULT NULL,
                model_version TEXT,
                model_prob REAL,
                calibrated_prob REAL,
                kelly_stake REAL,
                tier TEXT DEFAULT 'legacy',
                publish_status TEXT DEFAULT 'pending',
                actual_score TEXT,
                bet_category TEXT DEFAULT 'today'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_analytics (
                id SERIAL PRIMARY KEY,
                team_name TEXT,
                league TEXT,
                timestamp BIGINT,
                form_data TEXT,
                xg_data TEXT,
                h2h_data TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS roi_snapshots (
                id SERIAL PRIMARY KEY,
                date TEXT UNIQUE,
                daily_roi REAL,
                weekly_roi REAL,
                monthly_roi REAL,
                total_roi REAL,
                total_stakes REAL,
                total_profit_loss REAL,
                win_rate REAL,
                total_bets INTEGER,
                settled_bets INTEGER,
                milestone_50_reached INTEGER DEFAULT 0,
                milestone_60_reached INTEGER DEFAULT 0,
                milestone_70_reached INTEGER DEFAULT 0,
                consistency_days INTEGER DEFAULT 0,
                business_ready INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS roi_milestones (
                id SERIAL PRIMARY KEY,
                milestone_type TEXT,
                milestone_value REAL,
                achieved_date TEXT,
                achieved_roi REAL,
                total_bets INTEGER,
                consistency_days INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY,
                match_id TEXT NOT NULL,
                market TEXT NOT NULL,
                selection TEXT NOT NULL,
                model_version TEXT NOT NULL,
                prob REAL NOT NULL,
                calibrated_prob REAL,
                ev REAL,
                kelly_fraction REAL,
                created_at TEXT NOT NULL,
                outcome TEXT,
                profit_loss REAL,
                created_timestamp BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_metadata (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                market TEXT NOT NULL,
                trained_at TEXT NOT NULL,
                metrics_json TEXT,
                is_active INTEGER DEFAULT 0,
                UNIQUE(name, market, version)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS odds_movements (
                id SERIAL PRIMARY KEY,
                match_id TEXT,
                home_team TEXT,
                away_team TEXT,
                market TEXT,
                selection TEXT,
                opening_odds REAL,
                current_odds REAL,
                timestamp BIGINT,
                movement_velocity REAL,
                sharp_money_indicator REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sgp_predictions (
                id SERIAL PRIMARY KEY,
                timestamp BIGINT,
                match_id TEXT,
                home_team TEXT,
                away_team TEXT,
                league TEXT,
                match_date TEXT,
                kickoff_time TEXT,
                legs TEXT,
                parlay_description TEXT,
                parlay_probability REAL,
                fair_odds REAL,
                bookmaker_odds REAL,
                ev_percentage REAL,
                stake REAL DEFAULT 160,
                kelly_stake REAL,
                status TEXT DEFAULT 'pending',
                outcome TEXT,
                result TEXT,
                payout REAL,
                profit_loss REAL,
                settled_timestamp BIGINT,
                model_version TEXT,
                simulations INTEGER DEFAULT 200000,
                correlation_method TEXT DEFAULT 'copula',
                pricing_mode TEXT DEFAULT 'simulated',
                pricing_metadata TEXT DEFAULT '{}'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sgp_calibration (
                param_name TEXT PRIMARY KEY,
                param_value REAL,
                updated_timestamp BIGINT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sgp_leg_correlations (
                leg_pair TEXT PRIMARY KEY,
                both_win INTEGER DEFAULT 0,
                both_lose INTEGER DEFAULT 0,
                leg1_win_leg2_lose INTEGER DEFAULT 0,
                leg1_lose_leg2_win INTEGER DEFAULT 0,
                learned_correlation REAL,
                sample_count INTEGER,
                updated_timestamp BIGINT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_results_cache (
                home_team TEXT,
                away_team TEXT,
                match_date TEXT,
                home_score INTEGER,
                away_score INTEGER,
                cached_at TEXT NOT NULL,
                source TEXT,
                PRIMARY KEY (home_team, away_team, match_date)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verification_tracking (
                bet_id INTEGER PRIMARY KEY,
                last_checked_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_summaries (
                match_date TEXT PRIMARY KEY,
                sent_summary INTEGER DEFAULT 0,
                sent_at BIGINT
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_recommended_date_tier ON football_opportunities(recommended_date, tier)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_match_id ON football_opportunities(match_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_match_date ON football_opportunities(match_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sgp_match_date ON sgp_predictions(match_date)')
        
        conn.commit()
        logger.info("✅ PostgreSQL schema created successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Schema creation failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    init_schema()

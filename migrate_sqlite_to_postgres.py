import sqlite3
import psycopg2
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_table(sqlite_cursor, pg_cursor, table_name, columns):
    """Migrate a single table from SQLite to PostgreSQL"""
    logger.info(f"📦 Migrating {table_name}...")
    
    sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = sqlite_cursor.fetchone()[0]
    logger.info(f"   Found {count} rows to migrate")
    
    if count == 0:
        logger.info(f"   ⏭️  Skipping {table_name} (empty)")
        return
    
    sqlite_cursor.execute(f"SELECT {', '.join(columns)} FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    
    placeholders = ', '.join(['%s'] * len(columns))
    insert_query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    
    migrated = 0
    error_shown = False
    for row in rows:
        try:
            pg_cursor.execute(insert_query, row)
            migrated += 1
        except Exception as e:
            if not error_shown:
                logger.error(f"   ❌ First error in {table_name}: {e}")
                logger.error(f"   Row data: {row[:5]}...")  # Show first 5 values
                error_shown = True
            pg_cursor.connection.rollback()  # Rollback failed transaction
    
    logger.info(f"   ✅ Migrated {migrated}/{count} rows")

def migrate_all():
    """Migrate all data from SQLite to PostgreSQL"""
    logger.info("=" * 80)
    logger.info("SQLITE → POSTGRESQL MIGRATION")
    logger.info("=" * 80)
    
    sqlite_conn = sqlite3.connect('data/real_football.db')
    sqlite_cursor = sqlite_conn.cursor()
    
    pg_conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    pg_cursor = pg_conn.cursor()
    
    try:
        tables_to_migrate = [
            ('football_opportunities', [
                'timestamp', 'match_id', 'home_team', 'away_team', 'league', 'market',
                'selection', 'odds', 'edge_percentage', 'confidence', 'analysis', 'stake',
                'status', 'result', 'payout', 'settled_timestamp', 'roi_percentage',
                'match_date', 'kickoff_time', 'outcome', 'profit_loss', 'updated_at',
                'quality_score', 'recommended_tier', 'recommended_date', 'daily_rank',
                'model_version', 'model_prob', 'calibrated_prob', 'kelly_stake', 'tier',
                'publish_status', 'actual_score', 'bet_category'
            ]),
            ('team_analytics', [
                'team_name', 'league', 'timestamp', 'form_data', 'xg_data', 'h2h_data'
            ]),
            ('roi_snapshots', [
                'date', 'daily_roi', 'weekly_roi', 'monthly_roi', 'total_roi',
                'total_stakes', 'total_profit_loss', 'win_rate', 'total_bets',
                'settled_bets', 'milestone_50_reached', 'milestone_60_reached',
                'milestone_70_reached', 'consistency_days', 'business_ready'
            ]),
            ('roi_milestones', [
                'milestone_type', 'milestone_value', 'achieved_date', 'achieved_roi',
                'total_bets', 'consistency_days', 'notes'
            ]),
            ('predictions', [
                'match_id', 'market', 'selection', 'model_version', 'prob',
                'calibrated_prob', 'ev', 'kelly_fraction', 'created_at', 'outcome',
                'profit_loss', 'created_timestamp'
            ]),
            ('model_metadata', [
                'name', 'version', 'market', 'trained_at', 'metrics_json', 'is_active'
            ]),
            ('odds_movements', [
                'match_id', 'home_team', 'away_team', 'market', 'selection',
                'opening_odds', 'current_odds', 'timestamp', 'movement_velocity',
                'sharp_money_indicator'
            ]),
            ('sgp_predictions', [
                'timestamp', 'match_id', 'home_team', 'away_team', 'league', 'match_date',
                'kickoff_time', 'legs', 'parlay_description', 'parlay_probability',
                'fair_odds', 'bookmaker_odds', 'ev_percentage', 'stake', 'kelly_stake',
                'status', 'outcome', 'result', 'payout', 'profit_loss',
                'settled_timestamp', 'model_version', 'simulations',
                'correlation_method', 'pricing_mode', 'pricing_metadata'
            ]),
            ('sgp_calibration', [
                'param_name', 'param_value', 'updated_timestamp'
            ]),
            ('sgp_leg_correlations', [
                'leg_pair', 'both_win', 'both_lose', 'leg1_win_leg2_lose',
                'leg1_lose_leg2_win', 'learned_correlation', 'sample_count',
                'updated_timestamp'
            ]),
            ('match_results_cache', [
                'home_team', 'away_team', 'match_date', 'home_score', 'away_score',
                'cached_at', 'source'
            ]),
            ('verification_tracking', [
                'bet_id', 'last_checked_at'
            ])
        ]
        
        for table_name, columns in tables_to_migrate:
            try:
                migrate_table(sqlite_cursor, pg_cursor, table_name, columns)
            except Exception as e:
                logger.error(f"❌ Failed to migrate {table_name}: {e}")
        
        pg_conn.commit()
        
        logger.info("=" * 80)
        logger.info("✅ MIGRATION COMPLETE")
        logger.info("=" * 80)
        
        pg_cursor.execute("SELECT COUNT(*) FROM football_opportunities WHERE market = 'exact_score' AND DATE(match_date) = '2025-11-08'")
        nov8_count = pg_cursor.fetchone()[0]
        logger.info(f"📊 Verification: {nov8_count} exact score predictions from Nov 8 in PostgreSQL")
        
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        sqlite_cursor.close()
        sqlite_conn.close()
        pg_cursor.close()
        pg_conn.close()

if __name__ == "__main__":
    migrate_all()

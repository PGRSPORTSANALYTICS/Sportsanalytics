#!/usr/bin/env python3
"""
One-time migration script to import all predictions to Railway PostgreSQL.
Run this once on Railway to create tables and import data.
"""
import psycopg2
import os
import json

def import_to_railway():
    """Import all data from Replit to Railway PostgreSQL"""
    
    # Get Railway database URL from environment
    railway_db_url = os.getenv('DATABASE_URL')
    if not railway_db_url:
        print("❌ ERROR: DATABASE_URL not found in environment variables")
        return
    
    # Connect to Replit database (source)
    print("📡 Connecting to Replit database...")
    replit_conn = psycopg2.connect(
        host=os.getenv('PGHOST'),
        database=os.getenv('PGDATABASE'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        port=os.getenv('PGPORT')
    )
    
    # Connect to Railway database (destination)
    print("📡 Connecting to Railway database...")
    railway_conn = psycopg2.connect(railway_db_url)
    railway_conn.autocommit = False
    
    replit_cur = replit_conn.cursor()
    railway_cur = railway_conn.cursor()
    
    try:
        # Create tables on Railway
        print("🔨 Creating tables on Railway...")
        
        railway_cur.execute("""
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
              status TEXT,
              result TEXT,
              payout REAL,
              settled_timestamp BIGINT,
              roi_percentage REAL,
              match_date TEXT,
              kickoff_time TEXT,
              outcome TEXT,
              profit_loss REAL,
              updated_at TEXT,
              quality_score REAL,
              recommended_tier TEXT,
              recommended_date TEXT,
              daily_rank INTEGER,
              model_version TEXT,
              model_prob REAL,
              calibrated_prob REAL,
              kelly_stake REAL,
              tier TEXT,
              publish_status TEXT,
              actual_score TEXT,
              bet_category TEXT
            );
        """)
        
        railway_cur.execute("""
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
              stake REAL,
              kelly_stake REAL,
              status TEXT,
              outcome TEXT,
              result TEXT,
              payout REAL,
              profit_loss REAL,
              settled_timestamp BIGINT,
              model_version TEXT,
              simulations INTEGER,
              correlation_method TEXT,
              pricing_mode TEXT,
              pricing_metadata TEXT
            );
        """)
        
        railway_conn.commit()
        print("✅ Tables created successfully")
        
        # Import Exact Score predictions
        print("\n📊 Importing Exact Score predictions...")
        replit_cur.execute("""
            SELECT * FROM football_opportunities 
            WHERE bet_category = 'historical'
            ORDER BY id
        """)
        
        exact_score_records = replit_cur.fetchall()
        exact_score_columns = [desc[0] for desc in replit_cur.description]
        
        if exact_score_records:
            # Build INSERT statement
            placeholders = ', '.join(['%s'] * len(exact_score_columns))
            columns_str = ', '.join(exact_score_columns)
            insert_sql = f"""
                INSERT INTO football_opportunities ({columns_str})
                VALUES ({placeholders})
                ON CONFLICT DO NOTHING
            """
            
            railway_cur.executemany(insert_sql, exact_score_records)
            railway_conn.commit()
            print(f"✅ Imported {len(exact_score_records)} Exact Score predictions")
        else:
            print("⚠️ No Exact Score predictions found")
        
        # Import SGP predictions
        print("\n📊 Importing SGP predictions...")
        replit_cur.execute("""
            SELECT * FROM sgp_predictions
            ORDER BY id
        """)
        
        sgp_records = replit_cur.fetchall()
        sgp_columns = [desc[0] for desc in replit_cur.description]
        
        if sgp_records:
            # Build INSERT statement
            placeholders = ', '.join(['%s'] * len(sgp_columns))
            columns_str = ', '.join(sgp_columns)
            insert_sql = f"""
                INSERT INTO sgp_predictions ({columns_str})
                VALUES ({placeholders})
                ON CONFLICT DO NOTHING
            """
            
            railway_cur.executemany(insert_sql, sgp_records)
            railway_conn.commit()
            print(f"✅ Imported {len(sgp_records)} SGP predictions")
        else:
            print("⚠️ No SGP predictions found")
        
        # Verify import
        print("\n🔍 Verifying import...")
        railway_cur.execute("SELECT COUNT(*) FROM football_opportunities")
        exact_count = railway_cur.fetchone()[0]
        
        railway_cur.execute("SELECT COUNT(*) FROM sgp_predictions")
        sgp_count = railway_cur.fetchone()[0]
        
        print(f"\n✅ MIGRATION COMPLETE!")
        print(f"   📊 Exact Score predictions: {exact_count}")
        print(f"   📊 SGP predictions: {sgp_count}")
        print(f"   📊 Total: {exact_count + sgp_count} predictions")
        
    except Exception as e:
        railway_conn.rollback()
        print(f"\n❌ ERROR during migration: {e}")
        raise
    
    finally:
        replit_cur.close()
        railway_cur.close()
        replit_conn.close()
        railway_conn.close()

if __name__ == "__main__":
    print("🚀 Starting Railway Database Migration")
    print("=" * 50)
    import_to_railway()

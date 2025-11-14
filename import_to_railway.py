#!/usr/bin/env python3
"""
Import SQL file to Railway PostgreSQL database.
Usage: python import_to_railway.py <railway_database_url>
"""
import psycopg2
import sys

def import_sql_to_railway(database_url, sql_file='railway_complete_import.sql'):
    """Execute SQL file on Railway database"""
    
    print(f"📡 Connecting to Railway database...")
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        print(f"📄 Reading SQL file: {sql_file}")
        with open(sql_file, 'r') as f:
            sql_content = f.read()
        
        print(f"🔨 Executing SQL ({len(sql_content)} characters)...")
        cur.execute(sql_content)
        
        conn.commit()
        print("✅ SQL executed successfully")
        
        # Verify import
        print("\n🔍 Verifying import...")
        cur.execute("SELECT COUNT(*) FROM football_opportunities")
        exact_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM sgp_predictions")
        sgp_count = cur.fetchone()[0]
        
        print(f"\n✅ IMPORT COMPLETE!")
        print(f"   📊 Exact Score predictions: {exact_count}")
        print(f"   📊 SGP predictions: {sgp_count}")
        print(f"   📊 Total: {exact_count + sgp_count} predictions")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR during import: {e}")
        raise
    
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_to_railway.py <railway_database_url>")
        print("\nGet your DATABASE_URL from Railway:")
        print("  1. Go to Railway > Postgres service")
        print("  2. Click 'Variables' tab")
        print("  3. Copy DATABASE_URL value")
        sys.exit(1)
    
    database_url = sys.argv[1]
    print("🚀 Starting Railway Database Import")
    print("=" * 50)
    import_sql_to_railway(database_url)

#!/usr/bin/env python3
"""
EMERGENCY SGP DATA MIGRATION
Migrates all SGP predictions from SQLite to PostgreSQL
"""

import sqlite3
from db_helper import db_helper

def migrate_sgp_data():
    """Migrate all SGP predictions from SQLite to PostgreSQL"""
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect('data/real_football.db')
    sqlite_cursor = sqlite_conn.cursor()
    
    # Get all SGP predictions
    sqlite_cursor.execute('SELECT * FROM sgp_predictions')
    rows = sqlite_cursor.fetchall()
    
    column_names = [desc[0] for desc in sqlite_cursor.description]
    print(f"📊 Found {len(rows)} SGP predictions to migrate")
    print(f"📋 Columns: {', '.join(column_names)}")
    
    if not rows:
        print("❌ No data to migrate")
        return
    
    # Get PostgreSQL column count
    pg_cols = db_helper.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'sgp_predictions'
        ORDER BY ordinal_position
    """, fetch='all')
    pg_column_names = [col[0] for col in pg_cols]
    
    print(f"\n🔍 PostgreSQL has {len(pg_column_names)} columns")
    print(f"🔍 SQLite has {len(column_names)} columns")
    
    # Build insert query matching column order
    placeholders = ', '.join(['%s'] * len(pg_column_names))
    insert_query = f"""
        INSERT INTO sgp_predictions ({', '.join(pg_column_names)})
        VALUES ({placeholders})
        ON CONFLICT (id) DO NOTHING
    """
    
    migrated = 0
    skipped = 0
    
    for row in rows:
        try:
            # Map SQLite row to PostgreSQL columns
            values = []
            for pg_col in pg_column_names:
                try:
                    idx = column_names.index(pg_col)
                    values.append(row[idx])
                except ValueError:
                    # Column doesn't exist in SQLite, use NULL
                    values.append(None)
            
            db_helper.execute(insert_query, tuple(values))
            migrated += 1
            
            if migrated % 50 == 0:
                print(f"✅ Migrated {migrated}/{len(rows)}...")
                
        except Exception as e:
            skipped += 1
            if skipped <= 3:
                print(f"⚠️ Skipped row {row[0]}: {e}")
    
    sqlite_conn.close()
    
    print(f"\n{'='*60}")
    print(f"✅ MIGRATION COMPLETE!")
    print(f"{'='*60}")
    print(f"   Migrated: {migrated}")
    print(f"   Skipped: {skipped}")
    print(f"   Total: {len(rows)}")
    print(f"{'='*60}")
    
    # Verify
    count = db_helper.execute("SELECT COUNT(*) FROM sgp_predictions", fetch='one')[0]
    settled = db_helper.execute("SELECT COUNT(*) FROM sgp_predictions WHERE outcome IN ('win', 'loss')", fetch='one')[0]
    
    print(f"\n📊 PostgreSQL now has:")
    print(f"   Total SGPs: {count}")
    print(f"   Settled: {settled}")

if __name__ == "__main__":
    migrate_sgp_data()

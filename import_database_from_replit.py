"""
Import Replit Database Export to Railway
Run this on Railway after uploading the railway_export/ folder
"""

import psycopg2
import json
import os
from pathlib import Path

def import_database():
    """Import all JSON files to Railway PostgreSQL"""
    
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cur = conn.cursor()
    
    export_dir = "railway_export"
    
    if not os.path.exists(export_dir):
        print(f"❌ Export directory not found: {export_dir}/")
        print(f"   Upload the export folder from Replit first")
        return
    
    json_files = list(Path(export_dir).glob("*.json"))
    
    if not json_files:
        print(f"❌ No JSON files found in {export_dir}/")
        return
    
    total_imported = 0
    
    for json_file in sorted(json_files):
        table = json_file.stem  # filename without .json
        
        try:
            with open(json_file, 'r') as f:
                records = json.load(f)
            
            if not records:
                print(f"⏭️ Skipping {table} (empty)")
                continue
            
            # Get column names from first record
            columns = list(records[0].keys())
            
            # Build INSERT query
            placeholders = ', '.join(['%s'] * len(columns))
            col_names = ', '.join(columns)
            
            insert_query = f"""
                INSERT INTO {table} ({col_names})
                VALUES ({placeholders})
                ON CONFLICT DO NOTHING
            """
            
            # Insert all records
            for record in records:
                values = [record[col] for col in columns]
                cur.execute(insert_query, values)
            
            conn.commit()
            
            print(f"✅ Imported {len(records):,} records to {table}")
            total_imported += len(records)
            
        except Exception as e:
            print(f"⚠️ Could not import {table}: {e}")
            conn.rollback()
    
    cur.close()
    conn.close()
    
    print(f"\n🎉 Total imported: {total_imported:,} records")

if __name__ == "__main__":
    import_database()

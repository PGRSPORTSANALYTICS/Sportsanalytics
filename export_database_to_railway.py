"""
Export Replit Database to Railway
Run this on Replit to export all data
"""

import psycopg2
import json
import os
from datetime import datetime

def export_database():
    """Export all tables to JSON files for Railway import"""
    
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cur = conn.cursor()
    
    export_dir = "railway_export"
    os.makedirs(export_dir, exist_ok=True)
    
    tables = [
        'football_opportunities',
        'sgp_predictions',
        'telegram_subscribers',
        'api_football_cache',
        'odds_api_cache',
        'api_request_counter',
        'feature_performance',
        'learning_outcomes',
        'match_results_cache',
        'injury_cache',
        'sofascore_cache',
        'sgp_learning_outcomes',
        'sgp_calibration_params'
    ]
    
    total_exported = 0
    
    for table in tables:
        try:
            cur.execute(f"SELECT * FROM {table}")
            data = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            # Convert to list of dicts
            records = []
            for row in data:
                record = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    # Handle datetime serialization
                    if isinstance(value, datetime):
                        record[col] = value.isoformat()
                    else:
                        record[col] = value
                records.append(record)
            
            # Save to JSON
            filename = f"{export_dir}/{table}.json"
            with open(filename, 'w') as f:
                json.dump(records, f, indent=2, default=str)
            
            print(f"✅ Exported {len(records):,} records from {table}")
            total_exported += len(records)
            
        except Exception as e:
            print(f"⚠️ Could not export {table}: {e}")
    
    cur.close()
    conn.close()
    
    print(f"\n🎉 Total exported: {total_exported:,} records")
    print(f"📁 Files saved to: {export_dir}/")
    print(f"\n📤 Next: Upload {export_dir}/ folder to your Railway project")

if __name__ == "__main__":
    export_database()

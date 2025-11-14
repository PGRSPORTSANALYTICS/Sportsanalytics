"""
Export Replit database to SQL file for Railway import
This creates SQL INSERT statements that can be run directly on Railway
"""

import psycopg2
import os

def export_to_sql():
    """Export data as SQL INSERT statements"""
    
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cur = conn.cursor()
    
    output_file = "railway_import.sql"
    
    with open(output_file, 'w') as f:
        # Export football_opportunities
        cur.execute("SELECT * FROM football_opportunities")
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        
        f.write("-- Football Opportunities\n")
        for row in rows:
            values = []
            for val in row:
                if val is None:
                    values.append("NULL")
                elif isinstance(val, str):
                    values.append(f"'{val.replace(chr(39), chr(39)+chr(39))}'")
                else:
                    values.append(str(val))
            
            f.write(f"INSERT INTO football_opportunities ({', '.join(columns)}) VALUES ({', '.join(values)}) ON CONFLICT DO NOTHING;\n")
        
        print(f"✅ Exported {len(rows)} football_opportunities")
        
        # Export sgp_predictions
        cur.execute("SELECT * FROM sgp_predictions")
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        
        f.write("\n-- SGP Predictions\n")
        for row in rows:
            values = []
            for val in row:
                if val is None:
                    values.append("NULL")
                elif isinstance(val, str):
                    values.append(f"'{val.replace(chr(39), chr(39)+chr(39))}'")
                else:
                    values.append(str(val))
            
            f.write(f"INSERT INTO sgp_predictions ({', '.join(columns)}) VALUES ({', '.join(values)}) ON CONFLICT DO NOTHING;\n")
        
        print(f"✅ Exported {len(rows)} sgp_predictions")
    
    cur.close()
    conn.close()
    
    print(f"\n📁 SQL file created: {output_file}")
    print(f"📤 Next: Copy this file and run it on Railway PostgreSQL")
    print(f"\nTo import on Railway:")
    print(f"1. Download {output_file}")
    print(f"2. In Railway, click PostgreSQL service → Query tab")
    print(f"3. Paste the SQL and execute")

if __name__ == "__main__":
    export_to_sql()

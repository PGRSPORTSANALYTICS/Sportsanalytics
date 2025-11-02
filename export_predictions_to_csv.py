#!/usr/bin/env python3
"""
Export Predictions to CSV
Creates a CSV file with all unsettled predictions for easy result entry
"""

import sqlite3
import csv
from datetime import datetime

def export_predictions():
    """Export all unsettled predictions to CSV"""
    
    conn = sqlite3.connect('data/real_football.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT home_team, away_team, DATE(match_date) as date, selection
        FROM football_opportunities
        WHERE status != 'settled'
        AND DATE(match_date) < DATE('now')
        ORDER BY match_date
    ''')
    
    predictions = cursor.fetchall()
    
    filename = f'predictions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['home_team', 'away_team', 'date', 'predicted_score', 'actual_score'])
        
        for home, away, date, selection in predictions:
            predicted = selection.split(':')[-1].strip() if ':' in selection else ''
            writer.writerow([home, away, date, predicted, ''])  # actual_score left empty for user
    
    conn.close()
    
    print(f"✅ Exported {len(predictions)} predictions to: {filename}")
    print(f"\n📝 Next steps:")
    print(f"   1. Open {filename} in Excel/Google Sheets")
    print(f"   2. Fill in the 'actual_score' column (e.g., 2-0, 1-1, 3-1)")
    print(f"   3. Save the file")
    print(f"   4. Run: python3 bulk_results_import.py {filename}")
    
    return filename

if __name__ == "__main__":
    export_predictions()

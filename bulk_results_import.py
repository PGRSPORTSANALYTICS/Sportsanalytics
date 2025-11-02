#!/usr/bin/env python3
"""
Bulk Results Import Tool
Upload CSV with actual scores to update all predictions at once
"""

import sqlite3
import csv
import time
from datetime import datetime

def import_results_from_csv(csv_file):
    """
    Import actual results from CSV file
    
    CSV Format:
    home_team,away_team,date,actual_score
    Manchester City,Napoli,2024-09-18,2-0
    Brighton,Tottenham,2024-09-20,2-2
    """
    
    conn = sqlite3.connect('data/real_football.db')
    cursor = conn.cursor()
    
    updated = 0
    not_found = []
    
    print("📋 BULK RESULTS IMPORT")
    print("=" * 60)
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            home_team = row['home_team'].strip()
            away_team = row['away_team'].strip()
            date_str = row['date'].strip()
            actual_score = row['actual_score'].strip()
            
            # Find matching prediction
            cursor.execute('''
                SELECT id, selection, odds, stake
                FROM football_opportunities
                WHERE home_team LIKE ?
                AND away_team LIKE ?
                AND DATE(match_date) = ?
                AND status != 'settled'
            ''', (f'%{home_team}%', f'%{away_team}%', date_str))
            
            match = cursor.fetchone()
            
            if match:
                bet_id, selection, odds, stake = match
                predicted_score = selection.split(':')[-1].strip()
                
                # Determine outcome
                if actual_score == predicted_score:
                    outcome = 'win'
                    payout = stake * odds
                    profit_loss = payout - stake
                    status_icon = '✅ WIN'
                else:
                    outcome = 'loss'
                    payout = 0
                    profit_loss = -stake
                    status_icon = '❌ LOSS'
                
                # Calculate ROI
                roi_percentage = (profit_loss / stake) * 100 if stake > 0 else 0
                settled_ts = int(time.time())
                
                # Update database
                cursor.execute('''
                    UPDATE football_opportunities
                    SET 
                        actual_score = ?,
                        outcome = ?,
                        result = ?,
                        status = 'settled',
                        payout = ?,
                        profit_loss = ?,
                        roi_percentage = ?,
                        settled_timestamp = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                ''', (actual_score, outcome, actual_score, payout, profit_loss, 
                      roi_percentage, settled_ts, bet_id))
                
                print(f"{status_icon} {home_team} vs {away_team}: {predicted_score} → {actual_score}")
                updated += 1
            else:
                not_found.append(f"{home_team} vs {away_team} ({date_str})")
    
    conn.commit()
    conn.close()
    
    print("=" * 60)
    print(f"\n✅ IMPORT COMPLETE!")
    print(f"   Updated: {updated} bets")
    
    if not_found:
        print(f"\n⚠️  Not Found: {len(not_found)} matches")
        for match in not_found[:5]:
            print(f"   - {match}")
        if len(not_found) > 5:
            print(f"   ... and {len(not_found) - 5} more")
    
    # Show final stats
    conn = sqlite3.connect('data/real_football.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM football_opportunities WHERE status = "settled"')
    settled_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM football_opportunities WHERE outcome = "win"')
    wins = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(profit_loss) FROM football_opportunities WHERE status = "settled"')
    total_pl = cursor.fetchone()[0] or 0
    
    if settled_count > 0:
        hit_rate = (wins / settled_count) * 100
        print(f"\n📊 DASHBOARD STATS:")
        print(f"   Settled: {settled_count}")
        print(f"   Wins: {wins}")
        print(f"   Hit Rate: {hit_rate:.1f}%")
        print(f"   Total P&L: {total_pl:+.0f} SEK")
    
    conn.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 bulk_results_import.py results.csv")
        print("\nCSV Format:")
        print("home_team,away_team,date,actual_score")
        print("Manchester City,Napoli,2024-09-18,2-0")
        print("Brighton,Tottenham,2024-09-20,2-2")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    import_results_from_csv(csv_file)

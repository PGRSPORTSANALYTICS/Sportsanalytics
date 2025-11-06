#!/usr/bin/env python3
"""
Quick tool to manually update match results when scraping is delayed.
Usage: python3 manual_result_updater.py

Example: Enter results like "Red Star Belgrade vs Lille 1-0"
"""

import sqlite3
import sys
from datetime import datetime

def update_result(match_desc, score):
    """Update a single match result"""
    try:
        teams = match_desc.split(' vs ')
        if len(teams) != 2:
            print(f"❌ Invalid format. Use: Team1 vs Team2")
            return False
        
        home = teams[0].strip()
        away = teams[1].strip()
        
        conn = sqlite3.connect('data/real_football.db')
        cursor = conn.cursor()
        
        # Find pending prediction
        cursor.execute('''
            SELECT id, selection, stake, odds FROM football_opportunities
            WHERE (home_team LIKE ? OR home_team LIKE ?)
            AND (away_team LIKE ? OR away_team LIKE ?)
            AND market = 'exact_score'
            AND result IS NULL
            LIMIT 1
        ''', (f'%{home}%', f'%{home.split()[0]}%', f'%{away}%', f'%{away.split()[0]}%'))
        
        bet = cursor.fetchone()
        if not bet:
            print(f"❌ No pending prediction found for {home} vs {away}")
            conn.close()
            return False
        
        bet_id, predicted_score, stake, odds = bet
        
        # Extract predicted score
        pred = predicted_score.replace('Exact Score: ', '').strip()
        
        # Check if win
        is_win = pred == score
        payout = stake * odds if is_win else 0
        
        # Update database
        cursor.execute('''
            UPDATE football_opportunities 
            SET result = ?, payout = ?
            WHERE id = ?
        ''', (score, payout, bet_id))
        
        conn.commit()
        conn.close()
        
        status = '✅ WIN' if is_win else '❌ LOSS'
        profit = payout - stake if is_win else -stake
        print(f'{status} | {home} vs {away}: {score} (predicted {pred}) | {profit:+.0f} SEK')
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("📊 MANUAL RESULT UPDATER")
    print("=" * 60)
    print("Enter results in format: Team1 vs Team2 Score")
    print("Example: Red Star Belgrade vs Lille 1-0")
    print("Type 'done' when finished")
    print("=" * 60)
    
    updated = 0
    
    while True:
        try:
            line = input("\nEnter result (or 'done'): ").strip()
            
            if line.lower() in ['done', 'exit', 'quit', '']:
                break
            
            # Parse input: "Team1 vs Team2 Score"
            parts = line.rsplit(' ', 1)
            if len(parts) != 2:
                print("❌ Format: Team1 vs Team2 1-0")
                continue
            
            match_desc = parts[0].strip()
            score = parts[1].strip()
            
            if update_result(match_desc, score):
                updated += 1
                
        except KeyboardInterrupt:
            print("\n\nStopped by user")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print(f"\n✅ Updated {updated} results")
    print("Dashboard will show updates on next refresh!")

if __name__ == '__main__':
    main()

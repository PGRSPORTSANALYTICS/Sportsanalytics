"""Quick verification to populate actual scores"""
import sqlite3
from datetime import datetime
from results_scraper import ResultsScraper

conn = sqlite3.connect('data/real_football.db')
cursor = conn.cursor()
scraper = ResultsScraper()

# Get recent matches that need verification
cursor.execute('''
    SELECT home_team, away_team, match_date, selection
    FROM football_opportunities
    WHERE outcome IS NULL 
    AND match_date < '2025-10-31'
    ORDER BY match_date DESC
    LIMIT 20
''')

pending = cursor.fetchall()
print(f"Found {len(pending)} matches to verify")

for home, away, date, selection in pending:
    try:
        date_str = date.split('T')[0]
        print(f"\nChecking {home} vs {away} on {date_str}")
        
        results = scraper.get_results_for_date(date_str)
        
        for result in results:
            if result['home_team'] == home and result['away_team'] == away:
                actual_score = result['score']
                predicted_score = selection.split(':')[-1].strip()
                
                outcome = 'won' if actual_score == predicted_score else 'lost'
                
                cursor.execute('''
                    UPDATE football_opportunities
                    SET outcome = ?, actual_score = ?
                    WHERE home_team = ? AND away_team = ? AND match_date = ?
                ''', (outcome, actual_score, home, away, date))
                
                print(f"✅ {home} vs {away} = {actual_score} ({outcome})")
                break
                
    except Exception as e:
        print(f"❌ Error: {e}")

conn.commit()
conn.close()
print("\n✅ Verification complete!")

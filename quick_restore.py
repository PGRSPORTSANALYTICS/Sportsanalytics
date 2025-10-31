"""Quick restoration of all old settled predictions"""
import sqlite3
from datetime import datetime
from results_scraper import ResultsScraper
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

conn = sqlite3.connect('data/real_football.db')
cursor = conn.cursor()
scraper = ResultsScraper()

# Get old unverified predictions (before Oct 31)
cursor.execute('''
    SELECT home_team, away_team, match_date, selection
    FROM football_opportunities
    WHERE match_date < '2025-10-31'
    AND (outcome IS NULL OR outcome = '')
    ORDER BY match_date DESC
''')

pending = cursor.fetchall()
print(f"🔄 Restoring {len(pending)} old predictions...")

verified = 0
for home, away, date, selection in pending:
    try:
        date_str = date.split('T')[0]
        results = scraper.get_results_for_date(date_str)
        
        for result in results:
            if result.get('home_team') == home and result.get('away_team') == away:
                actual_score = result.get('final_score', '')
                if not actual_score:
                    continue
                    
                predicted_score = selection.split(':')[-1].strip()
                outcome = 'won' if actual_score == predicted_score else 'lost'
                
                cursor.execute('''
                    UPDATE football_opportunities
                    SET outcome = ?, actual_score = ?
                    WHERE home_team = ? AND away_team = ? AND match_date = ?
                ''', (outcome, actual_score, home, away, date))
                
                verified += 1
                if verified % 10 == 0:
                    print(f"✅ Restored {verified}/{len(pending)}...")
                break
                
    except Exception as e:
        pass

conn.commit()
conn.close()
print(f"\n✅ Restored {verified} predictions!")
print(f"⏳ {len(pending) - verified} still need verification")

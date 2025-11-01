"""
FIX MATCH DATES - One-time data repair
Sets match_date to the actual bet placement date for all pending bets
"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/real_football.db')
cursor = conn.cursor()

print("🔧 FIXING MATCH DATES FOR PENDING BETS")
print("="*60)

# Get all bets that need fixing (status != 'settled')
cursor.execute('''
    SELECT id, timestamp, match_date, home_team, away_team
    FROM football_opportunities
    WHERE status != 'settled'
    AND market = 'exact_score'
''')

bets = cursor.fetchall()
print(f"📊 Found {len(bets)} bets to fix")

fixed_count = 0
for bet_id, timestamp, old_match_date, home, away in bets:
    # Convert timestamp to date
    dt = datetime.fromtimestamp(timestamp)
    correct_date = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Update to correct date
    cursor.execute('''
        UPDATE football_opportunities
        SET match_date = ?,
            kickoff_time = ?
        WHERE id = ?
    ''', (correct_date, dt.strftime('%H:%M'), bet_id))
    
    fixed_count += 1
    if fixed_count <= 10:
        print(f"✅ Fixed: {home} vs {away}")
        print(f"   Old date: {old_match_date}")
        print(f"   New date: {correct_date}")

conn.commit()
print(f"\n🎯 Fixed {fixed_count} match dates")
print("✅ Data repair complete!")
conn.close()

"""
One-time script to verify all historical pending bets
"""
import sqlite3
from datetime import datetime, timedelta
from results_scraper import get_match_result
import time

conn = sqlite3.connect('data/real_football.db')
cursor = conn.cursor()

print("🔍 VERIFYING HISTORICAL PENDING BETS")
print("="*60)

# Get all pending bets from the past (before today)
today = datetime.now().date()

cursor.execute('''
    SELECT id, home_team, away_team, selection, odds, stake, match_date
    FROM football_opportunities
    WHERE bet_category = 'historical'
    AND status = 'pending'
    ORDER BY match_date DESC
''')

bets = cursor.fetchall()
print(f"📊 Found {len(bets)} historical pending bets\n")

settled = 0
not_found = 0

for bet_id, home, away, selection, odds, stake, match_date_str in bets:
    # Parse match date
    try:
        if 'T' in match_date_str:
            match_dt = datetime.fromisoformat(match_date_str.replace('Z', '+00:00'))
        else:
            match_dt = datetime.fromtimestamp(int(match_date_str))
        match_date = match_dt.strftime('%Y-%m-%d')
    except:
        print(f"⚠️ Bad date format for {home} vs {away}, skipping")
        continue
    
    # Get result
    result = get_match_result(home, away, match_date)
    
    if result:
        # Extract predicted score from selection
        predicted_score = selection.replace('Exact Score: ', '').replace('Exact Score ', '').strip()
        
        # Check if prediction matches
        if result == predicted_score:
            outcome = 'won'
            payout = stake * odds
            profit_loss = payout - stake
            print(f"✅ WIN: {home} vs {away} - {predicted_score} (Result: {result})")
        else:
            outcome = 'lost'
            payout = 0
            profit_loss = -stake
            print(f"❌ LOSS: {home} vs {away} - Predicted {predicted_score}, Got {result}")
        
        # Update bet with result
        cursor.execute('''
            UPDATE football_opportunities
            SET 
                status = 'settled',
                outcome = ?,
                result = ?,
                payout = ?,
                profit_loss = ?,
                roi_percentage = ?,
                settled_timestamp = ?
            WHERE id = ?
        ''', (
            outcome,
            result,
            payout,
            profit_loss,
            (profit_loss / stake * 100) if stake > 0 else 0,
            int(time.time()),
            bet_id
        ))
        settled += 1
    else:
        not_found += 1
        if not_found <= 5:
            print(f"⚠️ No result found: {home} vs {away} on {match_date}")

conn.commit()
print(f"\n✅ Settled: {settled}")
print(f"⚠️ Not found: {not_found}")
print(f"📊 Total processed: {len(bets)}")

conn.close()

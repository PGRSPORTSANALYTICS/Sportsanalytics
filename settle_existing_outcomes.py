"""
DIRECT SETTLEMENT - Fix all bets that have outcomes but wrong status
Calculates proper P&L, payout, and sets status='settled'
"""
import sqlite3
import time

conn = sqlite3.connect('data/real_football.db')
cursor = conn.cursor()

print("🔧 SETTLING BETS WITH EXISTING OUTCOMES")
print("="*60)

# Get all bets with outcomes but not properly settled
cursor.execute('''
    SELECT id, outcome, odds, stake
    FROM football_opportunities
    WHERE outcome IS NOT NULL 
    AND outcome != ''
    AND status != 'settled'
    AND market = 'exact_score'
''')

bets = cursor.fetchall()
print(f"📊 Found {len(bets)} bets to settle properly\n")

settled_count = 0
wins = 0
losses = 0
total_pnl = 0

for bet_id, outcome, odds, stake in bets:
    # Calculate P&L based on outcome
    if outcome in ('won', 'win'):
        payout = stake * odds
        profit_loss = payout - stake
        wins += 1
    else:  # lost, loss
        payout = 0
        profit_loss = -stake
        losses += 1
    
    total_pnl += profit_loss
    roi_percentage = (profit_loss / stake) * 100 if stake > 0 else 0
    settled_ts = int(time.time())
    
    # Properly settle the bet
    cursor.execute('''
        UPDATE football_opportunities
        SET 
            status = 'settled',
            payout = ?,
            profit_loss = ?,
            roi_percentage = ?,
            settled_timestamp = ?,
            updated_at = datetime('now')
        WHERE id = ?
    ''', (payout, profit_loss, roi_percentage, settled_ts, bet_id))
    
    settled_count += 1

conn.commit()

print(f"✅ Settled {settled_count} bets:")
print(f"   🎯 Wins: {wins}")
print(f"   ❌ Losses: {losses}")
print(f"   💰 Total P&L: {total_pnl:+.0f} SEK")
print(f"   📊 Hit Rate: {(wins/settled_count*100):.2f}%")
print("\n🎉 All historical bets now properly settled!")

conn.close()

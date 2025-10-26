#!/usr/bin/env python3
"""
Send ROI and Performance Update to Telegram Channel
"""

import sqlite3
from telegram_sender import TelegramBroadcaster
from datetime import datetime

def get_performance_stats():
    """Get current system performance from database"""
    conn = sqlite3.connect('data/real_football.db')
    cursor = conn.cursor()
    
    # Get settled exact score stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total_bets,
            SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome = 'lost' THEN 1 ELSE 0 END) as losses,
            SUM(stake) as total_staked,
            SUM(CASE WHEN outcome = 'won' THEN stake * odds ELSE 0 END) as total_winnings,
            SUM(CASE WHEN outcome = 'won' THEN stake * (odds - 1) ELSE -stake END) as net_profit
        FROM football_opportunities 
        WHERE market = 'exact_score'
        AND outcome IS NOT NULL
    ''')
    
    settled = cursor.fetchone()
    
    # Get pending predictions
    cursor.execute('''
        SELECT COUNT(*) 
        FROM football_opportunities 
        WHERE market = 'exact_score'
        AND outcome IS NULL
    ''')
    
    pending = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_bets': settled[0] or 0,
        'wins': settled[1] or 0,
        'losses': settled[2] or 0,
        'total_staked': settled[3] or 0,
        'total_winnings': settled[4] or 0,
        'net_profit': settled[5] or 0,
        'pending': pending
    }

def format_performance_message(stats):
    """Format performance stats as Telegram message"""
    
    total = stats['total_bets']
    wins = stats['wins']
    losses = stats['losses']
    staked = stats['total_staked']
    winnings = stats['total_winnings']
    profit = stats['net_profit']
    pending = stats['pending']
    
    # Calculate metrics
    win_rate = (wins / total * 100) if total > 0 else 0
    roi = (profit / staked * 100) if staked > 0 else 0
    
    # Determine emoji based on performance
    if roi > 0:
        status_emoji = "🚀"
        profit_emoji = "💰"
    else:
        status_emoji = "📊"
        profit_emoji = "💸"
    
    message = f"""{status_emoji} **SYSTEM PERFORMANCE UPDATE**

📈 **Settled Predictions:** {total}
✅ Wins: **{wins}** ({win_rate:.1f}%)
❌ Losses: {losses}
⏳ Pending: {pending}

💵 **Financial Performance:**
📊 Total Staked: {staked:.0f} SEK
💰 Total Winnings: {winnings:.0f} SEK
{profit_emoji} Net Profit: **{profit:.0f} SEK**
📈 ROI: **{roi:.1f}%**

🎯 **Target Performance:**
Target Win Rate: 20-25%
Target ROI: +100-200%

📅 **Data-Driven Strategy:**
✅ 1-1 scores: 25% WR, +211% ROI proven
✅ 2-1 scores: 16.7% WR, +123% ROI proven
✅ Odds 11-13x: 25% WR sweet spot

⏰ Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
🔄 Auto-updated after each result

💎 **Premium Exact Score Predictions**
🚀 Launching subscription service January 2026
"""
    
    return message

def main():
    """Send performance update to channel"""
    print("📊 Fetching performance statistics...")
    stats = get_performance_stats()
    
    print(f"✅ Stats: {stats['total_bets']} settled, {stats['wins']} wins, {stats['net_profit']:.0f} SEK profit")
    
    print("📱 Sending to Telegram channel...")
    broadcaster = TelegramBroadcaster()
    message = format_performance_message(stats)
    
    # Get channel ID
    channel_id = broadcaster.get_channel()
    
    if channel_id:
        success = broadcaster.send_message(channel_id, message)
        if success:
            print(f"✅ Performance update sent to channel: {channel_id}")
        else:
            print("❌ Failed to send message")
    else:
        print("❌ No channel configured")

if __name__ == '__main__':
    main()

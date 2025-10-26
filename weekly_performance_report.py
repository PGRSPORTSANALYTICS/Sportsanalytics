#!/usr/bin/env python3
"""
Weekly Performance Report for Telegram Channel
Sends detailed weekly stats every Sunday
"""

import sqlite3
from telegram_sender import TelegramBroadcaster
from datetime import datetime, timedelta

def get_weekly_stats():
    """Get last 7 days performance"""
    conn = sqlite3.connect('data/real_football.db')
    cursor = conn.cursor()
    
    week_ago = int((datetime.now() - timedelta(days=7)).timestamp())
    
    # Weekly stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total_bets,
            SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END) as wins,
            SUM(stake) as total_staked,
            SUM(CASE WHEN outcome = 'won' THEN stake * (odds - 1) ELSE -stake END) as net_profit
        FROM football_opportunities 
        WHERE market = 'exact_score'
        AND outcome IS NOT NULL
        AND timestamp >= ?
    ''', (week_ago,))
    
    weekly = cursor.fetchone()
    
    # All-time stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total_bets,
            SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END) as wins,
            SUM(stake) as total_staked,
            SUM(CASE WHEN outcome = 'won' THEN stake * (odds - 1) ELSE -stake END) as net_profit
        FROM football_opportunities 
        WHERE market = 'exact_score'
        AND outcome IS NOT NULL
    ''')
    
    alltime = cursor.fetchone()
    
    # Score breakdown
    cursor.execute('''
        SELECT 
            selection,
            COUNT(*) as count,
            SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END) as wins,
            SUM(stake) as staked,
            SUM(CASE WHEN outcome = 'won' THEN stake * (odds - 1) ELSE -stake END) as profit
        FROM football_opportunities 
        WHERE market = 'exact_score'
        AND outcome IS NOT NULL
        GROUP BY selection
        ORDER BY wins DESC
        LIMIT 5
    ''')
    
    top_scores = cursor.fetchall()
    
    conn.close()
    
    return {
        'weekly': {
            'total': weekly[0] or 0,
            'wins': weekly[1] or 0,
            'staked': weekly[2] or 0,
            'profit': weekly[3] or 0
        },
        'alltime': {
            'total': alltime[0] or 0,
            'wins': alltime[1] or 0,
            'staked': alltime[2] or 0,
            'profit': alltime[3] or 0
        },
        'top_scores': top_scores
    }

def format_weekly_report(stats):
    """Format weekly performance report"""
    
    weekly = stats['weekly']
    alltime = stats['alltime']
    
    # Calculate metrics
    weekly_wr = (weekly['wins'] / weekly['total'] * 100) if weekly['total'] > 0 else 0
    weekly_roi = (weekly['profit'] / weekly['staked'] * 100) if weekly['staked'] > 0 else 0
    
    alltime_wr = (alltime['wins'] / alltime['total'] * 100) if alltime['total'] > 0 else 0
    alltime_roi = (alltime['profit'] / alltime['staked'] * 100) if alltime['staked'] > 0 else 0
    
    # Top scores section
    top_scores_text = ""
    for score_data in stats['top_scores'][:3]:
        score = score_data[0].replace('Exact Score: ', '')
        count = score_data[1]
        wins = score_data[2]
        wr = (wins / count * 100) if count > 0 else 0
        top_scores_text += f"• {score}: {wins}/{count} ({wr:.1f}%)\n"
    
    message = f"""📊 **WEEKLY PERFORMANCE REPORT**
📅 Week: {(datetime.now() - timedelta(days=7)).strftime('%b %d')} - {datetime.now().strftime('%b %d, %Y')}

🗓️ **THIS WEEK:**
📈 Predictions: {weekly['total']}
✅ Wins: **{weekly['wins']}** ({weekly_wr:.1f}%)
💰 Profit: **{weekly['profit']:.0f} SEK** ({weekly_roi:.1f}% ROI)

📊 **ALL-TIME PERFORMANCE:**
📈 Total Predictions: {alltime['total']}
✅ Total Wins: **{alltime['wins']}** ({alltime_wr:.1f}%)
💵 Total Staked: {alltime['staked']:.0f} SEK
💰 Total Profit: **{alltime['profit']:.0f} SEK**
📈 Overall ROI: **{alltime_roi:.1f}%**

🏆 **TOP PERFORMING SCORES:**
{top_scores_text}
🎯 **DATA-PROVEN STRATEGY:**
✅ 1-1 scores: 25% WR target
✅ 2-1 scores: 16.7% WR target
✅ Odds 11-13x: Sweet spot

📅 **ROADMAP:**
• December 2025: 300-500 predictions
• January 2026: Launch subscription (499 SEK/month)
• Target: 20-25% win rate, +100-200% ROI

💎 **Premium Exact Score Predictions**
🚀 Building proven track record for subscribers
"""
    
    return message

def main():
    """Send weekly performance report to channel"""
    print("📊 Generating weekly performance report...")
    stats = get_weekly_stats()
    
    print(f"✅ This week: {stats['weekly']['total']} predictions, {stats['weekly']['wins']} wins")
    print(f"✅ All-time: {stats['alltime']['total']} predictions, {stats['alltime']['wins']} wins")
    
    print("📱 Sending to Telegram channel...")
    broadcaster = TelegramBroadcaster()
    message = format_weekly_report(stats)
    
    # Get channel ID
    channel_id = broadcaster.get_channel()
    
    if channel_id:
        success = broadcaster.send_message(channel_id, message)
        if success:
            print(f"✅ Weekly report sent to channel: {channel_id}")
        else:
            print("❌ Failed to send message")
    else:
        print("❌ No channel configured")

if __name__ == '__main__':
    main()

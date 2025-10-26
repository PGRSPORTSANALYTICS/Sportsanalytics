#!/usr/bin/env python3
"""
Automated Weekly and Monthly Performance Updates for Telegram
Sends ROI and hit rate updates to subscribers
"""

import os
import sqlite3
import requests
from datetime import datetime, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DB_PATH = 'data/real_football.db'

def get_channel_id():
    """Get the Telegram channel ID from database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT chat_id FROM telegram_subscribers WHERE is_channel = 1 LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Failed to get channel ID: {e}")
        return None


def get_performance_stats(start_date, end_date, period_name):
    """Calculate performance stats for a date range"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total_bets,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(profit_loss) as net_profit,
            SUM(stake) as total_staked
        FROM football_opportunities
        WHERE market = 'exact_score'
        AND outcome IS NOT NULL
        AND outcome != ''
        AND datetime(kickoff_time) BETWEEN datetime(?) AND datetime(?)
    """, (start_date, end_date))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0] > 0:
        total_bets, wins, losses, net_profit, total_staked = result
        wins = wins or 0
        losses = losses or 0
        net_profit = net_profit or 0
        total_staked = total_staked or 0
        
        hit_rate = (wins / total_bets * 100) if total_bets > 0 else 0
        roi = (net_profit / total_staked * 100) if total_staked > 0 else 0
        
        return {
            'period': period_name,
            'total_bets': total_bets,
            'wins': wins,
            'losses': losses,
            'hit_rate': hit_rate,
            'net_profit': net_profit,
            'total_staked': total_staked,
            'roi': roi
        }
    
    return None


def format_performance_message(stats, update_type):
    """Format the performance stats into a Telegram message"""
    if not stats:
        return None
    
    emoji_map = {
        'weekly': '📅',
        'monthly': '📊'
    }
    
    emoji = emoji_map.get(update_type, '📈')
    
    message = f"{emoji} *{update_type.upper()} PERFORMANCE UPDATE*\n"
    message += f"Period: {stats['period']}\n"
    message += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    message += f"📊 *STATISTICS*\n"
    message += f"• Total Predictions: {stats['total_bets']}\n"
    message += f"• Wins: {stats['wins']} ✅\n"
    message += f"• Losses: {stats['losses']} ❌\n"
    message += f"• Hit Rate: *{stats['hit_rate']:.1f}%*\n\n"
    
    message += f"💰 *FINANCIAL*\n"
    message += f"• Total Staked: {stats['total_staked']:.0f} SEK\n"
    
    if stats['net_profit'] >= 0:
        message += f"• Net Profit: *+{stats['net_profit']:.0f} SEK* 📈\n"
    else:
        message += f"• Net Profit: *{stats['net_profit']:.0f} SEK* 📉\n"
    
    message += f"• ROI: *{stats['roi']:+.1f}%*\n\n"
    
    if stats['hit_rate'] >= 20:
        message += "🔥 *ELITE PERFORMANCE!* Target hit rate achieved!\n"
    elif stats['hit_rate'] >= 15:
        message += "💪 *STRONG PERFORMANCE!* Above industry standard!\n"
    elif stats['hit_rate'] >= 10:
        message += "✅ *SOLID PERFORMANCE* Within expected range.\n"
    else:
        message += "⚠️ *BELOW TARGET* - Variance expected, tracking continues.\n"
    
    message += "\n━━━━━━━━━━━━━━━━━━━━\n"
    message += "📈 Transparency is our priority. Every result tracked & verified.\n"
    
    return message


def send_telegram_message(text):
    """Send message via Telegram API"""
    try:
        channel_id = get_channel_id()
        if not channel_id:
            print("❌ No Telegram channel configured")
            return False
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': channel_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"❌ Telegram API Error: {response.text}")
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")
        return False


def send_weekly_update():
    """Send weekly performance update (last 7 days)"""
    end_date = datetime.now().isoformat()
    start_date = (datetime.now() - timedelta(days=7)).isoformat()
    
    week_start = (datetime.now() - timedelta(days=7)).strftime('%b %d')
    week_end = datetime.now().strftime('%b %d, %Y')
    period_name = f"{week_start} - {week_end}"
    
    stats = get_performance_stats(start_date, end_date, period_name)
    
    if stats:
        message = format_performance_message(stats, 'weekly')
        
        if message and send_telegram_message(message):
            print(f"✅ Weekly update sent: {stats['total_bets']} bets, {stats['hit_rate']:.1f}% hit rate, {stats['roi']:+.1f}% ROI")
        else:
            print("❌ Failed to send weekly update")
    else:
        print("⚠️ No settled bets in the last 7 days, skipping weekly update")


def send_monthly_update():
    """Send monthly performance update (current month)"""
    now = datetime.now()
    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_date = now.isoformat()
    
    period_name = now.strftime('%B %Y')
    
    stats = get_performance_stats(start_date, end_date, period_name)
    
    if stats:
        message = format_performance_message(stats, 'monthly')
        
        if message and send_telegram_message(message):
            print(f"✅ Monthly update sent: {stats['total_bets']} bets, {stats['hit_rate']:.1f}% hit rate, {stats['roi']:+.1f}% ROI")
        else:
            print("❌ Failed to send monthly update")
    else:
        print("⚠️ No settled bets this month, skipping monthly update")


def send_all_time_update():
    """Send all-time performance update"""
    stats = get_performance_stats('2020-01-01', datetime.now().isoformat(), 'All Time')
    
    if stats:
        message = format_performance_message(stats, 'all-time')
        
        if message and send_telegram_message(message):
            print(f"✅ All-time update sent: {stats['total_bets']} bets, {stats['hit_rate']:.1f}% hit rate, {stats['roi']:+.1f}% ROI")
        else:
            print("❌ Failed to send all-time update")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        update_type = sys.argv[1]
        
        if update_type == 'weekly':
            send_weekly_update()
        elif update_type == 'monthly':
            send_monthly_update()
        elif update_type == 'all-time':
            send_all_time_update()
        else:
            print("Usage: python telegram_performance_updates.py [weekly|monthly|all-time]")
    else:
        print("Usage: python telegram_performance_updates.py [weekly|monthly|all-time]")

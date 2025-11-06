#!/usr/bin/env python3
"""
Daily Results Summary for Telegram
===================================
Sends end-of-day results summary showing all settled exact score predictions.

Features:
- Runs after all matches verified
- Shows wins (green) and losses (red)
- Daily stats (hit rate, profit)
- Broadcasts to all subscribers
"""

import sqlite3
import logging
from datetime import date, datetime
from telegram_sender import TelegramBroadcaster
from stats_master import get_todays_exact_score_stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = 'data/real_football.db'

def get_todays_results():
    """Get all exact score predictions that settled today"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get today's date
        today = date.today().isoformat()
        
        cursor.execute('''
            SELECT 
                home_team,
                away_team,
                selection,
                odds,
                actual_score,
                outcome,
                profit_loss,
                league
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND result IS NOT NULL
            AND date(settled_timestamp, 'unixepoch') = ?
            ORDER BY settled_timestamp DESC
        ''', (today,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'home_team': row[0],
                'away_team': row[1],
                'selection': row[2],
                'odds': row[3],
                'actual_score': row[4],
                'outcome': row[5],
                'profit': row[6],
                'league': row[7]
            })
        
        conn.close()
        return results
        
    except Exception as e:
        logger.error(f"❌ Error getting today's results: {e}")
        return []

def get_daily_stats(results):
    """Calculate daily statistics - BULLETPROOF VERSION"""
    if not results:
        return None
    
    # Use bulletproof stats module for accuracy
    stats = get_todays_exact_score_stats()
    
    return {
        'total': stats['total'],
        'wins': stats['wins'],
        'losses': stats['losses'],
        'hit_rate': stats['hit_rate'],
        'profit': stats['profit']
    }

def send_results_summary():
    """Send end-of-day results summary"""
    logger.info("📊 Running daily results summary...")
    
    results = get_todays_results()
    
    if not results:
        logger.info("⏳ No results settled today")
        return
    
    stats = get_daily_stats(results)
    
    # Format message
    today_str = date.today().strftime('%A, %B %d, %Y')
    message = f"🌙 **END OF DAY RESULTS**\n"
    message += f"📅 {today_str}\n\n"
    
    # Overall stats
    profit_emoji = "📈" if stats['profit'] >= 0 else "📉"
    message += f"📊 **DAILY STATS**\n"
    message += f"⚽ Predictions Settled: {stats['total']}\n"
    message += f"✅ Wins: {stats['wins']}\n"
    message += f"❌ Losses: {stats['losses']}\n"
    message += f"🎯 Hit Rate: {stats['hit_rate']:.1f}%\n"
    message += f"{profit_emoji} Profit: {stats['profit']:+.0f} SEK\n\n"
    message += "=" * 40 + "\n\n"
    
    # Individual results
    message += f"📋 **ALL PREDICTIONS**\n\n"
    
    for i, result in enumerate(results, 1):
        # Win/Loss indicator
        if result['outcome'] == 'win':
            status = "🟢 WIN"
        else:
            status = "🔴 LOSS"
        
        # Extract predicted score from selection
        predicted = result['selection'].replace('Exact Score: ', '')
        
        message += f"{status} **{result['home_team']} vs {result['away_team']}**\n"
        message += f"   🎯 Predicted: {predicted} @{result['odds']:.2f}x\n"
        message += f"   ⚽ Result: {result['actual_score']}\n"
        message += f"   💰 P/L: {result['profit']:+.0f} SEK\n"
        message += f"   🏆 {result['league']}\n\n"
    
    message += "=" * 40 + "\n"
    
    # Closing message
    if stats['hit_rate'] >= 15:
        message += "🔥 **Great performance today!**\n"
    elif stats['profit'] > 0:
        message += "💪 **Profitable day!**\n"
    else:
        message += "📊 **Results logged. On to tomorrow!**\n"
    
    message += "😴 Rest up for tomorrow's predictions!\n"
    
    # Broadcast to subscribers
    try:
        broadcaster = TelegramBroadcaster()
        subscribers = broadcaster.get_subscribers()
        channel = broadcaster.get_channel()
        
        sent_count = 0
        
        # Send to channel
        if channel:
            if broadcaster.send_message(channel, message):
                sent_count += 1
                logger.info(f"📢 Sent results to channel")
        
        # Send to individual subscribers
        for chat_id in subscribers:
            if broadcaster.send_message(chat_id, message):
                sent_count += 1
        
        logger.info(f"✅ Results summary sent to {sent_count} targets ({stats['total']} results)")
        
    except Exception as e:
        logger.error(f"❌ Error broadcasting results: {e}")

def main():
    """Manual trigger for testing"""
    logger.info("================================================================================")
    logger.info("📊 DAILY RESULTS SUMMARY - TELEGRAM BROADCASTER")
    logger.info("================================================================================")
    logger.info("📱 Sends end-of-day results for all settled exact score predictions")
    logger.info("================================================================================")
    
    send_results_summary()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Daily Results Summary for Telegram
===================================
Sends end-of-day results summary showing all settled predictions (exact score + SGP).

Features:
- Runs once at 23:00
- Shows wins (green) and losses (red)
- Daily stats (hit rate, profit)
- Broadcasts to all subscribers
- CONSOLIDATED - only one message per day
"""

import sqlite3
import logging
from datetime import date, datetime
from telegram_sender import TelegramBroadcaster
from stats_master import get_todays_exact_score_stats, get_todays_sgp_stats

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

def get_todays_sgp_results():
    """Get all SGP predictions that settled today"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get today's date
        today = date.today().isoformat()
        
        cursor.execute('''
            SELECT 
                home_team,
                away_team,
                parlay_description,
                bookmaker_odds,
                result,
                outcome,
                profit_loss,
                league
            FROM sgp_predictions
            WHERE status = 'settled'
            AND date(settled_timestamp, 'unixepoch') = ?
            ORDER BY settled_timestamp DESC
        ''', (today,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'home_team': row[0],
                'away_team': row[1],
                'description': row[2],
                'odds': row[3],
                'actual_score': row[4],
                'outcome': row[5],
                'profit': row[6],
                'league': row[7]
            })
        
        conn.close()
        return results
        
    except Exception as e:
        logger.error(f"❌ Error getting today's SGP results: {e}")
        return []

def send_results_summary():
    """Send end-of-day results summary - EXACT SCORE + SGP CONSOLIDATED"""
    logger.info("📊 Running daily results summary...")
    
    # Get both exact score and SGP results
    exact_results = get_todays_results()
    sgp_results = get_todays_sgp_results()
    
    # If nothing settled today, don't send
    if not exact_results and not sgp_results:
        logger.info("⏳ No results settled today")
        return
    
    # Get stats from bulletproof stats module
    exact_stats = get_todays_exact_score_stats() if exact_results else None
    sgp_stats = get_todays_sgp_stats() if sgp_results else None
    
    # Format consolidated message
    today_str = date.today().strftime('%A, %B %d, %Y')
    message = f"🌙 **END OF DAY RESULTS**\n"
    message += f"📅 {today_str}\n\n"
    
    # Calculate total profit
    total_profit = 0
    total_settled = 0
    total_wins = 0
    
    if exact_stats:
        total_profit += exact_stats['profit']
        total_settled += exact_stats['total']
        total_wins += exact_stats['wins']
    
    if sgp_stats:
        total_profit += sgp_stats['profit']
        total_settled += sgp_stats['total']
        total_wins += sgp_stats['wins']
    
    total_hit_rate = (total_wins / total_settled * 100) if total_settled > 0 else 0
    
    # Overall daily stats
    profit_emoji = "📈" if total_profit >= 0 else "📉"
    message += f"📊 **DAILY SUMMARY**\n"
    message += f"⚽ Total Settled: {total_settled}\n"
    message += f"✅ Wins: {total_wins}\n"
    message += f"❌ Losses: {total_settled - total_wins}\n"
    message += f"🎯 Hit Rate: {total_hit_rate:.1f}%\n"
    message += f"{profit_emoji} Profit: {total_profit:+.0f} SEK\n\n"
    message += "=" * 40 + "\n\n"
    
    # EXACT SCORE SECTION
    if exact_results and exact_stats:
        message += f"🎯 **EXACT SCORE** ({exact_stats['total']} bets, {exact_stats['hit_rate']:.1f}% hit rate)\n\n"
        
        for result in exact_results:
            status = "🟢 WIN" if result['outcome'] == 'win' else "🔴 LOSS"
            predicted = result['selection'].replace('Exact Score: ', '')
            
            message += f"{status} **{result['home_team']} vs {result['away_team']}**\n"
            message += f"   🎯 Predicted: {predicted} @{result['odds']:.2f}x\n"
            message += f"   ⚽ Result: {result['actual_score']}\n"
            message += f"   💰 P/L: {result['profit']:+.0f} SEK\n"
            message += f"   🏆 {result['league']}\n\n"
        
        message += "=" * 40 + "\n\n"
    
    # SGP SECTION
    if sgp_results and sgp_stats:
        message += f"🎲 **SGP PARLAYS** ({sgp_stats['total']} bets, {sgp_stats['hit_rate']:.1f}% hit rate)\n\n"
        
        for result in sgp_results:
            status = "🟢 WIN" if result['outcome'] == 'win' else "🔴 LOSS"
            
            message += f"{status} **{result['home_team']} vs {result['away_team']}**\n"
            message += f"   🎲 Parlay: {result['description']}\n"
            message += f"   📊 Odds: @{result['odds']:.2f}x\n"
            message += f"   ⚽ Score: {result['actual_score']}\n"
            message += f"   💰 P/L: {result['profit']:+.0f} SEK\n"
            message += f"   🏆 {result['league']}\n\n"
        
        message += "=" * 40 + "\n\n"
    
    # Closing message
    if total_hit_rate >= 20:
        message += "🔥 **OUTSTANDING PERFORMANCE!**\n"
    elif total_profit > 0:
        message += "💪 **Profitable day!**\n"
    else:
        message += "📊 **Results logged. Tomorrow's another day!**\n"
    
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
        
        logger.info(f"✅ Consolidated daily summary sent to {sent_count} targets ({total_settled} results)")
        
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

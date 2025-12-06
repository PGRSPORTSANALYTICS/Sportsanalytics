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

def get_results_for_date(match_date: str):
    """Get all exact score predictions that settled on a specific MATCH date"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
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
            AND date(match_date) = ?
            ORDER BY settled_timestamp DESC
        ''', (match_date,))
        
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
        logger.error(f"❌ Error getting results for {match_date}: {e}")
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

def get_sgp_results_for_date(match_date: str):
    """Get all SGP predictions that settled on a specific MATCH date"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
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
            AND date(match_date) = ?
            ORDER BY settled_timestamp DESC
        ''', (match_date,))
        
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
        logger.error(f"❌ Error getting SGP results for {match_date}: {e}")
        return []

def get_stats_for_date(match_date: str, market_type: str):
    """Get statistics for a specific match date"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if market_type == 'exact_score':
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(profit_loss) as profit
                FROM football_opportunities 
                WHERE market = 'exact_score' 
                AND result IS NOT NULL 
                AND date(match_date) = ?
            ''', (match_date,))
        else:  # SGP
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(profit_loss) as profit
                FROM sgp_predictions 
                WHERE result IS NOT NULL 
                AND date(match_date) = ?
            ''', (match_date,))
        
        row = cursor.fetchone()
        total, wins, profit = row if row else (0, 0, 0.0)
        losses = total - (wins or 0)
        hit_rate = (wins / total * 100) if total > 0 else 0.0
        
        conn.close()
        
        return {
            'total': total or 0,
            'wins': wins or 0,
            'losses': losses or 0,
            'hit_rate': round(hit_rate, 1),
            'profit': round(profit or 0.0, 2)
        }
    except Exception as e:
        logger.error(f"❌ Error getting stats for {match_date}: {e}")
        return {'total': 0, 'wins': 0, 'losses': 0, 'hit_rate': 0.0, 'profit': 0.0}

def send_results_summary_for_date(match_date: str):
    """Send results summary for a specific match date - 10 min after last match"""
    # DISABLED: User requested no result notifications to Telegram
    logger.info(f"📊 Results summary DISABLED for {match_date} (user request)")
    return
    
    # Get both exact score and SGP results for this specific date
    exact_results = get_results_for_date(match_date)
    sgp_results = get_sgp_results_for_date(match_date)
    
    # If nothing settled, don't send
    if not exact_results and not sgp_results:
        logger.info(f"⏳ No results for {match_date}")
        return
    
    # Get stats for this specific date
    exact_stats = get_stats_for_date(match_date, 'exact_score') if exact_results else None
    sgp_stats = get_stats_for_date(match_date, 'sgp') if sgp_results else None
    
    # Format consolidated message
    date_obj = datetime.fromisoformat(match_date)
    date_str = date_obj.strftime('%A, %B %d, %Y')
    # Use simple formatting - NO markdown to avoid Telegram errors
    message = f"🌙 END OF DAY RESULTS\n"
    message += f"📅 {date_str}\n\n"
    
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
    message += f"📊 DAILY SUMMARY\n"
    message += f"⚽ Total Settled: {total_settled}\n"
    message += f"✅ Wins: {total_wins}\n"
    message += f"❌ Losses: {total_settled - total_wins}\n"
    message += f"🎯 Hit Rate: {total_hit_rate:.1f}%\n"
    message += f"{profit_emoji} Profit: {total_profit:+.0f} SEK\n\n"
    message += "=" * 40 + "\n\n"
    
    # EXACT SCORE SECTION
    if exact_results and exact_stats:
        message += f"🎯 EXACT SCORE ({exact_stats['total']} bets, {exact_stats['hit_rate']:.1f}% hit rate)\n\n"
        
        for result in exact_results:
            status = "🟢 WIN" if result['outcome'] == 'win' else "🔴 LOSS"
            predicted = result['selection'].replace('Exact Score: ', '')
            
            message += f"{status} {result['home_team']} vs {result['away_team']}\n"
            message += f"   🎯 Predicted: {predicted} @{result['odds']:.2f}x\n"
            message += f"   ⚽ Result: {result['actual_score']}\n"
            message += f"   💰 P/L: {result['profit']:+.0f} SEK\n"
            message += f"   🏆 {result['league']}\n\n"
        
        message += "=" * 40 + "\n\n"
    
    # SGP SECTION
    if sgp_results and sgp_stats:
        message += f"🎲 SGP PARLAYS ({sgp_stats['total']} bets, {sgp_stats['hit_rate']:.1f}% hit rate)\n\n"
        
        for result in sgp_results:
            status = "🟢 WIN" if result['outcome'] == 'win' else "🔴 LOSS"
            
            message += f"{status} {result['home_team']} vs {result['away_team']}\n"
            message += f"   🎲 Parlay: {result['description']}\n"
            message += f"   📊 Odds: @{result['odds']:.2f}x\n"
            message += f"   ⚽ Score: {result['actual_score']}\n"
            message += f"   💰 P/L: {result['profit']:+.0f} SEK\n"
            message += f"   🏆 {result['league']}\n\n"
        
        message += "=" * 40 + "\n\n"
    
    # Closing message
    if total_hit_rate >= 20:
        message += "🔥 OUTSTANDING PERFORMANCE!\n"
    elif total_profit > 0:
        message += "💪 Profitable day!\n"
    else:
        message += "📊 Results logged. Tomorrow's another day!\n"
    
    message += "😴 Rest up for tomorrow's predictions!\n"
    
    # Telegram has 4096 char limit - split if needed
    def split_message(msg, max_len=4000):
        """Split message into chunks under Telegram's 4096 char limit"""
        if len(msg) <= max_len:
            return [msg]
        
        chunks = []
        lines = msg.split('\n')
        current_chunk = ""
        
        for line in lines:
            if len(current_chunk) + len(line) + 1 > max_len:
                chunks.append(current_chunk)
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    # Broadcast to subscribers
    try:
        broadcaster = TelegramBroadcaster()
        subscribers = broadcaster.get_subscribers()
        channel = broadcaster.get_channel()
        
        # Split message if too long
        message_chunks = split_message(message)
        logger.info(f"📨 Message split into {len(message_chunks)} part(s)")
        
        sent_count = 0
        
        # Send to channel
        if channel:
            for i, chunk in enumerate(message_chunks, 1):
                prefix = f"[Part {i}/{len(message_chunks)}]\n\n" if len(message_chunks) > 1 else ""
                if broadcaster.send_message(channel, prefix + chunk):
                    sent_count += 1
            logger.info(f"📢 Sent results to channel")
        
        # Send to individual subscribers
        for chat_id in subscribers:
            for chunk in message_chunks:
                if broadcaster.send_message(chat_id, chunk):
                    sent_count += 1
        
        logger.info(f"✅ Consolidated daily summary sent ({total_settled} results)")
        
    except Exception as e:
        logger.error(f"❌ Error broadcasting results: {e}")

def main():
    """Manual trigger for testing - defaults to yesterday's matches"""
    logger.info("================================================================================")
    logger.info("📊 DAILY RESULTS SUMMARY - TELEGRAM BROADCASTER")
    logger.info("================================================================================")
    logger.info("📱 Sends results 10 min after last match of the day settles")
    logger.info("================================================================================")
    
    # Default to yesterday's matches for testing
    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    logger.info(f"🔍 Testing with date: {yesterday}")
    send_results_summary_for_date(yesterday)

if __name__ == "__main__":
    main()

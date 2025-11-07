#!/usr/bin/env python3
"""
Daily Games Reminder for Telegram
==================================
Sends a morning reminder at 9 AM showing all predictions playing TODAY.

Features:
- Morning reminder (9 AM daily)
- Shows all matches playing today
- Includes kickoff times
- Broadcasts to all subscribers
"""

import sqlite3
import schedule
import time
import logging
from datetime import date, datetime
from telegram_sender import TelegramBroadcaster

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = 'data/real_football.db'

def get_todays_matches():
    """Get all predictions for matches playing today"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                home_team,
                away_team,
                selection,
                odds,
                match_date,
                kickoff_time,
                confidence,
                edge_percentage,
                league
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND bet_category = 'today'
            ORDER BY match_date, kickoff_time
        ''')
        
        matches = []
        for row in cursor.fetchall():
            matches.append({
                'home_team': row[0],
                'away_team': row[1],
                'selection': row[2],
                'odds': row[3],
                'match_date': row[4],
                'kickoff_time': row[5],
                'confidence': row[6],
                'edge': row[7],
                'league': row[8]
            })
        
        conn.close()
        return matches
        
    except Exception as e:
        logger.error(f"❌ Error getting today's matches: {e}")
        return []

def format_kickoff_time(match_date, kickoff_time):
    """Format kickoff time for display (today's games only, no date needed)"""
    if not match_date:
        return "TBD"
    
    try:
        # Parse match_date to get time
        if 'T' in match_date:
            dt = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(match_date)
        
        # Format: "20:00" (time only, since it's today)
        return dt.strftime('%H:%M')
    except:
        return str(kickoff_time) if kickoff_time else "TBD"

def send_daily_reminder():
    """Send morning reminder with today's matches"""
    logger.info("📅 Running daily games reminder...")
    
    matches = get_todays_matches()
    
    if not matches:
        logger.info("⏳ No matches playing today")
        return
    
    # Format message
    today_str = date.today().strftime('%A, %B %d, %Y')
    message = f"🌅 GOOD MORNING! TODAY'S PREDICTIONS\n"
    message += f"📅 {today_str}\n\n"
    message += f"⚽ {len(matches)} Predictions Playing Today\n"
    message += "=" * 40 + "\n\n"
    
    for i, match in enumerate(matches, 1):
        kickoff = format_kickoff_time(match['match_date'], match['kickoff_time'])
        
        message += f"{i}. {match['home_team']} vs {match['away_team']}\n"
        message += f"   🕐 Kickoff: {kickoff}\n"
        message += f"   🎯 Prediction: {match['selection']}\n"
        message += f"   💰 Odds: {match['odds']:.2f}x\n"
        message += f"   📊 Edge: {match['edge']:.1f}% | Confidence: {match['confidence']:.0f}\n"
        message += f"   🏆 {match['league']}\n\n"
    
    message += "=" * 40 + "\n"
    message += "🔥 Good luck today!\n"
    message += "📊 Results will be posted after matches finish\n"
    
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
                logger.info(f"📢 Sent reminder to channel")
        
        # Send to individual subscribers
        for chat_id in subscribers:
            if broadcaster.send_message(chat_id, message):
                sent_count += 1
        
        logger.info(f"✅ Daily reminder sent to {sent_count} targets ({len(matches)} matches)")
        
    except Exception as e:
        logger.error(f"❌ Error broadcasting reminder: {e}")

def main():
    """Main scheduler loop"""
    logger.info("================================================================================")
    logger.info("📅 DAILY GAMES REMINDER - TELEGRAM BROADCASTER")
    logger.info("================================================================================")
    logger.info("⏰ Schedule: Every day at 09:00")
    logger.info("📱 Sends morning reminder with today's predictions")
    logger.info("================================================================================")
    
    # Schedule daily at 9 AM
    schedule.every().day.at("09:00").do(send_daily_reminder)
    
    logger.info("🚀 Scheduler started. Waiting for 09:00...")
    logger.info("💡 Tip: Run manually with: python3 daily_games_reminder.py --now")
    
    # Check if --now flag is passed
    import sys
    if '--now' in sys.argv:
        logger.info("🔥 Running reminder NOW (manual trigger)...")
        send_daily_reminder()
    
    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()

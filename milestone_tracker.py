#!/usr/bin/env python3
"""
Milestone Tracker - Monitors data collection progress
Sends reminder when 500 predictions milestone is reached
"""
import sqlite3
from pathlib import Path
from telegram_sender import TelegramBroadcaster
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "real_football.db"
MILESTONE_FILE = Path(__file__).parent / ".milestone_500_reached"

def check_500_milestone():
    """Check if we've hit 500 settled predictions and send reminder"""
    
    # Skip if already notified
    if MILESTONE_FILE.exists():
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Count settled exact score predictions
        # Note: football_opportunities stores ONLY exact score predictions
        cursor.execute("""
            SELECT COUNT(*) FROM football_opportunities 
            WHERE result IN ('win', 'loss')
        """)
        
        settled_count = cursor.fetchone()[0]
        conn.close()
        
        logger.info(f"📊 Data collection progress: {settled_count}/500 settled predictions")
        
        if settled_count >= 500:
            logger.info("🎉 MILESTONE REACHED: 500 settled predictions!")
            
            # Send Telegram notification to Tips Channel (admin sees all channels)
            telegram = TelegramBroadcaster()
            
            message = f"""🎉 MILESTONE REACHED! 🎉

You've collected 500 settled exact score predictions!

📊 Data Collection Complete
✅ Ready for January 2026 launch
⚠️ Action Required:

Switch back to 12% EV threshold:
1. Edit expected_value_calculator.py line 22: min_edge=0.12
2. Edit confidence_scorer.py line 77: min_edge=0.12
3. Restart Real Football Champion workflow

This will reduce volume from ~20-25 to ~12-15 daily predictions, but increase quality to launch standards.

Current Stats:
• Settled Predictions: {settled_count}
• Learning Mode: 8% EV threshold
• Target Launch: January 2026
"""
            
            # Send to Tips Channel (admin will see it)
            telegram.send_message('-1003269011722', message)
            
            # Create milestone file to prevent duplicate notifications
            MILESTONE_FILE.write_text(f"{settled_count} predictions settled")
            
            logger.info("📱 Milestone notification sent to Telegram")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Error checking milestone: {e}")
        return False

if __name__ == "__main__":
    check_500_milestone()

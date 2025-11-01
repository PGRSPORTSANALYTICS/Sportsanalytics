"""
Daily Bet Categorizer - Runs automatically at midnight
Moves bets between today/future/historical categories
"""
import schedule
import time
from categorize_bets import categorize_all_bets
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def daily_categorization_job():
    """Run categorization job"""
    logging.info("🔄 Running daily bet categorization...")
    try:
        today, future, historical = categorize_all_bets()
        logging.info(f"✅ Categorized: {today} today, {future} future, {historical} historical")
    except Exception as e:
        logging.error(f"❌ Categorization failed: {e}")

def run_scheduler():
    """Run the scheduler"""
    logging.info("📅 Daily Bet Categorizer Started")
    logging.info("="*60)
    logging.info("⏰ Runs: Every day at 00:01 (midnight)")
    logging.info("="*60)
    
    # Schedule for midnight
    schedule.every().day.at("00:01").do(daily_categorization_job)
    
    # Also run on startup
    logging.info("🚀 Running initial categorization...")
    daily_categorization_job()
    
    logging.info("⏰ Waiting for next scheduled run...")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == '__main__':
    run_scheduler()

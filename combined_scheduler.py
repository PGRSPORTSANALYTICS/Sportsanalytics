"""
Combined Scheduler for Railway (Reduces service count from 8 to 3)

This runs multiple prediction workflows in a single service,
reducing Railway costs while maintaining all functionality.
"""

import schedule
import time
import logging
from datetime import datetime

# Import prediction modules
from real_football_champion import main as run_exact_score_predictions
from women_1x2_champion import main as run_women_predictions
from parlay_builder import run_parlay_builder
from auto_bet_logger import run_automatic_cycle as run_bet_logging
from daily_bet_categorizer import run_categorization
from daily_games_reminder import send_daily_reminder
from schedule_performance_updates import send_weekly_performance, send_monthly_performance

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def safe_run(task_name, task_func):
    """Run a task safely with error handling"""
    try:
        logger.info(f"🚀 Starting: {task_name}")
        task_func()
        logger.info(f"✅ Completed: {task_name}")
    except Exception as e:
        logger.error(f"❌ Error in {task_name}: {e}", exc_info=True)

def run_all_predictions():
    """Run all prediction generators"""
    safe_run("Exact Score Predictions", run_exact_score_predictions)
    safe_run("Parlay Builder", run_parlay_builder)
    safe_run("Women's 1X2 Predictions", run_women_predictions)

def run_daily_tasks():
    """Run daily maintenance tasks"""
    safe_run("Bet Categorization", run_categorization)
    safe_run("Daily Reminder", send_daily_reminder)

def run_bet_logging_cycle():
    """Run bet logging"""
    safe_run("Auto Bet Logger", run_bet_logging)

def main():
    """Configure and start the combined scheduler"""
    
    logger.info("=" * 80)
    logger.info("🎯 COMBINED SCHEDULER - RAILWAY DEPLOYMENT")
    logger.info("=" * 80)
    logger.info("📊 Exact Score Predictions: Every 1 hour")
    logger.info("🎲 Parlay Builder: Every 1 hour")
    logger.info("👩⚽ Women's 1X2 Predictions: Every 1 hour")
    logger.info("📝 Auto Bet Logger: Every 30 minutes")
    logger.info("📅 Daily Tasks: Every day at 00:01")
    logger.info("📊 Weekly Performance: Every Sunday at 20:00")
    logger.info("📊 Monthly Performance: 1st of month at 12:00")
    logger.info("=" * 80)
    
    # Schedule prediction generators (every 1 hour)
    schedule.every(1).hours.do(run_all_predictions)
    
    # Schedule bet logging (every 30 minutes)
    schedule.every(30).minutes.do(run_bet_logging_cycle)
    
    # Schedule daily tasks (midnight)
    schedule.every().day.at("00:01").do(run_daily_tasks)
    
    # Schedule performance updates
    schedule.every().sunday.at("20:00").do(
        lambda: safe_run("Weekly Performance", send_weekly_performance)
    )
    schedule.every().month.at("01").at("12:00").do(
        lambda: safe_run("Monthly Performance", send_monthly_performance)
    )
    
    # Run predictions immediately on startup
    logger.info("🚀 Running initial prediction cycle...")
    run_all_predictions()
    
    # Run main loop
    logger.info("⏰ Scheduler started. Running continuously...")
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("⏹️ Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Scheduler error: {e}", exc_info=True)
            time.sleep(60)  # Wait before retrying

if __name__ == "__main__":
    main()

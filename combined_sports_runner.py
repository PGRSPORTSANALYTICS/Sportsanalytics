#!/usr/bin/env python3
"""
Combined Sports Runner
Runs all prediction engines in a single workflow process
"""

import logging
import time
import schedule
from datetime import datetime
import threading

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_football_predictions():
    """Run football exact score predictions"""
    try:
        import real_football_champion
        logger.info("⚽ Starting Football Exact Score cycle...")
        real_football_champion.main()
    except Exception as e:
        logger.error(f"❌ Football prediction error: {e}")


def run_sgp_predictions():
    """Run SGP predictions"""
    try:
        import sgp_champion
        logger.info("🎲 Starting SGP cycle...")
        sgp_champion.main()
    except Exception as e:
        logger.error(f"❌ SGP prediction error: {e}")


def run_women_1x2_predictions():
    """Run women's 1X2 predictions"""
    try:
        from women_1x2_champion import run_prediction_cycle
        logger.info("👩⚽ Starting Women's 1X2 cycle...")
        run_prediction_cycle()
    except Exception as e:
        logger.error(f"❌ Women's 1X2 prediction error: {e}")


def run_college_basketball():
    """Run college basketball predictions"""
    try:
        from college_basket_champion import run_prediction_cycle
        logger.info("🏀 Starting College Basketball cycle...")
        run_prediction_cycle()
    except Exception as e:
        logger.error(f"❌ College Basketball prediction error: {e}")


def verify_basketball_results():
    """Verify College Basketball results"""
    try:
        from college_basket_result_verifier import CollegeBasketballResultVerifier
        logger.info("✅ Verifying College Basketball results...")
        verifier = CollegeBasketballResultVerifier()
        results = verifier.verify_pending_picks()
        logger.info(f"✅ Basketball verification: {results['verified']} verified, {results['failed']} failed")
    except Exception as e:
        logger.error(f"❌ Basketball verification error: {e}")


def run_performance_updates():
    """Run performance updates"""
    try:
        import schedule_performance_updates
        logger.info("📊 Running performance updates...")
        schedule_performance_updates.update_performance_metrics()
    except Exception as e:
        logger.error(f"❌ Performance update error: {e}")


def run_daily_categorizer():
    """Run daily bet categorizer"""
    try:
        import daily_bet_categorizer
        logger.info("📂 Running daily bet categorizer...")
        daily_bet_categorizer.categorize_todays_bets()
    except Exception as e:
        logger.error(f"❌ Daily categorizer error: {e}")


def run_daily_games_reminder():
    """Send daily games reminder"""
    try:
        import daily_games_reminder
        logger.info("📅 Running daily games reminder...")
        daily_games_reminder.send_daily_reminder()
    except Exception as e:
        logger.error(f"❌ Daily reminder error: {e}")


def main():
    """Main orchestration loop"""
    logger.info("="*80)
    logger.info("🚀 COMBINED SPORTS PREDICTION ENGINE")
    logger.info("="*80)
    logger.info("⚽ Football Exact Score - Every 1 hour")
    logger.info("🎲 SGP Predictions - Every 2 hours")
    logger.info("👩⚽ Women's 1X2 - Every 1 hour")
    logger.info("🏀 College Basketball - Every 2 hours")
    logger.info("✅ Basketball Results - Every 30 minutes")
    logger.info("📊 Performance Updates - Every 6 hours")
    logger.info("📂 Bet Categorizer - Daily at 23:00")
    logger.info("📅 Games Reminder - Daily at 08:00")
    logger.info("="*80)
    
    # Run all engines immediately on startup
    logger.info("🎬 Running initial prediction cycles...")
    run_football_predictions()
    time.sleep(5)
    run_sgp_predictions()
    time.sleep(5)
    run_women_1x2_predictions()
    time.sleep(5)
    run_college_basketball()
    time.sleep(5)
    run_performance_updates()
    
    # Schedule recurring tasks
    schedule.every(1).hours.do(run_football_predictions)
    schedule.every(2).hours.do(run_sgp_predictions)
    schedule.every(1).hours.do(run_women_1x2_predictions)
    schedule.every(2).hours.do(run_college_basketball)
    schedule.every(30).minutes.do(verify_basketball_results)
    schedule.every(6).hours.do(run_performance_updates)
    
    schedule.every().day.at("23:00").do(run_daily_categorizer)
    schedule.every().day.at("08:00").do(run_daily_games_reminder)
    
    logger.info("✅ All schedules configured. Starting main loop...")
    
    # Keep running
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
            break
        except Exception as e:
            logger.error(f"❌ Main loop error: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()

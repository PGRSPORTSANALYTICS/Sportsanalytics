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

# ============================================================
# PRODUCT ENABLE/DISABLE FLAGS - Set to False to pause product
# ============================================================
ENABLE_VALUE_SINGLES = True          # Core product - AI picks for 1X2, O/U, BTTS, etc.
ENABLE_PARLAYS = True                # Multi-match parlays from L1/L2 singles
ENABLE_COLLEGE_BASKETBALL = True     # ACTIVE - 63.3% hit rate, +$3,446 profit
ENABLE_ML_PARLAY = True              # ENABLED - test mode (data collection only)


def run_value_singles():
    """Run Value Singles predictions (core product)"""
    try:
        import real_football_champion
        logger.info("💰 Starting Value Singles cycle...")
        real_football_champion.run_single_cycle()
        logger.info("✅ Value Singles cycle complete")
    except Exception as e:
        logger.error(f"❌ Value Singles prediction error: {e}")


def run_parlay_builder():
    """Run multi-match parlay builder from approved singles"""
    try:
        from parlay_builder import run_parlay_builder as build_parlays
        logger.info("🎲 Starting Parlay Builder cycle...")
        parlays = build_parlays()
        logger.info(f"✅ Parlay Builder complete: {len(parlays)} parlays generated")
    except Exception as e:
        logger.error(f"❌ Parlay builder error: {e}")
        import traceback
        traceback.print_exc()


def run_college_basketball():
    """Run college basketball predictions"""
    try:
        from college_basket_champion import run_prediction_cycle
        logger.info("🏀 Starting College Basketball cycle...")
        run_prediction_cycle()
    except Exception as e:
        logger.error(f"❌ College Basketball prediction error: {e}")


def run_ml_parlay():
    """Run ML Parlay predictions (TEST MODE - no external posting)"""
    try:
        from ml_parlay_engine import run_prediction_cycle
        logger.info("🎰 Starting ML Parlay cycle (TEST MODE)...")
        run_prediction_cycle()
        logger.info("✅ ML Parlay cycle complete")
    except Exception as e:
        logger.error(f"❌ ML Parlay prediction error: {e}")


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


def verify_football_results():
    """Verify Football Exact Score and Value Singles results"""
    try:
        from verify_results import RealResultVerifier
        logger.info("⚽ Verifying Football results...")
        verifier = RealResultVerifier()
        results = verifier.verify_pending_tips()
        logger.info(f"⚽ Football verification: {results['verified']} verified, {results['failed']} failed")
    except Exception as e:
        logger.error(f"❌ Football verification error: {e}")


def verify_parlay_results():
    """Verify parlay results using ML parlay verifier"""
    try:
        from ml_parlay_verifier import MLParlayVerifier
        logger.info("🎲 Verifying Parlay results...")
        verifier = MLParlayVerifier()
        results = verifier.verify_pending_parlays()
        logger.info(f"🎲 Parlay verification: {results['verified']} verified, {results['failed']} failed")
    except Exception as e:
        logger.error(f"❌ Parlay verification error: {e}")
        import traceback
        traceback.print_exc()


def verify_ml_parlay_results():
    """Verify ML Parlay results (TEST MODE)"""
    try:
        from ml_parlay_verifier import MLParlayVerifier
        logger.info("🎰 Verifying ML Parlay results...")
        verifier = MLParlayVerifier()
        results = verifier.verify_pending_parlays()
        logger.info(f"🎰 ML Parlay verification: {results['verified']} verified, {results['failed']} failed")
    except Exception as e:
        logger.error(f"❌ ML Parlay verification error: {e}")


def print_daily_stake_summary():
    """Print today's staking summary"""
    try:
        from bankroll_manager import get_bankroll_manager
        bankroll_mgr = get_bankroll_manager()
        breakdown = bankroll_mgr.get_today_stake_breakdown()
        current_bankroll = bankroll_mgr.get_current_bankroll()
        usd_rate = 10.75
        
        logger.info("="*60)
        logger.info("💰 TODAY'S STAKING SUMMARY (1.6% Kelly)")
        logger.info("="*60)
        logger.info(f"   Value Singles:     {breakdown['value_singles']:,.0f} SEK")
        logger.info(f"   Multi-Match:       {breakdown['parlays']:,.0f} SEK")
        logger.info(f"   ML Parlays:        {breakdown['ml_parlays']:,.0f} SEK")
        logger.info(f"   Basketball:        {breakdown['basketball']:,.0f} SEK")
        logger.info("-"*60)
        logger.info(f"   TOTAL STAKED:      {breakdown['total']:,.0f} SEK (${breakdown['total']/usd_rate:,.0f} USD)")
        logger.info(f"   Current Bankroll:  {current_bankroll:,.0f} SEK (${current_bankroll/usd_rate:,.0f} USD)")
        logger.info("="*60)
    except Exception as e:
        logger.error(f"❌ Stake summary error: {e}")


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


def run_daily_recap():
    """Send daily recap of all results at 22:30"""
    try:
        from daily_recap import send_daily_recap
        logger.info("📊 Running daily recap...")
        send_daily_recap()
    except Exception as e:
        logger.error(f"❌ Daily recap error: {e}")


def main():
    """Main orchestration loop"""
    logger.info("="*80)
    logger.info("🚀 COMBINED SPORTS PREDICTION ENGINE")
    logger.info("="*80)
    logger.info("💰 Value Singles - Every 1 hour (Core Product)")
    logger.info("🎲 Multi-Match Parlays - Every 2 hours (after Value Singles)")
    logger.info("🏀 College Basketball - Every 2 hours")
    logger.info("🎰 ML Parlay (TEST MODE) - Every 3 hours")
    logger.info("="*80)
    logger.info("🔍 FAST RESULT VERIFICATION (5-minute cycles):")
    logger.info("💰 Value Singles Results - Every 5 minutes")
    logger.info("🎲 Parlay Results - Every 5 minutes")
    logger.info("🏀 Basketball Results - Every 5 minutes")
    logger.info("🎰 ML Parlay Results - Every 5 minutes")
    logger.info("="*80)
    logger.info("📊 Performance Updates - Every 6 hours")
    logger.info("📊 Daily Recap - Daily at 22:30")
    logger.info("📂 Bet Categorizer - Daily at 23:00")
    logger.info("📅 Games Reminder - Daily at 08:00")
    logger.info("="*80)
    
    # Run enabled engines on startup
    logger.info("🎬 Running initial prediction cycles...")
    if ENABLE_VALUE_SINGLES:
        run_value_singles()
        time.sleep(5)
    else:
        logger.info("⏸️ Value Singles PAUSED")
    
    if ENABLE_PARLAYS:
        run_parlay_builder()
        time.sleep(5)
    else:
        logger.info("⏸️ Parlays PAUSED")
    
    if ENABLE_COLLEGE_BASKETBALL:
        run_college_basketball()
        time.sleep(5)
    else:
        logger.info("⏸️ College Basketball PAUSED")
    
    if ENABLE_ML_PARLAY:
        run_ml_parlay()
        time.sleep(5)
    else:
        logger.info("⏸️ ML Parlay PAUSED")
    
    # Print daily stake summary after all prediction cycles
    print_daily_stake_summary()
    
    run_performance_updates()
    
    # CRITICAL: Run all verifications immediately on startup
    # This ensures no bets drag for days waiting for scheduler
    logger.info("🔄 Running immediate result verification...")
    verify_football_results()
    verify_parlay_results()
    verify_basketball_results()
    verify_ml_parlay_results()
    logger.info("✅ Initial verification complete")
    
    # Schedule recurring prediction tasks (only enabled products)
    if ENABLE_VALUE_SINGLES:
        schedule.every(1).hours.do(run_value_singles)
    if ENABLE_PARLAYS:
        schedule.every(2).hours.do(run_parlay_builder)
    if ENABLE_COLLEGE_BASKETBALL:
        schedule.every(2).hours.do(run_college_basketball)
    if ENABLE_ML_PARLAY:
        schedule.every(3).hours.do(run_ml_parlay)
    
    # Schedule result verification - Every 5 minutes for FAST results
    schedule.every(5).minutes.do(verify_football_results)
    schedule.every(5).minutes.do(verify_parlay_results)
    schedule.every(5).minutes.do(verify_basketball_results)
    schedule.every(5).minutes.do(verify_ml_parlay_results)
    
    # Print stake summary every hour
    schedule.every(1).hours.do(print_daily_stake_summary)
    
    schedule.every(6).hours.do(run_performance_updates)
    
    schedule.every().day.at("22:30").do(run_daily_recap)
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

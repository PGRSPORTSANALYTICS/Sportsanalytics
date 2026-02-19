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
ENABLE_PARLAYS = False               # DISABLED per Jan 2026 policy - no multi-match parlays
ENABLE_COLLEGE_BASKETBALL = True     # ACTIVE - 63.3% hit rate, +$3,446 profit
ENABLE_ML_PARLAY = False             # DISABLED Feb 16, 2026 - 11.9% hit rate, not profitable
ENABLE_PLAYER_PROPS = True           # LEARNING MODE - player props data collection (Feb 2026)

# ============================================================
# DAILY STOP-LOSS (Jan 28, 2026)
# ============================================================
ENABLE_DAILY_STOPLOSS = True         # Soft stop-loss at -5u per day
# Threshold configured in daily_stoploss.py (DAILY_STOPLOSS_UNITS = -5.0)

# ============================================================
# LIVE LEARNING MODE - Full Data Capture Enabled
# ============================================================
LIVE_LEARNING_MODE = True            # Capture ALL picks for maximum learning
LIVE_LEARNING_SAVE_ALL_TIERS = True  # Save L1, L2, L3, and Hidden Value picks
LIVE_LEARNING_CLV_TRACKING = True    # Track opening/closing odds for every pick

# ============================================================
# PGR ANALYTICS v2 — Multi-Book Intelligence (Feb 16, 2026)
# ============================================================
ENABLE_PGR_ANALYTICS = True          # Odds ingestion, bet sync, CLV tracking


def check_daily_stoploss() -> bool:
    """
    Check if daily stop-loss has been triggered.
    Returns True if new bets should be blocked.
    """
    if not ENABLE_DAILY_STOPLOSS:
        return False
    
    try:
        from daily_stoploss import is_stoploss_triggered
        triggered, pnl, message = is_stoploss_triggered()
        if triggered:
            logger.warning(f"🛑 DAILY STOP-LOSS ACTIVE: {message}")
        return triggered
    except Exception as e:
        logger.error(f"❌ Stop-loss check failed: {e}")
        return False  # Allow bets if check fails


def run_value_singles():
    """Run Value Singles predictions (core product)"""
    if check_daily_stoploss():
        logger.warning("⏭️ Value Singles SKIPPED - Daily stop-loss active")
        return
    
    try:
        import real_football_champion
        logger.info("💰 Starting Value Singles cycle...")
        real_football_champion.run_single_cycle()
        logger.info("✅ Value Singles cycle complete")
    except Exception as e:
        logger.error(f"❌ Value Singles prediction error: {e}")


def run_corners_cards():
    """Run Corners & Cards predictions (independent cycle with own cap)"""
    if check_daily_stoploss():
        logger.warning("⏭️ Corners/Cards SKIPPED - Daily stop-loss active")
        return
    
    try:
        import real_football_champion
        logger.info("🔢 Starting Corners & Cards cycle (independent)...")
        real_football_champion.run_corners_cards_cycle()
        logger.info("✅ Corners & Cards cycle complete")
    except Exception as e:
        logger.error(f"❌ Corners/Cards prediction error: {e}")
        import traceback
        traceback.print_exc()


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


def run_player_props():
    """Run Player Props predictions (LEARNING MODE - data collection)"""
    try:
        from player_props_engine import run_player_props_cycle
        logger.info("🎯 Starting Player Props cycle (LEARNING MODE)...")
        stats = run_player_props_cycle()
        logger.info(f"🎯 Player Props complete: {stats.get('football_props', 0)} football, "
                     f"{stats.get('basketball_props', 0)} basketball, "
                     f"{stats.get('total_saved', 0)} saved")
    except Exception as e:
        logger.error(f"❌ Player Props error: {e}")
        import traceback
        traceback.print_exc()


def run_player_props_settlement():
    """Settle player prop bets using actual game stats from nba_api"""
    try:
        from player_props_settlement import run_player_props_settlement as settle
        logger.info("🎯 Starting Player Props settlement...")
        stats = settle()
        if stats['settled'] > 0:
            logger.info(f"🎯 Props settled: {stats['won']}W/{stats['lost']}L/{stats['push']}P/{stats['void']}V")
        else:
            logger.info("🎯 No props to settle this cycle")
    except Exception as e:
        logger.error(f"❌ Player Props settlement error: {e}")
        import traceback
        traceback.print_exc()


def run_multi_sport_learning():
    """Run multi-sport learning engine (Tennis, Hockey, MMA)"""
    try:
        from multi_sport_learning_engine import run_multi_sport_learning as scan
        logger.info("🌐 Starting Multi-Sport Learning scan...")
        stats = scan()
        total = sum(stats[k]['saved'] for k in ['TENNIS', 'HOCKEY', 'MMA'])
        logger.info(f"🌐 Multi-Sport Learning: {total} picks saved "
                     f"(🎾{stats['TENNIS']['saved']} 🏒{stats['HOCKEY']['saved']} 🥊{stats['MMA']['saved']})")
    except Exception as e:
        logger.error(f"❌ Multi-Sport Learning error: {e}")
        import traceback
        traceback.print_exc()


def run_multi_sport_settlement():
    """Settle multi-sport learning bets (Tennis, Hockey, MMA)"""
    try:
        from multi_sport_settlement import run_multi_sport_settlement as settle
        logger.info("🌐 Starting Multi-Sport settlement...")
        stats = settle()
        if stats['settled'] > 0:
            logger.info(f"🌐 Multi-Sport settled: {stats['won']}W/{stats['lost']}L/{stats['push']}P/{stats['void']}V")
        else:
            logger.info("🌐 No multi-sport bets to settle")
    except Exception as e:
        logger.error(f"❌ Multi-Sport settlement error: {e}")
        import traceback
        traceback.print_exc()


def run_pgr_analytics():
    """Run PGR Analytics v2 cycle — odds ingestion, bet sync, CLV tracking"""
    try:
        from pgr_bridge import run_full_pgr_cycle
        logger.info("📊 Starting PGR Analytics cycle...")
        results = run_full_pgr_cycle()
        ingestion = results.get('ingestion', {})
        sync = results.get('sync_bets', {})
        settled = results.get('sync_results', {})
        logger.info(f"📊 PGR cycle: {ingestion.get('total_snapshots', 0)} odds snapshots, "
                     f"{sync.get('synced', 0)} bets synced, "
                     f"{settled.get('settled', 0)} results synced")
    except Exception as e:
        logger.error(f"❌ PGR Analytics error: {e}")
        import traceback
        traceback.print_exc()


def run_ml_parlay():
    """Run ML Parlay predictions (TEST MODE - no external posting)"""
    try:
        from ml_parlay_engine import run_prediction_cycle
        logger.info("🎰 Starting ML Parlay cycle (TEST MODE)...")
        run_prediction_cycle()
        logger.info("✅ ML Parlay cycle complete")
    except Exception as e:
        logger.error(f"❌ ML Parlay prediction error: {e}")


def run_learning_update():
    """Run self-learning stats computation and auto-promotion cycle"""
    try:
        from learning_engine import run_learning_update as update_stats
        logger.info("🧠 Running self-learning stats update...")
        saved = update_stats()
        logger.info(f"🧠 Learning stats updated: {saved} rows")
    except Exception as e:
        logger.error(f"❌ Learning stats error: {e}")
        import traceback
        traceback.print_exc()

    try:
        from auto_promoter import run_promotion_cycle
        logger.info("🔄 Running auto-promotion cycle...")
        changes = run_promotion_cycle()
        promoted = len(changes.get('promoted', []))
        demoted = len(changes.get('demoted', []))
        disabled = len(changes.get('disabled', []))
        if promoted or demoted or disabled:
            logger.info(f"🔄 Promotion changes: {promoted} promoted, {demoted} demoted, {disabled} disabled")
            for item in changes.get('promoted', []):
                logger.info(f"   ✅ PROMOTED: {item['league']}/{item['market']} (ROI {item['roi']:.1f}%)")
            for item in changes.get('demoted', []):
                logger.info(f"   ⚠️ DEMOTED: {item['league']}/{item['market']} (ROI {item['roi']:.1f}%)")
        else:
            logger.info("🔄 No promotion changes")
    except Exception as e:
        logger.error(f"❌ Auto-promotion error: {e}")
        import traceback
        traceback.print_exc()


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


def run_results_engine():
    """Run unified Results Engine for ALL bet types (settlement only, no Discord)"""
    try:
        from results_engine import run_results_engine as engine_cycle
        logger.info("🔄 Running Results Engine (unified settlement)...")
        stats = engine_cycle()
        logger.info(f"🔄 Results Engine: {stats['settled']} settled, {stats['voided']} voided, {stats['failed']} failed")
    except Exception as e:
        logger.error(f"❌ Results Engine error: {e}")
        import traceback
        traceback.print_exc()


def run_end_of_day_results():
    """Send daily results summary to Discord once all games are done"""
    try:
        from bet_distribution_controller import send_daily_results
        logger.info("📊 Sending end-of-day results to Discord...")
        results_sent = send_daily_results()
        if results_sent > 0:
            logger.info(f"📤 End-of-day results sent: {results_sent} bets")
        else:
            logger.info("📊 No settled bets to report today")
    except Exception as e:
        logger.error(f"❌ End-of-day results error: {e}")


def verify_football_results():
    """Verify Football Exact Score and Value Singles results"""
    try:
        from verify_results import RealResultVerifier
        logger.info("⚽ Verifying Football results...")
        verifier = RealResultVerifier()
        results = verifier.verify_pending_tips()
        logger.info(f"⚽ Football verification: {results['verified']} verified, {results['failed']} failed")
        
        # ROI webhook only sends after ALL day's matches are settled (end-of-day)
        # Individual results use DISCORD_RESULTS_WEBHOOK
    except Exception as e:
        logger.error(f"❌ Football verification error: {e}")


def verify_all_bets_corners_cards():
    """Verify Corners, Cards, and Value Singles from all_bets table"""
    try:
        from verify_results import RealResultVerifier
        logger.info("🔢 Verifying Corners & Cards from all_bets...")
        verifier = RealResultVerifier()
        results = verifier.verify_all_bets_pending()
        logger.info(f"🔢 Corners/Cards verification: {results['verified']} verified, {results['failed']} failed")
    except Exception as e:
        logger.error(f"❌ Corners/Cards verification error: {e}")
        import traceback
        traceback.print_exc()


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


def run_clv_update_cycle():
    """Run CLV (Closing Line Value) update cycle - capture closing odds near kickoff"""
    try:
        from clv_service import run_clv_update_cycle as clv_cycle
        logger.info("📊 Running CLV update cycle...")
        stats = clv_cycle()
        if stats.get('updated', 0) > 0:
            avg_clv = stats.get('avg_clv')
            if avg_clv is not None:
                logger.info(f"📊 CLV cycle: {stats['updated']} bets updated, avg CLV: {avg_clv:+.2f}%")
            else:
                logger.info(f"📊 CLV cycle: {stats['updated']} bets updated")
        else:
            logger.info(f"📊 CLV cycle: No bets updated ({stats.get('candidates', 0)} candidates checked)")
    except Exception as e:
        logger.error(f"❌ CLV update cycle error: {e}")
        import traceback
        traceback.print_exc()


def run_live_learning_enrichment():
    """Run LIVE LEARNING pick enrichment - adds syndicate engine data to pending picks"""
    if not LIVE_LEARNING_MODE:
        return
    
    try:
        from live_learning_tracker import enrich_pending_picks_with_syndicate_data
        logger.info("🔬 Running LIVE LEARNING enrichment cycle...")
        result = enrich_pending_picks_with_syndicate_data()
        if result.get('enriched', 0) > 0:
            logger.info(f"🔬 LIVE LEARNING: Enriched {result['enriched']} picks with syndicate data")
        else:
            logger.info("🔬 LIVE LEARNING: No picks to enrich")
    except Exception as e:
        logger.error(f"❌ LIVE LEARNING enrichment error: {e}")
        import traceback
        traceback.print_exc()


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
        from daily_recap import send_daily_discord_recap
        logger.info("📊 Running daily Discord recap...")
        send_daily_discord_recap()
    except Exception as e:
        logger.error(f"❌ Daily recap error: {e}")


def run_daily_analysis():
    """Run Daily Analysis Engine - Post-match analysis + upcoming match teaser"""
    try:
        from daily_analysis_engine import run_daily_analysis as analysis_cycle
        logger.info("📝 Running Daily Analysis Engine...")
        posts = analysis_cycle()
        logger.info(f"📝 Daily Analysis complete: {posts}/3 posts generated")
    except Exception as e:
        logger.error(f"❌ Daily Analysis error: {e}")


def run_free_picks():
    """Send value singles to Discord with full validation"""
    try:
        from bet_distribution_controller import distribute_value_singles
        logger.info("🎯 Running Value Singles Distribution...")
        sent = distribute_value_singles(5)  # 5 value singles
        logger.info(f"🎯 Value Singles complete: {sent} picks sent")
    except Exception as e:
        logger.error(f"❌ Value Singles distribution error: {e}")


def run_daily_free_pick():
    """Send 1 free pick to Discord daily (Jan 29, 2026 policy)"""
    try:
        from free_picks_engine import run_free_picks
        logger.info("🎁 Running Daily Free Pick (1 pick/day)...")
        sent = run_free_picks(picks_to_send=1)
        logger.info(f"🎁 Free pick complete: {sent} pick sent")
    except Exception as e:
        logger.error(f"❌ Free pick error: {e}")


def run_weekly_recap():
    """Send weekly recap on Sunday at 22:30"""
    try:
        from daily_recap import send_weekly_discord_recap
        logger.info("📈 Running weekly Discord recap...")
        send_weekly_discord_recap()
    except Exception as e:
        logger.error(f"❌ Weekly recap error: {e}")


def run_weekly_learning_report():
    """Send weekly learning system report on Sunday at 23:00"""
    try:
        from learning_weekly_report import send_weekly_learning_report
        logger.info("🧪 Running weekly learning system report...")
        send_weekly_learning_report()
    except Exception as e:
        logger.error(f"❌ Weekly learning report error: {e}")


def main():
    """Main orchestration loop"""
    logger.info("="*80)
    logger.info("🚀 COMBINED SPORTS PREDICTION ENGINE")
    logger.info("="*80)
    
    logger.info("="*80)
    logger.info("🏆 PRODUCTION MODEL v1.0 - ACTIVE (Jan 25, 2026)")
    logger.info("="*80)
    logger.info("📊 Learning Phase Results (Dec 25 - Jan 25):")
    logger.info("   • 1909 bets | 59.5% hit rate | +23.5% ROI | +449.2 units")
    logger.info("="*80)
    logger.info("✅ PRODUCTION MARKETS:")
    logger.info("   • CARDS: 88.4% hit rate, +127.70u")
    logger.info("   • CORNERS: 60.6% hit rate, +146.53u")
    logger.info("   • VALUE_SINGLE (Totals + BTTS only — no 1X2)")
    logger.info("🧪 LEARNING ONLY:")
    logger.info("   • PLAYER PROPS (football + basketball, data collection)")
    logger.info("   • BASKETBALL (data collection, no public output)")
    logger.info("   • HOME_WIN + AWAY_WIN (1X2 — bookmakers too sharp, data collection only)")
    logger.info("❌ DISABLED:")
    logger.info("   • SGP (2.8% hit rate)")
    logger.info("="*80)
    logger.info("📋 Post-learning rules:")
    logger.info("   • No stake increases")
    logger.info("   • No new markets")
    logger.info("   • No threshold changes")
    logger.info("   • CLV tracking: ENABLED")
    logger.info("="*80)
    
    logger.info("💰 Value Singles - Every 1 hour (Core Product)")
    logger.info("🔢 Corners & Cards - Every 1 hour (Independent, own cap: 10/day)")
    logger.info("🎲 Multi-Match Parlays - Every 2 hours (after Value Singles)")
    logger.info("🏀 College Basketball - Every 2 hours")
    logger.info("🎰 ML Parlay (TEST MODE) - Every 3 hours")
    logger.info("🎯 Player Props (LEARNING) - Every 6 hours")
    logger.info("📊 PGR Analytics v2 - Every 1 hour (odds ingestion + bet sync)")
    logger.info("="*80)
    logger.info("🔍 FAST RESULT VERIFICATION (5-minute cycles):")
    logger.info("💰 Value Singles Results - Every 5 minutes")
    logger.info("🎲 Parlay Results - Every 5 minutes")
    logger.info("🏀 Basketball Results - Every 5 minutes")
    logger.info("🎰 ML Parlay Results - Every 5 minutes")
    logger.info("="*80)
    logger.info("📊 CLV Tracking - Every 5 minutes (closing odds capture)")
    logger.info("📊 Performance Updates - Every 6 hours")
    logger.info("📊 Daily Recap - Daily at 22:30 (Discord)")
    logger.info("📈 Weekly Recap - Sunday at 22:30 (Discord)")
    logger.info("🧪 Learning System Report - Sunday at 23:00 (Discord)")
    logger.info("📂 Bet Categorizer - Daily at 23:00")
    logger.info("📅 Games Reminder - Daily at 08:00")
    logger.info("📝 Daily Analysis - Daily at 09:00 (Discord)")
    logger.info("🎁 Free Picks - Daily at 10:00 (Discord)")
    logger.info("="*80)
    
    # Run enabled engines on startup
    logger.info("🎬 Running initial prediction cycles...")
    if ENABLE_VALUE_SINGLES:
        run_value_singles()
        time.sleep(5)
        run_corners_cards()
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
    
    if ENABLE_PLAYER_PROPS:
        run_player_props()
        time.sleep(5)
    else:
        logger.info("⏸️ Player Props PAUSED")
    
    # Print daily stake summary after all prediction cycles
    print_daily_stake_summary()
    
    run_performance_updates()
    
    run_learning_update()
    
    # CRITICAL: Run Results Engine immediately on startup
    # This ensures no bets drag for days waiting for scheduler
    logger.info("🔄 Running immediate Results Engine...")
    run_results_engine()  # Unified settlement for ALL bet types
    verify_basketball_results()  # Basketball has separate verifier
    verify_ml_parlay_results()  # ML Parlay verification
    logger.info("✅ Initial verification complete")
    
    # Run PGR Analytics on startup — sync existing bets + capture odds
    if ENABLE_PGR_ANALYTICS:
        run_pgr_analytics()
        logger.info("📊 PGR Analytics initial sync complete")
    
    # Schedule recurring prediction tasks (only enabled products)
    if ENABLE_VALUE_SINGLES:
        schedule.every(1).hours.do(run_value_singles)
        schedule.every(1).hours.do(run_corners_cards)
    if ENABLE_PARLAYS:
        schedule.every(2).hours.do(run_parlay_builder)
    if ENABLE_COLLEGE_BASKETBALL:
        schedule.every(2).hours.do(run_college_basketball)
    if ENABLE_ML_PARLAY:
        schedule.every(3).hours.do(run_ml_parlay)
    if ENABLE_PLAYER_PROPS:
        schedule.every(6).hours.do(run_player_props)
    
    # Multi-Sport Learning (Tennis, Hockey, MMA) - Every 6 hours
    schedule.every(6).hours.do(run_multi_sport_learning)
    
    # Schedule result verification - Every 5 minutes for FAST results
    schedule.every(5).minutes.do(run_results_engine)  # Unified Results Engine
    schedule.every(5).minutes.do(verify_basketball_results)  # Basketball separate
    schedule.every(30).minutes.do(verify_ml_parlay_results)  # ML Parlay verification
    schedule.every(30).minutes.do(run_player_props_settlement)  # Player props settlement
    schedule.every(30).minutes.do(run_multi_sport_settlement)  # Multi-sport settlement
    
    # Schedule CLV update - Every 10 minutes for closing odds capture
    schedule.every(10).minutes.do(run_clv_update_cycle)
    
    # PGR Analytics v2 — odds ingestion + bet sync every hour, aligned with Value Singles
    if ENABLE_PGR_ANALYTICS:
        schedule.every(1).hours.do(run_pgr_analytics)
        logger.info("📊 PGR Analytics scheduled (every 1 hour)")
    
    # Schedule LIVE LEARNING enrichment - Every 10 minutes to add syndicate data
    if LIVE_LEARNING_MODE:
        schedule.every(10).minutes.do(run_live_learning_enrichment)
        run_live_learning_enrichment()  # Run immediately on startup
        logger.info("🔬 LIVE LEARNING enrichment scheduled (every 10 minutes)")
    
    # Print stake summary every hour
    schedule.every(1).hours.do(print_daily_stake_summary)
    
    schedule.every(6).hours.do(run_performance_updates)
    
    schedule.every(2).hours.do(run_learning_update)
    
    schedule.every().day.at("22:30").do(run_daily_recap)
    schedule.every().sunday.at("22:30").do(run_weekly_recap)
    schedule.every().sunday.at("23:00").do(run_weekly_learning_report)
    schedule.every().day.at("23:00").do(run_daily_categorizer)
    schedule.every().day.at("22:45").do(run_end_of_day_results)  # Results summary after all games
    schedule.every().day.at("08:00").do(run_daily_games_reminder)
    schedule.every().day.at("09:00").do(run_daily_analysis)
    schedule.every().day.at("10:00").do(run_free_picks)  # 5 value singles
    schedule.every().day.at("11:00").do(run_daily_free_pick)  # 1 free pick to Discord
    
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

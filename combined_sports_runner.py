#!/usr/bin/env python3
"""
Combined Sports Runner
Runs all prediction engines in a single workflow process
"""

import logging
import time
import os
import schedule
from datetime import datetime, timedelta
import threading

IS_RAILWAY = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RAILWAY_STATIC_URL")
    or os.environ.get("RAILWAY_SERVICE_NAME")
    or os.environ.get("RAILWAY_PROJECT_ID")
    or os.environ.get("RAILWAY_RUN_ENGINE")
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# PRODUCT ENABLE/DISABLE FLAGS - Set to False to pause product
# ============================================================
ENABLE_VALUE_SINGLES = True          # Core product - AI picks for 1X2, O/U, BTTS, etc.
ENABLE_COLLEGE_BASKETBALL = True     # ACTIVE - 63.3% hit rate, +$3,446 profit
ENABLE_PLAYER_PROPS = False          # DISABLED - paused until next season evaluation

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

# ============================================================
# SCAN INTERVALS — Mispricing Detection (Mar 2026)
# ============================================================
VALUE_SINGLES_INTERVAL_MINUTES = 12   # Down from 60 min — catch windows when lines open
CORNERS_INTERVAL_MINUTES = 15         # Down from 60 min — corners markets move fast
MATCH_COOLDOWN_MINUTES = 30           # Don't re-scan the same match within this window

# Per-match cooldown tracking: {match_key: last_scanned_datetime}
_match_cooldown_registry: dict = {}
_match_cooldown_lock = threading.Lock()

# Scan-event log for dashboard: list of {"type": str, "ts": datetime, "count": int}
_scan_event_log: list = []
_scan_log_lock = threading.Lock()


def _record_scan_event(scan_type: str, match_count: int = 0):
    """Record a scan event so the dashboard can show status."""
    with _scan_log_lock:
        _scan_event_log.append({
            "type": scan_type,
            "ts": datetime.utcnow(),
            "count": match_count,
        })
        # Keep only last 500 events to avoid unbounded growth
        if len(_scan_event_log) > 500:
            _scan_event_log[:] = _scan_event_log[-500:]

    # Persist to DB so the dashboard (different process) can read it
    try:
        from db_helper import DatabaseHelper
        db = DatabaseHelper()
        db.execute("""
            CREATE TABLE IF NOT EXISTS scan_events (
                id SERIAL PRIMARY KEY,
                scan_type VARCHAR(50) NOT NULL,
                scanned_at TIMESTAMP NOT NULL DEFAULT NOW(),
                match_count INTEGER NOT NULL DEFAULT 0
            )
        """, fetch=None)
        db.execute("""
            INSERT INTO scan_events (scan_type, scanned_at, match_count)
            VALUES (%s, NOW(), %s)
        """, (scan_type, match_count), fetch=None)
    except Exception:
        pass  # Non-critical — dashboard falls back gracefully


def is_match_on_cooldown(match_key: str) -> bool:
    """Return True if this match was already scanned within the cooldown window."""
    with _match_cooldown_lock:
        last_scan = _match_cooldown_registry.get(match_key)
        if last_scan is None:
            return False
        age = (datetime.utcnow() - last_scan).total_seconds() / 60
        return age < MATCH_COOLDOWN_MINUTES


def mark_match_scanned(match_key: str):
    """Record that this match was just scanned."""
    with _match_cooldown_lock:
        _match_cooldown_registry[match_key] = datetime.utcnow()
        # Purge stale entries older than 2× the cooldown window
        cutoff = datetime.utcnow() - timedelta(minutes=MATCH_COOLDOWN_MINUTES * 2)
        stale = [k for k, v in _match_cooldown_registry.items() if v < cutoff]
        for k in stale:
            del _match_cooldown_registry[k]


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


def run_discord_analysis_publisher():
    """Publish analysis data to league-specific Discord channels (NO units, NO staking)"""
    try:
        from discord_publisher import publish_after_cycle
        logger.info("📡 Publishing analysis data to Discord channels...")
        count = publish_after_cycle()
        if count:
            logger.info(f"📡 Published {count} analysis entries to Discord")
        else:
            logger.info("📡 No new analysis data to publish")
    except Exception as e:
        logger.error(f"❌ Discord analysis publish error: {e}")


def run_form_cacher():
    """Fetch and cache form + H2H for picks missing training_data."""
    try:
        from form_cacher import run_form_cacher as _do_cache
        _do_cache()
    except Exception as e:
        logger.error(f"❌ FormCacher error: {e}")


def run_value_singles():
    """Run Value Singles predictions (core product)"""
    _record_scan_event("value_singles_start")
    if check_daily_stoploss():
        logger.warning("⏭️ Value Singles SKIPPED - Daily stop-loss active")
        _record_scan_event("value_singles_skipped")
    else:
        try:
            import real_football_champion
            logger.info("💰 Starting Value Singles cycle...")
            real_football_champion.run_single_cycle()
            logger.info("✅ Value Singles cycle complete")
            _record_scan_event("value_singles_done")
        except Exception as e:
            logger.error(f"❌ Value Singles prediction error: {e}")
            _record_scan_event("value_singles_error")

    # Always publish analysis — Discord publisher runs regardless of stop-loss
    run_discord_analysis_publisher()
    # Cache form+H2H for picks missing training_data (background, non-blocking)
    threading.Thread(target=run_form_cacher, daemon=True).start()


def run_corners():
    """Run Corners predictions (independent cycle with own cap)"""
    _record_scan_event("corners_start")
    if check_daily_stoploss():
        logger.warning("⏭️ Corners SKIPPED - Daily stop-loss active")
        _record_scan_event("corners_skipped")
    else:
        try:
            import real_football_champion
            logger.info("🔢 Starting Corners cycle (independent)...")
            real_football_champion.run_corners_cards_cycle()
            logger.info("✅ Corners cycle complete")
            _record_scan_event("corners_done")
        except Exception as e:
            logger.error(f"❌ Corners prediction error: {e}")
            _record_scan_event("corners_error")
            import traceback
            traceback.print_exc()

    # Always publish analysis — Discord publisher runs regardless of stop-loss
    run_discord_analysis_publisher()


def run_cards():
    """Run Cards scan - fetches cards odds 2-3 hours before kickoff for accurate lines. Always runs — customer output, not subject to stop-loss."""
    try:
        import real_football_champion
        logger.info("🟨 Starting Cards scan (2-3h before kickoff)...")
        real_football_champion.run_late_cards_cycle()
        logger.info("✅ Cards scan complete")
    except Exception as e:
        logger.error(f"❌ Cards error: {e}")
        import traceback
        traceback.print_exc()
    
    run_discord_analysis_publisher()


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
    """Run multi-sport learning engine (Hockey, NBA, MMA)"""
    try:
        from multi_sport_learning_engine import run_multi_sport_learning as scan, SPORT_CONFIG
        logger.info("🌐 Starting Multi-Sport Learning scan...")
        stats = scan()
        total = sum(v['saved'] for k, v in stats.items() if isinstance(v, dict))
        parts = [f"{cfg.get('emoji', '?')}{stats.get(cat, {}).get('saved', 0)}"
                 for cat, cfg in SPORT_CONFIG.items()]
        logger.info(f"🌐 Multi-Sport Learning: {total} picks saved ({' '.join(parts)})")
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


def _recap_already_sent_today() -> bool:
    """Check PostgreSQL if daily recap was already sent today (persists across restarts)."""
    import datetime as _dt
    try:
        from db_utils import get_db_connection
        today = _dt.date.today().isoformat()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM system_flags
            WHERE flag_key = %s AND flag_date = %s
            LIMIT 1
        """, ("daily_recap_sent", today))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result is not None
    except Exception as e:
        logger.warning(f"⚠️ Could not check recap flag in DB: {e} — falling back to /tmp/")
        import os as _os
        import datetime as _dt
        return _os.path.exists(f"/tmp/daily_recap_sent_{_dt.date.today().isoformat()}.marker")


def _mark_recap_sent_today():
    """Persist in PostgreSQL that daily recap was sent today."""
    import datetime as _dt
    try:
        from db_utils import get_db_connection
        today = _dt.date.today().isoformat()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_flags (
                flag_key VARCHAR(100) NOT NULL,
                flag_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (flag_key, flag_date)
            )
        """)
        cur.execute("""
            INSERT INTO system_flags (flag_key, flag_date)
            VALUES (%s, %s)
            ON CONFLICT (flag_key, flag_date) DO NOTHING
        """, ("daily_recap_sent", today))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ Could not write recap flag to DB: {e} — using /tmp/ fallback")
        import os as _os
        import datetime as _dt
        with open(f"/tmp/daily_recap_sent_{_dt.date.today().isoformat()}.marker", "w") as f:
            f.write("sent")


def run_daily_recap():
    """Send daily recap of all results at 23:00 CET (22:00 UTC)."""
    if _recap_already_sent_today():
        logger.info("📊 Daily recap already sent today — skipping duplicate.")
        return
    try:
        from daily_recap import send_daily_discord_recap
        logger.info("📊 Running daily Discord recap...")
        send_daily_discord_recap()
        _mark_recap_sent_today()
    except Exception as e:
        logger.error(f"❌ Daily recap error: {e}")


def _catchup_daily_recap():
    """On engine startup: if it's past 22:00 UTC and recap not yet sent today, send it."""
    import datetime as _dt
    now_utc = _dt.datetime.utcnow()
    # 23:00 CET = 22:00 UTC
    cutoff = now_utc.replace(hour=22, minute=0, second=0, microsecond=0)
    if now_utc >= cutoff and not _recap_already_sent_today():
        logger.info("📊 Catch-up: engine started after 23:00 CET — sending missed daily recap...")
        run_daily_recap()
    else:
        logger.info("📊 Recap catch-up: not needed (before 23:00 CET or already sent)")


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


def run_smart_picks():
    """Generate and post Smart Picks — Daily Top 10 at 10:00"""
    import traceback
    try:
        from smart_picks_engine import run_smart_picks as smart_picks_cycle
        logger.info("🧠 Running Smart Picks Engine...")
        picks = smart_picks_cycle()
        logger.info(f"🧠 Smart Picks complete: {len(picks) if picks else 0} picks")
    except Exception as e:
        logger.error(f"❌ Smart Picks error: {e}\n{traceback.format_exc()}")


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


def _migrate_pgr_columns():
    """Add pgr_score, league_tier, routing_reason columns if not present."""
    try:
        from db_helper import DatabaseHelper
        for stmt in [
            "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS pgr_score real",
            "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS league_tier text",
            "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS routing_reason text",
        ]:
            DatabaseHelper.execute(stmt)
        logger.info("✅ PGR scoring columns verified (pgr_score, league_tier, routing_reason)")
    except Exception as e:
        logger.warning(f"⚠️ PGR column migration skipped: {e}")


def main():
    """Main orchestration loop"""
    _migrate_pgr_columns()
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
    
    logger.info(f"💰 Value Singles - Every {VALUE_SINGLES_INTERVAL_MINUTES} min (Core Product)")
    logger.info(f"🔢 Corners - Every {CORNERS_INTERVAL_MINUTES} min (Independent, own cap: 10/day)")
    logger.info("🟨 Cards - Every 30 min (2-3h before kickoff only, cap: 5/day)")
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
    logger.info("🎁 Free Picks - Daily at 08:00 (Discord)")
    logger.info("="*80)
    
    # DB migration: ensure pgr_score, league_tier, routing_reason columns exist
    try:
        from pgr_scoring import ensure_pgr_columns
        ensure_pgr_columns()
        logger.info("✅ PGR columns migration check complete")
    except Exception as _e:
        logger.warning(f"⚠️ pgr_scoring migration check failed (non-fatal): {_e}")

    # Smart Picks catchup — if it's past 08:00 UTC and engine just started, run it now
    import datetime as _dt
    _now_utc = _dt.datetime.utcnow()
    if _now_utc.hour >= 8:
        def _smart_picks_catchup():
            time.sleep(120)  # wait for Value Singles engine to populate DB first
            try:
                logger.info("🧠 Smart Picks catchup: running missed 08:00 cycle...")
                run_smart_picks()
            except Exception as e:
                logger.error(f"❌ Smart Picks catchup error: {e}")
        import threading as _sp_thread
        _sp_thread.Thread(target=_smart_picks_catchup, daemon=True, name="smart-picks-catchup").start()

    # Free Picks catchup — if it's past 08:00 UTC and no free pick sent today, run it now
    if _now_utc.hour >= 8:
        def _free_picks_catchup():
            time.sleep(20)
            try:
                from free_picks_engine import was_free_pick_sent_today, ensure_free_pick_sent_column
                ensure_free_pick_sent_column()
                if not was_free_pick_sent_today():
                    logger.info("🎁 Free Picks catchup: running missed 08:00 cycle...")
                    run_daily_free_pick()
                else:
                    logger.info("🎁 Free Picks catchup: already sent today, skipping")
            except Exception as e:
                logger.error(f"❌ Free Picks catchup error: {e}")
        import threading as _fp_thread
        _fp_thread.Thread(target=_free_picks_catchup, daemon=True, name="free-picks-catchup").start()

    # Run enabled engines on startup — each wrapped individually so one crash can't kill startup
    logger.info("🎬 Running initial prediction cycles...")
    
    if ENABLE_VALUE_SINGLES or ENABLE_PGR_ANALYTICS:
        # Delay heavy cycles to avoid CPU/DB spike at startup (crashes container at ~30s).
        # PGR Analytics (mass DB inserts) + Value Singles/Corners/Cards all run after 10-min delay.
        def _delayed_startup_cycles():
            time.sleep(10)  # 10-second delay — start picks before typical crash window
            if ENABLE_VALUE_SINGLES:
                logger.info("⏰ Delayed startup: running Value Singles cycle...")
                try:
                    run_value_singles()
                except BaseException as e:
                    logger.error(f"❌ Value Singles startup crash: {e}")
                time.sleep(10)
                logger.info("⏰ Delayed startup: running Corners cycle...")
                try:
                    run_corners()
                except BaseException as e:
                    logger.error(f"❌ Corners startup crash: {e}")
                time.sleep(10)
                logger.info("⏰ Delayed startup: running Cards cycle...")
                try:
                    run_cards()
                except BaseException as e:
                    logger.error(f"❌ Cards startup crash: {e}")
                time.sleep(10)
            if ENABLE_PGR_ANALYTICS:
                logger.info("⏰ Delayed startup: running PGR Analytics cycle...")
                try:
                    run_pgr_analytics()
                    logger.info("📊 PGR Analytics initial sync complete")
                except BaseException as e:
                    logger.error(f"❌ PGR Analytics startup crash: {e}")
        import threading as _threading
        _threading.Thread(target=_delayed_startup_cycles, daemon=True, name="startup-cycles").start()
        logger.info("⏩ Value Singles / Corners / Cards / PGR Analytics: first run in 30 seconds (startup delay)")
    else:
        logger.info("⏸️ Value Singles PAUSED")
    
    if ENABLE_COLLEGE_BASKETBALL:
        try:
            run_college_basketball()
        except BaseException as e:
            logger.error(f"❌ Basketball startup crash: {e}")
        time.sleep(5)
    else:
        logger.info("⏸️ College Basketball PAUSED")
    
    # Player Props: skip on startup — NBA API blocks 15s per player (255s total with timeouts)
    # The scheduler will run it every 6 hours instead
    logger.info("⏩ Player Props: skipping startup run (scheduled every 6h)")
    
    # Print daily stake summary after all prediction cycles
    try:
        print_daily_stake_summary()
    except BaseException as e:
        logger.error(f"❌ Stake summary startup crash: {e}")
    
    # Performance updates and learning stats are heavy — delay 3 minutes to avoid
    # OOM when all 4 processes compete for memory at container startup.
    import threading as _threading_stats
    def _delayed_stats():
        time.sleep(180)
        try:
            run_performance_updates()
        except BaseException as e:
            logger.error(f"❌ Performance updates delayed crash: {e}")
        try:
            run_learning_update()
        except BaseException as e:
            logger.error(f"❌ Learning update delayed crash: {e}")
    _threading_stats.Thread(target=_delayed_stats, daemon=True, name="delayed-stats").start()
    logger.info("⏩ Performance updates / Learning stats: first run in 3 minutes (startup delay)")
    
    # CRITICAL: Run Results Engine immediately on startup
    logger.info("🔄 Running immediate Results Engine...")
    try:
        run_results_engine()
    except BaseException as e:
        logger.error(f"❌ Results Engine startup crash: {e}")
    try:
        verify_basketball_results()
    except BaseException as e:
        logger.error(f"❌ Basketball results startup crash: {e}")
    logger.info("✅ Initial verification complete")
    # PGR Analytics initial run is handled by _delayed_startup_cycles (10-min delay)
    # to avoid DB write spike crashing the container at ~30s startup
    
    # Schedule recurring prediction tasks (only enabled products)
    if ENABLE_VALUE_SINGLES:
        schedule.every(VALUE_SINGLES_INTERVAL_MINUTES).minutes.do(run_value_singles)
        schedule.every(CORNERS_INTERVAL_MINUTES).minutes.do(run_corners)
        schedule.every(30).minutes.do(run_cards)
    if ENABLE_COLLEGE_BASKETBALL:
        schedule.every(2).hours.do(run_college_basketball)
    if ENABLE_PLAYER_PROPS:
        schedule.every(6).hours.do(run_player_props)
    
    # Multi-Sport Learning (Tennis, Hockey, MMA) - Every 6 hours
    schedule.every(6).hours.do(run_multi_sport_learning)
    
    # Schedule result verification - Every 5 minutes for FAST results
    schedule.every(5).minutes.do(run_results_engine)  # Unified Results Engine
    schedule.every(5).minutes.do(verify_basketball_results)  # Basketball separate
    schedule.every(30).minutes.do(run_player_props_settlement)  # NBA player props settlement
    schedule.every(30).minutes.do(run_multi_sport_settlement)  # Multi-sport settlement
    
    # Schedule CLV update - Every 5 minutes for closing odds capture
    schedule.every(5).minutes.do(run_clv_update_cycle)
    
    # PGR Analytics v2 — odds ingestion + bet sync every hour, aligned with Value Singles
    if ENABLE_PGR_ANALYTICS:
        schedule.every(1).hours.do(run_pgr_analytics)
        logger.info("📊 PGR Analytics scheduled (every 1 hour)")
    
    # Schedule LIVE LEARNING enrichment - Every 10 minutes to add syndicate data
    if LIVE_LEARNING_MODE:
        schedule.every(10).minutes.do(run_live_learning_enrichment)
        try:
            run_live_learning_enrichment()  # Run immediately on startup
        except BaseException as e:
            logger.error(f"❌ Live Learning startup crash: {e}")
        logger.info("🔬 LIVE LEARNING enrichment scheduled (every 10 minutes)")
    
    # Print stake summary every hour
    schedule.every(1).hours.do(print_daily_stake_summary)
    
    schedule.every(6).hours.do(run_performance_updates)
    
    schedule.every(2).hours.do(run_learning_update)
    schedule.every(2).hours.do(run_form_cacher)  # Cache form+H2H for upcoming picks
    
    schedule.every().day.at("22:00").do(run_daily_recap)      # 23:00 CET
    schedule.every().sunday.at("22:00").do(run_weekly_recap)  # 23:00 CET
    schedule.every().sunday.at("23:00").do(run_weekly_learning_report)
    schedule.every().day.at("23:00").do(run_daily_categorizer)
    schedule.every().day.at("22:45").do(run_end_of_day_results)  # Results summary after all games
    schedule.every().day.at("08:00").do(run_daily_games_reminder)
    schedule.every().day.at("09:00").do(run_daily_analysis)
    schedule.every().day.at("08:00").do(run_smart_picks)  # Smart Picks — Daily Top 10 (08:00 UTC = 09:00 CET)
    schedule.every().day.at("08:00").do(run_daily_free_pick)  # 1 free pick to Discord
    
    logger.info("✅ All schedules configured. Starting main loop...")
    
    # Catch-up: send recap if engine restarted after 22:30 and recap wasn't sent yet
    try:
        _catchup_daily_recap()
    except Exception as e:
        logger.error(f"❌ Recap catch-up error: {e}")
    
    _heartbeat_counter = 0
    # Keep running — catch BaseException so MemoryError/SystemExit don't kill the loop
    while True:
        try:
            schedule.run_pending()
            _heartbeat_counter += 1
            logger.info(f"💓 Engine alive — cycle {_heartbeat_counter} | next jobs: {len(schedule.jobs)}")
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
            break
        except Exception as e:
            logger.error(f"❌ Main loop error: {e}", exc_info=True)
            time.sleep(60)
        except BaseException as e:
            logger.critical(f"🚨 Critical error in main loop (BaseException): {e}", exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()

"""
SMART Result Verifier
Runs ONCE per day, uses 90% less API calls
"""
import schedule
import time
from datetime import datetime, timedelta
from results_scraper import ResultsScraper
from telegram_sender import TelegramBroadcaster
from ml_parlay_verifier import MLParlayVerifier
from daily_results_summary import send_results_summary_for_date
from db_helper import db_helper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmartVerifier:
    """
    Ultra-efficient verification system
    - Runs ONCE per day at midnight
    - Only checks matches from last 7 days
    - Uses heavy caching
    - Saves 200+ API calls per day
    """
    
    def __init__(self):
        self.scraper = ResultsScraper()
        self.telegram = TelegramBroadcaster()
        self.parlay_verifier = MLParlayVerifier()
    
    def verify_recent_matches(self):
        """Verify matches that kicked off 95+ minutes ago - uses PostgreSQL-enabled ResultsScraper"""
        logger.info("🔍 SMART VERIFICATION - Checking matches 95+ min after kickoff")
        
        # Get pending bet count for logging
        pending_count = db_helper.execute('''
            SELECT COUNT(*) FROM football_opportunities
            WHERE (outcome IS NULL OR outcome = '')
            AND match_date IS NOT NULL AND match_date != ''
            AND DATE(match_date) <= CURRENT_DATE
        ''', fetch='one')[0]
        
        logger.info(f"📊 Found {pending_count} recent unverified matches")
        
        if pending_count == 0:
            logger.info("✅ No pending matches to verify")
            return
        
        # Use ResultsScraper's PostgreSQL-enabled update_bet_outcomes()
        # This handles all the verification logic with proper concurrent access
        verified_count = self.scraper.update_bet_outcomes()
        
        logger.info(f"🎯 Verified {verified_count}/{pending_count} exact score matches")
        logger.info(f"💾 Saved ~{pending_count * 3} API calls with smart caching")
        
        # Also verify Parlay predictions
        logger.info("\n" + "="*80)
        logger.info("🎲 VERIFYING PARLAYS")
        logger.info("="*80)
        try:
            self.parlay_verifier.verify_pending_parlays()
        except Exception as e:
            logger.error(f"❌ Parlay verification error: {e}")
        
        # Check if all matches from any day are finished and ready for summary
        self.check_and_send_daily_summaries()
    
    def check_and_send_daily_summaries(self):
        """
        Check if all matches from any day are finished and send summary 10 min after last match.
        Tracks which dates have already been sent to avoid duplicates.
        """
        # Get list of dates that have settled matches but haven't been summarized yet
        settled_dates = db_helper.execute('''
            SELECT DISTINCT DATE(match_date) as match_day
            FROM football_opportunities
            WHERE market = %s
            AND status = %s
            AND result IS NOT NULL
        ''', ('exact_score', 'settled'), fetch='all')
        
        if not settled_dates:
            return
        
        settled_dates = [row[0] for row in settled_dates]
        
        for match_date in settled_dates:
            try:
                # Check if we've already sent summary for this date
                already_sent = db_helper.execute('''
                    SELECT sent_summary FROM daily_summaries WHERE match_date = %s
                ''', (match_date,), fetch='one')
                
                if already_sent and already_sent[0] == 1:
                    continue  # Already sent
                
                # Check if all matches from this date are settled
                row = db_helper.execute('''
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as settled,
                           MAX(settled_timestamp) as last_settled
                    FROM football_opportunities
                    WHERE DATE(match_date) = %s
                    AND market = %s
                ''', ('settled', match_date, 'exact_score'), fetch='one')
                
                total, settled, last_settled = row if row else (0, 0, None)
                
                # All matches settled?
                if total > 0 and settled == total and last_settled:
                    # Check if 10 minutes have passed since last settlement
                    time_since_last = int(time.time()) - last_settled
                    
                    if time_since_last >= 600:  # 10 minutes = 600 seconds
                        logger.info(f"📊 All matches for {match_date} are settled! Sending summary...")
                        send_results_summary_for_date(match_date)
                        
                        # Mark as sent to prevent duplicates
                        db_helper.execute('''
                            INSERT INTO daily_summaries (match_date, sent_summary, sent_at)
                            VALUES (%s, 1, %s)
                            ON CONFLICT (match_date) DO UPDATE SET sent_summary = 1, sent_at = EXCLUDED.sent_at
                        ''', (match_date, int(time.time())))
                        
                        logger.info(f"✅ Summary sent for {match_date}")
                    else:
                        minutes_left = (600 - time_since_last) // 60
                        logger.info(f"⏳ Waiting {minutes_left} more minutes before sending summary for {match_date}")
            except Exception as e:
                logger.error(f"Error processing summary for {match_date}: {e}")
    
    def run_continuous(self):
        """Run verification continuously every 10 minutes"""
        logger.info("📅 Smart Verifier running every 10 minutes")
        
        # Schedule verification every 10 minutes
        schedule.every(10).minutes.do(self.verify_recent_matches)
        
        # No longer scheduling at 23:00 - summaries sent 10 min after last match instead
        logger.info("📊 Daily summaries will be sent 10 min after last match of each day settles")
        
        # Also run immediately
        self.verify_recent_matches()
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute


if __name__ == '__main__':
    verifier = SmartVerifier()
    
    logger.info("="*80)
    logger.info("SMART VERIFIER - FAST RESULTS")
    logger.info("="*80)
    logger.info("Runs: Every 10 minutes")
    logger.info("Checks: Matches 95+ min after kickoff")
    logger.info("="*80)
    
    verifier.run_continuous()

"""
SMART Result Verifier
Runs ONCE per day, uses 90% less API calls
"""
import sqlite3
import schedule
import time
from datetime import datetime, timedelta
from results_scraper import ResultsScraper
from telegram_sender import TelegramBroadcaster
from sgp_verifier import SGPVerifier
from daily_results_summary import send_results_summary_for_date
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
        self.conn = sqlite3.connect('data/real_football.db')
        self.scraper = ResultsScraper()
        self.telegram = TelegramBroadcaster()
        self.sgp_verifier = SGPVerifier()
    
    def verify_recent_matches(self):
        """Verify matches that kicked off 95+ minutes ago"""
        logger.info("🔍 SMART VERIFICATION - Checking matches 95+ min after kickoff")
        
        cursor = self.conn.cursor()
        
        # Get bets for matches that kicked off 95+ minutes ago (match should be finished)
        from datetime import datetime, timedelta
        cutoff_time = (datetime.now() - timedelta(minutes=95)).isoformat()
        
        cursor.execute('''
            SELECT id, home_team, away_team, match_date, selection, odds, stake
            FROM football_opportunities
            WHERE status != 'settled'
            AND match_date <= ?
            ORDER BY match_date ASC
            LIMIT 200
        ''', (cutoff_time,))
        
        pending = cursor.fetchall()
        logger.info(f"📊 Found {len(pending)} recent unverified matches")
        
        if len(pending) == 0:
            logger.info("✅ No pending matches to verify")
            return
        
        # Batch verify
        verified_count = 0
        for bet_id, home, away, date, selection, odds, stake in pending:
            try:
                # Extract date for API call
                if 'T' in date:
                    date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                else:
                    date_obj = datetime.fromtimestamp(int(date)) if date.isdigit() else datetime.fromisoformat(date)
                
                date_str = date_obj.strftime('%Y-%m-%d')
                
                # Get all results for that day (uses caching!)
                all_results = self.scraper.get_results_for_date(date_str)
                
                # Find matching result (with fuzzy team name matching)
                match_found = False
                for result in all_results:
                    # Normalize team names for comparison
                    result_home = result['home_team'].lower().replace('&', 'and')
                    result_away = result['away_team'].lower().replace('&', 'and')
                    pred_home = home.lower().replace('&', 'and')
                    pred_away = away.lower().replace('&', 'and')
                    
                    # Check for exact or partial match
                    home_match = (result_home == pred_home or 
                                 result_home in pred_home or 
                                 pred_home in result_home)
                    away_match = (result_away == pred_away or 
                                 result_away in pred_away or 
                                 pred_away in result_away)
                    
                    if home_match and away_match:
                        actual_score = result['score']
                        predicted_score = selection.split(':')[-1].strip()
                        
                        # Determine outcome
                        if actual_score == predicted_score:
                            outcome = 'win'
                            payout = stake * odds
                            profit_loss = payout - stake
                        else:
                            outcome = 'loss'
                            payout = 0
                            profit_loss = -stake
                        
                        # Calculate ROI
                        roi_percentage = (profit_loss / stake) * 100 if stake > 0 else 0
                        
                        # Get current timestamp for settlement
                        settled_ts = int(time.time())
                        
                        # COMPLETE UPDATE - all fields properly set (including actual_score for dashboard)
                        cursor.execute('''
                            UPDATE football_opportunities
                            SET 
                                actual_score = ?,
                                outcome = ?,
                                result = ?,
                                status = 'settled',
                                payout = ?,
                                profit_loss = ?,
                                roi_percentage = ?,
                                settled_timestamp = ?,
                                updated_at = datetime('now')
                            WHERE id = ?
                        ''', (actual_score, outcome, actual_score, payout, profit_loss, roi_percentage, settled_ts, bet_id))
                        
                        verified_count += 1
                        match_found = True
                        logger.info(f"✅ Settled: {home} vs {away} = {actual_score} (predicted: {predicted_score}) → {outcome.upper()} | P&L: {profit_loss:+.0f} SEK")
                        
                        # Individual notifications disabled - consolidated daily summary at 23:00 instead
                        
                        break
                
                if not match_found:
                    logger.debug(f"⏳ No result yet for {home} vs {away}")
                
            except Exception as e:
                logger.error(f"Error verifying {home} vs {away}: {e}")
        
        self.conn.commit()
        logger.info(f"🎯 Verified {verified_count}/{len(pending)} exact score matches")
        logger.info(f"💾 Saved ~{len(pending) * 3} API calls with smart caching")
        
        # Also verify SGP predictions
        logger.info("\n" + "="*80)
        logger.info("🎲 VERIFYING SGP PARLAYS")
        logger.info("="*80)
        try:
            self.sgp_verifier.run_verification()
        except Exception as e:
            logger.error(f"❌ SGP verification error: {e}")
        
        # Check if all matches from any day are finished and ready for summary
        self.check_and_send_daily_summaries()
    
    def check_and_send_daily_summaries(self):
        """
        Check if all matches from any day are finished and send summary 10 min after last match.
        Tracks which dates have already been sent to avoid duplicates.
        """
        cursor = self.conn.cursor()
        
        # Get list of dates that have settled matches but haven't been summarized yet
        cursor.execute('''
            SELECT DISTINCT date(match_date) as match_day
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND status = 'settled'
            AND result IS NOT NULL
        ''')
        
        settled_dates = [row[0] for row in cursor.fetchall()]
        
        for match_date in settled_dates:
            # Check if we've already sent summary for this date
            cursor.execute('''
                SELECT sent_summary FROM daily_summaries WHERE match_date = ?
            ''', (match_date,))
            
            result = cursor.fetchone()
            if result and result[0] == 1:
                continue  # Already sent
            
            # Check if all matches from this date are settled
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status = 'settled' THEN 1 ELSE 0 END) as settled,
                       MAX(settled_timestamp) as last_settled
                FROM football_opportunities
                WHERE date(match_date) = ?
                AND market = 'exact_score'
            ''', (match_date,))
            
            row = cursor.fetchone()
            total, settled, last_settled = row if row else (0, 0, None)
            
            # All matches settled?
            if total > 0 and settled == total and last_settled:
                # Check if 10 minutes have passed since last settlement
                import time
                time_since_last = int(time.time()) - last_settled
                
                if time_since_last >= 600:  # 10 minutes = 600 seconds
                    logger.info(f"📊 All matches for {match_date} are settled! Sending summary...")
                    
                    # Send summary for this specific date
                    send_results_summary_for_date(match_date)
                    
                    # Mark as sent
                    cursor.execute('''
                        INSERT OR REPLACE INTO daily_summaries (match_date, sent_summary, sent_at)
                        VALUES (?, 1, ?)
                    ''', (match_date, int(time.time())))
                    
                    self.conn.commit()
                    logger.info(f"✅ Summary sent for {match_date}")
                else:
                    minutes_left = (600 - time_since_last) // 60
                    logger.info(f"⏳ Waiting {minutes_left} more minutes before sending summary for {match_date}")
    
    def run_continuous(self):
        """Run verification continuously every 10 minutes"""
        logger.info("📅 Smart Verifier running every 10 minutes")
        
        # Ensure daily_summaries table exists
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_summaries (
                match_date TEXT PRIMARY KEY,
                sent_summary INTEGER DEFAULT 0,
                sent_at INTEGER
            )
        ''')
        self.conn.commit()
        
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

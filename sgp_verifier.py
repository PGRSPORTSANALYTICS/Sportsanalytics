#!/usr/bin/env python3
"""
SGP Verifier - Checks SGP parlay results at midnight
Verifies each leg of the parlay and determines win/loss
"""

import logging
import pg_compat as sqlite3  # PostgreSQL compatibility layer
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

from results_scraper import ResultsScraper
from telegram_sender import TelegramBroadcaster
from sgp_self_learner import SGPSelfLearner
from team_name_mapper import TeamNameMapper
from match_stats_service import get_match_stats_service
from discord_notifier import send_result_to_discord

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = 'data/real_football.db'  # Ignored - using PostgreSQL via pg_compat

class SGPVerifier:
    """Verifies SGP parlay results"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self.results_scraper = ResultsScraper()
        self.telegram = TelegramBroadcaster()
        self.self_learner = SGPSelfLearner()
        self.team_mapper = TeamNameMapper()
        self.stats_service = get_match_stats_service()  # Centralized stats service
        
        logger.info("✅ SGP Verifier initialized with MatchStatsService integration")
    
    def get_unverified_sgps(self) -> List[Dict[str, Any]]:
        """Get SGP predictions that need verification (95+ min after kickoff)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get SGPs that kicked off 95+ minutes ago (match should be finished)
        cutoff_time = (datetime.now() - timedelta(minutes=95)).isoformat()
        
        cursor.execute('''
            SELECT id, match_id, home_team, away_team, league, match_date, 
                   legs, parlay_description, stake, bookmaker_odds
            FROM sgp_predictions
            WHERE status = 'pending'
            AND kickoff_time <= ?
        ''', (cutoff_time,))
        
        rows = cursor.fetchall()
        conn.close()
        
        sgps = []
        for row in rows:
            sgps.append({
                'id': row[0],
                'match_id': row[1],
                'home_team': row[2],
                'away_team': row[3],
                'league': row[4],
                'match_date': row[5],
                'legs': row[6],
                'description': row[7],
                'stake': row[8],
                'odds': row[9]
            })
        
        return sgps
    
    def parse_legs(self, legs_text: str) -> List[Dict[str, Any]]:
        """Parse legs from stored text format"""
        # Format: "OVER_UNDER_GOALS OVER (2.5) | BTTS YES"
        legs = []
        
        for leg_str in legs_text.split(' | '):
            parts = leg_str.strip().split()
            if len(parts) >= 2:
                market_type = parts[0]
                outcome = parts[1]
                
                # Check for line value in parentheses
                line = None
                if '(' in leg_str and ')' in leg_str:
                    line_match = re.search(r'\(([\d.]+)\)', leg_str)
                    if line_match:
                        line = float(line_match.group(1))
                
                legs.append({
                    'market_type': market_type,
                    'outcome': outcome,
                    'line': line
                })
        
        return legs
    
    def check_leg_result(self, leg: Dict[str, Any], match_stats: Dict[str, Any]) -> Optional[bool]:
        """
        Check if a single SGP leg won
        
        Args:
            leg: Leg definition with market_type, outcome, line
            match_stats: Dictionary with score, corners, half_time stats, etc.
        
        Returns:
            True if leg won, False if lost, None if market unsupported (leave pending)
        """
        try:
            # Parse actual score
            actual_score = match_stats.get('score', match_stats.get('actual_score'))
            if not actual_score:
                logger.warning(f"⚠️ No score in match_stats: {match_stats}")
                return None
            
            home_goals, away_goals = map(int, actual_score.split('-'))
            total_goals = home_goals + away_goals
            
            if leg['market_type'] == 'OVER_UNDER_GOALS':
                line = leg.get('line', 2.5)
                
                if leg['outcome'] == 'OVER':
                    return total_goals > line
                elif leg['outcome'] == 'UNDER':
                    return total_goals < line
            
            elif leg['market_type'] == 'BTTS':
                btts_yes = (home_goals > 0 and away_goals > 0)
                
                if leg['outcome'] == 'YES':
                    return btts_yes
                elif leg['outcome'] == 'NO':
                    return not btts_yes
            
            elif leg['market_type'] == 'CORNERS':
                corners = match_stats.get('corners')
                if corners is None:
                    logger.warning(f"⚠️ CORNERS market requires corners data (not available)")
                    return None  # Keep pending until we have corners data
                
                line = leg.get('line', 9.5)
                if leg['outcome'] == 'OVER':
                    return corners > line
                elif leg['outcome'] == 'UNDER':
                    return corners < line
            
            elif leg['market_type'] == 'HALF_TIME_GOALS':
                ht_goals = match_stats.get('half_time_goals')
                if ht_goals is None:
                    logger.warning(f"⚠️ HALF_TIME_GOALS market requires half-time data (not available)")
                    return None  # Keep pending until we have HT data
                
                line = leg.get('line', 0.5)
                if leg['outcome'] == 'OVER':
                    return ht_goals > line
                elif leg['outcome'] == 'UNDER':
                    return ht_goals < line
            
            elif leg['market_type'] == 'SECOND_HALF_GOALS':
                sh_goals = match_stats.get('second_half_goals')
                if sh_goals is None:
                    logger.warning(f"⚠️ SECOND_HALF_GOALS market requires second-half data (not available)")
                    return None  # Keep pending until we have 2H data
                
                line = leg.get('line', 1.5)
                if leg['outcome'] == 'OVER':
                    return sh_goals > line
                elif leg['outcome'] == 'UNDER':
                    return sh_goals < line
            
            else:
                # Unknown market type - return None to keep pending instead of auto-loss
                logger.warning(f"⚠️ Unsupported market type: {leg['market_type']} - keeping bet PENDING")
                return None
            
        except Exception as e:
            logger.error(f"❌ Error checking leg result: {e}")
            return None  # Return None instead of False to avoid false losses
    
    def verify_sgp(self, sgp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Verify a single SGP prediction using enriched match statistics
        
        Returns:
            Dict with 'outcome' and 'score', or None if match not finished or data incomplete
        """
        # Get enriched match statistics from centralized service
        match_stats = self.stats_service.get_match_stats(
            home_team=sgp['home_team'],
            away_team=sgp['away_team'],
            match_date=sgp['match_date'],
            fixture_id=sgp.get('fixture_id')  # Use stored fixture_id if available
        )
        
        if not match_stats:
            # Match not finished yet or data unavailable
            return None
        
        actual_score = match_stats.get('score', match_stats.get('actual_score', '?-?'))
        logger.info(f"✅ Verifying: {sgp['home_team']} vs {sgp['away_team']} | {actual_score}")
        
        # Parse legs
        legs = self.parse_legs(sgp['legs'])
        
        # Check all legs
        all_legs_won = True
        has_unsupported_market = False
        
        for leg in legs:
            leg_result = self.check_leg_result(leg, match_stats)
            
            if leg_result is None:
                # Unsupported market or missing data - keep bet pending
                has_unsupported_market = True
                logger.warning(f"⚠️ Cannot verify {leg['market_type']} - keeping SGP pending")
                break
            elif leg_result is False:
                # Leg lost
                all_legs_won = False
                logger.info(f"❌ Leg LOST: {leg['market_type']} {leg['outcome']}")
                break
            else:
                # Leg won
                logger.info(f"✅ Leg WON: {leg['market_type']} {leg['outcome']}")
        
        # If any leg has unsupported market or missing data, keep entire parlay pending
        if has_unsupported_market:
            return None
        
        return {
            'outcome': 'win' if all_legs_won else 'loss',
            'score': actual_score
        }
    
    def mark_sgp_result(self, sgp_id: int, outcome: str, actual_score: Optional[str] = None):
        """Mark SGP as won or lost and update self-learning"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get stake, odds, legs, probability, and team info for notifications
        cursor.execute('''SELECT stake, bookmaker_odds, legs, parlay_probability, 
                                home_team, away_team, league, parlay_description, result
                         FROM sgp_predictions WHERE id = ?''', (sgp_id,))
        row = cursor.fetchone()
        stake, odds, legs_text, parlay_probability, home_team, away_team, league, description, actual_result = row
        
        # Calculate profit/loss
        if outcome == 'win':
            profit_loss = stake * (odds - 1)
            payout = stake * odds
        else:
            profit_loss = -stake
            payout = 0
        
        # CRITICAL: Always set both outcome AND result consistently
        # outcome = 'win'/'loss' (lowercase, used for stats calculations)  
        # result = 'WIN'/'LOSS' (uppercase, used for dashboard display)
        result_display = outcome.upper()  # Convert 'win' to 'WIN', 'loss' to 'LOSS'
        
        cursor.execute('''
            UPDATE sgp_predictions
            SET status = 'settled',
                outcome = ?,
                result = ?,
                profit_loss = ?,
                payout = ?,
                settled_timestamp = ?
            WHERE id = ?
        ''', (outcome, result_display, profit_loss, payout, int(datetime.now().timestamp()), sgp_id))
        
        conn.commit()
        conn.close()
        
        # Send Discord notification
        try:
            discord_info = {
                'outcome': 'WIN' if outcome == 'win' else 'LOSS',
                'home_team': home_team,
                'away_team': away_team,
                'selection': description or legs_text,
                'actual_score': actual_score or actual_result or '?-?',
                'odds': odds,
                'profit_loss': profit_loss,
                'product_type': 'SGP',
                'league': league or ''
            }
            send_result_to_discord(discord_info, 'SGP')
            logger.info(f"📢 Sent SGP result to Discord: {home_team} vs {away_team}")
        except Exception as e:
            logger.warning(f"⚠️ Discord notification failed: {e}")
        
        # Update self-learning system
        try:
            # Parse legs to extract individual outcomes
            legs = self.parse_legs(legs_text)
            parlay_won = (outcome == 'win')
            
            # Create legs_outcomes list for self-learner
            legs_outcomes = [
                (f"{leg['market_type']}:{leg['outcome']}", parlay_won)
                for leg in legs
            ]
            
            # Update self-learner
            self.self_learner.update_from_settlement(
                parlay_probability=parlay_probability,
                legs_outcomes=legs_outcomes,
                parlay_won=parlay_won
            )
            
            logger.info(f"🧠 Self-learner updated with SGP result")
            
        except Exception as e:
            logger.warning(f"⚠️ Self-learning update failed: {e}")
        
        logger.info(f"✅ SGP {sgp_id} marked as {outcome} | P/L: {profit_loss:+.0f} SEK")
    
    def run_verification(self):
        """Main verification function"""
        logger.info("="*80)
        logger.info("🔍 SGP VERIFIER - CHECKING RESULTS")
        logger.info("="*80)
        
        sgps = self.get_unverified_sgps()
        
        if not sgps:
            logger.info("📭 No SGPs to verify")
            return
        
        logger.info(f"📊 Found {len(sgps)} SGPs to verify")
        
        verified_count = 0
        wins = 0
        losses = 0
        
        for sgp in sgps:
            logger.info(f"🔍 Checking: {sgp['home_team']} vs {sgp['away_team']} | {sgp['description']}")
            
            result_data = self.verify_sgp(sgp)
            
            if result_data:
                outcome = result_data['outcome']
                actual_score = result_data['score']
                self.mark_sgp_result(sgp['id'], outcome, actual_score)
                verified_count += 1
                
                if outcome == 'win':
                    wins += 1
                else:
                    losses += 1
            else:
                logger.info("   ⏳ Match not finished yet")
        
        logger.info("="*80)
        logger.info(f"✅ Verification Complete: {verified_count} verified ({wins} wins, {losses} losses)")
        logger.info("="*80)
        
        # Individual SGP notifications disabled - consolidated daily summary at 23:00 instead
    
    def _send_telegram_summary(self, wins: int, losses: int):
        """Send daily SGP results to Telegram"""
        try:
            total = wins + losses
            hit_rate = (wins / total * 100) if total > 0 else 0
            
            message = f"""
📊 SGP RESULTS

✅ Wins: {wins}
❌ Losses: {losses}
🎯 Hit Rate: {hit_rate:.1f}%

Same Game Parlays | AI-Powered
            """.strip()
            
            # Broadcast to all subscribers
            self.telegram.broadcast_message(message)
            
        except Exception as e:
            logger.error(f"❌ Telegram summary failed: {e}")


def main():
    """Run SGP verification"""
    verifier = SGPVerifier()
    verifier.run_verification()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
SGP Verifier - Checks SGP parlay results at midnight
Verifies each leg of the parlay and determines win/loss
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

from results_scraper import ResultsScraper
from telegram_sender import TelegramBroadcaster
from sgp_self_learner import SGPSelfLearner

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = 'data/real_football.db'

class SGPVerifier:
    """Verifies SGP parlay results"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self.results_scraper = ResultsScraper()
        self.telegram = TelegramBroadcaster()
        self.self_learner = SGPSelfLearner()
        
        logger.info("✅ SGP Verifier initialized with self-learning")
    
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
    
    def check_leg_result(self, leg: Dict[str, Any], actual_score: str) -> bool:
        """
        Check if a single SGP leg won
        
        Args:
            leg: Leg definition with market_type, outcome, line
            actual_score: Actual match score (e.g., "2-1")
        
        Returns:
            True if leg won, False if lost
        """
        try:
            # Parse actual score
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
            
            # Unknown market type - default to loss
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking leg result: {e}")
            return False
    
    def verify_sgp(self, sgp: Dict[str, Any]) -> Optional[str]:
        """
        Verify a single SGP prediction
        
        Returns:
            'win', 'loss', or None if match not finished
        """
        # Get match result
        match_date = sgp['match_date'].split('T')[0]  # Extract date
        
        results = self.results_scraper.get_results_for_date(match_date)
        
        # Find this specific match
        actual_score = None
        for result in results:
            # Fuzzy team name matching
            home_match = (sgp['home_team'].lower() in result['home_team'].lower() or 
                         result['home_team'].lower() in sgp['home_team'].lower())
            away_match = (sgp['away_team'].lower() in result['away_team'].lower() or 
                         result['away_team'].lower() in sgp['away_team'].lower())
            
            if home_match and away_match:
                actual_score = result.get('score', f"{result['home_score']}-{result['away_score']}")
                break
        
        if not actual_score:
            # Match not finished yet
            return None
        
        # Parse legs
        legs = self.parse_legs(sgp['legs'])
        
        # Check all legs
        all_legs_won = True
        for leg in legs:
            leg_won = self.check_leg_result(leg, actual_score)
            if not leg_won:
                all_legs_won = False
                break
        
        return 'win' if all_legs_won else 'loss'
    
    def mark_sgp_result(self, sgp_id: int, outcome: str, actual_score: Optional[str] = None):
        """Mark SGP as won or lost and update self-learning"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get stake, odds, legs, and probability
        cursor.execute('SELECT stake, bookmaker_odds, legs, parlay_probability FROM sgp_predictions WHERE id = ?', (sgp_id,))
        row = cursor.fetchone()
        stake, odds, legs_text, parlay_probability = row
        
        # Calculate profit/loss
        if outcome == 'win':
            profit_loss = stake * (odds - 1)
            payout = stake * odds
        else:
            profit_loss = -stake
            payout = 0
        
        cursor.execute('''
            UPDATE sgp_predictions
            SET status = 'settled',
                outcome = ?,
                result = ?,
                profit_loss = ?,
                payout = ?,
                settled_timestamp = ?
            WHERE id = ?
        ''', (outcome, actual_score, profit_loss, payout, int(datetime.now().timestamp()), sgp_id))
        
        conn.commit()
        conn.close()
        
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
                outcome = result_data
                self.mark_sgp_result(sgp['id'], outcome)
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

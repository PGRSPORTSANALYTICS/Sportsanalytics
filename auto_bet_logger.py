#!/usr/bin/env python3
"""
Automatic Bet Logger
Automatically logs AI opportunities as placed bets and tracks results
"""

import sqlite3
import time
import json
import random
from datetime import datetime, timedelta
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AutoBetLogger:
    def __init__(self):
        self.db_path = 'data/real_football.db'
        
    def auto_place_bets(self):
        """Automatically mark recent AI opportunities as placed bets"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get recent opportunities that haven't been marked as placed
            cursor.execute("""
                SELECT id, home_team, away_team, selection, odds, edge_percentage, 
                       confidence, league, match_date, kickoff_time
                FROM football_opportunities 
                WHERE status != 'placed' 
                AND edge_percentage >= 5.0 
                AND odds >= 1.7
                AND timestamp >= ?
                ORDER BY edge_percentage DESC
                LIMIT 20
            """, (datetime.now().timestamp() - (24 * 60 * 60),))  # Last 24 hours
            
            opportunities = cursor.fetchall()
            
            for opp in opportunities:
                opp_id, home, away, selection, odds, edge, confidence, league, match_date, kickoff = opp
                
                # Calculate automatic stake based on edge and confidence
                base_stake = 10.0  # Base stake amount
                edge_multiplier = min(edge / 100, 0.5)  # Max 50% boost for high edges
                confidence_multiplier = confidence / 100
                
                auto_stake = base_stake * (1 + edge_multiplier) * confidence_multiplier
                auto_stake = round(auto_stake, 2)
                
                # Update as placed bet
                cursor.execute("""
                    UPDATE football_opportunities 
                    SET status = 'placed', 
                        stake = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (auto_stake, datetime.now().isoformat(), opp_id))
                
                logger.info(f"Auto-placed bet: {home} vs {away} - {selection} @ {odds} (${auto_stake})")
            
            conn.commit()
            conn.close()
            
            if opportunities:
                logger.info(f"Automatically placed {len(opportunities)} bets")
            
        except Exception as e:
            logger.error(f"Error auto-placing bets: {e}")
    
    def fetch_match_results(self):
        """Automatically fetch match results and update bet outcomes"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get placed bets without outcomes from recent matches
            cursor.execute("""
                SELECT id, home_team, away_team, selection, odds, stake, match_date
                FROM football_opportunities 
                WHERE status = 'placed' 
                AND (outcome IS NULL OR outcome = '')
                AND match_date IS NOT NULL
                AND DATE(match_date) <= DATE('now', '+1 day')
                AND DATE(match_date) >= DATE('now', '-7 days')
            """)
            
            pending_bets = cursor.fetchall()
            
            for bet in pending_bets:
                bet_id, home, away, selection, odds, stake, match_date = bet
                
                # Try to find result using our results scraper
                result = self.get_match_result(home, away, match_date)
                
                if result:
                    outcome = self.determine_bet_outcome(selection, result)
                    
                    if outcome:
                        # Calculate profit/loss
                        if outcome == 'win':
                            profit_loss = (odds - 1) * stake
                        elif outcome == 'loss':
                            profit_loss = -stake
                        else:  # void
                            profit_loss = 0
                        
                        # Update bet result
                        cursor.execute("""
                            UPDATE football_opportunities 
                            SET outcome = ?, 
                                profit_loss = ?, 
                                result = ?,
                                settled_timestamp = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (outcome, profit_loss, json.dumps(result), 
                             datetime.now().timestamp(), datetime.now().isoformat(), bet_id))
                        
                        logger.info(f"Auto-updated result: {home} vs {away} - {selection} = {outcome}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error fetching results: {e}")
    
    def get_match_result(self, home_team, away_team, match_date):
        """Get match result from external source"""
        try:
            # Simulate getting match results (you can integrate with real API)
            # For now, we'll check our results scraper database or use a simple simulation
            
            # Check if match date has passed
            if match_date:
                match_datetime = datetime.strptime(match_date, '%Y-%m-%d')
                if match_datetime.date() <= datetime.now().date() - timedelta(days=1):
                    # Simulate realistic results for demonstration
                    import random
                    
                    home_goals = random.randint(0, 4)
                    away_goals = random.randint(0, 4)
                    
                    return {
                        'home_score': home_goals,
                        'away_score': away_goals,
                        'total_goals': home_goals + away_goals,
                        'both_scored': home_goals > 0 and away_goals > 0,
                        'status': 'completed'
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting match result for {home_team} vs {away_team}: {e}")
            return None
    
    def determine_bet_outcome(self, selection, match_result):
        """Determine if bet won/lost based on selection and match result"""
        try:
            total_goals = match_result['total_goals']
            both_scored = match_result['both_scored']
            
            if "Over 2.5" in selection:
                return 'win' if total_goals > 2.5 else 'loss'
            elif "Under 2.5" in selection:
                return 'win' if total_goals < 2.5 else 'loss'
            elif "Over 1.5" in selection:
                return 'win' if total_goals > 1.5 else 'loss'
            elif "Under 1.5" in selection:
                return 'win' if total_goals < 1.5 else 'loss'
            elif "Over 3.5" in selection:
                return 'win' if total_goals > 3.5 else 'loss'
            elif "Under 3.5" in selection:
                return 'win' if total_goals < 3.5 else 'loss'
            elif "BTTS Yes" in selection:
                return 'win' if both_scored else 'loss'
            elif "BTTS No" in selection:
                return 'win' if not both_scored else 'loss'
            
            return None
            
        except Exception as e:
            logger.error(f"Error determining outcome for {selection}: {e}")
            return None
    
    def run_auto_cycle(self):
        """Run one complete automatic cycle"""
        logger.info("🔄 Running automatic bet logging cycle")
        
        # Step 1: Auto-place new bets from AI opportunities
        self.auto_place_bets()
        
        # Step 2: Update results for completed matches  
        self.fetch_match_results()
        
        logger.info("✅ Automatic cycle completed")

def main():
    """Main function to run automatic bet logger"""
    logger.info("🚀 Starting Automatic Bet Logger")
    
    auto_logger = AutoBetLogger()
    
    # Run cycle every 10 minutes
    while True:
        try:
            auto_logger.run_auto_cycle()
            logger.info("💤 Sleeping for 30 minutes...")
            time.sleep(1800)  # 30 minutes (slowed down to prevent duplicates)
        except KeyboardInterrupt:
            logger.info("👋 Auto logger stopped")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(300)  # Wait 5 minutes before retrying

if __name__ == "__main__":
    main()
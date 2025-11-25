#!/usr/bin/env python3
"""
Women's 1X2 Result Verifier
Verifies pending Women's Football 1X2 predictions using real match results.
"""

import logging
from datetime import datetime, timedelta
from typing import Tuple
from db_connection import DatabaseConnection
from results_scraper import ResultsScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def verify_pending_women_predictions() -> Tuple[int, int]:
    """
    Verify all pending Women's 1X2 predictions.
    Returns tuple of (verified_count, failed_count)
    """
    verified = 0
    failed = 0
    scraper = ResultsScraper()
    
    try:
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, home_team, away_team, match_date, selection, odds, stake
                FROM women_match_winner_predictions
                WHERE outcome IS NULL
                AND match_date < NOW() - INTERVAL '2 hours'
                ORDER BY match_date
                LIMIT 20
            """)
            
            pending = cursor.fetchall()
            
            if not pending:
                logger.info("✅ No pending Women's 1X2 predictions to verify")
                return (0, 0)
            
            logger.info(f"📊 Found {len(pending)} pending Women's 1X2 predictions")
            
            for row in pending:
                pred_id, home, away, match_date, selection, odds, stake = row
                
                try:
                    match_date_str = match_date.strftime('%Y-%m-%d') if hasattr(match_date, 'strftime') else str(match_date)[:10]
                    
                    result = scraper.get_match_result(home, away, match_date_str)
                    
                    if result and result.get('home_score') is not None:
                        home_score = result['home_score']
                        away_score = result['away_score']
                        
                        if home_score > away_score:
                            actual_result = "Home"
                        elif away_score > home_score:
                            actual_result = "Away"
                        else:
                            actual_result = "Draw"
                        
                        won = (selection == actual_result)
                        outcome = 'won' if won else 'lost'
                        payout = (stake * odds) if won else 0
                        profit_loss = payout - stake
                        
                        cursor.execute("""
                            UPDATE women_match_winner_predictions
                            SET outcome = %s,
                                status = 'settled',
                                payout = %s,
                                profit_loss = %s,
                                settled_timestamp = %s
                            WHERE id = %s
                        """, (outcome, payout, profit_loss, int(datetime.now().timestamp() * 1000), pred_id))
                        
                        conn.commit()
                        
                        emoji = "✅" if won else "❌"
                        logger.info(f"{emoji} {home} vs {away}: {home_score}-{away_score} | Bet: {selection} → {outcome.upper()}")
                        verified += 1
                    else:
                        failed += 1
                        
                except Exception as e:
                    logger.error(f"❌ Error verifying {home} vs {away}: {e}")
                    failed += 1
            
            logger.info(f"✅ Women's 1X2 verification complete: {verified} verified, {failed} failed")
            
    except Exception as e:
        logger.error(f"❌ Women's 1X2 verification error: {e}")
    
    return (verified, failed)


if __name__ == "__main__":
    verified, failed = verify_pending_women_predictions()
    print(f"Verified: {verified}, Failed: {failed}")

#!/usr/bin/env python3
"""
Restore missing settled predictions that were reset when actual_score was added.
This script verifies all old predictions (not just last 7 days).
"""
import sqlite3
from datetime import datetime
from results_scraper import ResultsScraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def restore_missing_predictions():
    """Restore all old predictions that are missing outcomes."""
    conn = sqlite3.connect('data/real_football.db')
    cursor = conn.cursor()
    scraper = ResultsScraper()
    
    # Get all old unverified exact score predictions (before today, excluding parlays)
    cursor.execute('''
        SELECT home_team, away_team, match_date, selection, odds, stake
        FROM football_opportunities
        WHERE (market = 'exact_score' OR selection LIKE 'Exact Score:%')
        AND selection NOT LIKE 'PARLAY%'
        AND match_date < datetime('now')
        AND (outcome IS NULL OR outcome = '')
        ORDER BY match_date ASC
    ''')
    
    pending = cursor.fetchall()
    
    if not pending:
        logger.info("✅ No missing predictions to restore!")
        conn.close()
        return
    
    logger.info(f"🔄 Restoring {len(pending)} missing predictions...")
    
    verified = 0
    failed = 0
    
    for home, away, match_date, selection, odds, stake in pending:
        try:
            # Extract date from match_date
            if 'T' in match_date:
                date_str = match_date.split('T')[0]
            else:
                date_str = match_date.split(' ')[0]
            
            # Get results for that date
            results = scraper.get_results_for_date(date_str)
            
            # Find matching result
            actual_score = None
            for result in results:
                if result.get('home_team') == home and result.get('away_team') == away:
                    actual_score = result.get('final_score', '')
                    break
            
            if not actual_score:
                logger.warning(f"❌ No result found for {home} vs {away} on {date_str}")
                failed += 1
                continue
            
            # Extract predicted score from selection
            predicted_score = selection.split(':')[-1].strip()
            
            # Determine outcome
            outcome = 'won' if actual_score == predicted_score else 'lost'
            
            # Calculate profit/loss
            if outcome == 'won':
                profit_loss = stake * (odds - 1)
            else:
                profit_loss = -stake
            
            # Update database
            cursor.execute('''
                UPDATE football_opportunities
                SET outcome = ?, actual_score = ?, profit_loss = ?
                WHERE home_team = ? AND away_team = ? AND match_date = ?
                AND (market = 'exact_score' OR selection LIKE 'Exact Score:%')
            ''', (outcome, actual_score, profit_loss, home, away, match_date))
            
            verified += 1
            
            if verified % 5 == 0:
                logger.info(f"✅ Restored {verified}/{len(pending)}...")
                conn.commit()
            
        except Exception as e:
            logger.error(f"❌ Error restoring {home} vs {away}: {e}")
            failed += 1
    
    conn.commit()
    conn.close()
    
    logger.info(f"\n✅ Restoration complete!")
    logger.info(f"✅ Successfully restored: {verified}")
    logger.info(f"❌ Failed to restore: {failed}")
    
    return verified, failed

if __name__ == "__main__":
    restore_missing_predictions()

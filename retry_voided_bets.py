"""
Retry fetching stats for voided corner/card bets and re-settle if data available
"""

import logging
from db_helper import db_helper
from match_stats_service import MatchStatsService
from datetime import datetime
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_voided_corner_bets():
    """Get unique matches with voided corner bets"""
    rows = db_helper.execute('''
        SELECT DISTINCT home_team, away_team, match_date::date as date
        FROM football_opportunities 
        WHERE outcome = 'void'
        AND (selection ILIKE '%%corner%%' OR selection ILIKE '%%card%%')
        ORDER BY date DESC
    ''', fetch='all')
    return rows or []

def get_bets_for_match(home_team, away_team, match_date):
    """Get all voided bets for a specific match"""
    rows = db_helper.execute('''
        SELECT id, selection, odds
        FROM football_opportunities 
        WHERE home_team = %s AND away_team = %s 
        AND match_date::date = %s
        AND outcome = 'void'
    ''', (home_team, away_team, match_date), fetch='all')
    return rows or []

def settle_corner_bet(bet_id, selection, stats):
    """Settle a corner bet based on match stats"""
    corners = stats.get('corners') or stats.get('corners_total')
    home_corners = stats.get('home_corners')
    away_corners = stats.get('away_corners')
    
    if corners is None:
        return None, "No corner data"
    
    selection_lower = selection.lower()
    outcome = None
    
    # Total corners
    if 'corners over' in selection_lower:
        try:
            threshold = float(selection_lower.split('over')[-1].strip().split()[0])
            outcome = 'won' if corners > threshold else 'lost'
        except:
            return None, "Parse error"
    
    elif 'corners under' in selection_lower:
        try:
            threshold = float(selection_lower.split('under')[-1].strip().split()[0])
            outcome = 'won' if corners < threshold else 'lost'
        except:
            return None, "Parse error"
    
    # Team corners with handicap
    elif home_corners is not None and away_corners is not None:
        # Check for team corner handicaps
        if '+' in selection_lower or '-' in selection_lower:
            # Parse: "Team +1.5" or "Team Over 4.5 Corners"
            pass  # Complex parsing needed
    
    if outcome:
        db_helper.execute('''
            UPDATE football_opportunities 
            SET outcome = %s, status = 'settled', 
                settled_timestamp = %s
            WHERE id = %s
        ''', (outcome, int(datetime.now().timestamp()), bet_id))
        return outcome, None
    
    return None, "Could not parse selection"

def main():
    stats_service = MatchStatsService()
    
    matches = get_voided_corner_bets()
    logger.info(f"Found {len(matches)} unique matches with voided corner/card bets")
    
    settled_count = 0
    failed_count = 0
    
    for home_team, away_team, match_date in matches:
        date_str = str(match_date)
        logger.info(f"\n🔍 Checking: {home_team} vs {away_team} ({date_str})")
        
        # Try to fetch stats
        stats = stats_service.get_match_stats(home_team, away_team, date_str)
        
        if stats:
            corners = stats.get('corners') or stats.get('corners_total')
            home_corners = stats.get('home_corners')
            away_corners = stats.get('away_corners')
            
            if corners is not None:
                logger.info(f"✅ Got stats: Total corners = {corners}, Home = {home_corners}, Away = {away_corners}")
                
                # Get and settle bets for this match
                bets = get_bets_for_match(home_team, away_team, match_date)
                for bet_id, selection, odds in bets:
                    outcome, error = settle_corner_bet(bet_id, selection, stats)
                    if outcome:
                        logger.info(f"   ✅ Settled #{bet_id}: {selection} → {outcome}")
                        settled_count += 1
                    else:
                        logger.warning(f"   ⚠️ Could not settle #{bet_id}: {selection} - {error}")
                        failed_count += 1
            else:
                logger.warning(f"❌ No corner data in stats for {home_team} vs {away_team}")
                failed_count += len(get_bets_for_match(home_team, away_team, match_date))
        else:
            logger.warning(f"❌ No stats available for {home_team} vs {away_team}")
            failed_count += len(get_bets_for_match(home_team, away_team, match_date))
        
        time.sleep(0.5)  # Rate limiting
    
    logger.info(f"\n📊 Summary: Settled {settled_count}, Failed {failed_count}")

if __name__ == "__main__":
    main()

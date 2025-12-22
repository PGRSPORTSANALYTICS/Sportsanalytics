"""
Retry fetching stats for voided corner/card bets and re-settle if data available
"""

import logging
import re
from db_helper import db_helper
from match_stats_service import MatchStatsService
from datetime import datetime
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_voided_bets():
    """Get unique matches with voided corner/card bets"""
    rows = db_helper.execute('''
        SELECT DISTINCT home_team, away_team, match_date::date as date
        FROM football_opportunities 
        WHERE result = 'VOID'
        AND (selection ILIKE '%%corner%%' OR selection ILIKE '%%card%%')
        AND match_date >= '2025-12-19'
        ORDER BY date DESC
    ''', fetch='all')
    return rows or []

def get_bets_for_match(home_team, away_team, match_date):
    """Get all voided bets for a specific match"""
    rows = db_helper.execute('''
        SELECT id, selection, odds, market
        FROM football_opportunities 
        WHERE home_team = %s AND away_team = %s 
        AND match_date::date = %s
        AND result = 'VOID'
    ''', (home_team, away_team, match_date), fetch='all')
    return rows or []

def settle_corner_bet(bet_id, selection, odds, stats, home_team, away_team):
    """Settle a corner bet based on match stats"""
    corners = stats.get('corners') or stats.get('corners_total')
    home_corners = stats.get('home_corners')
    away_corners = stats.get('away_corners')
    
    if corners is None:
        return None, "No corner data"
    
    selection_lower = selection.lower()
    outcome = None
    
    # Total corners over/under
    over_match = re.search(r'corners?\s*over\s*(\d+\.?\d*)', selection_lower)
    under_match = re.search(r'corners?\s*under\s*(\d+\.?\d*)', selection_lower)
    
    if over_match:
        threshold = float(over_match.group(1))
        outcome = 'WON' if corners > threshold else 'LOST'
    elif under_match:
        threshold = float(under_match.group(1))
        outcome = 'WON' if corners < threshold else 'LOST'
    
    # Team-specific corners - e.g. "Manchester United Corners +0.5" or "Genoa Over 4.5 Corners"
    elif home_corners is not None and away_corners is not None:
        home_norm = home_team.lower().split()[-1]  # Last word of team name
        away_norm = away_team.lower().split()[-1]
        
        # Team corners over - e.g. "Genoa Over 4.5 Corners"
        team_over = re.search(r'(\w+)\s+over\s+(\d+\.?\d*)\s+corners?', selection_lower)
        if team_over:
            team_word = team_over.group(1)
            threshold = float(team_over.group(2))
            if team_word in home_team.lower():
                outcome = 'WON' if home_corners > threshold else 'LOST'
            elif team_word in away_team.lower():
                outcome = 'WON' if away_corners > threshold else 'LOST'
        
        # Team corner handicap - e.g. "Manchester United Corners +1.5"
        handicap_match = re.search(r'(.+?)\s+corners?\s*([+-]\d+\.?\d*)', selection_lower)
        if handicap_match and not outcome:
            team_part = handicap_match.group(1).strip()
            handicap = float(handicap_match.group(2))
            
            # Determine which team
            if any(word in team_part for word in home_team.lower().split()):
                adjusted = home_corners + handicap
                outcome = 'WON' if adjusted > away_corners else 'LOST'
            elif any(word in team_part for word in away_team.lower().split()):
                adjusted = away_corners + handicap
                outcome = 'WON' if adjusted > home_corners else 'LOST'
    
    if outcome:
        # Update both result and outcome columns
        payout = (odds - 1) if outcome == 'WON' else -1
        db_helper.execute('''
            UPDATE football_opportunities 
            SET result = %s, outcome = %s, status = 'settled', 
                settled_timestamp = %s, profit_loss = %s,
                actual_score = %s
            WHERE id = %s
        ''', (outcome, outcome.lower(), int(datetime.now().timestamp()), payout, 
              f"Corners: {corners} (H:{home_corners} A:{away_corners})", bet_id))
        return outcome, None
    
    return None, "Could not parse selection"

def settle_card_bet(bet_id, selection, odds, stats, home_team, away_team):
    """Settle a card bet based on match stats"""
    cards = stats.get('cards') or stats.get('cards_total') or stats.get('yellow_cards')
    home_cards = stats.get('home_cards') or stats.get('home_yellow')
    away_cards = stats.get('away_cards') or stats.get('away_yellow')
    
    if cards is None:
        return None, "No card data"
    
    selection_lower = selection.lower()
    outcome = None
    
    # Total cards over/under
    over_match = re.search(r'cards?\s*over\s*(\d+\.?\d*)', selection_lower)
    under_match = re.search(r'cards?\s*under\s*(\d+\.?\d*)', selection_lower)
    
    # Also match "Over X.5" without cards prefix
    if not over_match:
        over_match = re.search(r'over\s*(\d+\.?\d*)', selection_lower)
    if not under_match:
        under_match = re.search(r'under\s*(\d+\.?\d*)', selection_lower)
    
    if over_match:
        threshold = float(over_match.group(1))
        outcome = 'WON' if cards > threshold else 'LOST'
    elif under_match:
        threshold = float(under_match.group(1))
        outcome = 'WON' if cards < threshold else 'LOST'
    
    if outcome:
        payout = (odds - 1) if outcome == 'WON' else -1
        db_helper.execute('''
            UPDATE football_opportunities 
            SET result = %s, outcome = %s, status = 'settled', 
                settled_timestamp = %s, profit_loss = %s,
                actual_score = %s
            WHERE id = %s
        ''', (outcome, outcome.lower(), int(datetime.now().timestamp()), payout,
              f"Cards: {cards}", bet_id))
        return outcome, None
    
    return None, "Could not parse card selection"

def main():
    stats_service = MatchStatsService()
    
    matches = get_voided_bets()
    logger.info(f"Found {len(matches)} unique matches with voided corner/card bets")
    
    settled_count = 0
    failed_count = 0
    no_data_count = 0
    
    for home_team, away_team, match_date in matches:
        date_str = str(match_date)
        logger.info(f"\n🔍 Checking: {home_team} vs {away_team} ({date_str})")
        
        # Try to fetch stats
        stats = stats_service.get_match_stats(home_team, away_team, date_str)
        
        if stats:
            corners = stats.get('corners') or stats.get('corners_total')
            home_corners = stats.get('home_corners')
            away_corners = stats.get('away_corners')
            cards = stats.get('cards') or stats.get('yellow_cards')
            
            logger.info(f"✅ Got stats: Corners = {corners} (H:{home_corners} A:{away_corners}), Cards = {cards}")
            
            # Get and settle bets for this match
            bets = get_bets_for_match(home_team, away_team, match_date)
            for bet_id, selection, odds, market in bets:
                if 'corner' in selection.lower():
                    if corners is not None:
                        outcome, error = settle_corner_bet(bet_id, selection, odds, stats, home_team, away_team)
                    else:
                        outcome, error = None, "No corner data"
                elif 'card' in selection.lower() or market == 'Cards':
                    if cards is not None:
                        outcome, error = settle_card_bet(bet_id, selection, odds, stats, home_team, away_team)
                    else:
                        outcome, error = None, "No card data"
                else:
                    outcome, error = None, "Unknown bet type"
                
                if outcome:
                    logger.info(f"   ✅ Settled #{bet_id}: {selection} → {outcome}")
                    settled_count += 1
                else:
                    logger.warning(f"   ⚠️ Could not settle #{bet_id}: {selection} - {error}")
                    failed_count += 1
        else:
            logger.warning(f"❌ No stats available for {home_team} vs {away_team}")
            no_data_count += len(get_bets_for_match(home_team, away_team, match_date))
        
        time.sleep(0.3)  # Rate limiting
    
    logger.info(f"\n📊 Summary:")
    logger.info(f"   ✅ Settled: {settled_count}")
    logger.info(f"   ⚠️ Parse failed: {failed_count}")
    logger.info(f"   ❌ No data: {no_data_count}")

if __name__ == "__main__":
    main()

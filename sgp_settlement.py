"""
SGP Settlement Module - PostgreSQL-based automatic settlement for SGP predictions.
Uses team names and match dates to find results and settle bets.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import re

from db_helper import db_helper

logger = logging.getLogger('sgp_settlement')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


def normalize_team_name(name: str) -> str:
    """Normalize team name for matching"""
    if not name:
        return ""
    name = name.lower().strip()
    replacements = {
        "fc ": "", " fc": "",
        "afc ": "", " afc": "",
        "sc ": "", " sc": "",
        " sc": "", "sc ": "",
        "cf ": "", " cf": "",
        "ac ": "", " ac": "",
        "sv ": "", " sv": "",
        "ssc ": "", " ssc": "",
        "rsc ": "", " rsc": "",
        "bv ": "", " bv": "",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name.strip()


def teams_match(team1: str, team2: str) -> bool:
    """Check if two team names refer to the same team"""
    if not team1 or not team2:
        return False
    n1 = normalize_team_name(team1)
    n2 = normalize_team_name(team2)
    if n1 == n2:
        return True
    if n1 in n2 or n2 in n1:
        return True
    if len(n1) > 3 and len(n2) > 3:
        if n1[:4] == n2[:4]:
            return True
    return False


def find_match_result(home_team: str, away_team: str, match_date: str) -> Optional[Dict]:
    """Find match result from cache using team names and date"""
    try:
        results = db_helper.execute('''
            SELECT home_team, away_team, home_score, away_score, 
                   ht_home_goals, ht_away_goals, corners_total
            FROM match_results_cache
            WHERE match_date = %s
        ''', (match_date,), fetch='all')
        
        if not results:
            return None
        
        for result in results:
            if teams_match(result[0], home_team) and teams_match(result[1], away_team):
                return {
                    'home_team': result[0],
                    'away_team': result[1],
                    'home_score': result[2],
                    'away_score': result[3],
                    'ht_home_goals': result[4],
                    'ht_away_goals': result[5],
                    'corners_total': result[6],
                    'total_goals': result[2] + result[3]
                }
            if teams_match(result[1], home_team) and teams_match(result[0], away_team):
                return {
                    'home_team': result[1],
                    'away_team': result[0],
                    'home_score': result[3],
                    'away_score': result[2],
                    'ht_home_goals': result[5],
                    'ht_away_goals': result[4],
                    'corners_total': result[6],
                    'total_goals': result[2] + result[3]
                }
        
        return None
    except Exception as e:
        logger.error(f"Error finding match result: {e}")
        return None


def grade_sgp_leg(leg_text: str, result: Dict) -> Optional[bool]:
    """
    Grade a single SGP leg against actual result.
    Returns True=won, False=lost, None=unknown/void
    """
    total_goals = result['total_goals']
    home_score = result['home_score']
    away_score = result['away_score']
    ht_home = result.get('ht_home_goals') or 0
    ht_away = result.get('ht_away_goals') or 0
    ht_total = ht_home + ht_away
    second_half_goals = total_goals - ht_total
    corners_total = result.get('corners_total') or 0
    
    leg = leg_text.strip()
    leg_upper = leg.upper()
    
    # Over X.5 goals (full match)
    if leg.startswith('Over') and not '1H' in leg and not '2H' in leg:
        try:
            parts = leg.split()
            line = float(parts[1]) if len(parts) >= 2 else 2.5
            return total_goals > line
        except:
            pass
    
    # Under X.5 goals (full match)
    if leg.startswith('Under') and not '1H' in leg and not '2H' in leg:
        try:
            parts = leg.split()
            line = float(parts[1]) if len(parts) >= 2 else 2.5
            return total_goals < line
        except:
            pass
    
    # BTTS handling
    if 'BTTS' in leg_upper:
        btts_occurred = home_score > 0 and away_score > 0
        if 'NO' in leg_upper:
            return not btts_occurred
        else:
            return btts_occurred
    
    # 1H Over X.5 (first half goals over line)
    if '1H Over' in leg or '1H Goal' in leg:
        if '1H Over 1.5' in leg:
            return ht_total > 1.5
        elif '1H Over 0.5' in leg:
            return ht_total > 0.5
        elif '1H Goal' in leg:
            return ht_total > 0
        else:
            return ht_total > 0
    
    # 2H Over X.5 (second half goals over line)
    if '2H Over' in leg or '2H Goal' in leg or '2H Goals' in leg:
        if '2H Over 2.5' in leg:
            return second_half_goals > 2.5
        elif '2H Over 1.5' in leg:
            return second_half_goals > 1.5
        elif '2H Over 0.5' in leg:
            return second_half_goals > 0.5
        elif '2H Goal' in leg or '2H Goals' in leg:
            return second_half_goals > 0
        else:
            return second_half_goals > 0
    
    # Corners handling
    if 'Corners' in leg or 'CORNERS' in leg_upper:
        try:
            corner_match = re.search(r'(\d+\.?\d*)\+', leg)
            if corner_match:
                line = float(corner_match.group(1))
                if corners_total > 0:
                    return corners_total > line
                return None  # No corners data available
        except:
            pass
        return None  # Can't grade corners without data
    
    # Goals Both Halves
    if 'Goals Both Halves' in leg or 'GOALS BOTH HALVES' in leg_upper:
        return ht_total > 0 and second_half_goals > 0
    
    # 1H + 2H Goals shorthand
    if '1H + 2H Goals' in leg:
        return ht_total > 0 and second_half_goals > 0
    
    logger.warning(f"Unknown SGP leg type: '{leg}' - treating as VOID")
    return None  # Unknown leg = void (not auto-loss)


def grade_structured_leg(leg_text: str, result: Dict) -> Optional[bool]:
    """
    Grade a structured leg format like:
    - OVER_UNDER_GOALS OVER (2.5)
    - BTTS YES
    - HALF_TIME_GOALS OVER (0.5)
    - SECOND_HALF_GOALS OVER (0.5)
    - CORNERS OVER (9.5)
    Returns True=won, False=lost, None=unknown/void
    """
    total_goals = result['total_goals']
    home_score = result['home_score']
    away_score = result['away_score']
    ht_home = result.get('ht_home_goals') or 0
    ht_away = result.get('ht_away_goals') or 0
    ht_total = ht_home + ht_away
    second_half_goals = total_goals - ht_total
    corners_total = result.get('corners_total') or 0
    
    leg = leg_text.strip().upper()
    
    # OVER_UNDER_GOALS OVER (2.5)
    if leg.startswith('OVER_UNDER_GOALS'):
        try:
            match = re.search(r'(OVER|UNDER)\s*\(?([\d.]+)\)?', leg)
            if match:
                direction = match.group(1)
                line = float(match.group(2))
                if direction == 'OVER':
                    return total_goals > line
                else:
                    return total_goals < line
        except:
            pass
    
    # BTTS YES/NO
    if leg.startswith('BTTS'):
        btts_occurred = home_score > 0 and away_score > 0
        if 'NO' in leg:
            return not btts_occurred
        else:
            return btts_occurred
    
    # HALF_TIME_GOALS OVER (0.5)
    if leg.startswith('HALF_TIME_GOALS') or leg.startswith('1H'):
        try:
            match = re.search(r'(OVER|UNDER)\s*\(?([\d.]+)\)?', leg)
            if match:
                direction = match.group(1)
                line = float(match.group(2))
                if direction == 'OVER':
                    return ht_total > line
                else:
                    return ht_total < line
        except:
            pass
        return ht_total > 0  # Default: any goals in 1H
    
    # SECOND_HALF_GOALS OVER (0.5)
    if leg.startswith('SECOND_HALF_GOALS') or leg.startswith('2H'):
        try:
            match = re.search(r'(OVER|UNDER)\s*\(?([\d.]+)\)?', leg)
            if match:
                direction = match.group(1)
                line = float(match.group(2))
                if direction == 'OVER':
                    return second_half_goals > line
                else:
                    return second_half_goals < line
        except:
            pass
        return second_half_goals > 0  # Default: any goals in 2H
    
    # CORNERS OVER (9.5)
    if 'CORNER' in leg:
        try:
            match = re.search(r'(OVER|UNDER)\s*\(?([\d.]+)\)?', leg)
            if match:
                direction = match.group(1)
                line = float(match.group(2))
                if corners_total > 0:
                    if direction == 'OVER':
                        return corners_total > line
                    else:
                        return corners_total < line
                return None  # No corner data
        except:
            pass
        return None
    
    # GOALS_BOTH_HALVES or similar
    if 'BOTH' in leg and 'HALF' in leg and 'GOAL' in leg:
        return ht_total > 0 and second_half_goals > 0
    
    return None  # Unknown leg type


def grade_sgp_parlay(parlay_description: str, legs_str: Optional[str], result: Dict) -> Tuple[str, bool]:
    """
    Grade an SGP parlay - all legs must win.
    Uses structured legs_str if available, falls back to parlay_description.
    Returns: (outcome, is_gradeable) where:
      - outcome = 'win', 'loss', or 'void'
      - is_gradeable = True if we could grade it, False if should skip
    """
    # Prefer structured legs format if available
    if legs_str and '|' in legs_str:
        legs = [l.strip() for l in legs_str.split('|') if l.strip()]
        use_structured = True
    elif parlay_description:
        legs = [l.strip() for l in parlay_description.split(' + ') if l.strip()]
        use_structured = False
    else:
        return ('void', False)
    
    all_won = True
    has_unknown = False
    
    for leg in legs:
        if use_structured:
            leg_result = grade_structured_leg(leg, result)
        else:
            leg_result = grade_sgp_leg(leg, result)
        
        if leg_result is None:
            has_unknown = True
            logger.debug(f"   ⚠️ Unknown leg: {leg} - marking parlay as void")
        elif leg_result is False:
            all_won = False
            logger.debug(f"   ❌ Leg lost: {leg}")
        else:
            logger.debug(f"   ✅ Leg won: {leg}")
    
    if has_unknown:
        return ('void', False)
    
    if all_won:
        return ('win', True)
    else:
        return ('loss', True)


def settle_pending_sgp_bets():
    """Main function to settle all pending SGP bets"""
    logger.info("🎲 Starting SGP settlement cycle...")
    
    try:
        pending_bets = db_helper.execute('''
            SELECT id, home_team, away_team, match_date_only, parlay_description,
                   bookmaker_odds, stake, league, legs
            FROM sgp_predictions
            WHERE status = 'pending'
            AND match_date_only < CURRENT_DATE
            ORDER BY match_date_only
        ''', fetch='all')
        
        if not pending_bets:
            logger.info("✅ No pending SGP bets to settle")
            return 0
        
        logger.info(f"📊 Found {len(pending_bets)} pending SGP bets to check")
        
        settled_count = 0
        wins = 0
        losses = 0
        
        for bet in pending_bets:
            bet_id, home_team, away_team, match_date, parlay_desc, odds, stake, league, legs_str = bet
            
            result = find_match_result(home_team, away_team, str(match_date))
            
            if not result:
                logger.debug(f"⏭️ No result found yet for {home_team} vs {away_team} ({match_date})")
                continue
            
            outcome, is_gradeable = grade_sgp_parlay(parlay_desc, legs_str, result)
            
            if not is_gradeable:
                logger.info(f"⏭️ Cannot grade {home_team} vs {away_team} | {parlay_desc} - contains unknown legs, skipping")
                continue
            
            result_display = outcome.upper()
            
            if outcome == 'win':
                profit_loss = stake * (odds - 1)
                payout = stake * odds
                wins += 1
            else:
                profit_loss = -stake
                payout = 0
                losses += 1
            
            actual_score = f"{result['home_score']}-{result['away_score']}"
            settled_ts = int(time.time())
            
            db_helper.execute('''
                UPDATE sgp_predictions
                SET status = 'settled',
                    outcome = %s,
                    result = %s,
                    profit_loss = %s,
                    payout = %s,
                    settled_timestamp = %s
                WHERE id = %s
            ''', (outcome, result_display, profit_loss, payout, settled_ts, bet_id))
            
            settled_count += 1
            logger.info(f"{'✅' if won else '❌'} Settled SGP {bet_id}: {home_team} vs {away_team} ({actual_score}) - {parlay_desc} = {outcome.upper()}")
            
            try:
                from discord_notifier import send_result_to_discord
                discord_info = {
                    'outcome': result_display,
                    'home_team': home_team,
                    'away_team': away_team,
                    'selection': parlay_desc,
                    'actual_score': actual_score,
                    'odds': odds,
                    'profit_loss': profit_loss,
                    'product_type': 'SGP',
                    'league': league or ''
                }
                send_result_to_discord(discord_info, 'SGP')
            except Exception as e:
                logger.warning(f"Discord notification failed: {e}")
        
        logger.info(f"🎲 SGP Settlement complete: {settled_count} bets (✅ {wins} wins, ❌ {losses} losses)")
        return settled_count
        
    except Exception as e:
        logger.error(f"Error in SGP settlement: {e}")
        import traceback
        traceback.print_exc()
        return 0


if __name__ == "__main__":
    settle_pending_sgp_bets()

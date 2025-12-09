# parlay_builder.py
# ------------------------------------------------------------
# MULTI-MATCH PARLAY BUILDER
# Builds parlays from approved single bets (L1 and L2 trust only)
# Replaces the old SGP (same-game parlay) system
# ------------------------------------------------------------

import time
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from itertools import combinations

logger = logging.getLogger(__name__)

# ============================================================
# PARLAY CONFIGURATION
# ============================================================

MIN_LEGS = 2
MAX_LEGS = 4
MIN_PARLAY_ODDS = 4.00
MAX_PARLAY_ODDS = 20.00
MIN_PARLAY_EV = 0.05  # 5% minimum EV
MAX_PARLAYS_PER_DAY = 3
ALLOWED_TRUST_LEVELS = {"L1", "L2"}  # Only high-trust bets

# Stake configuration
PARLAY_STAKE_SEK = 200.0  # Fixed stake per parlay in SEK


def build_parlays_from_singles(singles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build multi-match parlays from approved single bets.
    
    Rules:
    1. Only L1 and L2 trust level singles
    2. 2-4 legs per parlay
    3. Only 1 leg per match (guaranteed since singles are unique per match)
    4. Total odds between 4.00 and 20.00
    5. EV >= 5% (probability_product * odds_product - 1)
    6. Return sorted by highest EV first
    7. Maximum 3 parlays per day
    
    Args:
        singles: List of single bet opportunities with probability and odds
        
    Returns:
        List of parlay opportunities sorted by EV (descending)
    """
    if not singles:
        print("📦 No singles provided for parlay building")
        return []
    
    # Filter to L1/L2 trust levels only
    eligible_singles = [
        s for s in singles 
        if s.get('trust_level') in ALLOWED_TRUST_LEVELS
    ]
    
    print(f"🎯 PARLAY BUILDER: {len(eligible_singles)} eligible singles (L1/L2 from {len(singles)} total)")
    
    if len(eligible_singles) < MIN_LEGS:
        print(f"   ❌ Need at least {MIN_LEGS} eligible singles to build parlays")
        return []
    
    # Extract match IDs to ensure no duplicate matches
    # (Singles should already be unique per match, but double-check)
    used_matches: Dict[str, Dict[str, Any]] = {}
    for s in eligible_singles:
        match_id = s.get('match_id')
        if match_id and match_id not in used_matches:
            used_matches[match_id] = s
    
    unique_singles = list(used_matches.values())
    print(f"   📊 {len(unique_singles)} unique matches available for parlay building")
    
    if len(unique_singles) < MIN_LEGS:
        print(f"   ❌ Need at least {MIN_LEGS} unique matches")
        return []
    
    # Generate all valid parlay combinations
    parlays = []
    
    for leg_count in range(MIN_LEGS, min(MAX_LEGS + 1, len(unique_singles) + 1)):
        for combo in combinations(unique_singles, leg_count):
            parlay = _evaluate_parlay(list(combo))
            if parlay:
                parlays.append(parlay)
    
    print(f"   📊 Generated {len(parlays)} valid parlay combinations")
    
    # Sort by EV descending
    parlays.sort(key=lambda x: x['ev_percentage'], reverse=True)
    
    # Limit to MAX_PARLAYS_PER_DAY
    selected_parlays = parlays[:MAX_PARLAYS_PER_DAY]
    
    print(f"   🏆 Selected top {len(selected_parlays)} parlays (max {MAX_PARLAYS_PER_DAY}/day)")
    for i, p in enumerate(selected_parlays, 1):
        print(f"      #{i}: {p['leg_count']} legs @ {p['total_odds']:.2f}x | EV: {p['ev_percentage']:.1f}%")
    
    return selected_parlays


def _evaluate_parlay(legs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Evaluate a potential parlay combination.
    
    Returns parlay dict if valid, None if doesn't meet criteria.
    """
    if not legs:
        return None
    
    # Calculate combined odds and probability
    total_odds = 1.0
    total_prob = 1.0
    
    leg_details = []
    
    for leg in legs:
        odds = leg.get('odds', 0)
        if odds <= 0:
            return None
            
        # Get probability from sim_probability (Monte Carlo) or calculate from analysis
        prob = leg.get('sim_probability')
        if not prob:
            # Fallback: try to get from analysis JSON
            try:
                analysis = json.loads(leg.get('analysis', '{}'))
                prob = analysis.get('p_model', 0)
            except:
                prob = 0
        
        if prob <= 0:
            return None
        
        total_odds *= odds
        total_prob *= prob
        
        leg_details.append({
            'match_id': leg.get('match_id'),
            'home_team': leg.get('home_team'),
            'away_team': leg.get('away_team'),
            'league': leg.get('league'),
            'selection': leg.get('selection'),
            'odds': odds,
            'probability': prob,
            'trust_level': leg.get('trust_level'),
            'match_date': leg.get('match_date'),
            'kickoff_time': leg.get('kickoff_time')
        })
    
    # Check odds range
    if total_odds < MIN_PARLAY_ODDS or total_odds > MAX_PARLAY_ODDS:
        return None
    
    # Calculate EV: (probability_product * odds_product) - 1
    ev = (total_prob * total_odds) - 1
    
    # Check minimum EV
    if ev < MIN_PARLAY_EV:
        return None
    
    # Build parlay object
    parlay = {
        'timestamp': int(time.time()),
        'leg_count': len(legs),
        'total_odds': round(total_odds, 2),
        'total_probability': round(total_prob, 4),
        'ev': round(ev, 4),
        'ev_percentage': round(ev * 100, 1),
        'stake': PARLAY_STAKE_SEK,
        'potential_return': round(PARLAY_STAKE_SEK * total_odds, 2),
        'legs': leg_details,
        'legs_json': json.dumps(leg_details),
        'product_type': 'PARLAY'
    }
    
    return parlay


def save_parlays_to_db(parlays: List[Dict[str, Any]]) -> int:
    """
    Save parlays to the database using the sgp_predictions schema.
    
    Returns count of saved parlays.
    """
    if not parlays:
        return 0
    
    saved = 0
    
    try:
        from db_helper import DatabaseHelper
        
        for parlay in parlays:
            try:
                legs = parlay.get('legs', [])
                if not legs:
                    continue
                
                # Build description from legs
                description_parts = []
                for leg in legs:
                    desc = f"{leg.get('home_team', '?')} vs {leg.get('away_team', '?')}: {leg.get('selection', '?')}"
                    description_parts.append(desc)
                description = " | ".join(description_parts)
                
                # Get match info from first leg
                first_leg = legs[0]
                
                # Build legs string in format expected by settlement (match_id|selection|odds)
                legs_str = json.dumps([{
                    'match_id': leg.get('match_id'),
                    'home_team': leg.get('home_team'),
                    'away_team': leg.get('away_team'),
                    'selection': leg.get('selection'),
                    'odds': leg.get('odds'),
                    'probability': leg.get('probability'),
                    'trust_level': leg.get('trust_level')
                } for leg in legs])
                
                # Calculate average trust level
                trust_levels = [leg.get('trust_level', 'L3') for leg in legs]
                avg_trust = 'L1' if all(t == 'L1' for t in trust_levels) else 'L2'
                
                # Insert into sgp_predictions table with correct schema
                DatabaseHelper.execute("""
                    INSERT INTO sgp_predictions (
                        timestamp, match_id, home_team, away_team, league,
                        match_date, kickoff_time, legs, parlay_description,
                        parlay_probability, fair_odds, bookmaker_odds,
                        ev_percentage, stake, status, result, mode,
                        bet_placed, trust_level, sim_probability, ev_sim
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    parlay.get('timestamp'),
                    f"PARLAY_{parlay.get('timestamp')}_{parlay.get('leg_count')}LEG",
                    f"{parlay.get('leg_count')}-Leg Multi-Match Parlay",
                    description[:200],
                    first_leg.get('league', 'Multi-League'),
                    first_leg.get('match_date', datetime.now().strftime('%Y-%m-%d')),
                    first_leg.get('kickoff_time', '00:00'),
                    legs_str,  # legs column (JSON string)
                    description[:500],  # parlay_description
                    parlay.get('total_probability'),  # parlay_probability
                    parlay.get('total_odds') / (1 + parlay.get('ev', 0)),  # fair_odds
                    parlay.get('total_odds'),  # bookmaker_odds
                    parlay.get('ev_percentage'),  # ev_percentage
                    parlay.get('stake'),  # stake in SEK
                    'PENDING',  # status
                    'PENDING',  # result
                    'PROD',  # mode
                    True,  # bet_placed
                    avg_trust,  # trust_level
                    parlay.get('total_probability'),  # sim_probability
                    parlay.get('ev') * 100 if parlay.get('ev') else 0  # ev_sim
                ))
                
                saved += 1
                print(f"   ✅ Saved {parlay.get('leg_count')}-leg parlay @ {parlay.get('total_odds'):.2f}x | EV: {parlay.get('ev_percentage'):.1f}%")
                
            except Exception as e:
                logger.error(f"Failed to save parlay: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"💾 Saved {saved} parlays to database")
        
    except Exception as e:
        logger.error(f"Database error saving parlays: {e}")
        return 0
    
    return saved


def run_parlay_builder() -> List[Dict[str, Any]]:
    """
    Main entry point: Fetch today's singles and build parlays.
    
    Returns list of generated parlays.
    """
    print("\n" + "="*60)
    print("🎲 MULTI-MATCH PARLAY BUILDER")
    print("="*60)
    
    try:
        from db_helper import DatabaseHelper
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get today's value singles that are still pending from football_opportunities table
        # Value Singles have market = 'Value Single'
        rows = DatabaseHelper.execute("""
            SELECT 
                id, match_id, home_team, away_team, league,
                selection, odds, stake, match_date, kickoff_time,
                edge_percentage, confidence, analysis, trust_level,
                sim_probability, ev_sim
            FROM football_opportunities
            WHERE match_date = %s
            AND market = 'Value Single'
            AND (result = 'PENDING' OR result IS NULL)
            AND bet_placed = true
            ORDER BY edge_percentage DESC
        """, (today,), fetch='all') or []
        
        print(f"📊 Found {len(rows)} pending value singles for {today}")
        
        if not rows:
            print("   No singles available for parlay building")
            return []
        
        # Convert to dict format
        singles = []
        for row in rows:
            single = {
                'id': row[0],
                'match_id': row[1],
                'home_team': row[2],
                'away_team': row[3],
                'league': row[4],
                'selection': row[5],
                'odds': float(row[6]) if row[6] else 0,
                'stake': float(row[7]) if row[7] else 0,
                'match_date': str(row[8]) if row[8] else today,
                'kickoff_time': str(row[9]) if row[9] else '',
                'edge_percentage': float(row[10]) if row[10] else 0,
                'confidence': int(row[11]) if row[11] else 0,
                'analysis': row[12] or '{}',
                'trust_level': row[13] or 'L3',
                'sim_probability': float(row[14]) if row[14] else 0,
                'ev_sim': float(row[15]) if row[15] else 0
            }
            singles.append(single)
        
        # Build parlays
        parlays = build_parlays_from_singles(singles)
        
        # Save to database
        if parlays:
            saved = save_parlays_to_db(parlays)
            print(f"✅ Parlay builder complete: {saved} parlays saved")
        else:
            print("ℹ️ No valid parlays generated")
        
        return parlays
        
    except Exception as e:
        logger.error(f"Parlay builder error: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parlays = run_parlay_builder()
    print(f"\nGenerated {len(parlays)} parlays")

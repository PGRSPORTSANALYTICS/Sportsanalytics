"""
Monte Carlo Database Integration
Connects the simulator to the database for live predictions.
"""

import datetime
from typing import Optional, Dict, List
import os

try:
    from db_connection import DatabaseConnection
    HAS_DB = True
except ImportError:
    HAS_DB = False

from monte_carlo_simulator import simulate_match, find_value_bets, get_top_exact_scores, calc_ev


def get_match_row(match_id: int) -> Optional[dict]:
    """
    Fetch match info + expected goals from the database.
    """
    if not HAS_DB:
        return None
    
    sql = """
    SELECT
        id as match_id,
        league,
        home_team,
        away_team,
        match_date as start_time,
        odds
    FROM football_opportunities
    WHERE id = %s
    LIMIT 1;
    """
    
    try:
        with DatabaseConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (match_id,))
                row = cur.fetchone()
                if row:
                    return {
                        "match_id": row[0],
                        "league": row[1],
                        "home_team": row[2],
                        "away_team": row[3],
                        "start_time": row[4],
                        "odds": row[5]
                    }
    except Exception as e:
        print(f"Error fetching match: {e}")
    
    return None


def get_market_odds_for_match(match_id: str) -> Dict:
    """
    Fetch odds for 1X2, O2.5, BTTS from The Odds API cache.
    """
    if not HAS_DB:
        return {}
    
    sql = """
    SELECT response_data
    FROM odds_api_cache
    WHERE cache_key LIKE %s
    ORDER BY cached_at DESC
    LIMIT 1;
    """
    
    data = {
        "home_win": None,
        "draw": None,
        "away_win": None,
        "over_25": None,
        "btts_yes": None,
    }
    
    try:
        with DatabaseConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (f"%{match_id}%",))
                row = cur.fetchone()
                if row and row[0]:
                    import json
                    odds_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except Exception as e:
        print(f"Error fetching odds: {e}")
    
    return data


def get_pending_matches_with_xg() -> List[Dict]:
    """
    Get all pending matches that have xG data for simulation.
    """
    if not HAS_DB:
        return []
    
    sql = """
    SELECT 
        id,
        home_team,
        away_team,
        league,
        match_date,
        analysis
    FROM football_opportunities
    WHERE result IS NULL OR result = ''
    ORDER BY match_date ASC
    LIMIT 50;
    """
    
    matches = []
    try:
        with DatabaseConnection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                for row in rows:
                    matches.append({
                        "id": row[0],
                        "home_team": row[1],
                        "away_team": row[2],
                        "league": row[3],
                        "match_date": row[4],
                        "analysis": row[5]
                    })
    except Exception as e:
        print(f"Error fetching pending matches: {e}")
    
    return matches


def run_monte_carlo_analysis(home_xg: float, away_xg: float, market_odds: Dict, min_ev: float = 0.05) -> Dict:
    """
    Run full Monte Carlo analysis for a match.
    
    Args:
        home_xg: Expected goals for home team
        away_xg: Expected goals for away team
        market_odds: Dict of market -> odds
        min_ev: Minimum EV threshold
    
    Returns:
        Complete analysis with probabilities and value bets
    """
    simulation = simulate_match(home_xg, away_xg, n_sim=10000)
    
    value_bets = find_value_bets(simulation, market_odds, min_ev)
    
    top_scores = get_top_exact_scores(simulation, top_n=5)
    
    for score_info in top_scores:
        score_key = f"score_{score_info['score']}"
        if score_key in market_odds:
            ev_result = calc_ev(score_info["probability"], market_odds[score_key])
            score_info["market_odds"] = market_odds[score_key]
            score_info["ev"] = ev_result["ev"]
            score_info["ev_pct"] = ev_result["ev_pct"]
    
    return {
        "simulation": simulation,
        "value_bets": value_bets,
        "top_scores": top_scores,
        "home_xg": home_xg,
        "away_xg": away_xg,
        "expected_total": home_xg + away_xg
    }


if __name__ == "__main__":
    print("=== MONTE CARLO DB INTEGRATION TEST ===")
    
    analysis = run_monte_carlo_analysis(
        home_xg=1.5,
        away_xg=1.2,
        market_odds={
            "home_win": 2.10,
            "draw": 3.40,
            "away_win": 3.50,
            "over_25": 1.95,
            "btts_yes": 1.85,
            "score_1-1": 6.50,
            "score_2-1": 9.00,
            "score_1-0": 8.00
        },
        min_ev=0.03
    )
    
    print(f"\nExpected Goals: Home {analysis['home_xg']} - Away {analysis['away_xg']}")
    print(f"Expected Total: {analysis['expected_total']:.1f}")
    
    print(f"\n1X2 Probabilities:")
    sim = analysis["simulation"]
    print(f"  Home: {sim['one_x_two']['1']:.1%}")
    print(f"  Draw: {sim['one_x_two']['X']:.1%}")
    print(f"  Away: {sim['one_x_two']['2']:.1%}")
    
    print(f"\nTop 5 Scores:")
    for s in analysis["top_scores"]:
        ev_str = f" | EV: {s.get('ev_pct', 0):.1f}%" if 'ev_pct' in s else ""
        print(f"  {s['score']}: {s['probability_pct']:.1f}%{ev_str}")
    
    print(f"\nValue Bets Found ({len(analysis['value_bets'])}):")
    for bet in analysis["value_bets"]:
        print(f"  {bet['market']}: {bet['ev_pct']:.1f}% EV @ {bet['market_odds']} odds")

"""
Monte Carlo Match Simulator
Uses Poisson distribution to simulate thousands of matches
and calculate probabilities for all betting markets.
"""

import numpy as np
from collections import Counter
from typing import Dict, Optional


def simulate_match(lambda_home: float, lambda_away: float, n_sim: int = 10000, max_goals: int = 8) -> Dict:
    """
    Simulate a football match using Monte Carlo simulation with Poisson distribution.
    
    Args:
        lambda_home: Expected goals for home team (xG)
        lambda_away: Expected goals for away team (xG)
        n_sim: Number of simulations (default 10,000)
        max_goals: Maximum goals to consider per team
    
    Returns:
        Dictionary with probabilities for all markets
    """
    home_goals = np.random.poisson(lam=lambda_home, size=n_sim)
    away_goals = np.random.poisson(lam=lambda_away, size=n_sim)

    home_goals = np.clip(home_goals, 0, max_goals)
    away_goals = np.clip(away_goals, 0, max_goals)

    score_counts = Counter(zip(home_goals, away_goals))

    score_probs = {
        f"{h}-{a}": count / n_sim
        for (h, a), count in score_counts.items()
    }

    home_wins = float((home_goals > away_goals).mean())
    draws     = float((home_goals == away_goals).mean())
    away_wins = float((home_goals < away_goals).mean())

    btts_yes = float(((home_goals > 0) & (away_goals > 0)).mean())
    over_15  = float(((home_goals + away_goals) > 1.5).mean())
    over_25  = float(((home_goals + away_goals) > 2.5).mean())
    over_35  = float(((home_goals + away_goals) > 3.5).mean())
    under_25 = float(((home_goals + away_goals) < 2.5).mean())
    under_35 = float(((home_goals + away_goals) < 3.5).mean())

    total_goals = home_goals + away_goals
    
    over_05 = float((total_goals > 0.5).mean())
    over_45 = float((total_goals > 4.5).mean())
    under_15 = float((total_goals < 1.5).mean())
    under_45 = float((total_goals < 4.5).mean())
    
    home_ah_minus05 = float((home_goals - away_goals > -0.5).mean())
    home_ah_minus10 = float((home_goals - away_goals > -1.0).mean())
    home_ah_minus15 = float((home_goals - away_goals > -1.5).mean())
    home_ah_plus05 = float((home_goals - away_goals > 0.5).mean())
    home_ah_plus10 = float((home_goals - away_goals > 1.0).mean())
    home_ah_plus15 = float((home_goals - away_goals > 1.5).mean())
    
    away_ah_minus05 = float((away_goals - home_goals > -0.5).mean())
    away_ah_minus10 = float((away_goals - home_goals > -1.0).mean())
    away_ah_minus15 = float((away_goals - home_goals > -1.5).mean())
    away_ah_plus05 = float((away_goals - home_goals > 0.5).mean())
    away_ah_plus10 = float((away_goals - home_goals > 1.0).mean())
    away_ah_plus15 = float((away_goals - home_goals > 1.5).mean())
    
    dc_1x = home_wins + draws
    dc_12 = home_wins + away_wins
    dc_x2 = draws + away_wins

    return {
        "scores": score_probs,
        "one_x_two": {"1": home_wins, "X": draws, "2": away_wins},
        "btts_yes": btts_yes,
        "btts_no": 1.0 - btts_yes,
        "over_05": over_05,
        "over_15": over_15,
        "over_25": over_25,
        "over_35": over_35,
        "over_45": over_45,
        "under_05": 1.0 - over_05,
        "under_15": under_15,
        "under_25": under_25,
        "under_35": under_35,
        "under_45": under_45,
        "avg_total_goals": float(total_goals.mean()),
        "home_ah_-0.5": home_ah_minus05,
        "home_ah_-1.0": home_ah_minus10,
        "home_ah_-1.5": home_ah_minus15,
        "home_ah_+0.5": home_ah_plus05,
        "home_ah_+1.0": home_ah_plus10,
        "home_ah_+1.5": home_ah_plus15,
        "away_ah_-0.5": away_ah_minus05,
        "away_ah_-1.0": away_ah_minus10,
        "away_ah_-1.5": away_ah_minus15,
        "away_ah_+0.5": away_ah_plus05,
        "away_ah_+1.0": away_ah_plus10,
        "away_ah_+1.5": away_ah_plus15,
        "double_chance_1X": dc_1x,
        "double_chance_12": dc_12,
        "double_chance_X2": dc_x2,
        "simulations": n_sim
    }


def implied_prob(odds: float) -> float:
    """Convert decimal odds to implied probability."""
    if odds <= 0:
        return 0.0
    return 1.0 / odds


def fair_odds(p: float) -> Optional[float]:
    """Convert probability to fair odds."""
    if p <= 0:
        return None
    return 1.0 / p


def calc_ev(p_model: float, odds_market: float) -> Dict:
    """
    Calculate edge and expected value.
    
    Args:
        p_model: Model's probability estimate
        odds_market: Bookmaker's offered odds
    
    Returns:
        Dictionary with edge and EV percentages
    """
    if odds_market <= 0:
        return {"edge": 0.0, "ev": 0.0, "edge_pct": 0.0, "ev_pct": 0.0}

    p_market = implied_prob(odds_market)
    edge = p_model - p_market
    ev = (p_model * odds_market) - 1.0
    
    return {
        "edge": edge,
        "ev": ev,
        "edge_pct": edge * 100,
        "ev_pct": ev * 100
    }


def find_value_bets(simulation_result: Dict, market_odds: Dict, min_ev: float = 0.05) -> list:
    """
    Find value bets from simulation results vs market odds.
    
    Args:
        simulation_result: Output from simulate_match()
        market_odds: Dict of market_name -> odds
        min_ev: Minimum EV threshold (default 5%)
    
    Returns:
        List of value bets with positive EV
    """
    value_bets = []
    
    market_probs = {
        "home_win": simulation_result["one_x_two"]["1"],
        "draw": simulation_result["one_x_two"]["X"],
        "away_win": simulation_result["one_x_two"]["2"],
        "btts_yes": simulation_result["btts_yes"],
        "btts_no": simulation_result["btts_no"],
        "over_25": simulation_result["over_25"],
        "under_25": simulation_result["under_25"],
        "over_35": simulation_result["over_35"],
        "under_35": simulation_result["under_35"],
    }
    
    for score, prob in simulation_result["scores"].items():
        market_probs[f"score_{score}"] = prob
    
    for market, odds in market_odds.items():
        if market in market_probs:
            p_model = market_probs[market]
            ev_result = calc_ev(p_model, odds)
            
            if ev_result["ev"] >= min_ev:
                value_bets.append({
                    "market": market,
                    "model_prob": p_model,
                    "model_prob_pct": p_model * 100,
                    "market_odds": odds,
                    "fair_odds": fair_odds(p_model),
                    "edge": ev_result["edge"],
                    "edge_pct": ev_result["edge_pct"],
                    "ev": ev_result["ev"],
                    "ev_pct": ev_result["ev_pct"]
                })
    
    value_bets.sort(key=lambda x: x["ev"], reverse=True)
    return value_bets


def get_top_exact_scores(simulation_result: Dict, top_n: int = 5) -> list:
    """Get the most likely exact scores from simulation."""
    scores = simulation_result["scores"]
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    return [
        {
            "score": score,
            "probability": prob,
            "probability_pct": prob * 100,
            "fair_odds": fair_odds(prob)
        }
        for score, prob in sorted_scores[:top_n]
    ]


if __name__ == "__main__":
    result = simulate_match(lambda_home=1.8, lambda_away=1.2)
    
    print("=== MONTE CARLO SIMULATION (10,000 matches) ===")
    print(f"\n1X2 Probabilities:")
    print(f"  Home Win: {result['one_x_two']['1']:.1%}")
    print(f"  Draw:     {result['one_x_two']['X']:.1%}")
    print(f"  Away Win: {result['one_x_two']['2']:.1%}")
    
    print(f"\nGoals Markets:")
    print(f"  Over 2.5:  {result['over_25']:.1%}")
    print(f"  Under 2.5: {result['under_25']:.1%}")
    print(f"  BTTS Yes:  {result['btts_yes']:.1%}")
    
    print(f"\nTop 5 Most Likely Scores:")
    for score_info in get_top_exact_scores(result):
        print(f"  {score_info['score']}: {score_info['probability_pct']:.1f}% (fair odds: {score_info['fair_odds']:.2f})")
    
    example_odds = {
        "home_win": 1.85,
        "over_25": 1.90,
        "score_2-1": 9.00
    }
    
    print(f"\nValue Bets (vs example odds):")
    for bet in find_value_bets(result, example_odds, min_ev=0.03):
        print(f"  {bet['market']}: {bet['ev_pct']:.1f}% EV @ {bet['market_odds']} odds")

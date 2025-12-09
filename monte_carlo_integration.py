"""
Monte Carlo Integration Bridge
Provides unified interface for Monte Carlo simulation + tiered trust filtering
for all prediction engines.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from monte_carlo_simulator import simulate_match, calc_ev, fair_odds, implied_prob
from bet_filter import BetCandidate, filter_level1_high_trust, filter_level2_medium_trust, filter_level3_soft_value, build_daily_card


@dataclass
class MonteCarloResult:
    """Result from Monte Carlo simulation with trust classification."""
    home_xg: float
    away_xg: float
    
    home_win_prob: float = 0.0
    draw_prob: float = 0.0
    away_win_prob: float = 0.0
    
    btts_yes_prob: float = 0.0
    over_25_prob: float = 0.0
    over_35_prob: float = 0.0
    under_25_prob: float = 0.0
    
    score_probs: Dict[str, float] = field(default_factory=dict)
    top_scores: List[Tuple[str, float]] = field(default_factory=list)
    
    simulations: int = 10000


def run_monte_carlo(home_xg: float, away_xg: float, n_sim: int = 10000) -> MonteCarloResult:
    """
    Run Monte Carlo simulation and return structured result.
    
    Args:
        home_xg: Expected goals for home team
        away_xg: Expected goals for away team
        n_sim: Number of simulations
    
    Returns:
        MonteCarloResult with all probabilities
    """
    sim = simulate_match(home_xg, away_xg, n_sim=n_sim)
    
    sorted_scores = sorted(sim["scores"].items(), key=lambda x: x[1], reverse=True)[:10]
    
    return MonteCarloResult(
        home_xg=home_xg,
        away_xg=away_xg,
        home_win_prob=sim["one_x_two"]["1"],
        draw_prob=sim["one_x_two"]["X"],
        away_win_prob=sim["one_x_two"]["2"],
        btts_yes_prob=sim["btts_yes"],
        over_25_prob=sim["over_25"],
        over_35_prob=sim["over_35"],
        under_25_prob=sim.get("under_25", 1.0 - sim["over_25"]),
        score_probs=sim["scores"],
        top_scores=sorted_scores,
        simulations=n_sim
    )


def classify_trust_level(
    ev_sim: float,
    ev_model: float,
    confidence: float,
    disagreement: float,
    sim_approved: bool,
    odds: float
) -> str:
    """
    NOVA v2.0 - Classify a bet into trust level (L1/L2/L3/REJECTED).
    Retuned Dec 9, 2025 for higher volume while maintaining safety.
    
    Args:
        ev_sim: EV from simulation
        ev_model: EV from model
        confidence: Model confidence (0-1)
        disagreement: Disagreement between models (0-1)
        sim_approved: Whether simulation filter approved
        odds: Market odds
    
    Returns:
        Trust level string: "L1_HIGH_TRUST", "L2_MEDIUM_TRUST", "L3_SOFT_VALUE", or "REJECTED"
    
    Thresholds (NOVA v2.0):
        L1: sim_approved + EV >= 5% + confidence >= 55% + odds 1.50-3.00
        L2: EV >= 2% + confidence >= 52% + disagreement <= 20% + odds 1.50-3.20
        L3: EV >= 0% + confidence >= 50% + disagreement <= 25% + odds 1.40-3.50
    """
    # L1 - High Trust
    if (sim_approved and 
        ev_sim >= 0.05 and 
        confidence >= 0.55 and
        1.50 <= odds <= 3.00):
        return "L1_HIGH_TRUST"
    
    # L2 - Medium Trust
    if (ev_model >= 0.02 and 
        confidence >= 0.52 and 
        disagreement <= 0.20 and 
        1.50 <= odds <= 3.20):
        return "L2_MEDIUM_TRUST"
    
    # L3 - Soft Value (fallback)
    if (ev_model >= 0 and 
        confidence >= 0.50 and 
        disagreement <= 0.25 and
        1.40 <= odds <= 3.50):
        return "L3_SOFT_VALUE"
    
    return "REJECTED"


def analyze_bet_with_monte_carlo(
    home_xg: float,
    away_xg: float,
    market: str,
    selection: str,
    market_odds: float,
    model_confidence: float = 0.5,
    n_sim: int = 10000
) -> Dict[str, Any]:
    """
    Full analysis of a bet using Monte Carlo simulation.
    
    Args:
        home_xg: Expected goals for home team
        away_xg: Expected goals for away team
        market: Market type (1X2, BTTS, OVER_2_5, EXACT_SCORE, etc.)
        selection: Selection within market
        market_odds: Bookmaker odds
        model_confidence: Original model confidence (0-1)
        n_sim: Number of simulations
    
    Returns:
        Dict with full analysis including trust_level
    """
    mc = run_monte_carlo(home_xg, away_xg, n_sim)
    
    sim_prob = 0.0
    
    if market == "1X2":
        if selection in ["1", "HOME", "home_win"]:
            sim_prob = mc.home_win_prob
        elif selection in ["X", "DRAW", "draw"]:
            sim_prob = mc.draw_prob
        elif selection in ["2", "AWAY", "away_win"]:
            sim_prob = mc.away_win_prob
    
    elif market in ["BTTS", "btts"]:
        if selection.lower() in ["yes", "btts_yes"]:
            sim_prob = mc.btts_yes_prob
        else:
            sim_prob = 1.0 - mc.btts_yes_prob
    
    elif market in ["OVER_2_5", "over_25", "O2.5"]:
        if "over" in selection.lower():
            sim_prob = mc.over_25_prob
        else:
            sim_prob = mc.under_25_prob
    
    elif market in ["OVER_3_5", "over_35", "O3.5"]:
        if "over" in selection.lower():
            sim_prob = mc.over_35_prob
        else:
            sim_prob = 1.0 - mc.over_35_prob
    
    elif market in ["EXACT_SCORE", "exact_score"]:
        sim_prob = mc.score_probs.get(selection, 0.0)
    
    else:
        sim_prob = model_confidence
    
    ev_result = calc_ev(sim_prob, market_odds)
    ev_sim = ev_result["ev"]
    
    model_prob = model_confidence
    ev_model_result = calc_ev(model_prob, market_odds)
    ev_model = ev_model_result["ev"]
    
    disagreement = abs(sim_prob - model_prob)
    
    sim_approved = ev_sim >= 0.03
    
    trust_level = classify_trust_level(
        ev_sim=ev_sim,
        ev_model=ev_model,
        confidence=sim_prob,
        disagreement=disagreement,
        sim_approved=sim_approved,
        odds=market_odds
    )
    
    return {
        "market": market,
        "selection": selection,
        "odds": market_odds,
        
        "sim_probability": sim_prob,
        "sim_probability_pct": sim_prob * 100,
        "model_probability": model_prob,
        "model_probability_pct": model_prob * 100,
        
        "fair_odds": fair_odds(sim_prob),
        "ev_sim": ev_sim,
        "ev_sim_pct": ev_sim * 100,
        "ev_model": ev_model,
        "ev_model_pct": ev_model * 100,
        
        "edge": ev_result["edge"],
        "edge_pct": ev_result["edge_pct"],
        
        "disagreement": disagreement,
        "disagreement_pct": disagreement * 100,
        
        "sim_approved": sim_approved,
        "trust_level": trust_level,
        
        "home_xg": home_xg,
        "away_xg": away_xg,
        "simulations": n_sim,
        
        "monte_carlo": {
            "home_win": mc.home_win_prob,
            "draw": mc.draw_prob,
            "away_win": mc.away_win_prob,
            "btts_yes": mc.btts_yes_prob,
            "over_25": mc.over_25_prob,
            "top_scores": mc.top_scores[:5]
        }
    }


def get_best_exact_score_with_mc(
    home_xg: float,
    away_xg: float,
    score_odds: Dict[str, float],
    min_ev: float = 0.03,
    n_sim: int = 10000
) -> Optional[Dict[str, Any]]:
    """
    Find the best exact score bet using Monte Carlo.
    
    Args:
        home_xg: Expected goals for home team
        away_xg: Expected goals for away team
        score_odds: Dict of score -> odds (e.g., {"2-1": 9.00, "1-0": 7.50})
        min_ev: Minimum EV required
        n_sim: Number of simulations
    
    Returns:
        Best exact score bet analysis or None
    """
    mc = run_monte_carlo(home_xg, away_xg, n_sim)
    
    value_scores = []
    
    for score, odds in score_odds.items():
        prob = mc.score_probs.get(score, 0.0)
        if prob <= 0:
            continue
        
        ev_result = calc_ev(prob, odds)
        
        if ev_result["ev"] >= min_ev:
            value_scores.append({
                "score": score,
                "probability": prob,
                "probability_pct": prob * 100,
                "odds": odds,
                "fair_odds": fair_odds(prob),
                "ev": ev_result["ev"],
                "ev_pct": ev_result["ev_pct"],
                "edge": ev_result["edge"],
                "edge_pct": ev_result["edge_pct"],
                "trust_level": "L1_HIGH_TRUST" if ev_result["ev"] >= 0.03 else "L2_MEDIUM_TRUST"
            })
    
    if not value_scores:
        return None
    
    value_scores.sort(key=lambda x: x["ev"], reverse=True)
    
    return value_scores[0]


if __name__ == "__main__":
    print("=== MONTE CARLO INTEGRATION TEST ===\n")
    
    analysis = analyze_bet_with_monte_carlo(
        home_xg=1.5,
        away_xg=1.2,
        market="1X2",
        selection="1",
        market_odds=2.10,
        model_confidence=0.45
    )
    
    print(f"Market: {analysis['market']} - {analysis['selection']} @ {analysis['odds']}")
    print(f"Sim Probability: {analysis['sim_probability_pct']:.1f}%")
    print(f"Model Probability: {analysis['model_probability_pct']:.1f}%")
    print(f"EV (Sim): {analysis['ev_sim_pct']:.1f}%")
    print(f"Disagreement: {analysis['disagreement_pct']:.1f}%")
    print(f"Trust Level: {analysis['trust_level']}")
    
    print("\n--- Exact Score Test ---")
    score_odds = {"1-0": 7.50, "2-1": 9.00, "1-1": 6.50, "2-0": 8.00, "0-0": 10.00}
    best = get_best_exact_score_with_mc(1.5, 1.2, score_odds, min_ev=0.02)
    
    if best:
        print(f"Best Score: {best['score']} @ {best['odds']}")
        print(f"Probability: {best['probability_pct']:.1f}%")
        print(f"EV: {best['ev_pct']:.1f}%")
        print(f"Trust Level: {best['trust_level']}")
    else:
        print("No value scores found")

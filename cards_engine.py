"""
Cards Engine - Match and Team Cards Over/Under Predictions
Uses Monte Carlo simulation with historical discipline data
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from datetime import datetime
import numpy as np
from scipy import stats

from multimarket_config import (
    PRODUCT_CONFIGS,
    get_market_label,
    MarketType
)

logger = logging.getLogger(__name__)

@dataclass
class CardsCandidate:
    fixture_id: str
    home_team: str
    away_team: str
    market_key: str
    selection: str
    line: float
    model_prob: float
    book_odds: float
    ev: float
    confidence: float
    trust_tier: str
    metadata: Dict[str, Any]


CARDS_LINES = {
    "match": [2.5, 3.5, 4.5, 5.5, 6.5],
    "booking_points": [30.5, 40.5, 50.5, 60.5],
    "home": [0.5, 1.5, 2.5, 3.5],
    "away": [0.5, 1.5, 2.5, 3.5],
}

DEFAULT_DISCIPLINE_STATS = {
    "cards_pg": 2.1,
    "cards_against_pg": 1.9,
    "fouls_pg": 11.5,
    "yellow_cards_pg": 1.8,
    "red_cards_pg": 0.05,
    "referee_avg_cards": 4.2,
}

BOOKING_POINTS = {
    "yellow": 10,
    "red": 25,
}


class CardsEngine:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or PRODUCT_CONFIGS.get("CARDS_MATCH", {})
        self.num_sims = 10000
        logger.info("✅ CardsEngine initialized")
    
    def estimate_cards_distribution(
        self,
        home_stats: Dict,
        away_stats: Dict,
        referee_stats: Optional[Dict] = None,
        is_derby: bool = False
    ) -> Dict[str, np.ndarray]:
        """
        Estimate cards distribution using Poisson with referee adjustment.
        """
        home_cards_mean = home_stats.get("cards_pg", DEFAULT_DISCIPLINE_STATS["cards_pg"])
        away_cards_mean = away_stats.get("cards_pg", DEFAULT_DISCIPLINE_STATS["cards_pg"])
        
        ref_factor = 1.0
        if referee_stats:
            ref_avg = referee_stats.get("cards_per_match", DEFAULT_DISCIPLINE_STATS["referee_avg_cards"])
            ref_factor = ref_avg / DEFAULT_DISCIPLINE_STATS["referee_avg_cards"]
        
        derby_factor = 1.15 if is_derby else 1.0
        
        adj_home_cards = home_cards_mean * ref_factor * derby_factor
        adj_away_cards = away_cards_mean * ref_factor * derby_factor
        
        home_yellows = np.random.poisson(adj_home_cards * 0.95, self.num_sims)
        away_yellows = np.random.poisson(adj_away_cards * 0.95, self.num_sims)
        
        home_reds = np.random.binomial(1, 0.05 * derby_factor, self.num_sims)
        away_reds = np.random.binomial(1, 0.05 * derby_factor, self.num_sims)
        
        home_cards = home_yellows + home_reds
        away_cards = away_yellows + away_reds
        total_cards = home_cards + away_cards
        
        home_booking_pts = (home_yellows * BOOKING_POINTS["yellow"] + 
                           home_reds * BOOKING_POINTS["red"])
        away_booking_pts = (away_yellows * BOOKING_POINTS["yellow"] + 
                           away_reds * BOOKING_POINTS["red"])
        total_booking_pts = home_booking_pts + away_booking_pts
        
        return {
            "home_cards": home_cards,
            "away_cards": away_cards,
            "total_cards": total_cards,
            "home_yellows": home_yellows,
            "away_yellows": away_yellows,
            "home_booking_pts": home_booking_pts,
            "away_booking_pts": away_booking_pts,
            "total_booking_pts": total_booking_pts,
        }
    
    def calculate_over_under_probs(
        self,
        simulations: np.ndarray,
        line: float
    ) -> Dict[str, float]:
        """Calculate Over/Under probabilities from simulation results."""
        over_prob = np.mean(simulations > line)
        under_prob = np.mean(simulations < line)
        push_prob = np.mean(simulations == line)
        
        return {
            "over": float(over_prob),
            "under": float(under_prob),
            "push": float(push_prob),
        }
    
    def calculate_ev(self, model_prob: float, book_odds: float) -> float:
        """Calculate expected value."""
        if model_prob <= 0 or book_odds <= 1:
            return -1.0
        return (model_prob * book_odds) - 1
    
    def classify_trust_tier(
        self,
        ev: float,
        confidence: float,
        sim_approved: bool = True,
        product_key: str = "CARDS_MATCH"
    ) -> str:
        """Classify bet into trust tier based on EV and confidence."""
        config = PRODUCT_CONFIGS.get(product_key, {})
        
        l1_ev = getattr(config, 'l1_min_ev', 0.05)
        l1_conf = getattr(config, 'l1_min_confidence', 0.55)
        l2_ev = getattr(config, 'l2_min_ev', 0.02)
        l2_conf = getattr(config, 'l2_min_confidence', 0.52)
        
        if sim_approved and ev >= l1_ev and confidence >= l1_conf:
            return "L1_HIGH_TRUST"
        elif sim_approved and ev >= l2_ev and confidence >= l2_conf:
            return "L2_MEDIUM_TRUST"
        elif ev >= 0 and confidence >= 0.50:
            return "L3_SOFT_VALUE"
        return "REJECTED"
    
    def check_derby_flag(self, home_team: str, away_team: str) -> bool:
        """Check if match is a derby/rivalry."""
        derbies = [
            {"Arsenal", "Tottenham"},
            {"Liverpool", "Everton"},
            {"Manchester United", "Manchester City"},
            {"Chelsea", "Tottenham"},
            {"Real Madrid", "Barcelona"},
            {"Real Madrid", "Atlético Madrid"},
            {"AC Milan", "Inter Milan"},
            {"Juventus", "Inter Milan"},
            {"Borussia Dortmund", "Bayern Munich"},
            {"Ajax", "Feyenoord"},
            {"Celtic", "Rangers"},
            {"Benfica", "Porto"},
        ]
        
        teams = {home_team, away_team}
        for derby in derbies:
            if len(teams.intersection(derby)) == 2:
                return True
        return False
    
    def generate_market_predictions(
        self,
        fixture: Dict,
        odds_snapshot: Dict[str, float],
        team_stats: Optional[Dict] = None,
        referee_stats: Optional[Dict] = None
    ) -> List[CardsCandidate]:
        """
        Generate cards market predictions for a fixture.
        """
        candidates = []
        
        fixture_id = fixture.get("fixture_id", "unknown")
        home_team = fixture.get("home_team", "Home")
        away_team = fixture.get("away_team", "Away")
        
        home_stats = (team_stats or {}).get("home", DEFAULT_DISCIPLINE_STATS)
        away_stats = (team_stats or {}).get("away", DEFAULT_DISCIPLINE_STATS)
        
        is_derby = self.check_derby_flag(home_team, away_team)
        
        sims = self.estimate_cards_distribution(
            home_stats, 
            away_stats, 
            referee_stats,
            is_derby
        )
        
        market_configs = [
            ("CARDS_MATCH", "MATCH_CARDS_OVER_{}_5", "MATCH_CARDS_UNDER_{}_5", 
             "total_cards", CARDS_LINES["match"]),
            ("CARDS_MATCH", "BOOKING_POINTS_OVER_{}_5", "BOOKING_POINTS_UNDER_{}_5",
             "total_booking_pts", CARDS_LINES["booking_points"]),
            ("CARDS_TEAM", "HOME_CARDS_OVER_{}_5", None,
             "home_cards", CARDS_LINES["home"]),
            ("CARDS_TEAM", "AWAY_CARDS_OVER_{}_5", None,
             "away_cards", CARDS_LINES["away"]),
        ]
        
        for product_key, over_template, under_template, sim_key, lines in market_configs:
            config = PRODUCT_CONFIGS.get(product_key)
            if not config:
                continue
            
            min_ev = getattr(config, 'min_ev', 0.02)
            min_odds = getattr(config, 'min_odds', 1.60)
            max_odds = getattr(config, 'max_odds', 2.80)
            min_conf = getattr(config, 'min_confidence', 0.52)
            
            for line in lines:
                line_str = str(int(line))
                
                for direction, template in [("over", over_template), ("under", under_template)]:
                    if template is None:
                        continue
                    
                    market_key = template.format(line_str)
                    
                    book_odds = odds_snapshot.get(market_key, 0)
                    if not (min_odds <= book_odds <= max_odds):
                        continue
                    
                    probs = self.calculate_over_under_probs(sims[sim_key], line)
                    model_prob = probs[direction]
                    
                    if model_prob < min_conf:
                        continue
                    
                    ev = self.calculate_ev(model_prob, book_odds)
                    if ev < min_ev:
                        continue
                    
                    trust_tier = self.classify_trust_tier(
                        ev, model_prob, 
                        sim_approved=True,
                        product_key=product_key
                    )
                    if trust_tier == "REJECTED":
                        continue
                    
                    selection = f"{direction.title()} {line}"
                    
                    market_type = (MarketType.CARDS_MATCH if product_key == "CARDS_MATCH" 
                                   else MarketType.CARDS_TEAM)
                    
                    candidate = CardsCandidate(
                        fixture_id=fixture_id,
                        home_team=home_team,
                        away_team=away_team,
                        market_key=market_key,
                        selection=selection,
                        line=line,
                        model_prob=model_prob,
                        book_odds=book_odds,
                        ev=ev,
                        confidence=model_prob,
                        trust_tier=trust_tier,
                        metadata={
                            "market_type": market_type.value,
                            "sim_key": sim_key,
                            "direction": direction,
                            "is_derby": is_derby,
                            "mean_value": float(np.mean(sims[sim_key])),
                            "std_value": float(np.std(sims[sim_key])),
                        }
                    )
                    candidates.append(candidate)
                    
                    logger.debug(
                        f"🟨 Cards candidate: {home_team} vs {away_team} | "
                        f"{get_market_label(market_key)} @ {book_odds} | "
                        f"p={model_prob:.1%} EV={ev:.1%} | {trust_tier}"
                    )
        
        candidates.sort(key=lambda x: x.ev, reverse=True)
        
        return candidates


def run_cards_cycle(fixtures: List[Dict], odds_data: Dict) -> List[CardsCandidate]:
    """Run cards engine cycle for all fixtures."""
    engine = CardsEngine()
    all_candidates = []
    
    for fixture in fixtures:
        fixture_id = fixture.get("fixture_id")
        odds_snapshot = odds_data.get(fixture_id, {})
        
        if not odds_snapshot:
            continue
        
        candidates = engine.generate_market_predictions(fixture, odds_snapshot)
        all_candidates.extend(candidates)
    
    match_config = PRODUCT_CONFIGS.get("CARDS_MATCH")
    team_config = PRODUCT_CONFIGS.get("CARDS_TEAM")
    
    match_max = getattr(match_config, 'max_per_day', 6)
    team_max = getattr(team_config, 'max_per_day', 4)
    
    match_candidates = [c for c in all_candidates if c.metadata["market_type"] == "CARDS_MATCH"]
    team_candidates = [c for c in all_candidates if c.metadata["market_type"] == "CARDS_TEAM"]
    
    match_candidates.sort(key=lambda x: x.ev, reverse=True)
    team_candidates.sort(key=lambda x: x.ev, reverse=True)
    
    selected = match_candidates[:match_max] + team_candidates[:team_max]
    
    logger.info(f"🟨 CARDS ENGINE: {len(selected)}/{len(all_candidates)} candidates selected")
    
    return selected


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    test_fixture = {
        "fixture_id": "test_456",
        "home_team": "Arsenal",
        "away_team": "Tottenham",
    }
    
    test_odds = {
        "MATCH_CARDS_OVER_3_5": 1.85,
        "MATCH_CARDS_OVER_4_5": 2.20,
        "MATCH_CARDS_UNDER_4_5": 1.70,
        "BOOKING_POINTS_OVER_40_5": 1.90,
        "HOME_CARDS_OVER_1_5": 1.80,
        "AWAY_CARDS_OVER_1_5": 1.75,
    }
    
    engine = CardsEngine()
    candidates = engine.generate_market_predictions(test_fixture, test_odds)
    
    print(f"\n=== Cards Engine Test: {len(candidates)} candidates ===")
    for c in candidates[:5]:
        print(f"  {c.home_team} vs {c.away_team} | {c.market_key}")
        print(f"    Odds: {c.book_odds} | Prob: {c.model_prob:.1%} | EV: {c.ev:.1%}")
        print(f"    Trust: {c.trust_tier} | Derby: {c.metadata['is_derby']}")

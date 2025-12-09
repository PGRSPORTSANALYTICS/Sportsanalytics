"""
Shots Engine - Team and Match Shots Over/Under Predictions
Uses Monte Carlo simulation with xG/xShots-derived distributions
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
class ShotsCandidate:
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


SHOTS_LINES = {
    "team_total": [8.5, 9.5, 10.5, 11.5, 12.5],
    "team_sot": [2.5, 3.5, 4.5, 5.5],
    "home": [3.5, 4.5, 5.5, 6.5],
    "away": [3.5, 4.5, 5.5, 6.5],
    "home_sot": [1.5, 2.5, 3.5],
    "away_sot": [1.5, 2.5, 3.5],
}

DEFAULT_TEAM_STATS = {
    "shots_pg": 12.5,
    "shots_against_pg": 11.5,
    "sot_pg": 4.2,
    "sot_against_pg": 3.8,
    "xg_pg": 1.45,
}


class ShotsEngine:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or PRODUCT_CONFIGS.get("SHOTS_TEAM", {})
        self.num_sims = 10000
        logger.info("✅ ShotsEngine initialized")
    
    def estimate_shots_distribution(
        self, 
        home_stats: Dict, 
        away_stats: Dict
    ) -> Dict[str, np.ndarray]:
        """
        Estimate shots distribution using Poisson with xG-adjusted rates.
        Returns simulated distributions for home shots, away shots, total shots.
        """
        home_shots_mean = home_stats.get("shots_pg", DEFAULT_TEAM_STATS["shots_pg"])
        away_shots_mean = away_stats.get("shots_pg", DEFAULT_TEAM_STATS["shots_pg"])
        
        away_def_factor = away_stats.get("shots_against_pg", DEFAULT_TEAM_STATS["shots_against_pg"]) / DEFAULT_TEAM_STATS["shots_against_pg"]
        home_def_factor = home_stats.get("shots_against_pg", DEFAULT_TEAM_STATS["shots_against_pg"]) / DEFAULT_TEAM_STATS["shots_against_pg"]
        
        adj_home_shots = home_shots_mean * away_def_factor * 1.05
        adj_away_shots = away_shots_mean * home_def_factor * 0.95
        
        home_sims = np.random.poisson(adj_home_shots, self.num_sims)
        away_sims = np.random.poisson(adj_away_shots, self.num_sims)
        
        home_sot_mean = home_stats.get("sot_pg", DEFAULT_TEAM_STATS["sot_pg"])
        away_sot_mean = away_stats.get("sot_pg", DEFAULT_TEAM_STATS["sot_pg"])
        
        home_sot_sims = np.random.poisson(home_sot_mean * away_def_factor, self.num_sims)
        away_sot_sims = np.random.poisson(away_sot_mean * home_def_factor, self.num_sims)
        
        return {
            "home_shots": home_sims,
            "away_shots": away_sims,
            "total_shots": home_sims + away_sims,
            "home_sot": home_sot_sims,
            "away_sot": away_sot_sims,
            "total_sot": home_sot_sims + away_sot_sims,
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
        sim_approved: bool = True
    ) -> str:
        """Classify bet into trust tier based on EV and confidence."""
        config = PRODUCT_CONFIGS.get("SHOTS_TEAM", {})
        
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
    
    def generate_market_predictions(
        self,
        fixture: Dict,
        odds_snapshot: Dict[str, float],
        team_stats: Optional[Dict] = None
    ) -> List[ShotsCandidate]:
        """
        Generate shots market predictions for a fixture.
        
        Args:
            fixture: Fixture data with home_team, away_team, fixture_id
            odds_snapshot: Dict mapping market keys to book odds
            team_stats: Optional pre-fetched team statistics
        
        Returns:
            List of ShotsCandidate objects that pass minimum thresholds
        """
        candidates = []
        
        fixture_id = fixture.get("fixture_id", "unknown")
        home_team = fixture.get("home_team", "Home")
        away_team = fixture.get("away_team", "Away")
        
        home_stats = (team_stats or {}).get("home", DEFAULT_TEAM_STATS)
        away_stats = (team_stats or {}).get("away", DEFAULT_TEAM_STATS)
        
        sims = self.estimate_shots_distribution(home_stats, away_stats)
        
        config = PRODUCT_CONFIGS.get("SHOTS_TEAM")
        if not config:
            return candidates
        
        min_ev = getattr(config, 'min_ev', 0.02)
        min_odds = getattr(config, 'min_odds', 1.60)
        max_odds = getattr(config, 'max_odds', 2.80)
        min_conf = getattr(config, 'min_confidence', 0.52)
        
        market_mappings = [
            ("TEAM_SHOTS_OVER_{}_5", "total_shots", "over", SHOTS_LINES["team_total"]),
            ("TEAM_SHOTS_UNDER_{}_5", "total_shots", "under", SHOTS_LINES["team_total"]),
            ("TEAM_SOT_OVER_{}_5", "total_sot", "over", SHOTS_LINES["team_sot"]),
            ("TEAM_SOT_UNDER_{}_5", "total_sot", "under", SHOTS_LINES["team_sot"]),
            ("HOME_SHOTS_OVER_{}_5", "home_shots", "over", SHOTS_LINES["home"]),
            ("AWAY_SHOTS_OVER_{}_5", "away_shots", "over", SHOTS_LINES["away"]),
            ("HOME_SOT_OVER_{}_5", "home_sot", "over", SHOTS_LINES["home_sot"]),
            ("AWAY_SOT_OVER_{}_5", "away_sot", "over", SHOTS_LINES["away_sot"]),
        ]
        
        for market_template, sim_key, direction, lines in market_mappings:
            for line in lines:
                line_str = str(int(line))
                market_key = market_template.format(line_str)
                
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
                
                trust_tier = self.classify_trust_tier(ev, model_prob, sim_approved=True)
                if trust_tier == "REJECTED":
                    continue
                
                selection = f"{direction.title()} {line}"
                
                candidate = ShotsCandidate(
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
                        "market_type": MarketType.SHOTS_TEAM.value,
                        "sim_key": sim_key,
                        "direction": direction,
                        "mean_value": float(np.mean(sims[sim_key])),
                        "std_value": float(np.std(sims[sim_key])),
                    }
                )
                candidates.append(candidate)
                
                logger.debug(
                    f"📊 Shots candidate: {home_team} vs {away_team} | "
                    f"{get_market_label(market_key)} @ {book_odds} | "
                    f"p={model_prob:.1%} EV={ev:.1%} | {trust_tier}"
                )
        
        candidates.sort(key=lambda x: x.ev, reverse=True)
        
        return candidates


def run_shots_cycle(fixtures: List[Dict], odds_data: Dict) -> List[ShotsCandidate]:
    """Run shots engine cycle for all fixtures."""
    engine = ShotsEngine()
    all_candidates = []
    
    for fixture in fixtures:
        fixture_id = fixture.get("fixture_id")
        odds_snapshot = odds_data.get(fixture_id, {})
        
        if not odds_snapshot:
            continue
        
        candidates = engine.generate_market_predictions(fixture, odds_snapshot)
        all_candidates.extend(candidates)
    
    config = PRODUCT_CONFIGS.get("SHOTS_TEAM")
    max_per_day = getattr(config, 'max_per_day', 6)
    
    all_candidates.sort(key=lambda x: x.ev, reverse=True)
    selected = all_candidates[:max_per_day]
    
    logger.info(f"🎯 SHOTS ENGINE: {len(selected)}/{len(all_candidates)} candidates selected")
    
    return selected


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    test_fixture = {
        "fixture_id": "test_123",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
    }
    
    test_odds = {
        "TEAM_SHOTS_OVER_10_5": 1.85,
        "TEAM_SHOTS_OVER_11_5": 2.10,
        "TEAM_SHOTS_UNDER_10_5": 1.95,
        "TEAM_SOT_OVER_3_5": 1.90,
        "HOME_SHOTS_OVER_5_5": 1.75,
    }
    
    engine = ShotsEngine()
    candidates = engine.generate_market_predictions(test_fixture, test_odds)
    
    print(f"\n=== Shots Engine Test: {len(candidates)} candidates ===")
    for c in candidates[:5]:
        print(f"  {c.home_team} vs {c.away_team} | {c.market_key}")
        print(f"    Odds: {c.book_odds} | Prob: {c.model_prob:.1%} | EV: {c.ev:.1%}")
        print(f"    Trust: {c.trust_tier}")

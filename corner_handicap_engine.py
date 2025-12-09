"""
Corner Handicap Engine - Corner Handicap Line Predictions
Extends corners analysis to model corner difference distributions
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
class CornerHCCandidate:
    fixture_id: str
    home_team: str
    away_team: str
    market_key: str
    selection: str
    handicap_line: float
    model_prob: float
    book_odds: float
    ev: float
    confidence: float
    trust_tier: str
    metadata: Dict[str, Any]


HANDICAP_LINES = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]

DEFAULT_CORNER_STATS = {
    "corners_for_pg": 5.2,
    "corners_against_pg": 4.8,
    "corner_ratio": 1.08,
}


class CornerHandicapEngine:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or PRODUCT_CONFIGS.get("CORNERS_HANDICAP", {})
        self.num_sims = 10000
        logger.info("✅ CornerHandicapEngine initialized")
    
    def estimate_corners_distribution(
        self,
        home_stats: Dict,
        away_stats: Dict
    ) -> Dict[str, np.ndarray]:
        """
        Estimate corner distribution for both teams using Poisson.
        Home teams typically get more corners.
        """
        home_corners_mean = home_stats.get("corners_for_pg", DEFAULT_CORNER_STATS["corners_for_pg"])
        away_corners_mean = away_stats.get("corners_for_pg", DEFAULT_CORNER_STATS["corners_for_pg"])
        
        away_concede_rate = away_stats.get("corners_against_pg", DEFAULT_CORNER_STATS["corners_against_pg"])
        home_concede_rate = home_stats.get("corners_against_pg", DEFAULT_CORNER_STATS["corners_against_pg"])
        
        adj_home_corners = (home_corners_mean * 0.6 + away_concede_rate * 0.4) * 1.08
        adj_away_corners = (away_corners_mean * 0.6 + home_concede_rate * 0.4) * 0.95
        
        home_sims = np.random.poisson(adj_home_corners, self.num_sims)
        away_sims = np.random.poisson(adj_away_corners, self.num_sims)
        
        corner_diff = home_sims.astype(int) - away_sims.astype(int)
        
        return {
            "home_corners": home_sims,
            "away_corners": away_sims,
            "total_corners": home_sims + away_sims,
            "corner_diff": corner_diff,
        }
    
    def calculate_handicap_prob(
        self,
        corner_diff: np.ndarray,
        handicap_line: float,
        team: str = "home"
    ) -> float:
        """
        Calculate probability of covering a handicap line.
        
        For home -1.5: home must win corners by 2+
        For away +1.5: away must not lose by 2+ (diff <= 1)
        """
        if team == "home":
            return float(np.mean(corner_diff > handicap_line))
        else:
            return float(np.mean(-corner_diff > handicap_line))
    
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
        config = PRODUCT_CONFIGS.get("CORNERS_HANDICAP", {})
        
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
    ) -> List[CornerHCCandidate]:
        """
        Generate corner handicap predictions for a fixture.
        """
        candidates = []
        
        fixture_id = fixture.get("fixture_id", "unknown")
        home_team = fixture.get("home_team", "Home")
        away_team = fixture.get("away_team", "Away")
        
        home_stats = (team_stats or {}).get("home", DEFAULT_CORNER_STATS)
        away_stats = (team_stats or {}).get("away", DEFAULT_CORNER_STATS)
        
        sims = self.estimate_corners_distribution(home_stats, away_stats)
        corner_diff = sims["corner_diff"]
        
        config = PRODUCT_CONFIGS.get("CORNERS_HANDICAP")
        if not config:
            return candidates
        
        min_ev = getattr(config, 'min_ev', 0.02)
        min_odds = getattr(config, 'min_odds', 1.70)
        max_odds = getattr(config, 'max_odds', 2.50)
        min_conf = getattr(config, 'min_confidence', 0.52)
        
        for line in HANDICAP_LINES:
            for team in ["home", "away"]:
                line_str = str(line).replace(".", "_").replace("-", "-")
                if line > 0:
                    line_str = f"+{line_str}"
                
                team_prefix = "HOME" if team == "home" else "AWAY"
                market_key = f"CORNERS_HC_{team_prefix}_{line_str}"
                
                book_odds = odds_snapshot.get(market_key, 0)
                if not (min_odds <= book_odds <= max_odds):
                    continue
                
                model_prob = self.calculate_handicap_prob(corner_diff, line, team)
                
                if model_prob < min_conf:
                    continue
                
                ev = self.calculate_ev(model_prob, book_odds)
                if ev < min_ev:
                    continue
                
                trust_tier = self.classify_trust_tier(ev, model_prob, sim_approved=True)
                if trust_tier == "REJECTED":
                    continue
                
                team_name = home_team if team == "home" else away_team
                selection = f"{team_name} {'+' if line > 0 else ''}{line}"
                
                candidate = CornerHCCandidate(
                    fixture_id=fixture_id,
                    home_team=home_team,
                    away_team=away_team,
                    market_key=market_key,
                    selection=selection,
                    handicap_line=line,
                    model_prob=model_prob,
                    book_odds=book_odds,
                    ev=ev,
                    confidence=model_prob,
                    trust_tier=trust_tier,
                    metadata={
                        "market_type": MarketType.CORNERS_HANDICAP.value,
                        "team": team,
                        "mean_diff": float(np.mean(corner_diff)),
                        "std_diff": float(np.std(corner_diff)),
                        "home_mean": float(np.mean(sims["home_corners"])),
                        "away_mean": float(np.mean(sims["away_corners"])),
                    }
                )
                candidates.append(candidate)
                
                logger.debug(
                    f"🔷 Corner HC candidate: {home_team} vs {away_team} | "
                    f"{selection} @ {book_odds} | "
                    f"p={model_prob:.1%} EV={ev:.1%} | {trust_tier}"
                )
        
        candidates.sort(key=lambda x: x.ev, reverse=True)
        
        return candidates


def run_corner_handicap_cycle(fixtures: List[Dict], odds_data: Dict) -> List[CornerHCCandidate]:
    """Run corner handicap engine cycle for all fixtures."""
    engine = CornerHandicapEngine()
    all_candidates = []
    
    for fixture in fixtures:
        fixture_id = fixture.get("fixture_id")
        odds_snapshot = odds_data.get(fixture_id, {})
        
        if not odds_snapshot:
            continue
        
        candidates = engine.generate_market_predictions(fixture, odds_snapshot)
        all_candidates.extend(candidates)
    
    config = PRODUCT_CONFIGS.get("CORNERS_HANDICAP")
    max_per_day = getattr(config, 'max_per_day', 6)
    
    all_candidates.sort(key=lambda x: x.ev, reverse=True)
    selected = all_candidates[:max_per_day]
    
    logger.info(f"🔷 CORNER HANDICAP ENGINE: {len(selected)}/{len(all_candidates)} candidates selected")
    
    return selected


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    test_fixture = {
        "fixture_id": "test_789",
        "home_team": "Manchester City",
        "away_team": "Burnley",
    }
    
    test_odds = {
        "CORNERS_HC_HOME_-1_5": 1.85,
        "CORNERS_HC_HOME_-2_5": 2.30,
        "CORNERS_HC_AWAY_+1_5": 1.95,
        "CORNERS_HC_AWAY_+2_5": 1.70,
    }
    
    engine = CornerHandicapEngine()
    candidates = engine.generate_market_predictions(test_fixture, test_odds)
    
    print(f"\n=== Corner Handicap Engine Test: {len(candidates)} candidates ===")
    for c in candidates[:5]:
        print(f"  {c.home_team} vs {c.away_team} | {c.selection}")
        print(f"    Odds: {c.book_odds} | Prob: {c.model_prob:.1%} | EV: {c.ev:.1%}")
        print(f"    Trust: {c.trust_tier}")
        print(f"    Mean diff: {c.metadata['mean_diff']:.1f}")

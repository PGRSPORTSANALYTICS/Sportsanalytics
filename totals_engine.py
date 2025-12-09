"""
Totals Engine - Over/Under Goals Product (MultiMarket Expansion v1.0)
=====================================================================
Separate product for Over/Under goal markets with Nova v2.0 trust tiers.

Markets: Over/Under 1.5, 2.5, 3.5 goals
Daily Limit: 10 bets max
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from bet_filter import BetCandidate
from multimarket_config import PRODUCT_CONFIGS, get_market_label, MarketType

logger = logging.getLogger(__name__)

TOTALS_CONFIG = PRODUCT_CONFIGS["TOTALS"]

TOTALS_MARKETS = {
    "FT_OVER_1_5": ("over_15", "Over 1.5 Goals"),
    "FT_UNDER_1_5": ("under_15", "Under 1.5 Goals"),
    "FT_OVER_2_5": ("over_25", "Over 2.5 Goals"),
    "FT_UNDER_2_5": ("under_25", "Under 2.5 Goals"),
    "FT_OVER_3_5": ("over_35", "Over 3.5 Goals"),
    "FT_UNDER_3_5": ("under_35", "Under 3.5 Goals"),
}


class TotalsEngine:
    """Engine for Over/Under goal market predictions."""
    
    def __init__(self):
        self.config = TOTALS_CONFIG
        self.daily_picks: List[BetCandidate] = []
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"🎯 Totals Engine initialized (max {self.config.max_per_day}/day)")
    
    def calculate_probabilities(self, mc_result: Dict) -> Dict[str, float]:
        probs = {}
        for market_key, (sim_key, _) in TOTALS_MARKETS.items():
            if sim_key in mc_result:
                probs[market_key] = mc_result[sim_key]
            elif sim_key.startswith("under_"):
                over_key = sim_key.replace("under_", "over_")
                if over_key in mc_result:
                    probs[market_key] = 1.0 - mc_result[over_key]
        return probs
    
    def find_value_bets(
        self,
        match: str,
        home_team: str,
        away_team: str,
        league: str,
        mc_result: Dict,
        odds_dict: Dict[str, float],
        match_date: str = None
    ) -> List[BetCandidate]:
        candidates = []
        probs = self.calculate_probabilities(mc_result)
        
        for market_key, p_model in probs.items():
            odds = odds_dict.get(market_key)
            if odds is None:
                continue
            
            if not (self.config.min_odds <= odds <= self.config.max_odds):
                continue
            
            if p_model < self.config.min_confidence:
                continue
            
            ev = (p_model * odds) - 1.0
            
            if ev < self.config.min_ev:
                continue
            
            sim_approved = ev >= 0.03
            
            if ev >= self.config.l1_min_ev and p_model >= self.config.l1_min_confidence and sim_approved:
                tier = "L1_HIGH_TRUST"
            elif ev >= self.config.l2_min_ev and p_model >= self.config.l2_min_confidence and sim_approved:
                tier = "L2_MEDIUM_TRUST"
            elif ev >= self.config.l3_min_ev and p_model >= self.config.l3_min_confidence:
                tier = "L3_SOFT_VALUE"
            else:
                continue
            
            selection_text = TOTALS_MARKETS.get(market_key, (None, market_key))[1]
            
            candidate = BetCandidate(
                match=match,
                market=market_key,
                selection=selection_text,
                odds=odds,
                ev_sim=ev,
                ev_model=ev,
                confidence=p_model,
                disagreement=0.0,
                approved=sim_approved,
                tier=tier,
                market_type="TOTALS",
                product="TOTALS",
                league=league,
                home_team=home_team,
                away_team=away_team,
                match_date=match_date or self.today
            )
            candidates.append(candidate)
        
        return candidates
    
    def select_best_per_match(self, candidates: List[BetCandidate]) -> List[BetCandidate]:
        by_match: Dict[str, List[BetCandidate]] = {}
        for c in candidates:
            if c.match not in by_match:
                by_match[c.match] = []
            by_match[c.match].append(c)
        
        selected = []
        for match, match_candidates in by_match.items():
            sorted_cands = sorted(match_candidates, key=lambda x: (
                0 if x.tier == "L1_HIGH_TRUST" else (1 if x.tier == "L2_MEDIUM_TRUST" else 2),
                -x.ev_sim
            ))
            selected.append(sorted_cands[0])
        
        return selected
    
    def apply_daily_filter(self, candidates: List[BetCandidate]) -> List[BetCandidate]:
        l1 = [c for c in candidates if c.tier == "L1_HIGH_TRUST"]
        l2 = [c for c in candidates if c.tier == "L2_MEDIUM_TRUST"]
        l3 = [c for c in candidates if c.tier == "L3_SOFT_VALUE"]
        
        l1_sorted = sorted(l1, key=lambda x: x.ev_sim, reverse=True)[:3]
        l2_sorted = sorted(l2, key=lambda x: x.ev_sim, reverse=True)
        l3_sorted = sorted(l3, key=lambda x: x.ev_sim, reverse=True)
        
        selected = list(l1_sorted)
        
        remaining = self.config.max_per_day - len(selected)
        selected.extend(l2_sorted[:remaining])
        
        if len(selected) < 5 and l3_sorted:
            remaining = min(5 - len(selected), len(l3_sorted))
            selected.extend(l3_sorted[:remaining])
        
        return selected
    
    def get_summary(self, bets: List[BetCandidate]) -> Dict:
        tier_counts = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0}
        total_ev = 0.0
        
        for b in bets:
            if b.tier in tier_counts:
                tier_counts[b.tier] += 1
            total_ev += b.ev_sim
        
        return {
            "product": "TOTALS",
            "total": len(bets),
            "by_tier": tier_counts,
            "avg_ev": total_ev / len(bets) if bets else 0.0,
            "max_per_day": self.config.max_per_day
        }


if __name__ == "__main__":
    engine = TotalsEngine()
    
    mock_mc = {
        "over_15": 0.82,
        "over_25": 0.58,
        "over_35": 0.32,
        "under_25": 0.42,
        "under_35": 0.68,
    }
    
    mock_odds = {
        "FT_OVER_2_5": 1.85,
        "FT_UNDER_2_5": 2.00,
        "FT_OVER_3_5": 2.80,
        "FT_UNDER_3_5": 1.45,
    }
    
    candidates = engine.find_value_bets(
        match="Liverpool vs Chelsea",
        home_team="Liverpool",
        away_team="Chelsea",
        league="Premier League",
        mc_result=mock_mc,
        odds_dict=mock_odds
    )
    
    print("=== TOTALS ENGINE TEST ===\n")
    for c in candidates:
        print(f"[{c.tier}] {c.match} | {c.selection} @ {c.odds}")
        print(f"   EV: {c.ev_sim:.1%} | Confidence: {c.confidence:.0%}")
    
    print(f"\n{engine.get_summary(candidates)}")

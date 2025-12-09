"""
BTTS Engine - Both Teams To Score Product (MultiMarket Expansion v1.0)
======================================================================
Separate product for BTTS markets with Nova v2.0 trust tiers.

Markets: BTTS Yes, BTTS No
Daily Limit: 8 bets max
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

from bet_filter import BetCandidate
from multimarket_config import PRODUCT_CONFIGS, get_market_label, MarketType

logger = logging.getLogger(__name__)

BTTS_CONFIG = PRODUCT_CONFIGS["BTTS"]

BTTS_MARKETS = {
    "BTTS_YES": ("btts_yes", "BTTS Yes"),
    "BTTS_NO": ("btts_no", "BTTS No"),
}


class BTTSEngine:
    """Engine for Both Teams To Score market predictions."""
    
    def __init__(self):
        self.config = BTTS_CONFIG
        self.daily_picks: List[BetCandidate] = []
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"⚽ BTTS Engine initialized (max {self.config.max_per_day}/day)")
    
    def calculate_probabilities(self, mc_result: Dict) -> Dict[str, float]:
        probs = {}
        for market_key, (sim_key, _) in BTTS_MARKETS.items():
            if sim_key in mc_result:
                probs[market_key] = mc_result[sim_key]
        return probs
    
    def check_h2h_btts_filter(self, h2h_data: Optional[Dict] = None) -> bool:
        if not h2h_data:
            return True
        
        btts_rate = h2h_data.get("btts_rate", 0.5)
        if btts_rate < 0.3:
            return False
        
        return True
    
    def find_value_bets(
        self,
        match: str,
        home_team: str,
        away_team: str,
        league: str,
        mc_result: Dict,
        odds_dict: Dict[str, float],
        match_date: str = None,
        h2h_data: Optional[Dict] = None
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
            
            if market_key == "BTTS_YES" and h2h_data:
                if not self.check_h2h_btts_filter(h2h_data):
                    logger.debug(f"⚠️ BTTS Yes blocked by H2H filter: {match}")
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
            
            selection_text = BTTS_MARKETS.get(market_key, (None, market_key))[1]
            
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
                market_type="BTTS",
                product="BTTS",
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
        
        l1_sorted = sorted(l1, key=lambda x: x.ev_sim, reverse=True)[:2]
        l2_sorted = sorted(l2, key=lambda x: x.ev_sim, reverse=True)
        l3_sorted = sorted(l3, key=lambda x: x.ev_sim, reverse=True)
        
        selected = list(l1_sorted)
        
        remaining = self.config.max_per_day - len(selected)
        selected.extend(l2_sorted[:remaining])
        
        if len(selected) < 3 and l3_sorted:
            remaining = min(3 - len(selected), len(l3_sorted))
            selected.extend(l3_sorted[:remaining])
        
        return selected
    
    def get_summary(self, bets: List[BetCandidate]) -> Dict:
        tier_counts = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0}
        btts_yes_count = 0
        btts_no_count = 0
        total_ev = 0.0
        
        for b in bets:
            if b.tier in tier_counts:
                tier_counts[b.tier] += 1
            if b.market == "BTTS_YES":
                btts_yes_count += 1
            elif b.market == "BTTS_NO":
                btts_no_count += 1
            total_ev += b.ev_sim
        
        return {
            "product": "BTTS",
            "total": len(bets),
            "btts_yes": btts_yes_count,
            "btts_no": btts_no_count,
            "by_tier": tier_counts,
            "avg_ev": total_ev / len(bets) if bets else 0.0,
            "max_per_day": self.config.max_per_day
        }


if __name__ == "__main__":
    engine = BTTSEngine()
    
    mock_mc = {
        "btts_yes": 0.62,
        "btts_no": 0.38,
    }
    
    mock_odds = {
        "BTTS_YES": 1.72,
        "BTTS_NO": 2.10,
    }
    
    candidates = engine.find_value_bets(
        match="Liverpool vs Chelsea",
        home_team="Liverpool",
        away_team="Chelsea",
        league="Premier League",
        mc_result=mock_mc,
        odds_dict=mock_odds
    )
    
    print("=== BTTS ENGINE TEST ===\n")
    for c in candidates:
        print(f"[{c.tier}] {c.match} | {c.selection} @ {c.odds}")
        print(f"   EV: {c.ev_sim:.1%} | Confidence: {c.confidence:.0%}")
    
    print(f"\n{engine.get_summary(candidates)}")

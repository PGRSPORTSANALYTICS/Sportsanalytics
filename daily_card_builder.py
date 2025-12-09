"""
Daily Card Builder - MultiMarket Expansion v1.0 (Dec 9, 2025)
=============================================================
Orchestrates all products into a unified daily betting card.

Products included:
1. Value Singles (ML/AH/DC) - max 15/day
2. Totals (Over/Under) - max 10/day
3. BTTS - max 8/day
4. Corners - max 6 match, 4 team
5. ML Parlays - max 5/day
6. Multi-Match Parlays - max 2/day

Nova v2.0 trust tiers applied to each product.
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from bet_filter import BetCandidate
from multimarket_config import PRODUCT_CONFIGS, DAILY_TARGETS, ProductType

logger = logging.getLogger(__name__)


@dataclass
class DailyCard:
    date: str
    value_singles: List[BetCandidate] = field(default_factory=list)
    totals: List[BetCandidate] = field(default_factory=list)
    btts: List[BetCandidate] = field(default_factory=list)
    corners_match: List[BetCandidate] = field(default_factory=list)
    corners_team: List[BetCandidate] = field(default_factory=list)
    ml_parlays: List[Dict] = field(default_factory=list)
    multi_match_parlays: List[Dict] = field(default_factory=list)
    
    def get_all_singles(self) -> List[BetCandidate]:
        return (
            self.value_singles + 
            self.totals + 
            self.btts + 
            self.corners_match + 
            self.corners_team
        )
    
    def total_bets(self) -> int:
        return (
            len(self.value_singles) +
            len(self.totals) +
            len(self.btts) +
            len(self.corners_match) +
            len(self.corners_team) +
            len(self.ml_parlays) +
            len(self.multi_match_parlays)
        )
    
    def get_tier_breakdown(self) -> Dict[str, Dict[str, int]]:
        breakdown = {}
        
        products = {
            "VALUE_SINGLES": self.value_singles,
            "TOTALS": self.totals,
            "BTTS": self.btts,
            "CORNERS_MATCH": self.corners_match,
            "CORNERS_TEAM": self.corners_team,
        }
        
        for product_name, bets in products.items():
            tier_counts = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0}
            for b in bets:
                if b.tier in tier_counts:
                    tier_counts[b.tier] += 1
            breakdown[product_name] = tier_counts
        
        return breakdown


class DailyCardBuilder:
    
    def __init__(self):
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info("📋 Daily Card Builder initialized (MultiMarket Expansion v1.0)")
    
    def build_card(
        self,
        value_singles: List[BetCandidate],
        totals: List[BetCandidate],
        btts: List[BetCandidate],
        corners_match: List[BetCandidate],
        corners_team: List[BetCandidate],
        ml_parlays: List[Dict] = None,
        multi_match_parlays: List[Dict] = None
    ) -> DailyCard:
        card = DailyCard(date=self.today)
        
        card.value_singles = self._filter_product(
            value_singles,
            PRODUCT_CONFIGS["VALUE_SINGLES"].max_per_day,
            "VALUE_SINGLES"
        )
        
        card.totals = self._filter_product(
            totals,
            PRODUCT_CONFIGS["TOTALS"].max_per_day,
            "TOTALS"
        )
        
        card.btts = self._filter_product(
            btts,
            PRODUCT_CONFIGS["BTTS"].max_per_day,
            "BTTS"
        )
        
        card.corners_match = self._filter_product(
            corners_match,
            PRODUCT_CONFIGS["CORNERS_MATCH"].max_per_day,
            "CORNERS_MATCH"
        )
        
        card.corners_team = self._filter_product(
            corners_team,
            PRODUCT_CONFIGS["CORNERS_TEAM"].max_per_day,
            "CORNERS_TEAM"
        )
        
        if ml_parlays:
            card.ml_parlays = ml_parlays[:PRODUCT_CONFIGS["ML_PARLAYS"].max_per_day]
        
        if multi_match_parlays:
            card.multi_match_parlays = multi_match_parlays[:PRODUCT_CONFIGS["MULTI_MATCH_PARLAYS"].max_per_day]
        
        return card
    
    def _filter_product(
        self,
        candidates: List[BetCandidate],
        max_count: int,
        product_name: str
    ) -> List[BetCandidate]:
        if not candidates:
            return []
        
        l1 = [c for c in candidates if c.tier == "L1_HIGH_TRUST"]
        l2 = [c for c in candidates if c.tier == "L2_MEDIUM_TRUST"]
        l3 = [c for c in candidates if c.tier == "L3_SOFT_VALUE"]
        
        l1_sorted = sorted(l1, key=lambda x: x.ev_sim, reverse=True)
        l2_sorted = sorted(l2, key=lambda x: x.ev_sim, reverse=True)
        l3_sorted = sorted(l3, key=lambda x: x.ev_sim, reverse=True)
        
        selected = []
        
        l1_cap = min(3, max_count)
        selected.extend(l1_sorted[:l1_cap])
        
        remaining = max_count - len(selected)
        selected.extend(l2_sorted[:remaining])
        
        targets = DAILY_TARGETS.get(product_name, {"min": 3})
        if len(selected) < targets["min"] and l3_sorted:
            remaining = min(targets["min"] - len(selected), len(l3_sorted))
            selected.extend(l3_sorted[:remaining])
        
        return selected
    
    def print_card_summary(self, card: DailyCard):
        print("\n" + "=" * 60)
        print(f"📋 DAILY BETTING CARD - {card.date}")
        print("=" * 60)
        
        print(f"\n🎯 VALUE SINGLES (ML/AH/DC): {len(card.value_singles)} bets")
        if card.value_singles:
            self._print_section(card.value_singles)
        
        print(f"\n📊 TOTALS (Over/Under): {len(card.totals)} bets")
        if card.totals:
            self._print_section(card.totals)
        
        print(f"\n⚽ BTTS: {len(card.btts)} bets")
        if card.btts:
            self._print_section(card.btts)
        
        print(f"\n🔢 CORNERS (Match): {len(card.corners_match)} bets")
        if card.corners_match:
            self._print_section(card.corners_match)
        
        print(f"\n🔢 CORNERS (Team): {len(card.corners_team)} bets")
        if card.corners_team:
            self._print_section(card.corners_team)
        
        print(f"\n🎰 ML PARLAYS: {len(card.ml_parlays)} parlays")
        print(f"🎲 MULTI-MATCH PARLAYS: {len(card.multi_match_parlays)} parlays")
        
        print("\n" + "-" * 60)
        print("📈 TIER BREAKDOWN:")
        breakdown = card.get_tier_breakdown()
        for product, tiers in breakdown.items():
            if sum(tiers.values()) > 0:
                print(f"  {product}: L1={tiers['L1_HIGH_TRUST']} | L2={tiers['L2_MEDIUM_TRUST']} | L3={tiers['L3_SOFT_VALUE']}")
        
        print(f"\n💰 TOTAL BETS: {card.total_bets()}")
        print("=" * 60)
    
    def _print_section(self, bets: List[BetCandidate], max_show: int = 5):
        for b in bets[:max_show]:
            tier_label = b.tier.replace("_", " ").replace("HIGH TRUST", "HT").replace("MEDIUM TRUST", "MT").replace("SOFT VALUE", "SV") if b.tier else "?"
            print(f"  [{tier_label[:5]}] {b.match}")
            print(f"         {b.selection} @ {b.odds:.2f} | EV: {b.ev_sim:.1%} | Conf: {b.confidence:.0%}")
        if len(bets) > max_show:
            print(f"  ... and {len(bets) - max_show} more")
    
    def get_card_stats(self, card: DailyCard) -> Dict:
        all_singles = card.get_all_singles()
        
        total_ev = sum(b.ev_sim for b in all_singles)
        avg_ev = total_ev / len(all_singles) if all_singles else 0
        avg_odds = sum(b.odds for b in all_singles) / len(all_singles) if all_singles else 0
        avg_conf = sum(b.confidence for b in all_singles) / len(all_singles) if all_singles else 0
        
        return {
            "date": card.date,
            "total_bets": card.total_bets(),
            "value_singles": len(card.value_singles),
            "totals": len(card.totals),
            "btts": len(card.btts),
            "corners_match": len(card.corners_match),
            "corners_team": len(card.corners_team),
            "ml_parlays": len(card.ml_parlays),
            "multi_match_parlays": len(card.multi_match_parlays),
            "avg_ev": avg_ev,
            "avg_odds": avg_odds,
            "avg_confidence": avg_conf,
            "tier_breakdown": card.get_tier_breakdown()
        }


if __name__ == "__main__":
    builder = DailyCardBuilder()
    
    mock_singles = [
        BetCandidate("Liverpool vs Chelsea", "HOME_WIN", "Home Win", 1.85, ev_sim=0.06, confidence=0.58, tier="L1_HIGH_TRUST", market_type="ML", product="VALUE_SINGLES"),
        BetCandidate("Arsenal vs City", "AWAY_WIN", "Away Win", 2.10, ev_sim=0.04, confidence=0.55, tier="L2_MEDIUM_TRUST", market_type="ML", product="VALUE_SINGLES"),
    ]
    
    mock_totals = [
        BetCandidate("Bayern vs Dortmund", "FT_OVER_2_5", "Over 2.5 Goals", 1.75, ev_sim=0.05, confidence=0.60, tier="L1_HIGH_TRUST", market_type="TOTALS", product="TOTALS"),
    ]
    
    mock_btts = [
        BetCandidate("Real vs Barca", "BTTS_YES", "BTTS Yes", 1.70, ev_sim=0.04, confidence=0.58, tier="L2_MEDIUM_TRUST", market_type="BTTS", product="BTTS"),
    ]
    
    card = builder.build_card(
        value_singles=mock_singles,
        totals=mock_totals,
        btts=mock_btts,
        corners_match=[],
        corners_team=[]
    )
    
    builder.print_card_summary(card)
    print(f"\nStats: {builder.get_card_stats(card)}")

"""
Tiered Bet Filter System
Multi-level trust filtering for bet candidates based on simulation, model, and confidence.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class BetCandidate:
    """Represents a potential bet with all analysis metrics."""
    match: str
    market: str
    selection: str
    odds: float
    
    ev_sim: float = 0.0
    ev_model: float = 0.0
    confidence: float = 0.0
    disagreement: float = 0.0
    approved: bool = False
    
    stake: float = 0.0
    tier: Optional[str] = None


def filter_level1_high_trust(candidates: List[BetCandidate], min_ev: float = 0.03) -> List[BetCandidate]:
    """
    Level 1: HIGH TRUST
    - Must be approved by simulation filter
    - EV_sim >= 3%
    """
    level1 = [b for b in candidates if b.approved and b.ev_sim >= min_ev]
    for b in level1:
        b.tier = "L1_HIGH_TRUST"
    return level1


def filter_level2_medium_trust(candidates: List[BetCandidate]) -> List[BetCandidate]:
    """
    Level 2: MEDIUM TRUST
    - EV_model >= 0 (positive expectation)
    - Confidence >= 60%
    - Low model disagreement (<= 15%)
    - Odds in sweet spots: 1.50-2.20 or 4.0-6.0
    """
    level2 = [
        b for b in candidates
        if b.ev_model >= 0
        and b.confidence >= 0.60
        and b.disagreement <= 0.15
        and (1.50 <= b.odds <= 2.20 or 4.0 <= b.odds <= 6.0)
    ]
    for b in level2:
        b.tier = "L2_MEDIUM_TRUST"
    return level2


def filter_level3_soft_value(candidates: List[BetCandidate]) -> List[BetCandidate]:
    """
    Level 3: SOFT VALUE (fallback)
    - EV_model >= 0
    - Confidence >= 55%
    - Moderate disagreement (<= 20%)
    """
    level3 = [
        b for b in candidates
        if b.ev_model >= 0
        and b.confidence >= 0.55
        and b.disagreement <= 0.20
    ]
    for b in level3:
        b.tier = "L3_SOFT_VALUE"
    return level3


def apply_tiered_filter(candidates: List[BetCandidate], max_bets: int = 10) -> List[BetCandidate]:
    """
    Apply tiered filtering with priority:
    1. First fill from Level 1 (highest trust)
    2. Then fill from Level 2
    3. Finally fill from Level 3 if still needed
    
    Returns up to max_bets sorted by tier then EV.
    """
    selected = []
    remaining_slots = max_bets
    
    seen = set()
    
    level1 = filter_level1_high_trust(candidates)
    for b in sorted(level1, key=lambda x: x.ev_sim, reverse=True):
        key = (b.match, b.market, b.selection)
        if key not in seen and remaining_slots > 0:
            selected.append(b)
            seen.add(key)
            remaining_slots -= 1
    
    if remaining_slots > 0:
        remaining = [b for b in candidates if (b.match, b.market, b.selection) not in seen]
        level2 = filter_level2_medium_trust(remaining)
        for b in sorted(level2, key=lambda x: x.ev_model, reverse=True):
            key = (b.match, b.market, b.selection)
            if key not in seen and remaining_slots > 0:
                selected.append(b)
                seen.add(key)
                remaining_slots -= 1
    
    if remaining_slots > 0:
        remaining = [b for b in candidates if (b.match, b.market, b.selection) not in seen]
        level3 = filter_level3_soft_value(remaining)
        for b in sorted(level3, key=lambda x: x.ev_model, reverse=True):
            key = (b.match, b.market, b.selection)
            if key not in seen and remaining_slots > 0:
                selected.append(b)
                seen.add(key)
                remaining_slots -= 1
    
    return selected


def summarize_filtered_bets(bets: List[BetCandidate]) -> dict:
    """Get summary of filtered bets by tier."""
    tier_counts = {}
    tier_ev = {}
    
    for b in bets:
        tier = b.tier or "UNCLASSIFIED"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        tier_ev[tier] = tier_ev.get(tier, 0) + b.ev_sim
    
    return {
        "total": len(bets),
        "by_tier": tier_counts,
        "total_ev_by_tier": tier_ev
    }


if __name__ == "__main__":
    test_candidates = [
        BetCandidate("Liverpool vs Chelsea", "1X2", "1", 1.85, ev_sim=0.05, ev_model=0.04, confidence=0.72, disagreement=0.08, approved=True),
        BetCandidate("Real Madrid vs Barcelona", "BTTS", "Yes", 1.75, ev_sim=0.02, ev_model=0.03, confidence=0.65, disagreement=0.10, approved=False),
        BetCandidate("Bayern vs Dortmund", "O2.5", "Over", 1.90, ev_sim=0.01, ev_model=0.02, confidence=0.58, disagreement=0.18, approved=False),
        BetCandidate("PSG vs Marseille", "1X2", "2", 5.00, ev_sim=0.08, ev_model=0.06, confidence=0.62, disagreement=0.12, approved=True),
        BetCandidate("Napoli vs Juventus", "1X2", "X", 3.50, ev_sim=-0.02, ev_model=0.01, confidence=0.55, disagreement=0.15, approved=False),
    ]
    
    print("=== TIERED BET FILTER TEST ===\n")
    
    selected = apply_tiered_filter(test_candidates, max_bets=5)
    
    for b in selected:
        print(f"[{b.tier}] {b.match} | {b.selection} @ {b.odds}")
        print(f"   EV_sim: {b.ev_sim:.1%} | EV_model: {b.ev_model:.1%} | Conf: {b.confidence:.0%}")
    
    print(f"\n{summarize_filtered_bets(selected)}")

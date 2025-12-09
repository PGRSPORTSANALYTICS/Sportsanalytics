"""
NOVA v2.0 - Tiered Bet Filter System (Dec 9, 2025)
===================================================
Multi-level trust filtering for bet candidates.
Retuned for higher daily volume while maintaining safety.

Tier Thresholds:
- L1 (High Trust): Sim approved, EV >= 5%, Confidence >= 55%, Odds 1.50-3.00
- L2 (Medium Trust): EV >= 2%, Confidence >= 52%, Disagreement <= 20%, Odds 1.50-3.20
- L3 (Soft Value): EV >= 0%, Confidence >= 50%, Disagreement <= 25%, Odds 1.40-3.50

Goal: 5-15 Value Singles on typical match days
"""

from dataclasses import dataclass
from typing import List, Optional

# ============================================================
# NOVA v2.0 TRUST LEVEL THRESHOLDS
# ============================================================

# L1 - High Trust (priority picks)
L1_MIN_EV = 0.05          # 5% EV
L1_MIN_CONFIDENCE = 0.55  # 55%
L1_MIN_ODDS = 1.50
L1_MAX_ODDS = 3.00
L1_MAX_PER_DAY = 3        # Cap high trust to best 3

# L2 - Medium Trust (bread and butter)
L2_MIN_EV = 0.02          # 2% EV
L2_MIN_CONFIDENCE = 0.52  # 52%
L2_MAX_DISAGREEMENT = 0.20  # 20% disagreement allowed
L2_MIN_ODDS = 1.50
L2_MAX_ODDS = 3.20

# L3 - Soft Value (fallback when < 5 total picks)
L3_MIN_EV = 0.00          # 0% EV (break even)
L3_MIN_CONFIDENCE = 0.50  # 50%
L3_MAX_DISAGREEMENT = 0.25  # 25% disagreement allowed
L3_MIN_ODDS = 1.40
L3_MAX_ODDS = 3.50
L3_MIN_DAILY_TARGET = 5   # Only use L3 if total picks < 5


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


def filter_level1_high_trust(candidates: List[BetCandidate]) -> List[BetCandidate]:
    """
    Level 1: HIGH TRUST (NOVA v2.0)
    - Must be approved by simulation filter
    - EV_sim >= 5%
    - Confidence >= 55%
    - Odds 1.50 - 3.00
    """
    level1 = [
        b for b in candidates 
        if b.approved 
        and b.ev_sim >= L1_MIN_EV
        and b.confidence >= L1_MIN_CONFIDENCE
        and L1_MIN_ODDS <= b.odds <= L1_MAX_ODDS
    ]
    for b in level1:
        b.tier = "L1_HIGH_TRUST"
    return level1


def filter_level2_medium_trust(candidates: List[BetCandidate]) -> List[BetCandidate]:
    """
    Level 2: MEDIUM TRUST (NOVA v2.0)
    - EV_model >= 2%
    - Confidence >= 52%
    - Disagreement <= 20%
    - Odds 1.50 - 3.20
    """
    level2 = [
        b for b in candidates
        if b.ev_model >= L2_MIN_EV
        and b.confidence >= L2_MIN_CONFIDENCE
        and b.disagreement <= L2_MAX_DISAGREEMENT
        and L2_MIN_ODDS <= b.odds <= L2_MAX_ODDS
    ]
    for b in level2:
        b.tier = "L2_MEDIUM_TRUST"
    return level2


def filter_level3_soft_value(candidates: List[BetCandidate]) -> List[BetCandidate]:
    """
    Level 3: SOFT VALUE (NOVA v2.0 - fallback only)
    - EV_model >= 0% (break even)
    - Confidence >= 50%
    - Disagreement <= 25%
    - Odds 1.40 - 3.50
    Only used when daily card < 5 picks
    """
    level3 = [
        b for b in candidates
        if b.ev_model >= L3_MIN_EV
        and b.confidence >= L3_MIN_CONFIDENCE
        and b.disagreement <= L3_MAX_DISAGREEMENT
        and L3_MIN_ODDS <= b.odds <= L3_MAX_ODDS
    ]
    for b in level3:
        b.tier = "L3_SOFT_VALUE"
    return level3


def apply_tiered_filter(candidates: List[BetCandidate], max_bets: int = 15) -> List[BetCandidate]:
    """
    Apply tiered filtering with priority (NOVA v2.0):
    1. First fill from Level 1 (highest trust) - max 3
    2. Then fill from Level 2 (medium trust)
    3. Finally fill from Level 3 only if total < 5 picks
    
    Returns up to max_bets sorted by tier then EV.
    """
    selected = []
    remaining_slots = max_bets
    
    seen = set()
    
    # L1 - High Trust (capped at L1_MAX_PER_DAY)
    level1 = filter_level1_high_trust(candidates)
    l1_count = 0
    for b in sorted(level1, key=lambda x: x.ev_sim, reverse=True):
        key = (b.match, b.market, b.selection)
        if key not in seen and remaining_slots > 0 and l1_count < L1_MAX_PER_DAY:
            selected.append(b)
            seen.add(key)
            remaining_slots -= 1
            l1_count += 1
    
    # L2 - Medium Trust
    if remaining_slots > 0:
        remaining = [b for b in candidates if (b.match, b.market, b.selection) not in seen]
        level2 = filter_level2_medium_trust(remaining)
        for b in sorted(level2, key=lambda x: x.ev_model, reverse=True):
            key = (b.match, b.market, b.selection)
            if key not in seen and remaining_slots > 0:
                selected.append(b)
                seen.add(key)
                remaining_slots -= 1
    
    # L3 - Soft Value (only if we have fewer than target picks)
    if len(selected) < L3_MIN_DAILY_TARGET and remaining_slots > 0:
        remaining = [b for b in candidates if (b.match, b.market, b.selection) not in seen]
        level3 = filter_level3_soft_value(remaining)
        for b in sorted(level3, key=lambda x: x.ev_model, reverse=True):
            key = (b.match, b.market, b.selection)
            if key not in seen and remaining_slots > 0:
                selected.append(b)
                seen.add(key)
                remaining_slots -= 1
    
    return selected


def build_daily_card(candidates: List[BetCandidate], max_per_tier: int = 5) -> List[BetCandidate]:
    """
    Build the daily betting card with priority from each tier (NOVA v2.0).
    
    Priority order:
    1. Up to 3 L1 (High Trust) picks
    2. Up to 7 L2 (Medium Trust) picks  
    3. Up to 5 L3 (Soft Value) picks - ONLY if L1+L2 < 5
    
    Target: 5-15 picks per day on typical match days
    
    Returns: Daily card with up to 15 bets total.
    """
    level1 = filter_level1_high_trust(candidates)
    level2 = filter_level2_medium_trust([c for c in candidates if c not in level1])
    
    # Sort and cap L1 and L2
    level1_sorted = sorted(level1, key=lambda x: x.ev_sim, reverse=True)[:L1_MAX_PER_DAY]
    level2_sorted = sorted(level2, key=lambda x: x.ev_model, reverse=True)[:7]
    
    daily_card = []
    daily_card += level1_sorted
    daily_card += level2_sorted
    
    # Only add L3 if we don't have enough picks
    if len(daily_card) < L3_MIN_DAILY_TARGET:
        level3 = filter_level3_soft_value([c for c in candidates if c not in level1 and c not in level2])
        level3_sorted = sorted(level3, key=lambda x: x.ev_model, reverse=True)[:max_per_tier]
        daily_card += level3_sorted
    
    # Emergency fallback if still < 3 picks
    if len(daily_card) < 3:
        daily_card = sorted(candidates, key=lambda x: x.confidence, reverse=True)[:5]
        for b in daily_card:
            b.tier = "EMERGENCY_FALLBACK"
    
    return daily_card


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

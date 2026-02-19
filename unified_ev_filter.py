"""
Unified EV Filter - Standardized Filtering for All Markets
===========================================================
Provides a shared filter function so all products use consistent EV rules.

Each product has defined thresholds for:
- L1 (High Trust): EV >= 5%, confidence >= 60%, disagreement <= 12%
- L2 (Medium Trust): EV >= 3%, confidence >= 57%, disagreement <= 15%
- L3 (Soft Value): EV >= 0%, confidence >= 55%, disagreement <= 20%

Usage:
    from unified_ev_filter import apply_unified_filter, classify_trust_tier
    
    tier = classify_trust_tier(ev=0.06, confidence=0.62, product="TOTALS")
    filtered = apply_unified_filter(candidates, product="CORNERS_MATCH")
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProductFilterConfig:
    product: str
    l1_min_ev: float = 0.05
    l1_min_confidence: float = 0.60
    l1_max_disagreement: float = 0.12
    l2_min_ev: float = 0.03
    l2_min_confidence: float = 0.57
    l2_max_disagreement: float = 0.15
    l3_min_ev: float = 0.00
    l3_min_confidence: float = 0.55
    l3_max_disagreement: float = 0.20
    min_odds: float = 1.50
    max_odds: float = 3.50
    max_per_day: int = 10


PRODUCT_FILTER_CONFIGS: Dict[str, ProductFilterConfig] = {
    "VALUE_SINGLES": ProductFilterConfig(
        product="VALUE_SINGLES",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.40, max_odds=3.50, max_per_day=15
    ),
    "TOTALS": ProductFilterConfig(
        product="TOTALS",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.60, max_odds=2.80, max_per_day=10
    ),
    "BTTS": ProductFilterConfig(
        product="BTTS",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.70, max_odds=2.30, max_per_day=8
    ),
    "CORNERS_MATCH": ProductFilterConfig(
        product="CORNERS_MATCH",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.70, max_odds=2.50, max_per_day=6
    ),
    "CORNERS_TEAM": ProductFilterConfig(
        product="CORNERS_TEAM",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.70, max_odds=2.50, max_per_day=4
    ),
    "CORNERS_HANDICAP": ProductFilterConfig(
        product="CORNERS_HANDICAP",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.70, max_odds=2.50, max_per_day=6
    ),
    "CARDS_MATCH": ProductFilterConfig(
        product="CARDS_MATCH",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.70, max_odds=2.50, max_per_day=6
    ),
    "CARDS_TEAM": ProductFilterConfig(
        product="CARDS_TEAM",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.70, max_odds=2.50, max_per_day=4
    ),
    "SHOTS_TEAM": ProductFilterConfig(
        product="SHOTS_TEAM",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.70, max_odds=2.50, max_per_day=6
    ),
    "ML_AH": ProductFilterConfig(
        product="ML_AH",
        l1_min_ev=0.05, l1_min_confidence=0.55, l1_max_disagreement=0.12,
        l2_min_ev=0.02, l2_min_confidence=0.52, l2_max_disagreement=0.15,
        l3_min_ev=0.00, l3_min_confidence=0.50, l3_max_disagreement=0.20,
        min_odds=1.50, max_odds=3.50, max_per_day=15
    ),
}


def get_filter_config(product: str) -> ProductFilterConfig:
    """Get filter configuration for a product."""
    product_upper = product.upper()
    if product_upper in PRODUCT_FILTER_CONFIGS:
        return PRODUCT_FILTER_CONFIGS[product_upper]
    return PRODUCT_FILTER_CONFIGS.get("VALUE_SINGLES", ProductFilterConfig(product=product))


def classify_trust_tier(
    ev: float,
    confidence: float,
    product: str,
    sim_approved: bool = True,
    disagreement: float = 0.0
) -> str:
    """
    Classify a bet into trust tier using unified filter rules.
    
    Args:
        ev: Expected value (e.g., 0.05 for 5% EV)
        confidence: Model probability/confidence
        product: Product type (TOTALS, CORNERS_MATCH, etc.)
        sim_approved: Whether Monte Carlo simulation approved the bet
        disagreement: Model vs market disagreement (optional)
    
    Returns:
        Trust tier string: L1_HIGH_TRUST, L2_MEDIUM_TRUST, L3_SOFT_VALUE, or REJECTED
    """
    config = get_filter_config(product)
    
    if (sim_approved and 
        ev >= config.l1_min_ev and 
        confidence >= config.l1_min_confidence and
        disagreement <= config.l1_max_disagreement):
        return "L1_HIGH_TRUST"
    
    if (sim_approved and 
        ev >= config.l2_min_ev and 
        confidence >= config.l2_min_confidence and
        disagreement <= config.l2_max_disagreement):
        return "L2_MEDIUM_TRUST"
    
    if (ev >= config.l3_min_ev and 
        confidence >= config.l3_min_confidence and
        disagreement <= config.l3_max_disagreement):
        return "L3_SOFT_VALUE"
    
    return "REJECTED"


def apply_unified_filter(
    candidates: List[Any],
    product: str,
    max_per_day: Optional[int] = None
) -> List[Any]:
    """
    Apply unified EV filter to a list of candidates.
    
    Args:
        candidates: List of bet candidate objects (must have ev, confidence, tier attributes)
        product: Product type for filter config
        max_per_day: Override max picks per day (optional)
    
    Returns:
        Filtered and sorted list of candidates
    """
    config = get_filter_config(product)
    max_picks = max_per_day or config.max_per_day
    
    valid_tiers = {"L1_HIGH_TRUST", "L2_MEDIUM_TRUST", "L3_SOFT_VALUE"}
    
    filtered = []
    rejected_count = 0
    
    for c in candidates:
        tier = getattr(c, 'tier', getattr(c, 'trust_tier', 'REJECTED'))
        if tier not in valid_tiers:
            rejected_count += 1
            continue
        
        odds = getattr(c, 'odds', getattr(c, 'book_odds', 0))
        if not (config.min_odds <= odds <= config.max_odds):
            rejected_count += 1
            continue
        
        filtered.append(c)
    
    tier_order = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 1, "L3_SOFT_VALUE": 2}
    filtered.sort(key=lambda x: (
        tier_order.get(getattr(x, 'tier', getattr(x, 'trust_tier', 'L3_SOFT_VALUE')), 3),
        -getattr(x, 'ev', getattr(x, 'ev_sim', 0))
    ))
    
    selected = filtered[:max_picks]
    
    logger.debug(
        f"📊 {product} Filter: {len(candidates)} total → "
        f"{len(filtered)} valid → {len(selected)} selected "
        f"(rejected: {rejected_count})"
    )
    
    return selected


def get_filter_stats(candidates: List[Any], product: str) -> Dict[str, Any]:
    """
    Get filter statistics for debugging/logging.
    
    Returns dict with counts by tier, average EV, rejection reasons.
    """
    config = get_filter_config(product)
    
    stats = {
        "product": product,
        "total_candidates": len(candidates),
        "tier_counts": {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0, "REJECTED": 0},
        "rejected_reasons": {"low_ev": 0, "low_confidence": 0, "odds_out_of_range": 0, "other": 0},
        "avg_ev": 0.0,
        "max_per_day": config.max_per_day,
    }
    
    total_ev = 0.0
    valid_count = 0
    
    for c in candidates:
        tier = getattr(c, 'tier', getattr(c, 'trust_tier', 'REJECTED'))
        ev = getattr(c, 'ev', getattr(c, 'ev_sim', 0))
        conf = getattr(c, 'confidence', getattr(c, 'model_prob', 0))
        odds = getattr(c, 'odds', getattr(c, 'book_odds', 0))
        
        if tier in stats["tier_counts"]:
            stats["tier_counts"][tier] += 1
        else:
            stats["tier_counts"]["REJECTED"] += 1
        
        if tier == "REJECTED":
            if ev < config.l3_min_ev:
                stats["rejected_reasons"]["low_ev"] += 1
            elif conf < config.l3_min_confidence:
                stats["rejected_reasons"]["low_confidence"] += 1
            elif not (config.min_odds <= odds <= config.max_odds):
                stats["rejected_reasons"]["odds_out_of_range"] += 1
            else:
                stats["rejected_reasons"]["other"] += 1
        else:
            total_ev += ev
            valid_count += 1
    
    stats["avg_ev"] = round(total_ev / valid_count, 4) if valid_count > 0 else 0.0
    
    return stats


def log_filter_summary(candidates_by_product: Dict[str, List[Any]]) -> None:
    """
    Log a summary of filter results across all products.
    """
    logger.info("=" * 60)
    logger.info("UNIFIED EV FILTER SUMMARY")
    logger.info("=" * 60)
    
    total_generated = 0
    total_selected = 0
    
    for product, candidates in candidates_by_product.items():
        stats = get_filter_stats(candidates, product)
        filtered = apply_unified_filter(candidates, product)
        
        total_generated += stats["total_candidates"]
        total_selected += len(filtered)
        
        logger.info(
            f"  {product:20s}: {stats['total_candidates']:3d} generated → {len(filtered):3d} selected | "
            f"L1={stats['tier_counts']['L1_HIGH_TRUST']:2d} "
            f"L2={stats['tier_counts']['L2_MEDIUM_TRUST']:2d} "
            f"L3={stats['tier_counts']['L3_SOFT_VALUE']:2d} | "
            f"Avg EV={stats['avg_ev']:.2%}"
        )
    
    logger.info("-" * 60)
    logger.info(f"  TOTAL: {total_generated} generated → {total_selected} selected")
    logger.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("UNIFIED EV FILTER - CONFIGURATION")
    print("=" * 60)
    
    for product, config in PRODUCT_FILTER_CONFIGS.items():
        print(f"\n{product}:")
        print(f"  L1: EV >= {config.l1_min_ev:.0%}, Conf >= {config.l1_min_confidence:.0%}, Disagree <= {config.l1_max_disagreement:.0%}")
        print(f"  L2: EV >= {config.l2_min_ev:.0%}, Conf >= {config.l2_min_confidence:.0%}, Disagree <= {config.l2_max_disagreement:.0%}")
        print(f"  L3: EV >= {config.l3_min_ev:.0%}, Conf >= {config.l3_min_confidence:.0%}, Disagree <= {config.l3_max_disagreement:.0%}")
        print(f"  Odds: {config.min_odds} - {config.max_odds}")
        print(f"  Max/Day: {config.max_per_day}")
    
    print("\n" + "=" * 60)
    print("TEST CLASSIFICATION")
    print("-" * 60)
    
    test_cases = [
        ("TOTALS", 0.08, 0.62, True, 0.05),
        ("CORNERS_MATCH", 0.04, 0.54, True, 0.10),
        ("CARDS_MATCH", 0.01, 0.51, False, 0.08),
        ("SHOTS_TEAM", 0.06, 0.58, True, 0.18),
    ]
    
    for product, ev, conf, sim_ok, disagree in test_cases:
        tier = classify_trust_tier(ev, conf, product, sim_ok, disagree)
        print(f"  {product}: EV={ev:.0%}, Conf={conf:.0%}, Sim={sim_ok}, Disagree={disagree:.0%} -> {tier}")

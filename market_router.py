"""
Market Router Module (Dec 9, 2025)
==================================
Central router for balancing daily betting card across markets.

Key Features:
- Prevents single-market spam (e.g., all Over 2.5 Goals)
- Respects per-product and per-market caps
- Prioritizes by trust tier (L1 > L2 > L3) then EV
- Two-pass selection: strict caps first, then fill remaining slots

Usage:
    from market_router import route_picks
    
    candidates = [...list of picks...]
    balanced_card = route_picks(candidates)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union

from market_router_config import (
    MARKET_CAPS,
    GLOBAL_DAILY_MAX_PICKS,
    get_market_cap_key,
    map_product_to_router_category,
)

logger = logging.getLogger(__name__)


@dataclass
class RouterCandidate:
    """
    Standardized pick format for routing.
    Converts various internal formats to a consistent structure.
    """
    fixture_id: str
    home_team: str
    away_team: str
    market_key: str
    market_type: str
    product: str
    selection: str
    odds: float
    ev: float
    confidence: float
    trust_level: str
    model_prob: float = 0.0
    line: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    original: Any = None
    
    @property
    def match(self) -> str:
        return f"{self.home_team} vs {self.away_team}"
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RouterCandidate":
        """Create RouterCandidate from dictionary."""
        trust = d.get("trust_level") or d.get("trust_tier") or d.get("tier") or "L3_SOFT_VALUE"
        if not trust.startswith("L"):
            trust = "L3_SOFT_VALUE"
        
        product = d.get("product") or d.get("product_type") or "VALUE_SINGLES"
        
        market_key = d.get("market_key") or d.get("market") or ""
        market_type = d.get("market_type") or ""
        
        ev = d.get("ev") or d.get("ev_sim") or d.get("edge_percentage") or 0.0
        if isinstance(ev, str):
            try:
                ev = float(ev.replace("%", "")) / 100 if "%" in ev else float(ev)
            except:
                ev = 0.0
        if ev > 1:
            ev = ev / 100
        
        conf = d.get("confidence") or 0.0
        if isinstance(conf, str):
            try:
                conf = float(conf.replace("%", "")) / 100 if "%" in conf else float(conf)
            except:
                conf = 0.0
        if conf > 1:
            conf = conf / 100
        
        return cls(
            fixture_id=str(d.get("fixture_id") or d.get("match_id") or ""),
            home_team=d.get("home_team", ""),
            away_team=d.get("away_team", ""),
            market_key=market_key,
            market_type=market_type,
            product=product,
            selection=d.get("selection", ""),
            odds=float(d.get("odds") or d.get("book_odds") or 0),
            ev=ev,
            confidence=conf,
            trust_level=trust,
            model_prob=float(d.get("model_prob", 0)),
            line=d.get("line"),
            metadata=d.get("metadata", {}),
            original=d,
        )
    
    @classmethod
    def from_unified_candidate(cls, uc) -> "RouterCandidate":
        """Create RouterCandidate from UnifiedCandidate object."""
        trust = getattr(uc, "trust_tier", None) or getattr(uc, "trust_level", None) or "L3_SOFT_VALUE"
        
        return cls(
            fixture_id=getattr(uc, "fixture_id", ""),
            home_team=getattr(uc, "home_team", ""),
            away_team=getattr(uc, "away_team", ""),
            market_key=getattr(uc, "market_key", ""),
            market_type=getattr(uc, "market_type", ""),
            product=getattr(uc, "product_type", "VALUE_SINGLES"),
            selection=getattr(uc, "selection", ""),
            odds=float(getattr(uc, "book_odds", 0) or getattr(uc, "odds", 0)),
            ev=float(getattr(uc, "ev", 0)),
            confidence=float(getattr(uc, "confidence", 0)),
            trust_level=trust,
            model_prob=float(getattr(uc, "model_prob", 0)),
            line=getattr(uc, "line", None),
            metadata=getattr(uc, "metadata", {}),
            original=uc,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert back to dictionary format."""
        return {
            "fixture_id": self.fixture_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "match": self.match,
            "market_key": self.market_key,
            "market_type": self.market_type,
            "product": self.product,
            "product_type": self.product,
            "selection": self.selection,
            "odds": self.odds,
            "ev": self.ev,
            "confidence": self.confidence,
            "trust_level": self.trust_level,
            "trust_tier": self.trust_level,
            "model_prob": self.model_prob,
            "line": self.line,
            "metadata": self.metadata,
        }


def _normalize_candidates(candidates: List[Any]) -> List[RouterCandidate]:
    """Convert various candidate formats to RouterCandidate."""
    normalized = []
    
    for c in candidates:
        try:
            if isinstance(c, RouterCandidate):
                normalized.append(c)
            elif isinstance(c, dict):
                normalized.append(RouterCandidate.from_dict(c))
            elif hasattr(c, "fixture_id") and hasattr(c, "ev"):
                normalized.append(RouterCandidate.from_unified_candidate(c))
            else:
                logger.warning(f"Unknown candidate type: {type(c)}")
        except Exception as e:
            logger.warning(f"Failed to normalize candidate: {e}")
    
    return normalized


def _get_trust_weight(trust_level: str) -> int:
    """Get sorting weight for trust level (higher = better)."""
    trust_upper = trust_level.upper() if trust_level else ""
    
    if "L1" in trust_upper:
        return 3
    elif "L2" in trust_upper:
        return 2
    elif "L3" in trust_upper:
        return 1
    return 0


def route_picks(
    candidate_picks: List[Any],
    global_max: Optional[int] = None,
    market_caps: Optional[Dict] = None,
) -> List[RouterCandidate]:
    """
    Route and balance picks across markets using caps.
    
    This function:
    1. Normalizes all candidates to RouterCandidate format
    2. Sorts by trust tier (L1 > L2 > L3) then EV descending
    3. First pass: strictly respect all per-market and product caps
    4. Second pass: fill remaining slots while respecting product caps only
    
    Args:
        candidate_picks: List of picks (dicts, UnifiedCandidate objects, or RouterCandidates)
        global_max: Override for GLOBAL_DAILY_MAX_PICKS
        market_caps: Override for MARKET_CAPS
    
    Returns:
        List of selected RouterCandidates for the balanced daily card
    """
    if not candidate_picks:
        logger.info("No candidates to route")
        return []
    
    max_picks = global_max or GLOBAL_DAILY_MAX_PICKS
    caps = market_caps or MARKET_CAPS
    
    normalized = _normalize_candidates(candidate_picks)
    logger.info(f"📊 Router received {len(normalized)} candidates")
    
    sorted_picks = sorted(
        normalized,
        key=lambda p: (_get_trust_weight(p.trust_level), p.ev),
        reverse=True,
    )
    
    product_counts: Dict[str, int] = defaultdict(int)
    market_counts: Dict[tuple, int] = defaultdict(int)
    selected: List[RouterCandidate] = []
    seen_matches: Dict[str, set] = defaultdict(set)
    
    for pick in sorted_picks:
        if len(selected) >= max_picks:
            break
        
        router_product = map_product_to_router_category(pick.product)
        
        product_cfg = caps.get(router_product)
        if not product_cfg:
            logger.debug(f"No config for product {router_product}, skipping")
            continue
        
        product_max = product_cfg.get("max_picks", 10)
        if product_counts[router_product] >= product_max:
            continue
        
        match_key = f"{pick.fixture_id}:{pick.market_key}"
        if match_key in seen_matches[router_product]:
            continue
        
        per_market_caps = product_cfg.get("per_market_caps", {})
        cap_key = get_market_cap_key(pick.market_key, router_product)
        
        if cap_key not in per_market_caps:
            cap_key = next(
                (k for k in per_market_caps.keys() if cap_key.startswith(k) or k.startswith(cap_key.split("_")[0])),
                list(per_market_caps.keys())[-1] if per_market_caps else None
            )
        
        market_cap = per_market_caps.get(cap_key) if cap_key else None
        
        if market_cap is not None:
            if market_counts[(router_product, cap_key)] >= market_cap:
                continue
        
        selected.append(pick)
        product_counts[router_product] += 1
        seen_matches[router_product].add(match_key)
        
        if market_cap is not None:
            market_counts[(router_product, cap_key)] += 1
    
    if len(selected) < max_picks:
        for pick in sorted_picks:
            if len(selected) >= max_picks:
                break
            
            if pick in selected:
                continue
            
            router_product = map_product_to_router_category(pick.product)
            
            product_cfg = caps.get(router_product)
            if not product_cfg:
                continue
            
            product_max = product_cfg.get("max_picks", 10)
            if product_counts[router_product] >= product_max:
                continue
            
            match_key = f"{pick.fixture_id}:{pick.market_key}"
            if match_key in seen_matches[router_product]:
                continue
            
            selected.append(pick)
            product_counts[router_product] += 1
            seen_matches[router_product].add(match_key)
    
    _log_routing_summary(selected, product_counts, market_counts)
    
    return selected


def _log_routing_summary(
    selected: List[RouterCandidate],
    product_counts: Dict[str, int],
    market_counts: Dict[tuple, int],
) -> None:
    """Log summary of routing decisions."""
    logger.info(f"=" * 60)
    logger.info(f"🎯 MARKET ROUTER SUMMARY: {len(selected)} picks selected")
    logger.info(f"=" * 60)
    
    logger.info("By Product:")
    for product, count in sorted(product_counts.items()):
        if count > 0:
            logger.info(f"  {product}: {count}")
    
    logger.info("By Market Type:")
    for (product, market), count in sorted(market_counts.items()):
        if count > 0:
            logger.info(f"  {product}/{market}: {count}")
    
    trust_counts = defaultdict(int)
    for pick in selected:
        if "L1" in pick.trust_level.upper():
            trust_counts["L1"] += 1
        elif "L2" in pick.trust_level.upper():
            trust_counts["L2"] += 1
        else:
            trust_counts["L3"] += 1
    
    logger.info(f"By Trust Tier: L1={trust_counts['L1']} L2={trust_counts['L2']} L3={trust_counts['L3']}")
    
    if selected:
        avg_ev = sum(p.ev for p in selected) / len(selected)
        logger.info(f"Average EV: {avg_ev:.1%}")
    
    logger.info(f"=" * 60)


def get_routing_stats(selected: List[RouterCandidate]) -> Dict[str, Any]:
    """
    Get statistics about routed picks for API/dashboard.
    
    Returns dict with counts by product, market, and trust tier.
    """
    by_product = defaultdict(int)
    by_market = defaultdict(int)
    by_trust = defaultdict(int)
    
    for pick in selected:
        router_product = map_product_to_router_category(pick.product)
        by_product[router_product] += 1
        
        cap_key = get_market_cap_key(pick.market_key, router_product)
        by_market[f"{router_product}/{cap_key}"] += 1
        
        if "L1" in pick.trust_level.upper():
            by_trust["L1_HIGH_TRUST"] += 1
        elif "L2" in pick.trust_level.upper():
            by_trust["L2_MEDIUM_TRUST"] += 1
        else:
            by_trust["L3_SOFT_VALUE"] += 1
    
    avg_ev = sum(p.ev for p in selected) / len(selected) if selected else 0
    
    products_covered = [p for p, c in by_product.items() if c > 0]
    
    return {
        "total_picks": len(selected),
        "by_product": dict(by_product),
        "by_market": dict(by_market),
        "by_trust_tier": dict(by_trust),
        "average_ev": round(avg_ev * 100, 2),
        "products_covered": products_covered,
        "market_diversity": len([m for m, c in by_market.items() if c > 0]),
        "balance_score": _calculate_balance_score(by_product),
    }


def _calculate_balance_score(by_product: Dict[str, int]) -> float:
    """
    Calculate how balanced the card is (0-100).
    
    100 = perfectly balanced across all products
    0 = all picks in single product
    """
    if not by_product:
        return 0.0
    
    total = sum(by_product.values())
    if total == 0:
        return 0.0
    
    num_products = len([c for c in by_product.values() if c > 0])
    
    if num_products == 1:
        return 10.0
    
    ideal_per_product = total / num_products
    
    variance = sum((c - ideal_per_product) ** 2 for c in by_product.values() if c > 0)
    avg_variance = variance / num_products
    
    product_diversity_bonus = min(num_products * 10, 40)
    variance_penalty = min(avg_variance * 2, 50)
    
    score = 50 + product_diversity_bonus - variance_penalty
    
    return max(0, min(100, round(score, 1)))


def test_router():
    """Test the router with mock candidates."""
    print("=" * 60)
    print("MARKET ROUTER TEST")
    print("=" * 60)
    
    mock_candidates = [
        {"fixture_id": "1", "home_team": "Liverpool", "away_team": "Chelsea", "market_key": "FT_OVER_2_5", "product": "TOTALS", "ev": 0.12, "confidence": 0.58, "trust_level": "L1_HIGH_TRUST", "odds": 2.10, "selection": "Over 2.5"},
        {"fixture_id": "2", "home_team": "Arsenal", "away_team": "City", "market_key": "FT_OVER_2_5", "product": "TOTALS", "ev": 0.11, "confidence": 0.57, "trust_level": "L1_HIGH_TRUST", "odds": 2.05, "selection": "Over 2.5"},
        {"fixture_id": "3", "home_team": "United", "away_team": "Spurs", "market_key": "FT_OVER_2_5", "product": "TOTALS", "ev": 0.10, "confidence": 0.56, "trust_level": "L2_MEDIUM_TRUST", "odds": 2.00, "selection": "Over 2.5"},
        {"fixture_id": "4", "home_team": "Everton", "away_team": "Villa", "market_key": "FT_OVER_2_5", "product": "TOTALS", "ev": 0.09, "confidence": 0.55, "trust_level": "L2_MEDIUM_TRUST", "odds": 1.95, "selection": "Over 2.5"},
        {"fixture_id": "5", "home_team": "Newcastle", "away_team": "Brighton", "market_key": "FT_OVER_2_5", "product": "TOTALS", "ev": 0.08, "confidence": 0.54, "trust_level": "L2_MEDIUM_TRUST", "odds": 1.90, "selection": "Over 2.5"},
        {"fixture_id": "6", "home_team": "West Ham", "away_team": "Fulham", "market_key": "FT_UNDER_2_5", "product": "TOTALS", "ev": 0.07, "confidence": 0.54, "trust_level": "L2_MEDIUM_TRUST", "odds": 1.85, "selection": "Under 2.5"},
        {"fixture_id": "7", "home_team": "Wolves", "away_team": "Palace", "market_key": "FT_OVER_3_5", "product": "TOTALS", "ev": 0.15, "confidence": 0.60, "trust_level": "L1_HIGH_TRUST", "odds": 2.50, "selection": "Over 3.5"},
        {"fixture_id": "1", "home_team": "Liverpool", "away_team": "Chelsea", "market_key": "BTTS_YES", "product": "BTTS", "ev": 0.08, "confidence": 0.56, "trust_level": "L2_MEDIUM_TRUST", "odds": 1.80, "selection": "BTTS Yes"},
        {"fixture_id": "2", "home_team": "Arsenal", "away_team": "City", "market_key": "BTTS_YES", "product": "BTTS", "ev": 0.07, "confidence": 0.55, "trust_level": "L2_MEDIUM_TRUST", "odds": 1.75, "selection": "BTTS Yes"},
        {"fixture_id": "3", "home_team": "United", "away_team": "Spurs", "market_key": "BTTS_NO", "product": "BTTS", "ev": 0.06, "confidence": 0.54, "trust_level": "L3_SOFT_VALUE", "odds": 2.00, "selection": "BTTS No"},
        {"fixture_id": "1", "home_team": "Liverpool", "away_team": "Chelsea", "market_key": "HOME_WIN", "product": "VALUE_SINGLES", "ev": 0.09, "confidence": 0.57, "trust_level": "L2_MEDIUM_TRUST", "odds": 1.85, "selection": "Liverpool Win"},
        {"fixture_id": "2", "home_team": "Arsenal", "away_team": "City", "market_key": "AWAY_WIN", "product": "VALUE_SINGLES", "ev": 0.08, "confidence": 0.56, "trust_level": "L2_MEDIUM_TRUST", "odds": 2.10, "selection": "City Win"},
        {"fixture_id": "3", "home_team": "United", "away_team": "Spurs", "market_key": "DRAW", "product": "VALUE_SINGLES", "ev": 0.12, "confidence": 0.58, "trust_level": "L1_HIGH_TRUST", "odds": 3.40, "selection": "Draw"},
        {"fixture_id": "4", "home_team": "Everton", "away_team": "Villa", "market_key": "AH_HOME_-0.5", "product": "VALUE_SINGLES", "ev": 0.07, "confidence": 0.55, "trust_level": "L2_MEDIUM_TRUST", "odds": 1.90, "selection": "Everton -0.5"},
        {"fixture_id": "1", "home_team": "Liverpool", "away_team": "Chelsea", "market_key": "CORNERS_OVER_9_5", "product": "CORNERS_MATCH", "ev": 0.06, "confidence": 0.54, "trust_level": "L3_SOFT_VALUE", "odds": 1.90, "selection": "Corners Over 9.5"},
        {"fixture_id": "2", "home_team": "Arsenal", "away_team": "City", "market_key": "CORNERS_OVER_10_5", "product": "CORNERS_MATCH", "ev": 0.08, "confidence": 0.56, "trust_level": "L2_MEDIUM_TRUST", "odds": 2.00, "selection": "Corners Over 10.5"},
        {"fixture_id": "1", "home_team": "Liverpool", "away_team": "Chelsea", "market_key": "MATCH_CARDS_OVER_4_5", "product": "CARDS_MATCH", "ev": 0.07, "confidence": 0.55, "trust_level": "L2_MEDIUM_TRUST", "odds": 1.85, "selection": "Cards Over 4.5"},
        {"fixture_id": "2", "home_team": "Arsenal", "away_team": "City", "market_key": "MATCH_CARDS_OVER_3_5", "product": "CARDS_MATCH", "ev": 0.06, "confidence": 0.54, "trust_level": "L3_SOFT_VALUE", "odds": 1.70, "selection": "Cards Over 3.5"},
        {"fixture_id": "1", "home_team": "Liverpool", "away_team": "Chelsea", "market_key": "TEAM_SHOTS_OVER_10_5", "product": "SHOTS_TEAM", "ev": 0.09, "confidence": 0.57, "trust_level": "L1_HIGH_TRUST", "odds": 1.95, "selection": "Shots Over 10.5"},
        {"fixture_id": "2", "home_team": "Arsenal", "away_team": "City", "market_key": "HOME_SHOTS_OVER_4_5", "product": "SHOTS_TEAM", "ev": 0.05, "confidence": 0.53, "trust_level": "L3_SOFT_VALUE", "odds": 1.80, "selection": "Home Shots Over 4.5"},
    ]
    
    print(f"\nInput: {len(mock_candidates)} candidates")
    print("-" * 60)
    
    selected = route_picks(mock_candidates)
    
    print(f"\nOutput: {len(selected)} selected picks")
    print("-" * 60)
    
    for i, pick in enumerate(selected, 1):
        print(f"{i:2d}. {pick.match} | {pick.selection} | {pick.product} | {pick.trust_level} | EV={pick.ev:.1%}")
    
    stats = get_routing_stats(selected)
    print(f"\n📊 Routing Statistics:")
    print(f"   Total: {stats['total_picks']}")
    print(f"   Products: {stats['products_covered']}")
    print(f"   Market Diversity: {stats['market_diversity']}")
    print(f"   Balance Score: {stats['balance_score']}/100")
    print(f"   Average EV: {stats['average_ev']}%")
    print(f"   By Trust: {stats['by_trust_tier']}")
    
    return selected, stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_router()

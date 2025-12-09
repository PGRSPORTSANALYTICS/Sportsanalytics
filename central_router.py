"""
Central Engine Router
Orchestrates all prediction engines and builds unified daily betting card.

Updated Dec 9, 2025: Integrated Market Router for balanced daily cards.
The router prevents single-market spam and ensures portfolio diversification.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from datetime import datetime, date
from collections import defaultdict
import os

from multimarket_config import (
    PRODUCT_CONFIGS,
    DAILY_TARGETS,
    get_market_label,
    get_product_for_market,
    MarketType,
    ProductType
)
from odds_drift import OddsDriftTracker, OddsDriftInfo
from market_router import route_picks, get_routing_stats, RouterCandidate
from market_router_config import GLOBAL_DAILY_MAX_PICKS, MARKET_CAPS

logger = logging.getLogger(__name__)


@dataclass
class UnifiedCandidate:
    """Unified candidate structure for all engine outputs."""
    fixture_id: str
    home_team: str
    away_team: str
    market_key: str
    market_type: str
    product_type: str
    selection: str
    line: Optional[float]
    model_prob: float
    book_odds: float
    ev: float
    confidence: float
    trust_tier: str
    drift_info: Optional[OddsDriftInfo] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyCard:
    """Complete daily betting card with all products."""
    date: str
    value_singles: List[UnifiedCandidate] = field(default_factory=list)
    totals: List[UnifiedCandidate] = field(default_factory=list)
    btts: List[UnifiedCandidate] = field(default_factory=list)
    corners: List[UnifiedCandidate] = field(default_factory=list)
    shots: List[UnifiedCandidate] = field(default_factory=list)
    cards: List[UnifiedCandidate] = field(default_factory=list)
    corner_handicaps: List[UnifiedCandidate] = field(default_factory=list)
    parlays: List[Dict] = field(default_factory=list)
    
    summary: Dict[str, Any] = field(default_factory=dict)
    routing_stats: Dict[str, Any] = field(default_factory=dict)
    markets_covered: List[str] = field(default_factory=list)
    
    def get_all_singles(self) -> List[UnifiedCandidate]:
        """Get all singles across products."""
        return (self.value_singles + self.totals + self.btts + 
                self.corners + self.shots + self.cards + self.corner_handicaps)
    
    def get_total_count(self) -> int:
        return len(self.get_all_singles()) + len(self.parlays)
    
    def get_average_ev(self) -> float:
        all_singles = self.get_all_singles()
        if not all_singles:
            return 0.0
        return sum(c.ev for c in all_singles) / len(all_singles)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            "date": self.date,
            "value_singles": [self._candidate_to_dict(c) for c in self.value_singles],
            "totals": [self._candidate_to_dict(c) for c in self.totals],
            "btts": [self._candidate_to_dict(c) for c in self.btts],
            "corners": [self._candidate_to_dict(c) for c in self.corners],
            "shots": [self._candidate_to_dict(c) for c in self.shots],
            "cards": [self._candidate_to_dict(c) for c in self.cards],
            "corner_handicaps": [self._candidate_to_dict(c) for c in self.corner_handicaps],
            "parlays": self.parlays,
            "summary": self.generate_summary(),
            "routing_stats": self.routing_stats,
            "markets_covered": self.markets_covered,
        }
    
    def _candidate_to_dict(self, c: UnifiedCandidate) -> Dict:
        return {
            "fixture_id": c.fixture_id,
            "match": f"{c.home_team} vs {c.away_team}",
            "market": get_market_label(c.market_key),
            "market_key": c.market_key,
            "market_type": c.market_type,
            "product_type": c.product_type,
            "selection": c.selection,
            "line": c.line,
            "odds": c.book_odds,
            "probability": round(c.model_prob * 100, 1),
            "ev": round(c.ev * 100, 1),
            "confidence": round(c.confidence * 100, 1),
            "trust_tier": c.trust_tier,
            "drift_score": c.drift_info.drift_score if c.drift_info else None,
        }
    
    def generate_summary(self) -> Dict:
        """Generate summary statistics."""
        all_singles = self.get_all_singles()
        
        by_trust = defaultdict(int)
        by_market_type = defaultdict(int)
        by_product = defaultdict(int)
        
        for c in all_singles:
            by_trust[c.trust_tier] += 1
            by_market_type[c.market_type] += 1
            by_product[c.product_type] += 1
        
        return {
            "total_singles": len(all_singles),
            "total_parlays": len(self.parlays),
            "total_bets": self.get_total_count(),
            "average_ev": round(self.get_average_ev() * 100, 1),
            "by_trust_tier": dict(by_trust),
            "by_market_type": dict(by_market_type),
            "by_product": dict(by_product),
            "l1_count": by_trust.get("L1_HIGH_TRUST", 0),
            "l2_count": by_trust.get("L2_MEDIUM_TRUST", 0),
            "l3_count": by_trust.get("L3_SOFT_VALUE", 0),
        }


class CentralRouter:
    """
    Central orchestrator for all prediction engines.
    Loads fixtures, calls engines, filters results, and builds daily card.
    """
    
    def __init__(self):
        self.drift_tracker = OddsDriftTracker()
        self.engines = {}
        self._load_engines()
        logger.info("✅ CentralRouter initialized")
    
    def _load_engines(self):
        """Lazy-load available engines."""
        try:
            from shots_engine import ShotsEngine
            self.engines["shots"] = ShotsEngine()
        except ImportError as e:
            logger.warning(f"Could not load ShotsEngine: {e}")
        
        try:
            from cards_engine import CardsEngine
            self.engines["cards"] = CardsEngine()
        except ImportError as e:
            logger.warning(f"Could not load CardsEngine: {e}")
        
        try:
            from corner_handicap_engine import CornerHandicapEngine
            self.engines["corner_handicap"] = CornerHandicapEngine()
        except ImportError as e:
            logger.warning(f"Could not load CornerHandicapEngine: {e}")
        
        logger.info(f"📦 Loaded {len(self.engines)} specialty engines: {list(self.engines.keys())}")
    
    def _convert_to_unified(
        self,
        candidate: Any,
        product_type: str
    ) -> UnifiedCandidate:
        """Convert engine-specific candidate to unified format."""
        return UnifiedCandidate(
            fixture_id=candidate.fixture_id,
            home_team=candidate.home_team,
            away_team=candidate.away_team,
            market_key=candidate.market_key,
            market_type=candidate.metadata.get("market_type", "UNKNOWN"),
            product_type=product_type,
            selection=candidate.selection,
            line=getattr(candidate, "line", None) or getattr(candidate, "handicap_line", None),
            model_prob=candidate.model_prob,
            book_odds=candidate.book_odds,
            ev=candidate.ev,
            confidence=candidate.confidence,
            trust_tier=candidate.trust_tier,
            metadata=candidate.metadata,
        )
    
    def apply_drift_filter(
        self,
        candidates: List[UnifiedCandidate]
    ) -> List[UnifiedCandidate]:
        """Apply drift analysis and filter candidates."""
        filtered = []
        
        for candidate in candidates:
            drift_info = self.drift_tracker.get_drift_analysis(
                fixture_id=candidate.fixture_id,
                market_key=candidate.market_key,
                model_prob=candidate.model_prob,
                current_odds=candidate.book_odds
            )
            
            candidate.drift_info = drift_info
            
            should_block, reason = self.drift_tracker.should_block_bet(
                drift_info, candidate.trust_tier
            )
            
            if should_block:
                logger.debug(
                    f"⛔ Blocked: {candidate.home_team} vs {candidate.away_team} | "
                    f"{candidate.market_key} | {reason}"
                )
                continue
            
            if drift_info.drift_score < -0.5:
                candidate.metadata["market_disagrees"] = True
            
            filtered.append(candidate)
        
        return filtered
    
    def apply_daily_limits(
        self,
        candidates: List[UnifiedCandidate]
    ) -> Dict[str, List[UnifiedCandidate]]:
        """Apply daily limits per product type."""
        by_product = defaultdict(list)
        
        for c in candidates:
            by_product[c.product_type].append(c)
        
        limited = {}
        for product_type, product_candidates in by_product.items():
            product_candidates.sort(key=lambda x: (
                0 if x.trust_tier == "L1_HIGH_TRUST" else 
                1 if x.trust_tier == "L2_MEDIUM_TRUST" else 2,
                -x.ev
            ))
            
            config = PRODUCT_CONFIGS.get(product_type)
            max_per_day = getattr(config, 'max_per_day', 10) if config else 10
            
            limited[product_type] = product_candidates[:max_per_day]
        
        return limited
    
    def run_new_market_engines(
        self,
        fixtures: List[Dict],
        odds_data: Dict[str, Dict[str, float]]
    ) -> List[UnifiedCandidate]:
        """Run shots, cards, and corner handicap engines."""
        all_candidates = []
        
        if "shots" in self.engines:
            for fixture in fixtures:
                fixture_id = fixture.get("fixture_id", "")
                odds_snapshot = odds_data.get(fixture_id, {}) if fixture_id else {}
                if odds_snapshot:
                    shots_candidates = self.engines["shots"].generate_market_predictions(
                        fixture, odds_snapshot
                    )
                    for c in shots_candidates:
                        all_candidates.append(self._convert_to_unified(c, "SHOTS_TEAM"))
        
        if "cards" in self.engines:
            for fixture in fixtures:
                fixture_id = fixture.get("fixture_id", "")
                odds_snapshot = odds_data.get(fixture_id, {}) if fixture_id else {}
                if odds_snapshot:
                    cards_candidates = self.engines["cards"].generate_market_predictions(
                        fixture, odds_snapshot
                    )
                    for c in cards_candidates:
                        product = "CARDS_MATCH" if c.metadata.get("market_type") == "CARDS_MATCH" else "CARDS_TEAM"
                        all_candidates.append(self._convert_to_unified(c, product))
        
        if "corner_handicap" in self.engines:
            for fixture in fixtures:
                fixture_id = fixture.get("fixture_id", "")
                odds_snapshot = odds_data.get(fixture_id, {}) if fixture_id else {}
                if odds_snapshot:
                    hc_candidates = self.engines["corner_handicap"].generate_market_predictions(
                        fixture, odds_snapshot
                    )
                    for c in hc_candidates:
                        all_candidates.append(self._convert_to_unified(c, "CORNERS_HANDICAP"))
        
        return all_candidates
    
    def build_daily_card(
        self,
        fixtures: List[Dict],
        odds_data: Dict[str, Dict[str, float]],
        existing_value_singles: Optional[List[Dict]] = None,
        use_router: bool = True
    ) -> DailyCard:
        """
        Build complete daily betting card.
        
        Args:
            fixtures: List of fixture dicts with home_team, away_team, fixture_id
            odds_data: Dict mapping fixture_id to market odds
            existing_value_singles: Optional pre-generated value singles from main engine
            use_router: Whether to use market router for balancing (default: True)
        
        Returns:
            DailyCard with all qualified bets, balanced by market router
        """
        today = date.today().isoformat()
        card = DailyCard(date=today)
        
        all_candidates: List[Dict] = []
        
        new_market_candidates = self.run_new_market_engines(fixtures, odds_data)
        logger.info(f"📊 Generated {len(new_market_candidates)} candidates from specialty engines")
        
        filtered_candidates = self.apply_drift_filter(new_market_candidates)
        logger.info(f"📊 {len(filtered_candidates)} candidates passed drift filter")
        
        for c in filtered_candidates:
            all_candidates.append(self._unified_to_router_dict(c))
        
        if existing_value_singles:
            for vs in existing_value_singles:
                router_dict = self._value_single_to_router_dict(vs)
                all_candidates.append(router_dict)
        
        logger.info(f"📊 Total candidates for routing: {len(all_candidates)}")
        
        if use_router and all_candidates:
            routed = route_picks(all_candidates)
            routing_stats = get_routing_stats(routed)
            
            card.routing_stats = routing_stats
            card.markets_covered = routing_stats.get("products_covered", [])
            
            for pick in routed:
                candidate = self._router_to_unified(pick)
                product = pick.product.upper()
                
                if product in ["TOTALS"]:
                    card.totals.append(candidate)
                elif product in ["BTTS"]:
                    card.btts.append(candidate)
                elif product in ["ML_AH", "VALUE_SINGLES"]:
                    card.value_singles.append(candidate)
                elif product in ["CORNERS_MATCH", "CORNERS"]:
                    card.corners.append(candidate)
                elif product in ["CORNERS_TEAM"]:
                    card.corners.append(candidate)
                elif product in ["CORNERS_HANDICAP"]:
                    card.corner_handicaps.append(candidate)
                elif product in ["CARDS_MATCH"]:
                    card.cards.append(candidate)
                elif product in ["CARDS_TEAM"]:
                    card.cards.append(candidate)
                elif product in ["SHOTS_TEAM", "SHOTS"]:
                    card.shots.append(candidate)
                else:
                    card.value_singles.append(candidate)
            
            logger.info(f"🎯 Router balanced card: {len(routed)} picks across {len(card.markets_covered)} markets")
        else:
            limited = self.apply_daily_limits(filtered_candidates)
            
            for product_type, candidates in limited.items():
                if product_type == "SHOTS_TEAM":
                    card.shots = candidates
                elif product_type == "CARDS_MATCH":
                    card.cards.extend([c for c in candidates if c.market_type == "CARDS_MATCH"])
                elif product_type == "CARDS_TEAM":
                    card.cards.extend([c for c in candidates if c.market_type == "CARDS_TEAM"])
                elif product_type == "CORNERS_HANDICAP":
                    card.corner_handicaps = candidates
            
            if existing_value_singles:
                for vs in existing_value_singles:
                    card.value_singles.append(UnifiedCandidate(
                        fixture_id=vs.get("fixture_id", ""),
                        home_team=vs.get("home_team", ""),
                        away_team=vs.get("away_team", ""),
                        market_key=vs.get("market_key", ""),
                        market_type=vs.get("market_type", "ML"),
                        product_type="VALUE_SINGLES",
                        selection=vs.get("selection", ""),
                        line=vs.get("line"),
                        model_prob=vs.get("model_prob", 0),
                        book_odds=vs.get("book_odds", 0),
                        ev=vs.get("ev", 0),
                        confidence=vs.get("confidence", 0),
                        trust_tier=vs.get("trust_tier", "L3_SOFT_VALUE"),
                        metadata=vs.get("metadata", {}),
                    ))
        
        card.summary = card.generate_summary()
        self._log_card_summary(card)
        
        return card
    
    def _unified_to_router_dict(self, c: UnifiedCandidate) -> Dict:
        """Convert UnifiedCandidate to router-compatible dict."""
        return {
            "fixture_id": c.fixture_id,
            "home_team": c.home_team,
            "away_team": c.away_team,
            "market_key": c.market_key,
            "market_type": c.market_type,
            "product": c.product_type,
            "selection": c.selection,
            "odds": c.book_odds,
            "ev": c.ev,
            "confidence": c.confidence,
            "trust_level": c.trust_tier,
            "model_prob": c.model_prob,
            "line": c.line,
            "metadata": c.metadata,
        }
    
    def _value_single_to_router_dict(self, vs: Dict) -> Dict:
        """Convert value single dict to router-compatible dict."""
        market_key = vs.get("market_key", "") or vs.get("market", "")
        
        product = "VALUE_SINGLES"
        if "OVER" in market_key.upper() or "UNDER" in market_key.upper():
            if "CORNER" in market_key.upper():
                product = "CORNERS_MATCH"
            elif "CARD" in market_key.upper():
                product = "CARDS_MATCH"
            elif "SHOT" in market_key.upper():
                product = "SHOTS_TEAM"
            else:
                product = "TOTALS"
        elif "BTTS" in market_key.upper():
            product = "BTTS"
        
        return {
            "fixture_id": vs.get("fixture_id", "") or vs.get("match_id", ""),
            "home_team": vs.get("home_team", ""),
            "away_team": vs.get("away_team", ""),
            "market_key": market_key,
            "market_type": vs.get("market_type", "ML"),
            "product": product,
            "selection": vs.get("selection", ""),
            "odds": vs.get("book_odds", 0) or vs.get("odds", 0),
            "ev": vs.get("ev", 0) or vs.get("edge_percentage", 0),
            "confidence": vs.get("confidence", 0),
            "trust_level": vs.get("trust_tier", "") or vs.get("trust_level", "L3_SOFT_VALUE"),
            "model_prob": vs.get("model_prob", 0),
            "line": vs.get("line"),
            "metadata": vs.get("metadata", {}),
        }
    
    def _router_to_unified(self, pick: RouterCandidate) -> UnifiedCandidate:
        """Convert RouterCandidate back to UnifiedCandidate."""
        return UnifiedCandidate(
            fixture_id=pick.fixture_id,
            home_team=pick.home_team,
            away_team=pick.away_team,
            market_key=pick.market_key,
            market_type=pick.market_type,
            product_type=pick.product,
            selection=pick.selection,
            line=pick.line,
            model_prob=pick.model_prob,
            book_odds=pick.odds,
            ev=pick.ev,
            confidence=pick.confidence,
            trust_tier=pick.trust_level,
            metadata=pick.metadata,
        )
    
    def _log_card_summary(self, card: DailyCard):
        """Log daily card summary."""
        summary = card.summary
        
        logger.info("=" * 60)
        logger.info(f"📋 DAILY CARD: {card.date}")
        logger.info("=" * 60)
        logger.info(f"   Total Bets: {summary['total_bets']}")
        logger.info(f"   Average EV: {summary['average_ev']:.1f}%")
        logger.info(f"   L1 (High Trust): {summary['l1_count']}")
        logger.info(f"   L2 (Medium Trust): {summary['l2_count']}")
        logger.info(f"   L3 (Soft Value): {summary['l3_count']}")
        logger.info("-" * 60)
        logger.info(f"   By Product:")
        for product, count in summary.get("by_product", {}).items():
            logger.info(f"      {product}: {count}")
        
        if card.routing_stats:
            logger.info("-" * 60)
            logger.info("   📊 ROUTER STATS:")
            logger.info(f"      Markets Covered: {card.markets_covered}")
            logger.info(f"      Balance Score: {card.routing_stats.get('balance_score', 0)}/100")
            logger.info(f"      Market Diversity: {card.routing_stats.get('market_diversity', 0)}")
        
        logger.info("=" * 60)


_router_instance: Optional[CentralRouter] = None

def get_central_router() -> CentralRouter:
    """Get singleton instance of CentralRouter."""
    global _router_instance
    if _router_instance is None:
        _router_instance = CentralRouter()
    return _router_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    router = get_central_router()
    
    test_fixtures = [
        {
            "fixture_id": "test_1",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
        },
        {
            "fixture_id": "test_2",
            "home_team": "Manchester City",
            "away_team": "Liverpool",
        },
    ]
    
    test_odds = {
        "test_1": {
            "TEAM_SHOTS_OVER_10_5": 1.85,
            "MATCH_CARDS_OVER_4_5": 1.90,
            "CORNERS_HC_HOME_-1_5": 2.00,
        },
        "test_2": {
            "TEAM_SHOTS_OVER_11_5": 1.95,
            "MATCH_CARDS_OVER_5_5": 2.10,
            "CORNERS_HC_HOME_-2_5": 2.40,
        },
    }
    
    card = router.build_daily_card(test_fixtures, test_odds)
    
    print("\n=== Daily Card Result ===")
    print(f"Shots: {len(card.shots)}")
    print(f"Cards: {len(card.cards)}")
    print(f"Corner Handicaps: {len(card.corner_handicaps)}")
    print(f"Total: {card.get_total_count()}")

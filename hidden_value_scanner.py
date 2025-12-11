"""
Hidden Value Scanner v1.0
=========================
Identifies "soft edge" picks that narrowly miss normal EV thresholds
but look attractive based on:
- High confidence
- Strong profile boost scores
- Positive market weights
- Proximity to EV threshold

These picks are flagged separately as "HiddenValue" / "SoftEdge" and 
shown as experimental options for advanced users.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from hidden_value_config import (
    HIDDEN_VALUE_CONFIG,
    HiddenValueConfig,
    get_hidden_value_config,
)

logger = logging.getLogger(__name__)


@dataclass
class HiddenValuePick:
    """A hidden value / soft edge pick."""
    match_id: str
    home_team: str
    away_team: str
    match_date: datetime
    market_key: str
    selection: str
    odds: float
    
    raw_ev: float
    boosted_ev: float
    final_ev: float
    
    raw_confidence: float
    boosted_confidence: float
    
    boost_score: float
    market_weight: float
    
    soft_edge_score: float
    selection_rank: int
    
    profile_boost_factors: List[Tuple[str, float]] = field(default_factory=list)
    
    category: str = "HiddenValue"
    trust_tier: str = "HV"
    
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "match_id": self.match_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "match_date": self.match_date.isoformat() if isinstance(self.match_date, datetime) else str(self.match_date),
            "market_key": self.market_key,
            "selection": self.selection,
            "odds": self.odds,
            "raw_ev": round(self.raw_ev * 100, 2),
            "boosted_ev": round(self.boosted_ev * 100, 2),
            "final_ev": round(self.final_ev * 100, 2),
            "raw_confidence": round(self.raw_confidence * 100, 1),
            "boosted_confidence": round(self.boosted_confidence * 100, 1),
            "boost_score": round(self.boost_score, 3),
            "market_weight": round(self.market_weight, 3),
            "soft_edge_score": round(self.soft_edge_score, 1),
            "selection_rank": self.selection_rank,
            "profile_boost_factors": [
                {"factor": f[0], "score": round(f[1], 3)} for f in self.profile_boost_factors
            ],
            "category": self.category,
            "trust_tier": self.trust_tier,
            "reason": self.reason,
        }


@dataclass
class RejectedCandidate:
    """A candidate that failed standard filters."""
    match_id: str
    home_team: str
    away_team: str
    match_date: Any
    market_key: str
    selection: str
    odds: float
    raw_ev: float
    boosted_ev: float
    final_ev: float
    raw_confidence: float
    boosted_confidence: float
    boost_score: float
    market_weight: float
    profile_boost_factors: List[Tuple[str, float]] = field(default_factory=list)


class HiddenValueScanner:
    """
    Syndicate-style Hidden Value Scanner.
    
    Scans rejected candidates to find "soft edges" that might still
    have value despite failing standard EV thresholds.
    """
    
    def __init__(self, config: Optional[HiddenValueConfig] = None):
        self.config = config or get_hidden_value_config()
        self._today_picks: List[HiddenValuePick] = []
        self._today_date: Optional[datetime] = None
        
        logger.info("🔍 Hidden Value Scanner v1.0 initialized")
        logger.info(f"   EV range: {self.config.ev_near_miss_range} | Max picks: {self.config.max_picks_per_day}")
    
    def scan_candidates(
        self,
        rejected_candidates: List[RejectedCandidate],
        existing_picks_today: int = 0,
    ) -> List[HiddenValuePick]:
        """
        Scan rejected candidates for hidden value picks.
        
        Args:
            rejected_candidates: List of candidates that failed standard filters
            existing_picks_today: Number of HV picks already made today
        
        Returns:
            List of HiddenValuePick objects, sorted by soft_edge_score
        """
        if self._today_date != datetime.now().date():
            self._today_picks = []
            self._today_date = datetime.now().date()
        
        remaining_slots = self.config.max_picks_per_day - existing_picks_today - len(self._today_picks)
        if remaining_slots <= 0:
            logger.debug("Hidden Value Scanner: Daily limit reached")
            return []
        
        qualifying = self._filter_near_misses(rejected_candidates)
        
        scored = self._score_candidates(qualifying)
        
        sorted_picks = sorted(scored, key=lambda x: x.soft_edge_score, reverse=True)
        
        selected = sorted_picks[:remaining_slots]
        
        for i, pick in enumerate(selected):
            pick.selection_rank = i + 1 + len(self._today_picks)
        
        self._today_picks.extend(selected)
        
        if selected and self.config.enable_logging:
            for pick in selected:
                self._log_selection(pick)
        
        return selected
    
    def _filter_near_misses(
        self,
        candidates: List[RejectedCandidate]
    ) -> List[RejectedCandidate]:
        """Filter candidates that are near misses on EV threshold."""
        ev_min, ev_max = self.config.ev_near_miss_range
        qualifying = []
        
        for c in candidates:
            if c.market_key in self.config.exclude_markets:
                continue
            
            ev_in_range = ev_min <= c.final_ev <= ev_max
            
            conf_ok = (
                c.raw_confidence >= self.config.min_confidence or
                c.boosted_confidence >= self.config.min_boosted_confidence
            )
            
            if ev_in_range and conf_ok:
                qualifying.append(c)
                continue
            
            if c.boost_score >= 0.3 and c.final_ev > -0.02:
                qualifying.append(c)
                continue
            
            if c.market_weight >= 1.1 and c.final_ev > -0.01:
                qualifying.append(c)
        
        return qualifying
    
    def _score_candidates(
        self,
        candidates: List[RejectedCandidate]
    ) -> List[HiddenValuePick]:
        """Score candidates to determine soft edge score."""
        picks = []
        
        if not candidates:
            return picks
        
        boost_scores = [c.boost_score for c in candidates]
        boost_threshold = sorted(boost_scores, reverse=True)[
            int(len(boost_scores) * (1 - self.config.min_boost_score_percentile))
        ] if boost_scores else 0
        
        for c in candidates:
            ev_min, ev_max = self.config.ev_near_miss_range
            ev_range = ev_max - ev_min
            ev_proximity = 1 - abs(c.final_ev - ev_max) / max(ev_range, 0.01)
            ev_proximity = max(0, min(1, ev_proximity))
            ev_component = ev_proximity * 100 * self.config.ev_proximity_weight
            
            conf_normalized = min(1.0, (c.boosted_confidence - 0.50) / 0.20)
            conf_component = conf_normalized * 100 * self.config.confidence_weight
            
            boost_normalized = min(1.0, max(0, c.boost_score / 0.5))
            boost_component = boost_normalized * 100 * self.config.boost_score_weight
            
            weight_normalized = min(1.0, max(0, (c.market_weight - 0.9) / 0.3))
            weight_component = weight_normalized * 100 * self.config.market_weight_factor
            
            soft_edge_score = ev_component + conf_component + boost_component + weight_component
            
            if soft_edge_score < self.config.min_soft_edge_score:
                continue
            
            reasons = []
            if c.boosted_confidence >= self.config.min_boosted_confidence:
                reasons.append(f"High confidence ({c.boosted_confidence*100:.0f}%)")
            if c.boost_score >= boost_threshold:
                reasons.append(f"Strong profile boost ({c.boost_score:+.2f})")
            if c.market_weight >= 1.05:
                reasons.append(f"Favorable market weight ({c.market_weight:.2f})")
            if c.final_ev >= 0:
                reasons.append(f"Near EV threshold ({c.final_ev*100:+.1f}%)")
            
            pick = HiddenValuePick(
                match_id=c.match_id,
                home_team=c.home_team,
                away_team=c.away_team,
                match_date=c.match_date,
                market_key=c.market_key,
                selection=c.selection,
                odds=c.odds,
                raw_ev=c.raw_ev,
                boosted_ev=c.boosted_ev,
                final_ev=c.final_ev,
                raw_confidence=c.raw_confidence,
                boosted_confidence=c.boosted_confidence,
                boost_score=c.boost_score,
                market_weight=c.market_weight,
                soft_edge_score=soft_edge_score,
                selection_rank=0,
                profile_boost_factors=c.profile_boost_factors,
                category=self.config.category_label,
                trust_tier=self.config.trust_tier_label,
                reason="; ".join(reasons) if reasons else "Soft edge detected",
            )
            
            picks.append(pick)
        
        return picks
    
    def _log_selection(self, pick: HiddenValuePick):
        """Log hidden value selection."""
        logger.info(
            f"🔍 HIDDEN VALUE [{pick.market_key}]: "
            f"{pick.home_team} vs {pick.away_team} | "
            f"{pick.selection} @ {pick.odds:.2f} | "
            f"Score={pick.soft_edge_score:.1f} | "
            f"EV={pick.final_ev*100:+.1f}% | "
            f"Reason: {pick.reason}"
        )
    
    def get_today_picks(self) -> List[HiddenValuePick]:
        """Get all hidden value picks made today."""
        if self._today_date != datetime.now().date():
            return []
        return self._today_picks
    
    def reset_daily(self):
        """Reset daily picks counter."""
        self._today_picks = []
        self._today_date = datetime.now().date()


def scan_for_hidden_value(
    rejected_candidates: List[Dict[str, Any]],
    scanner: Optional[HiddenValueScanner] = None,
) -> List[HiddenValuePick]:
    """
    Convenience function to scan for hidden value picks.
    
    Args:
        rejected_candidates: List of dicts with candidate data
        scanner: Optional pre-initialized scanner
    
    Returns:
        List of HiddenValuePick objects
    """
    if scanner is None:
        scanner = HiddenValueScanner()
    
    candidates = []
    for c in rejected_candidates:
        try:
            candidate = RejectedCandidate(
                match_id=c.get("match_id", ""),
                home_team=c.get("home_team", ""),
                away_team=c.get("away_team", ""),
                match_date=c.get("match_date", datetime.now()),
                market_key=c.get("market_key", ""),
                selection=c.get("selection", ""),
                odds=c.get("odds", 0),
                raw_ev=c.get("raw_ev", 0),
                boosted_ev=c.get("boosted_ev", 0),
                final_ev=c.get("final_ev", 0),
                raw_confidence=c.get("raw_confidence", 0),
                boosted_confidence=c.get("boosted_confidence", 0),
                boost_score=c.get("boost_score", 0),
                market_weight=c.get("market_weight", 1.0),
                profile_boost_factors=c.get("profile_boost_factors", []),
            )
            candidates.append(candidate)
        except Exception as e:
            logger.debug(f"Error parsing candidate: {e}")
    
    return scanner.scan_candidates(candidates)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    scanner = HiddenValueScanner()
    
    test_candidates = [
        RejectedCandidate(
            match_id="test_1",
            home_team="Arsenal",
            away_team="Chelsea",
            match_date=datetime.now(),
            market_key="FT_OVER_2_5",
            selection="Over 2.5",
            odds=1.95,
            raw_ev=0.01,
            boosted_ev=0.015,
            final_ev=0.018,
            raw_confidence=0.56,
            boosted_confidence=0.59,
            boost_score=0.25,
            market_weight=1.08,
            profile_boost_factors=[("tempo_index", 0.2), ("rivalry_index", 0.15)],
        ),
        RejectedCandidate(
            match_id="test_2",
            home_team="Liverpool",
            away_team="Man City",
            match_date=datetime.now(),
            market_key="BTTS_YES",
            selection="BTTS Yes",
            odds=1.72,
            raw_ev=-0.005,
            boosted_ev=0.008,
            final_ev=0.012,
            raw_confidence=0.58,
            boosted_confidence=0.61,
            boost_score=0.35,
            market_weight=1.12,
            profile_boost_factors=[("pressure_index", 0.3), ("tempo_index", 0.2)],
        ),
        RejectedCandidate(
            match_id="test_3",
            home_team="Everton",
            away_team="Newcastle",
            match_date=datetime.now(),
            market_key="CARDS_MATCH",
            selection="Over 4.5 Cards",
            odds=1.85,
            raw_ev=-0.02,
            boosted_ev=-0.01,
            final_ev=-0.005,
            raw_confidence=0.52,
            boosted_confidence=0.54,
            boost_score=0.15,
            market_weight=0.98,
            profile_boost_factors=[("referee_profile", 0.1)],
        ),
    ]
    
    picks = scanner.scan_candidates(test_candidates)
    
    print("\n" + "="*60)
    print("HIDDEN VALUE SCANNER TEST")
    print("="*60)
    print(f"\nScanned {len(test_candidates)} rejected candidates")
    print(f"Found {len(picks)} hidden value picks:")
    
    for pick in picks:
        print(f"\n  #{pick.selection_rank}: {pick.home_team} vs {pick.away_team}")
        print(f"     Market: {pick.market_key} | {pick.selection} @ {pick.odds:.2f}")
        print(f"     Soft Edge Score: {pick.soft_edge_score:.1f}")
        print(f"     EV Chain: {pick.raw_ev*100:.1f}% → {pick.boosted_ev*100:.1f}% → {pick.final_ev*100:.1f}%")
        print(f"     Confidence: {pick.raw_confidence*100:.0f}% → {pick.boosted_confidence*100:.0f}%")
        print(f"     Reason: {pick.reason}")

"""
Market Weight Engine v1.0
=========================
Learns which markets perform best over time and applies soft bias
to EV calculations and priority scoring.

Uses rolling windows of historical performance data including:
- ROI (units won/lost)
- Win rate
- Closing Line Value (CLV)

Sample size shrinkage prevents overreaction to small samples.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import os

from market_weight_config import (
    MARKET_WEIGHT_CONFIG,
    MarketWeightConfig,
    get_market_weight_config,
)

logger = logging.getLogger(__name__)


@dataclass
class MarketStats:
    """Statistics for a single market type."""
    market_key: str
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    pending: int = 0
    total_stake: float = 0.0
    total_return: float = 0.0
    avg_odds: float = 0.0
    avg_clv: float = 0.0
    
    @property
    def roi(self) -> float:
        """Calculate ROI as (return - stake) / stake."""
        if self.total_stake <= 0:
            return 0.0
        return (self.total_return - self.total_stake) / self.total_stake
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        settled = self.wins + self.losses
        if settled <= 0:
            return 0.5
        return self.wins / settled
    
    @property
    def units_profit(self) -> float:
        """Calculate profit in units (assuming 1 unit per bet)."""
        return self.total_return - self.total_stake


@dataclass
class WeightResult:
    """Result of market weight calculation."""
    market_key: str
    market_group: str
    weight: float
    confidence_factor: float
    stats: Optional[MarketStats]
    components: Dict[str, float]
    adjusted_ev: Optional[float] = None
    raw_ev: Optional[float] = None


class MarketWeightEngine:
    """
    Syndicate-style Market Weighting Engine.
    
    Analyzes historical performance data to compute market weights
    that gently bias the system towards higher-performing markets.
    """
    
    def __init__(self, config: Optional[MarketWeightConfig] = None):
        self.config = config or get_market_weight_config()
        self._cache: Dict[str, MarketStats] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(hours=1)
        
        logger.info("📊 Market Weight Engine v1.0 initialized")
        logger.info(f"   Window: {self.config.rolling_window_days} days | Weight range: {self.config.min_weight}-{self.config.max_weight}")
    
    def get_market_weight(
        self,
        market_key: str,
        base_ev: Optional[float] = None,
    ) -> WeightResult:
        """
        Get weight for a specific market type.
        
        Args:
            market_key: Market identifier (e.g., 'FT_OVER_2_5', 'CARDS_MATCH')
            base_ev: Optional base EV to compute adjusted EV
        
        Returns:
            WeightResult with weight and optional adjusted EV
        """
        market_group = self.config.market_group_mapping.get(market_key, market_key)
        
        stats = self._get_market_stats(market_key)
        
        if stats is None or stats.total_bets < self.config.min_sample_size:
            group_stats = self._get_group_stats(market_group)
            if group_stats and group_stats.total_bets >= self.config.min_sample_size:
                stats = group_stats
        
        if stats is None or stats.total_bets < self.config.min_sample_size:
            return WeightResult(
                market_key=market_key,
                market_group=market_group,
                weight=self.config.neutral_weight,
                confidence_factor=0.0,
                stats=stats,
                components={"fallback": 1.0},
                raw_ev=base_ev,
                adjusted_ev=base_ev,
            )
        
        weight, components = self._calculate_weight(stats)
        
        confidence_factor = self._calculate_confidence_factor(stats)
        
        shrunk_weight = self._apply_shrinkage(weight, confidence_factor)
        
        adjusted_ev = None
        if base_ev is not None:
            adjusted_ev = self._apply_weight_to_ev(base_ev, shrunk_weight)
        
        result = WeightResult(
            market_key=market_key,
            market_group=market_group,
            weight=shrunk_weight,
            confidence_factor=confidence_factor,
            stats=stats,
            components=components,
            raw_ev=base_ev,
            adjusted_ev=adjusted_ev,
        )
        
        if self.config.enable_logging and abs(shrunk_weight - 1.0) > 0.05:
            self._log_weight(result)
        
        return result
    
    def _get_market_stats(self, market_key: str) -> Optional[MarketStats]:
        """Get statistics for a specific market from database."""
        if self._is_cache_valid() and market_key in self._cache:
            return self._cache[market_key]
        
        stats = self._query_market_stats(market_key)
        
        if stats:
            self._cache[market_key] = stats
            self._cache_timestamp = datetime.now()
        
        return stats
    
    def _get_group_stats(self, market_group: str) -> Optional[MarketStats]:
        """Get aggregated statistics for a market group."""
        group_key = f"__group__{market_group}"
        
        if self._is_cache_valid() and group_key in self._cache:
            return self._cache[group_key]
        
        stats = self._query_group_stats(market_group)
        
        if stats:
            self._cache[group_key] = stats
            self._cache_timestamp = datetime.now()
        
        return stats
    
    def _query_market_stats(self, market_key: str) -> Optional[MarketStats]:
        """Query database for market statistics."""
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                return None
            
            conn = psycopg2.connect(database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cutoff_date = datetime.now() - timedelta(days=self.config.rolling_window_days)
            
            query = """
                SELECT 
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN result = 'pending' OR result IS NULL THEN 1 ELSE 0 END) as pending,
                    COALESCE(SUM(stake), 0) as total_stake,
                    COALESCE(SUM(payout), 0) as total_return,
                    COALESCE(AVG(odds), 0) as avg_odds,
                    COALESCE(AVG(clv), 0) as avg_clv
                FROM all_bets
                WHERE market_key = %s
                    AND match_date >= %s
                    AND mode = 'PROD'
                LIMIT %s
            """
            
            cursor.execute(query, (market_key, cutoff_date, self.config.max_bets_per_window))
            row = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if row and row['total_bets'] > 0:
                return MarketStats(
                    market_key=market_key,
                    total_bets=int(row['total_bets']),
                    wins=int(row['wins'] or 0),
                    losses=int(row['losses'] or 0),
                    pending=int(row['pending'] or 0),
                    total_stake=float(row['total_stake'] or 0),
                    total_return=float(row['total_return'] or 0),
                    avg_odds=float(row['avg_odds'] or 0),
                    avg_clv=float(row['avg_clv'] or 0),
                )
            
            return None
            
        except Exception as e:
            logger.debug(f"Market stats query error: {e}")
            return None
    
    def _query_group_stats(self, market_group: str) -> Optional[MarketStats]:
        """Query database for aggregated group statistics."""
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                return None
            
            group_markets = [k for k, v in self.config.market_group_mapping.items() if v == market_group]
            if not group_markets:
                return None
            
            conn = psycopg2.connect(database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cutoff_date = datetime.now() - timedelta(days=self.config.rolling_window_days)
            
            placeholders = ','.join(['%s'] * len(group_markets))
            query = f"""
                SELECT 
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN result = 'pending' OR result IS NULL THEN 1 ELSE 0 END) as pending,
                    COALESCE(SUM(stake), 0) as total_stake,
                    COALESCE(SUM(payout), 0) as total_return,
                    COALESCE(AVG(odds), 0) as avg_odds,
                    COALESCE(AVG(clv), 0) as avg_clv
                FROM all_bets
                WHERE market_key IN ({placeholders})
                    AND match_date >= %s
                    AND mode = 'PROD'
            """
            
            cursor.execute(query, (*group_markets, cutoff_date))
            row = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if row and row['total_bets'] > 0:
                return MarketStats(
                    market_key=f"GROUP_{market_group}",
                    total_bets=int(row['total_bets']),
                    wins=int(row['wins'] or 0),
                    losses=int(row['losses'] or 0),
                    pending=int(row['pending'] or 0),
                    total_stake=float(row['total_stake'] or 0),
                    total_return=float(row['total_return'] or 0),
                    avg_odds=float(row['avg_odds'] or 0),
                    avg_clv=float(row['avg_clv'] or 0),
                )
            
            return None
            
        except Exception as e:
            logger.debug(f"Group stats query error: {e}")
            return None
    
    def _calculate_weight(self, stats: MarketStats) -> Tuple[float, Dict[str, float]]:
        """Calculate raw weight from statistics."""
        components = {}
        
        roi_contribution = stats.roi * self.config.roi_scale_factor
        roi_contribution = max(-0.5, min(0.5, roi_contribution))
        components["roi"] = roi_contribution * self.config.roi_weight
        
        win_rate_delta = stats.win_rate - self.config.win_rate_baseline
        wr_contribution = win_rate_delta * 2.0
        wr_contribution = max(-0.4, min(0.4, wr_contribution))
        components["win_rate"] = wr_contribution * self.config.win_rate_weight
        
        clv_contribution = stats.avg_clv - self.config.clv_baseline
        clv_contribution = max(-0.3, min(0.3, clv_contribution / 5.0))
        components["clv"] = clv_contribution * self.config.clv_weight
        
        total_adjustment = sum(components.values())
        raw_weight = self.config.neutral_weight + total_adjustment
        
        raw_weight = max(self.config.min_weight, min(self.config.max_weight, raw_weight))
        
        return raw_weight, components
    
    def _calculate_confidence_factor(self, stats: MarketStats) -> float:
        """Calculate confidence factor based on sample size."""
        n = stats.wins + stats.losses
        
        if n >= self.config.sample_shrinkage_threshold:
            return 1.0
        elif n >= self.config.min_sample_size:
            return n / self.config.sample_shrinkage_threshold
        else:
            return 0.0
    
    def _apply_shrinkage(self, weight: float, confidence_factor: float) -> float:
        """Apply shrinkage towards neutral weight based on confidence."""
        return self.config.neutral_weight + (weight - self.config.neutral_weight) * confidence_factor
    
    def _apply_weight_to_ev(self, base_ev: float, weight: float) -> float:
        """Apply market weight to EV."""
        if self.config.ev_adjustment_mode == "multiply":
            adjusted = base_ev * weight
        else:
            adjustment = (weight - 1.0) * 0.1
            adjusted = base_ev + adjustment
        
        if base_ev > 0 and adjusted < 0:
            min_ev = base_ev * (1 - self.config.max_ev_reduction_pct)
            adjusted = max(min_ev, adjusted)
        
        return adjusted
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache_timestamp is None:
            return False
        return datetime.now() - self._cache_timestamp < self._cache_ttl
    
    def clear_cache(self):
        """Clear the statistics cache."""
        self._cache = {}
        self._cache_timestamp = None
    
    def _log_weight(self, result: WeightResult):
        """Log significant weight adjustments."""
        direction = "+" if result.weight > 1.0 else ""
        stats_info = ""
        if result.stats:
            stats_info = f"N={result.stats.total_bets} ROI={result.stats.roi*100:.1f}%"
        
        logger.info(
            f"📊 MARKET WEIGHT [{result.market_key}]: "
            f"Weight={result.weight:.3f} | "
            f"Conf={result.confidence_factor:.2f} | "
            f"{stats_info}"
        )
    
    def get_all_weights(self) -> Dict[str, WeightResult]:
        """Get weights for all known markets."""
        weights = {}
        for market_key in self.config.market_group_mapping.keys():
            weights[market_key] = self.get_market_weight(market_key)
        return weights


def apply_market_weight(
    market_key: str,
    boosted_ev: float,
    engine: Optional[MarketWeightEngine] = None
) -> Tuple[float, WeightResult]:
    """
    Convenience function to apply market weight to EV.
    
    Args:
        market_key: Market identifier
        boosted_ev: EV after profile boost
        engine: Optional pre-initialized engine
    
    Returns:
        Tuple of (weighted_ev, WeightResult)
    """
    if engine is None:
        engine = MarketWeightEngine()
    
    result = engine.get_market_weight(market_key, boosted_ev)
    
    return result.adjusted_ev or boosted_ev, result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    engine = MarketWeightEngine()
    
    print("\n" + "="*60)
    print("MARKET WEIGHT ENGINE TEST")
    print("="*60)
    
    test_markets = ["FT_OVER_2_5", "BTTS_YES", "CARDS_MATCH", "CORNERS_MATCH", "HOME_WIN"]
    
    for market in test_markets:
        result = engine.get_market_weight(market, base_ev=0.05)
        print(f"\n{market}:")
        print(f"  Weight: {result.weight:.3f}")
        print(f"  Confidence: {result.confidence_factor:.2f}")
        print(f"  Group: {result.market_group}")
        if result.stats:
            print(f"  Stats: N={result.stats.total_bets}, ROI={result.stats.roi*100:.1f}%, WR={result.stats.win_rate*100:.0f}%")
        print(f"  Raw EV: {result.raw_ev*100:.1f}% → Weighted EV: {(result.adjusted_ev or 0)*100:.1f}%")

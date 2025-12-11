"""
Market Weight Configuration
===========================
Controls how historical performance data influences market weighting.

Weights are calculated based on rolling ROI, win rate, and sample size.
Small samples shrink towards 1.0 (neutral) to avoid overreaction.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class MarketWeightConfig:
    """Master configuration for market weighting engine."""
    
    rolling_window_days: int = 30
    max_bets_per_window: int = 300
    
    min_sample_size: int = 10
    sample_shrinkage_threshold: int = 50
    
    min_weight: float = 0.60
    max_weight: float = 1.40
    neutral_weight: float = 1.0
    
    roi_weight: float = 0.50
    win_rate_weight: float = 0.30
    clv_weight: float = 0.20
    
    roi_scale_factor: float = 5.0
    win_rate_baseline: float = 0.50
    clv_baseline: float = 0.0
    
    ev_adjustment_mode: str = "multiply"
    max_ev_reduction_pct: float = 0.15
    
    fallback_weight: float = 1.0
    enable_logging: bool = True
    
    market_group_mapping: Dict[str, str] = field(default_factory=lambda: {
        "FT_OVER_2_5": "TOTALS",
        "FT_UNDER_2_5": "TOTALS",
        "FT_OVER_3_5": "TOTALS",
        "FT_UNDER_3_5": "TOTALS",
        "FT_OVER_1_5": "TOTALS",
        "FT_UNDER_1_5": "TOTALS",
        "BTTS_YES": "BTTS",
        "BTTS_NO": "BTTS",
        "HOME_WIN": "1X2",
        "AWAY_WIN": "1X2",
        "DRAW": "1X2",
        "CORNERS_MATCH": "CORNERS",
        "CORNERS_TEAM": "CORNERS",
        "CORNERS_HANDICAP": "CORNERS",
        "CARDS_MATCH": "CARDS",
        "CARDS_TEAM": "CARDS",
        "SHOTS_TEAM": "SHOTS",
    })


MARKET_WEIGHT_CONFIG = MarketWeightConfig()


def get_market_weight_config() -> MarketWeightConfig:
    """Get the active market weight configuration."""
    return MARKET_WEIGHT_CONFIG


def update_config(**kwargs) -> MarketWeightConfig:
    """Update configuration parameters dynamically."""
    global MARKET_WEIGHT_CONFIG
    for key, value in kwargs.items():
        if hasattr(MARKET_WEIGHT_CONFIG, key):
            setattr(MARKET_WEIGHT_CONFIG, key, value)
    return MARKET_WEIGHT_CONFIG

"""
Hidden Value Scanner Configuration
===================================
Controls soft edge detection for picks that narrowly miss normal EV thresholds.

These picks are flagged separately and shown as "experimental/advanced" options.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class HiddenValueConfig:
    """Master configuration for hidden value scanner."""
    
    ev_near_miss_range: tuple = (-0.01, 0.02)
    
    min_confidence: float = 0.55
    min_boosted_confidence: float = 0.57
    
    min_boost_score_percentile: float = 0.75
    min_market_weight: float = 0.95
    
    confidence_weight: float = 0.30
    ev_proximity_weight: float = 0.25
    boost_score_weight: float = 0.25
    market_weight_factor: float = 0.20
    
    max_picks_per_day: int = 5
    min_soft_edge_score: float = 40.0
    
    category_label: str = "HiddenValue"
    trust_tier_label: str = "HV"
    
    exclude_markets: List[str] = field(default_factory=lambda: [])
    
    priority_markets: List[str] = field(default_factory=lambda: [
        "FT_OVER_2_5",
        "FT_UNDER_2_5",
        "BTTS_YES",
        "CORNERS_MATCH",
        "CARDS_MATCH",
    ])
    
    enable_logging: bool = True
    show_in_daily_card: bool = True


HIDDEN_VALUE_CONFIG = HiddenValueConfig()


def get_hidden_value_config() -> HiddenValueConfig:
    """Get the active hidden value configuration."""
    return HIDDEN_VALUE_CONFIG


def update_config(**kwargs) -> HiddenValueConfig:
    """Update configuration parameters dynamically."""
    global HIDDEN_VALUE_CONFIG
    for key, value in kwargs.items():
        if hasattr(HIDDEN_VALUE_CONFIG, key):
            setattr(HIDDEN_VALUE_CONFIG, key, value)
    return HIDDEN_VALUE_CONFIG

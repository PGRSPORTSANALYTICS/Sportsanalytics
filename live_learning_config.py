#!/usr/bin/env python3
"""
Live Learning Mode Configuration
================================
Configuration for LIVE LEARNING MODE - full data capture across all markets.

Purpose: Gather maximum real-world betting data for system self-calibration,
EV model strengthening, trust tier refinement, and market weight optimization.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class LiveLearningConfig:
    """Configuration for Live Learning Mode."""
    
    mode: str = "LIVE_LEARNING"
    version: str = "1.0"
    activated_at: Optional[datetime] = None
    
    capture_all_picks: bool = True
    capture_trust_tiers: List[str] = field(default_factory=lambda: [
        "L1_HIGH_TRUST",
        "L2_MEDIUM_TRUST", 
        "L3_SOFT_VALUE",
        "HIDDEN_VALUE"
    ])
    
    enable_clv_tracking: bool = True
    clv_capture_interval_minutes: int = 30
    clv_final_capture_minutes_before_ko: int = 5
    
    enable_profile_boost: bool = True
    enable_market_weight: bool = True
    enable_hidden_value_scanner: bool = True
    
    ev_filter_enabled: bool = False
    min_ev_threshold: float = -1.0
    min_confidence_threshold: float = 0.0
    
    ev_near_miss_range: tuple = (-0.01, 0.02)
    
    unit_based_tracking: bool = True
    default_stake_units: float = 1.0
    
    store_raw_ev: bool = True
    store_boosted_ev: bool = True
    store_weighted_ev: bool = True
    store_profile_boost_details: bool = True
    store_market_weight_details: bool = True
    store_hidden_value_status: bool = True
    
    market_weight_learning_enabled: bool = True
    market_weight_min_sample_size: int = 10
    market_weight_learning_rate: float = 0.1
    
    pick_markets: List[str] = field(default_factory=lambda: [
        "1X2", "HOME_WIN", "AWAY_WIN", "DRAW",
        "ASIAN_HANDICAP", "DOUBLE_CHANCE", "DNB",
        "FT_OVER_1_5", "FT_OVER_2_5", "FT_OVER_3_5",
        "FT_UNDER_1_5", "FT_UNDER_2_5", "FT_UNDER_3_5",
        "BTTS_YES", "BTTS_NO",
        "CORNERS_MATCH", "CORNERS_TEAM", "CORNERS_HANDICAP",
        "CARDS_MATCH", "CARDS_TEAM",
        "SHOTS_TEAM", "SHOTS_MATCH"
    ])
    
    logging_mode: str = "VERBOSE"
    log_every_pick: bool = True
    log_clv_updates: bool = True
    log_result_settlements: bool = True
    
    def to_dict(self) -> Dict:
        """Convert config to dictionary."""
        return {
            "mode": self.mode,
            "version": self.version,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "capture_all_picks": self.capture_all_picks,
            "capture_trust_tiers": self.capture_trust_tiers,
            "enable_clv_tracking": self.enable_clv_tracking,
            "ev_filter_enabled": self.ev_filter_enabled,
            "unit_based_tracking": self.unit_based_tracking,
            "market_weight_learning_enabled": self.market_weight_learning_enabled,
            "pick_markets": self.pick_markets,
            "logging_mode": self.logging_mode,
        }


LIVE_LEARNING_CONFIG = LiveLearningConfig(
    activated_at=datetime.now()
)


def get_live_learning_config() -> LiveLearningConfig:
    """Get the current live learning configuration."""
    return LIVE_LEARNING_CONFIG


def is_live_learning_active() -> bool:
    """Check if live learning mode is active."""
    return LIVE_LEARNING_CONFIG.mode == "LIVE_LEARNING"

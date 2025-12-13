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
    version: str = "1.1"
    activated_at: Optional[datetime] = None
    
    # ROI TARGETS
    target_roi_min: float = 20.0  # 20% minimum target ROI
    target_roi_max: float = 25.0  # 25% stretch goal ROI
    target_hit_rate_min: float = 52.0  # Minimum hit rate for profitability
    
    # Learning phase settings
    learning_phase_weeks: int = 4  # Weeks before full optimization kicks in
    min_bets_before_optimization: int = 200  # Min settled bets before auto-adjustments
    
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
    
    # DISABLED MARKETS (historically unprofitable)
    enable_exact_score: bool = False  # -111 units, 2% hit rate - DISABLED
    
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
            "target_roi": {"min": self.target_roi_min, "max": self.target_roi_max},
            "target_hit_rate_min": self.target_hit_rate_min,
            "learning_phase_weeks": self.learning_phase_weeks,
            "min_bets_before_optimization": self.min_bets_before_optimization,
            "capture_all_picks": self.capture_all_picks,
            "capture_trust_tiers": self.capture_trust_tiers,
            "enable_clv_tracking": self.enable_clv_tracking,
            "ev_filter_enabled": self.ev_filter_enabled,
            "unit_based_tracking": self.unit_based_tracking,
            "market_weight_learning_enabled": self.market_weight_learning_enabled,
            "pick_markets": self.pick_markets,
            "logging_mode": self.logging_mode,
        }
    
    def check_roi_target(self, current_roi: float) -> Dict:
        """Check if current ROI meets target."""
        if current_roi >= self.target_roi_max:
            status = "EXCEEDS_TARGET"
            message = f"ROI {current_roi:.1f}% exceeds stretch goal of {self.target_roi_max}%"
        elif current_roi >= self.target_roi_min:
            status = "ON_TARGET"
            message = f"ROI {current_roi:.1f}% meets minimum target of {self.target_roi_min}%"
        elif current_roi > 0:
            status = "BELOW_TARGET"
            gap = self.target_roi_min - current_roi
            message = f"ROI {current_roi:.1f}% is {gap:.1f}% below target"
        else:
            status = "NEGATIVE"
            message = f"ROI {current_roi:.1f}% - focus on reducing losses"
        
        return {
            "current_roi": current_roi,
            "target_min": self.target_roi_min,
            "target_max": self.target_roi_max,
            "status": status,
            "message": message
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

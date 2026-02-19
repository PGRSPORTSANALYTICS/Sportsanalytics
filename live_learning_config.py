#!/usr/bin/env python3
"""
Production Model v1.0 Configuration
====================================
Post-learning production configuration based on verified edge (Dec 25, 2025 - Jan 25, 2026).

ACTIVE MODE: PRODUCTION v1.0 (Jan 25, 2026)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Learning Phase Results:
- 1909 bets settled, 59.5% hit rate, +23.5% ROI, +449.2 units

PRODUCTION MARKETS (Live):
- CARDS: 88.4% hit rate, +127.70u
- CORNERS: 60.6% hit rate, +146.53u  
- VALUE_SINGLE (excl. Away Win)

LEARNING ONLY (Low weight):
- BASKETBALL, Away Win

DISABLED: SGP (all variants)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class StabilityModeConfig:
    """Production Mode v1.0 configuration (post-learning phase)."""
    
    enabled: bool = False  # STABILITY MODE DISABLED - Production v1.0 active
    activated_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime = field(default_factory=lambda: datetime(2026, 1, 25))
    
    hard_ev_cap: float = 0.25
    ev_deflator: float = 1.0  # No deflation in production
    
    blocked_ev_bands: List[tuple] = field(default_factory=lambda: [
        (0.50, 1.00),  # Still block unrealistic EV
    ])
    
    sgp_enabled: bool = False
    sgp_reason: str = "SGP permanently disabled - 2.8% hit rate, -5065u in learning phase"
    
    market_exposure_caps: Dict[str, float] = field(default_factory=lambda: {
        "CORNERS": 0.35,      # PRODUCTION - slight increase
        "SGP": 0.00,          # DISABLED
        "VALUE_SINGLE": 0.35, # PRODUCTION (excl. Away Win)
        "CARDS": 0.25,        # PRODUCTION - slight increase
        "BASKET_SINGLE": 0.10, # LEARNING ONLY - reduced
        "TOTALS": 0.25,
        "BTTS": 0.20,
        "EXACT_SCORE": 0.00,
        "AWAY_WIN": 0.00,     # LEARNING ONLY - not counted in production
    })
    
    production_markets: List[str] = field(default_factory=lambda: [
        "CARDS",
        "CORNERS", 
        "VALUE_SINGLE",  # Excluding Away Win
    ])
    
    learning_only_markets: List[str] = field(default_factory=lambda: [
        "BASKET_SINGLE",
        "AWAY_WIN",
    ])
    
    disabled_markets: List[str] = field(default_factory=lambda: [
        "SGP",
        "EXACT_SCORE",
    ])
    
    clv_tracking_enabled: bool = True
    clv_capture_on_bet_placement: bool = True
    clv_capture_at_kickoff: bool = True
    
    unit_flat_staking: bool = True  # Keep flat staking for now
    stake_per_bet: float = 1.0
    no_kelly_scaling: bool = True
    
    production_objectives: Dict[str, str] = field(default_factory=lambda: {
        "primary": "Maintain verified edge on production markets",
        "secondary": "Continue learning on experimental markets",
        "tertiary": "Log all post-learning changes",
    })
    
    learning_phase_results: Dict[str, Any] = field(default_factory=lambda: {
        "start_date": "2025-12-25",
        "end_date": "2026-01-25",
        "total_bets": 1909,
        "hit_rate": 59.5,
        "roi": 23.5,
        "profit_units": 449.2,
        "cards_hit_rate": 88.4,
        "corners_hit_rate": 60.6,
    })


@dataclass
class LiveLearningConfig:
    """Configuration for Live Learning Mode."""
    
    mode: str = "PRODUCTION"
    version: str = "2.0"
    activated_at: Optional[datetime] = field(default_factory=lambda: datetime(2026, 1, 25))
    
    stability_mode: StabilityModeConfig = field(default_factory=StabilityModeConfig)
    
    target_roi_min: float = 20.0
    target_roi_max: float = 25.0
    target_hit_rate_min: float = 52.0
    
    learning_phase_weeks: int = 4  # Completed
    learning_phase_completed: bool = True
    min_bets_before_optimization: int = 200  # Met: 1909 bets
    
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
    
    enable_exact_score: bool = False
    enable_sgp: bool = False
    
    ev_filter_enabled: bool = True
    min_ev_threshold: float = 0.02
    max_ev_threshold: float = 0.25
    ev_deflator: float = 1.0  # No deflation in production
    
    blocked_ev_bands: List[tuple] = field(default_factory=lambda: [
        (0.50, 1.00),
    ])
    
    min_confidence_threshold: float = 0.50
    
    ev_near_miss_range: tuple = (-0.01, 0.02)
    
    unit_based_tracking: bool = True
    default_stake_units: float = 1.0
    
    store_raw_ev: bool = True
    store_boosted_ev: bool = True
    store_weighted_ev: bool = True
    store_profile_boost_details: bool = True
    store_market_weight_details: bool = True
    store_hidden_value_status: bool = True
    
    store_opening_odds: bool = True
    store_closing_odds: bool = True
    store_clv_delta: bool = True
    
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
    ])
    
    disabled_markets: List[str] = field(default_factory=lambda: [
        "SGP",
        "EXACT_SCORE",
    ])
    
    logging_mode: str = "VERBOSE"
    log_every_pick: bool = True
    log_clv_updates: bool = True
    log_result_settlements: bool = True
    
    def apply_ev_deflator(self, raw_ev: float) -> float:
        """Apply EV deflator to raw EV estimate."""
        deflated = raw_ev * self.ev_deflator
        return min(deflated, self.max_ev_threshold)
    
    def is_ev_blocked(self, ev: float) -> bool:
        """Check if EV falls in a blocked band."""
        for low, high in self.blocked_ev_bands:
            if low <= ev <= high:
                return True
        return False
    
    def get_market_cap(self, market: str) -> float:
        """Get exposure cap for a market."""
        return self.stability_mode.market_exposure_caps.get(market.upper(), 0.25)
    
    def is_market_disabled(self, market: str) -> bool:
        """Check if a market is disabled."""
        return market.upper() in self.disabled_markets
    
    def to_dict(self) -> Dict:
        """Convert config to dictionary."""
        return {
            "mode": self.mode,
            "version": self.version,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "stability_mode": {
                "enabled": self.stability_mode.enabled,
                "hard_ev_cap": self.stability_mode.hard_ev_cap,
                "ev_deflator": self.stability_mode.ev_deflator,
                "sgp_enabled": self.stability_mode.sgp_enabled,
                "clv_tracking": self.stability_mode.clv_tracking_enabled,
                "market_caps": self.stability_mode.market_exposure_caps,
            },
            "target_roi": {"min": self.target_roi_min, "max": self.target_roi_max},
            "target_hit_rate_min": self.target_hit_rate_min,
            "learning_phase_weeks": self.learning_phase_weeks,
            "min_bets_before_optimization": self.min_bets_before_optimization,
            "capture_all_picks": self.capture_all_picks,
            "capture_trust_tiers": self.capture_trust_tiers,
            "enable_clv_tracking": self.enable_clv_tracking,
            "ev_filter_enabled": self.ev_filter_enabled,
            "max_ev_threshold": self.max_ev_threshold,
            "ev_deflator": self.ev_deflator,
            "blocked_ev_bands": self.blocked_ev_bands,
            "disabled_markets": self.disabled_markets,
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
    
    def get_stability_status(self) -> Dict:
        """Get current stability mode status."""
        return {
            "mode": "STABILITY_VERIFICATION",
            "version": self.version,
            "hard_ev_cap": f"{self.max_ev_threshold:.0%}",
            "ev_deflator": f"{self.ev_deflator:.0%}",
            "blocked_bands": [f"{l:.0%}-{h:.0%}" for l, h in self.blocked_ev_bands],
            "sgp_status": "DISABLED" if not self.enable_sgp else "ENABLED",
            "corners_cap": f"{self.stability_mode.market_exposure_caps.get('CORNERS', 0.30):.0%}",
            "clv_tracking": "ENABLED" if self.enable_clv_tracking else "DISABLED",
            "staking": "FLAT 1 UNIT" if self.unit_based_tracking else "VARIABLE",
            "objective": "Verify edge via CLV, not P/L",
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


def is_stability_mode_active() -> bool:
    """Check if stability verification mode is active."""
    return LIVE_LEARNING_CONFIG.stability_mode.enabled


def apply_ev_controls(raw_ev: float) -> tuple:
    """
    Apply all EV controls from stability mode.
    Returns: (adjusted_ev, is_blocked, block_reason)
    """
    config = LIVE_LEARNING_CONFIG
    
    if config.is_ev_blocked(raw_ev):
        return (0, True, f"EV {raw_ev:.1%} in blocked band 50-100%")
    
    deflated = config.apply_ev_deflator(raw_ev)
    
    if deflated > config.max_ev_threshold:
        deflated = config.max_ev_threshold
    
    return (deflated, False, None)


def check_market_allowed(market: str, current_exposure: Dict[str, float]) -> tuple:
    """
    Check if a market is allowed given current exposure.
    Returns: (is_allowed, reason)
    """
    config = LIVE_LEARNING_CONFIG
    
    if config.is_market_disabled(market):
        return (False, f"{market} is disabled in stability mode")
    
    market_upper = market.upper()
    cap = config.get_market_cap(market_upper)
    current = current_exposure.get(market_upper, 0)
    
    if current >= cap:
        return (False, f"{market} at cap ({current:.0%} >= {cap:.0%})")
    
    return (True, None)


if __name__ == "__main__":
    config = get_live_learning_config()
    print("=" * 60)
    print("LIVE LEARNING MODE - STABILITY & VERIFICATION")
    print("=" * 60)
    
    status = config.get_stability_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 60)
    print("EV CONTROL TESTS")
    print("=" * 60)
    
    test_evs = [0.05, 0.15, 0.30, 0.55, 0.80, 1.20]
    for ev in test_evs:
        adj, blocked, reason = apply_ev_controls(ev)
        if blocked:
            print(f"  Raw EV {ev:.0%} → BLOCKED ({reason})")
        else:
            print(f"  Raw EV {ev:.0%} → Adjusted {adj:.1%}")

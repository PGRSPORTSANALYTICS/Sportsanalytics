"""
Profile Boost Configuration
===========================
Controls how contextual factors influence EV and confidence adjustments.

All boost factors apply small adjustments (max +/- 25%) to base predictions.
Missing data always defaults to neutral (0 contribution).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProfileBoostConfig:
    """Master configuration for profile boost engine."""
    
    alpha_ev: float = 0.15
    beta_confidence: float = 0.12
    
    min_boost_score: float = -1.0
    max_boost_score: float = 1.0
    
    feature_weights: Dict[str, float] = field(default_factory=lambda: {
        "tempo_index": 0.20,
        "wing_play_index": 0.12,
        "referee_profile": 0.18,
        "rivalry_index": 0.10,
        "formation_aggression": 0.10,
        "weather_factor": 0.08,
        "pressure_index": 0.12,
        "recent_form_momentum": 0.10,
    })
    
    tempo_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "high_tempo_min": 1.15,
        "low_tempo_max": 0.85,
        "boost_high_tempo": 0.25,
        "penalty_low_tempo": -0.15,
    })
    
    referee_profile_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "strict_ref_cards_pg": 5.0,
        "lenient_ref_cards_pg": 2.5,
        "high_corner_ref": 11.0,
        "low_corner_ref": 8.5,
        "strict_boost": 0.30,
        "lenient_penalty": -0.20,
    })
    
    rivalry_boost: Dict[str, float] = field(default_factory=lambda: {
        "derby_flag_boost": 0.35,
        "historic_rivalry_boost": 0.25,
        "same_city_boost": 0.30,
        "neutral_rivalry": 0.0,
    })
    
    weather_modifiers: Dict[str, float] = field(default_factory=lambda: {
        "heavy_rain_factor": 0.20,
        "strong_wind_threshold": 35,
        "wind_boost": 0.15,
        "extreme_wind_threshold": 50,
        "extreme_wind_boost": 0.25,
        "snow_factor": 0.18,
        "clear_neutral": 0.0,
    })
    
    market_specific_weights: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "FT_OVER_2_5": {"tempo_index": 0.30, "wing_play_index": 0.15, "referee_profile": 0.10, "pressure_index": 0.25},
        "FT_UNDER_2_5": {"tempo_index": -0.20, "wing_play_index": -0.10, "pressure_index": -0.15},
        "BTTS_YES": {"tempo_index": 0.25, "pressure_index": 0.20, "wing_play_index": 0.15},
        "BTTS_NO": {"tempo_index": -0.15, "pressure_index": -0.10},
        "CORNERS_MATCH": {"wing_play_index": 0.35, "referee_profile": 0.25, "tempo_index": 0.20, "weather_factor": 0.15},
        "CORNERS_TEAM": {"wing_play_index": 0.35, "tempo_index": 0.25, "pressure_index": 0.20},
        "CORNERS_HANDICAP": {"wing_play_index": 0.30, "referee_profile": 0.20, "tempo_index": 0.25},
        "CARDS_MATCH": {"referee_profile": 0.40, "rivalry_index": 0.25, "formation_aggression": 0.20, "tempo_index": 0.10},
        "CARDS_TEAM": {"referee_profile": 0.35, "formation_aggression": 0.25, "rivalry_index": 0.20},
        "SHOTS_TEAM": {"tempo_index": 0.30, "pressure_index": 0.30, "wing_play_index": 0.20},
        "HOME_WIN": {"recent_form_momentum": 0.25, "pressure_index": 0.20, "rivalry_index": 0.15},
        "AWAY_WIN": {"recent_form_momentum": 0.30, "pressure_index": 0.15, "rivalry_index": 0.15},
        "DRAW": {"tempo_index": -0.10, "rivalry_index": 0.20},
    })
    
    log_top_n_factors: int = 3
    enable_logging: bool = True


PROFILE_BOOST_CONFIG = ProfileBoostConfig()


def get_profile_boost_config() -> ProfileBoostConfig:
    """Get the active profile boost configuration."""
    return PROFILE_BOOST_CONFIG


def update_config(**kwargs) -> ProfileBoostConfig:
    """Update configuration parameters dynamically."""
    global PROFILE_BOOST_CONFIG
    for key, value in kwargs.items():
        if hasattr(PROFILE_BOOST_CONFIG, key):
            setattr(PROFILE_BOOST_CONFIG, key, value)
    return PROFILE_BOOST_CONFIG

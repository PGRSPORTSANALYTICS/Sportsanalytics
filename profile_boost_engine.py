"""
Profile Boost Engine v1.0
=========================
Adjusts base EV and confidence based on contextual factors like:
- Pace/Tempo Index
- Wing Play Index  
- Referee Profile
- Rivalry/Derby flags
- Formation Aggression
- Weather conditions
- Pressure Index
- Recent Form Momentum

All missing data gracefully degrades to neutral (0 contribution).
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from profile_boost_config import (
    PROFILE_BOOST_CONFIG,
    ProfileBoostConfig,
    get_profile_boost_config,
)

logger = logging.getLogger(__name__)


@dataclass
class BoostResult:
    """Result of profile boost calculation."""
    raw_ev: float
    raw_confidence: float
    boosted_ev: float
    boosted_confidence: float
    boost_score: float
    contributing_factors: List[Tuple[str, float]]
    market_type: str
    details: Dict[str, Any] = field(default_factory=dict)


class ProfileBoostEngine:
    """
    Syndicate-style Profile Boost Engine.
    
    Applies contextual adjustments to base EV and confidence values
    based on match-specific factors like tempo, referee profile,
    rivalry intensity, weather, and more.
    """
    
    def __init__(self, config: Optional[ProfileBoostConfig] = None):
        self.config = config or get_profile_boost_config()
        logger.info("🚀 Profile Boost Engine v1.0 initialized")
        logger.info(f"   Alpha (EV): {self.config.alpha_ev}, Beta (Conf): {self.config.beta_confidence}")
    
    def calculate_boost(
        self,
        base_ev: float,
        base_confidence: float,
        market_type: str,
        context: Dict[str, Any],
    ) -> BoostResult:
        """
        Calculate boosted EV and confidence based on contextual factors.
        
        Args:
            base_ev: Original expected value (e.g., 0.05 for 5%)
            base_confidence: Original confidence (e.g., 0.58 for 58%)
            market_type: Type of market (e.g., 'FT_OVER_2_5', 'CARDS_MATCH')
            context: Dict with contextual features like tempo_index, referee_stats, etc.
        
        Returns:
            BoostResult with boosted values and explanation
        """
        factor_scores = self._calculate_factor_scores(context, market_type)
        
        boost_score = self._aggregate_boost_score(factor_scores, market_type)
        
        boost_score = max(
            self.config.min_boost_score,
            min(self.config.max_boost_score, boost_score)
        )
        
        boosted_ev = base_ev * (1 + self.config.alpha_ev * boost_score)
        boosted_confidence = base_confidence * (1 + self.config.beta_confidence * boost_score)
        
        boosted_confidence = min(0.99, max(0.01, boosted_confidence))
        
        contributing_factors = sorted(
            factor_scores.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:self.config.log_top_n_factors]
        
        result = BoostResult(
            raw_ev=base_ev,
            raw_confidence=base_confidence,
            boosted_ev=boosted_ev,
            boosted_confidence=boosted_confidence,
            boost_score=boost_score,
            contributing_factors=contributing_factors,
            market_type=market_type,
            details={
                "all_factors": factor_scores,
                "alpha_ev": self.config.alpha_ev,
                "beta_confidence": self.config.beta_confidence,
            }
        )
        
        if self.config.enable_logging and abs(boost_score) > 0.05:
            self._log_boost(result)
        
        return result
    
    def _calculate_factor_scores(
        self,
        context: Dict[str, Any],
        market_type: str
    ) -> Dict[str, float]:
        """Calculate individual factor scores from context."""
        scores = {}
        
        scores["tempo_index"] = self._score_tempo(context)
        scores["wing_play_index"] = self._score_wing_play(context)
        scores["referee_profile"] = self._score_referee(context, market_type)
        scores["rivalry_index"] = self._score_rivalry(context)
        scores["formation_aggression"] = self._score_formation_aggression(context)
        scores["weather_factor"] = self._score_weather(context)
        scores["pressure_index"] = self._score_pressure(context)
        scores["recent_form_momentum"] = self._score_form_momentum(context)
        
        return scores
    
    def _score_tempo(self, context: Dict[str, Any]) -> float:
        """Score tempo/pace factor."""
        tempo = context.get("tempo_index", 1.0)
        if tempo is None:
            return 0.0
        
        thresholds = self.config.tempo_thresholds
        
        if tempo >= thresholds["high_tempo_min"]:
            return thresholds["boost_high_tempo"] * min(1.5, tempo / thresholds["high_tempo_min"])
        elif tempo <= thresholds["low_tempo_max"]:
            return thresholds["penalty_low_tempo"] * (thresholds["low_tempo_max"] / max(0.5, tempo))
        
        return (tempo - 1.0) * 0.5
    
    def _score_wing_play(self, context: Dict[str, Any]) -> float:
        """Score wing play intensity."""
        wing_play = context.get("wing_play_index", 1.0)
        if wing_play is None:
            return 0.0
        
        return (wing_play - 1.0) * 0.3
    
    def _score_referee(self, context: Dict[str, Any], market_type: str) -> float:
        """Score referee profile based on market type."""
        ref_stats = context.get("referee_stats", {})
        if not ref_stats:
            return 0.0
        
        thresholds = self.config.referee_profile_thresholds
        
        if "CARDS" in market_type:
            cards_pg = ref_stats.get("cards_per_match", 3.5)
            if cards_pg >= thresholds["strict_ref_cards_pg"]:
                return thresholds["strict_boost"]
            elif cards_pg <= thresholds["lenient_ref_cards_pg"]:
                return thresholds["lenient_penalty"]
            return (cards_pg - 3.5) / 3.5 * 0.2
        
        elif "CORNERS" in market_type:
            corners_pg = ref_stats.get("corners_per_match", 10.0)
            if corners_pg >= thresholds["high_corner_ref"]:
                return 0.25
            elif corners_pg <= thresholds["low_corner_ref"]:
                return -0.15
            return (corners_pg - 10.0) / 10.0 * 0.15
        
        return 0.0
    
    def _score_rivalry(self, context: Dict[str, Any]) -> float:
        """Score rivalry intensity."""
        rivalry_boost = self.config.rivalry_boost
        
        if context.get("is_derby", False):
            return rivalry_boost["derby_flag_boost"]
        if context.get("is_same_city", False):
            return rivalry_boost["same_city_boost"]
        if context.get("historic_rivalry", False):
            return rivalry_boost["historic_rivalry_boost"]
        
        rivalry_index = context.get("rivalry_index", 1.0)
        if rivalry_index and rivalry_index > 1.0:
            return min(0.3, (rivalry_index - 1.0) * 0.25)
        
        return rivalry_boost["neutral_rivalry"]
    
    def _score_formation_aggression(self, context: Dict[str, Any]) -> float:
        """Score formation aggression factor."""
        aggression = context.get("formation_aggression", 1.0)
        if aggression is None:
            return 0.0
        
        return (aggression - 1.0) * 0.25
    
    def _score_weather(self, context: Dict[str, Any]) -> float:
        """Score weather conditions."""
        weather = context.get("weather", {})
        if not weather:
            return 0.0
        
        modifiers = self.config.weather_modifiers
        score = 0.0
        
        if weather.get("is_rain", False):
            score += modifiers["heavy_rain_factor"]
        if weather.get("is_snow", False):
            score += modifiers["snow_factor"]
        
        wind_speed = weather.get("wind_speed", 0)
        if wind_speed >= modifiers["extreme_wind_threshold"]:
            score += modifiers["extreme_wind_boost"]
        elif wind_speed >= modifiers["strong_wind_threshold"]:
            score += modifiers["wind_boost"]
        
        return score
    
    def _score_pressure(self, context: Dict[str, Any]) -> float:
        """Score pressure/pressing intensity."""
        pressure = context.get("pressure_index", 1.0)
        if pressure is None:
            return 0.0
        
        return (pressure - 1.0) * 0.3
    
    def _score_form_momentum(self, context: Dict[str, Any]) -> float:
        """Score recent form momentum."""
        momentum = context.get("form_momentum", 0.0)
        if momentum is None:
            return 0.0
        
        return momentum * 0.2
    
    def _aggregate_boost_score(
        self,
        factor_scores: Dict[str, float],
        market_type: str
    ) -> float:
        """Aggregate factor scores using market-specific weights."""
        market_weights = self.config.market_specific_weights.get(
            market_type,
            self.config.feature_weights
        )
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for factor, score in factor_scores.items():
            weight = market_weights.get(factor, self.config.feature_weights.get(factor, 0.1))
            weighted_sum += score * weight
            total_weight += weight
        
        if total_weight > 0:
            return weighted_sum / total_weight
        return 0.0
    
    def _log_boost(self, result: BoostResult):
        """Log significant boosts."""
        direction = "+" if result.boost_score > 0 else ""
        top_factors = ", ".join([f"{f[0]}={f[1]:.2f}" for f in result.contributing_factors])
        
        logger.info(
            f"🔥 PROFILE BOOST [{result.market_type}]: "
            f"EV {result.raw_ev*100:.1f}%→{result.boosted_ev*100:.1f}% | "
            f"Conf {result.raw_confidence*100:.0f}%→{result.boosted_confidence*100:.0f}% | "
            f"Boost: {direction}{result.boost_score:.2f} | "
            f"Factors: {top_factors}"
        )


def apply_profile_boost(
    base_ev: float,
    base_confidence: float,
    market_type: str,
    context: Dict[str, Any],
    engine: Optional[ProfileBoostEngine] = None
) -> BoostResult:
    """
    Convenience function to apply profile boost.
    
    Args:
        base_ev: Original expected value
        base_confidence: Original confidence
        market_type: Type of market
        context: Contextual features dict
        engine: Optional pre-initialized engine
    
    Returns:
        BoostResult with boosted values
    """
    if engine is None:
        engine = ProfileBoostEngine()
    
    return engine.calculate_boost(base_ev, base_confidence, market_type, context)


def build_context_from_match(match_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build context dict from match data for profile boost.
    Extracts and normalizes contextual features from various data sources.
    """
    context = {}
    
    home_stats = match_data.get("home_stats", {})
    away_stats = match_data.get("away_stats", {})
    
    home_passes = home_stats.get("passes_per_minute", 8.0)
    away_passes = away_stats.get("passes_per_minute", 8.0)
    home_attacks = home_stats.get("attacks_per_90", 100)
    away_attacks = away_stats.get("attacks_per_90", 100)
    
    tempo_raw = ((home_passes + away_passes) / 16.0 + (home_attacks + away_attacks) / 200) / 2
    context["tempo_index"] = round(tempo_raw, 3)
    
    home_crosses = home_stats.get("crosses_per_90", 15)
    away_crosses = away_stats.get("crosses_per_90", 15)
    home_wide = home_stats.get("wide_zone_touches", 40)
    away_wide = away_stats.get("wide_zone_touches", 40)
    
    wing_raw = ((home_crosses + away_crosses) / 30.0 + (home_wide + away_wide) / 80) / 2
    context["wing_play_index"] = round(wing_raw, 3)
    
    ref_stats = match_data.get("referee_stats", {})
    if ref_stats:
        context["referee_stats"] = {
            "cards_per_match": ref_stats.get("cards_per_match", 3.5),
            "corners_per_match": ref_stats.get("corners_per_match", 10.0),
            "fouls_per_match": ref_stats.get("fouls_per_match", 25.0),
        }
    
    context["is_derby"] = match_data.get("is_derby", False)
    context["is_same_city"] = match_data.get("is_same_city", False)
    context["historic_rivalry"] = match_data.get("historic_rivalry", False)
    context["rivalry_index"] = match_data.get("rivalry_index", 1.0)
    
    home_aggression = home_stats.get("formation_aggression", 1.0)
    away_aggression = away_stats.get("formation_aggression", 1.0)
    context["formation_aggression"] = (home_aggression + away_aggression) / 2
    
    weather = match_data.get("weather", {})
    if weather:
        context["weather"] = {
            "is_rain": weather.get("is_rain", False),
            "is_snow": weather.get("is_snow", False),
            "wind_speed": weather.get("wind_speed", 0),
            "temperature": weather.get("temperature", 15),
        }
    
    home_ppda = home_stats.get("ppda", 10.0)
    away_ppda = away_stats.get("ppda", 10.0)
    avg_ppda = (home_ppda + away_ppda) / 2
    context["pressure_index"] = round(12.0 / max(6.0, avg_ppda), 3)
    
    home_form = home_stats.get("recent_form_score", 0)
    away_form = away_stats.get("recent_form_score", 0)
    context["form_momentum"] = (home_form + away_form) / 2
    
    return context


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    engine = ProfileBoostEngine()
    
    test_context = {
        "tempo_index": 1.25,
        "wing_play_index": 1.15,
        "referee_stats": {"cards_per_match": 5.5, "corners_per_match": 11.0},
        "is_derby": True,
        "formation_aggression": 1.2,
        "pressure_index": 1.3,
        "weather": {"is_rain": True, "wind_speed": 40},
        "form_momentum": 0.15,
    }
    
    result = engine.calculate_boost(
        base_ev=0.05,
        base_confidence=0.58,
        market_type="FT_OVER_2_5",
        context=test_context
    )
    
    print("\n" + "="*60)
    print("PROFILE BOOST ENGINE TEST")
    print("="*60)
    print(f"Market: {result.market_type}")
    print(f"Raw EV: {result.raw_ev*100:.1f}% → Boosted EV: {result.boosted_ev*100:.1f}%")
    print(f"Raw Conf: {result.raw_confidence*100:.0f}% → Boosted Conf: {result.boosted_confidence*100:.0f}%")
    print(f"Boost Score: {result.boost_score:+.3f}")
    print(f"Top Factors: {result.contributing_factors}")

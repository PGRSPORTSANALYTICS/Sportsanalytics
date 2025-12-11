"""
Corners Engine v2.0 - Syndicate-Style Advanced Corners Model
=============================================================
Uses advanced factors: Pace, Wing Play, Referee Bias, Weather, Corner Pressure Index
All factors degrade gracefully with sensible defaults when data is missing.

Markets:
- Match Total Corners: Over/Under 8.5, 9.5, 10.5, 11.5
- Team Corners: Home/Away Over X corners
- Corner Handicaps: Home/Away -1.5, -2.5, etc.

Daily Limits: 6 match corners, 4 team corners, 6 corner handicaps
"""

import logging
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

from bet_filter import BetCandidate
from multimarket_config import PRODUCT_CONFIGS, get_market_label, MarketType

logger = logging.getLogger(__name__)

MATCH_CORNERS_CONFIG = PRODUCT_CONFIGS["CORNERS_MATCH"]
TEAM_CORNERS_CONFIG = PRODUCT_CONFIGS["CORNERS_TEAM"]
HANDICAP_CORNERS_CONFIG = PRODUCT_CONFIGS.get("CORNERS_HANDICAP", MATCH_CORNERS_CONFIG)

MATCH_CORNER_LINES = [8.5, 9.5, 10.5, 11.5]
TEAM_CORNER_LINES = [3.5, 4.5, 5.5]
HANDICAP_LINES = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]

DEFAULT_HOME_CORNERS = 5.2
DEFAULT_AWAY_CORNERS = 4.8
DEFAULT_TOTAL_CORNERS = 10.0
DEFAULT_REFEREE_CORNERS = 10.0

LEAGUE_CORNER_AVGS = {
    "Premier League": 10.2,
    "La Liga": 9.8,
    "Serie A": 10.0,
    "Bundesliga": 10.5,
    "Ligue 1": 10.0,
    "Eredivisie": 10.8,
    "Primeira Liga": 10.2,
    "Championship": 10.4,
    "MLS": 9.8,
    "default": 10.0,
}

FACTOR_WEIGHTS = {
    "pace": 0.25,
    "wing_play": 0.20,
    "referee": 0.20,
    "weather": 0.15,
    "corner_pressure": 0.20,
}


@dataclass
class CornerFactors:
    pace_factor: float = 1.0
    wing_play_index: float = 1.0
    referee_bias: float = 1.0
    weather_factor: float = 1.0
    corner_pressure_home: float = 1.0
    corner_pressure_away: float = 1.0
    
    def get_combined_factor(self) -> float:
        weights = FACTOR_WEIGHTS
        combined = (
            (self.pace_factor ** weights["pace"]) *
            (self.wing_play_index ** weights["wing_play"]) *
            (self.referee_bias ** weights["referee"]) *
            (self.weather_factor ** weights["weather"]) *
            (((self.corner_pressure_home + self.corner_pressure_away) / 2) ** weights["corner_pressure"])
        )
        return max(0.70, min(1.40, combined))
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "pace_factor": round(self.pace_factor, 3),
            "wing_play_index": round(self.wing_play_index, 3),
            "referee_bias": round(self.referee_bias, 3),
            "weather_factor": round(self.weather_factor, 3),
            "corner_pressure_home": round(self.corner_pressure_home, 3),
            "corner_pressure_away": round(self.corner_pressure_away, 3),
            "combined_factor": round(self.get_combined_factor(), 3),
        }


class SyndicateCornersModel:
    
    def __init__(self, num_sims: int = 10000):
        self.num_sims = num_sims
        self.home_corner_avg = DEFAULT_HOME_CORNERS
        self.away_corner_avg = DEFAULT_AWAY_CORNERS
    
    def compute_pace_factor(
        self,
        home_stats: Dict,
        away_stats: Dict
    ) -> float:
        home_passes_pm = home_stats.get("passes_per_minute", 8.0)
        away_passes_pm = away_stats.get("passes_per_minute", 8.0)
        home_attacks = home_stats.get("attacks_per_90", 100)
        away_attacks = away_stats.get("attacks_per_90", 100)
        home_dangerous = home_stats.get("dangerous_attacks_per_90", 50)
        away_dangerous = away_stats.get("dangerous_attacks_per_90", 50)
        
        avg_passes = (home_passes_pm + away_passes_pm) / 2
        avg_attacks = (home_attacks + away_attacks) / 2
        avg_dangerous = (home_dangerous + away_dangerous) / 2
        
        passes_factor = min(1.15, max(0.85, avg_passes / 8.0))
        attacks_factor = min(1.15, max(0.85, avg_attacks / 100))
        danger_factor = min(1.15, max(0.85, avg_dangerous / 50))
        
        pace_score = (passes_factor * 0.3) + (attacks_factor * 0.35) + (danger_factor * 0.35)
        
        return round(pace_score, 3)
    
    def compute_wing_play_index(
        self,
        home_stats: Dict,
        away_stats: Dict
    ) -> float:
        home_crosses = home_stats.get("crosses_per_90", 15)
        away_crosses = away_stats.get("crosses_per_90", 15)
        home_wide_touches = home_stats.get("wide_zone_touches", 40)
        away_wide_touches = away_stats.get("wide_zone_touches", 40)
        home_flank_pct = home_stats.get("flank_attack_pct", 0.35)
        away_flank_pct = away_stats.get("flank_attack_pct", 0.35)
        
        avg_crosses = (home_crosses + away_crosses) / 2
        avg_wide = (home_wide_touches + away_wide_touches) / 2
        avg_flank = (home_flank_pct + away_flank_pct) / 2
        
        cross_factor = min(1.20, max(0.80, avg_crosses / 15))
        wide_factor = min(1.15, max(0.85, avg_wide / 40))
        flank_factor = min(1.15, max(0.85, avg_flank / 0.35))
        
        wing_index = (cross_factor * 0.45) + (wide_factor * 0.30) + (flank_factor * 0.25)
        
        return round(wing_index, 3)
    
    def compute_referee_corner_bias(
        self,
        referee_stats: Optional[Dict]
    ) -> float:
        if not referee_stats:
            return 1.0
        
        ref_corners = referee_stats.get("corners_per_match", DEFAULT_REFEREE_CORNERS)
        ref_fouls_near_box = referee_stats.get("fouls_near_box_per_match", 5)
        ref_stoppage_rate = referee_stats.get("stoppage_rate", 0.5)
        
        corners_factor = ref_corners / DEFAULT_REFEREE_CORNERS
        fouls_factor = ref_fouls_near_box / 5.0
        
        bias = (corners_factor * 0.7) + (fouls_factor * 0.3)
        
        return round(max(0.80, min(1.25, bias)), 3)
    
    def compute_weather_factor(
        self,
        weather: Optional[Dict]
    ) -> float:
        if not weather:
            return 1.0
        
        wind_speed = weather.get("wind_speed", 0)
        is_rain = weather.get("is_rain", False) or weather.get("rain_intensity", 0) > 0
        pitch_condition = weather.get("pitch_condition", "good")
        
        wind_factor = 1.0
        if wind_speed > 40:
            wind_factor = 1.12
        elif wind_speed > 25:
            wind_factor = 1.06
        elif wind_speed > 15:
            wind_factor = 1.02
        
        rain_factor = 1.05 if is_rain else 1.0
        
        pitch_factors = {
            "poor": 0.95,
            "wet": 1.03,
            "slippery": 1.05,
            "good": 1.0,
            "excellent": 1.0,
        }
        pitch_factor = pitch_factors.get(pitch_condition.lower(), 1.0)
        
        combined = wind_factor * rain_factor * pitch_factor
        
        return round(max(0.90, min(1.20, combined)), 3)
    
    def compute_corner_pressure_index(
        self,
        team_stats: Dict,
        is_home: bool = True,
        match_importance: float = 1.0
    ) -> float:
        xg_corners = team_stats.get("xg_from_corners", 0.3)
        comeback_rate = team_stats.get("comeback_frequency", 0.15)
        late_attack_intensity = team_stats.get("late_game_attack_intensity", 1.0)
        shots_when_trailing = team_stats.get("shots_when_trailing", 5)
        
        xg_factor = min(1.15, max(0.85, xg_corners / 0.3))
        comeback_factor = min(1.10, max(0.90, 1 + (comeback_rate - 0.15) * 2))
        late_factor = min(1.15, max(0.90, late_attack_intensity))
        trailing_factor = min(1.10, max(0.90, shots_when_trailing / 5))
        
        home_boost = 1.03 if is_home else 1.0
        
        cpi = (xg_factor * 0.3 + comeback_factor * 0.25 + 
               late_factor * 0.25 + trailing_factor * 0.20) * home_boost * match_importance
        
        return round(max(0.85, min(1.25, cpi)), 3)
    
    def compute_all_factors(
        self,
        home_stats: Dict,
        away_stats: Dict,
        referee_stats: Optional[Dict] = None,
        weather: Optional[Dict] = None,
        match_importance: float = 1.0
    ) -> CornerFactors:
        return CornerFactors(
            pace_factor=self.compute_pace_factor(home_stats, away_stats),
            wing_play_index=self.compute_wing_play_index(home_stats, away_stats),
            referee_bias=self.compute_referee_corner_bias(referee_stats),
            weather_factor=self.compute_weather_factor(weather),
            corner_pressure_home=self.compute_corner_pressure_index(home_stats, True, match_importance),
            corner_pressure_away=self.compute_corner_pressure_index(away_stats, False, match_importance),
        )
    
    def estimate_corners(
        self,
        home_xg: float = 1.5,
        away_xg: float = 1.2,
        home_form_corners: Optional[float] = None,
        away_form_corners: Optional[float] = None,
        league_avg_corners: float = DEFAULT_TOTAL_CORNERS,
        factors: Optional[CornerFactors] = None
    ) -> Tuple[float, float]:
        if home_form_corners and away_form_corners:
            home_exp = home_form_corners
            away_exp = away_form_corners
        else:
            xg_factor_home = 0.8 + (home_xg / 3.0)
            xg_factor_away = 0.8 + (away_xg / 3.0)
            
            home_exp = DEFAULT_HOME_CORNERS * xg_factor_home
            away_exp = DEFAULT_AWAY_CORNERS * xg_factor_away
            
            total_raw = home_exp + away_exp
            scale = league_avg_corners / total_raw if total_raw > 0 else 1.0
            home_exp *= scale
            away_exp *= scale
        
        if factors:
            combined = factors.get_combined_factor()
            home_cpi_adj = factors.corner_pressure_home / 1.0
            away_cpi_adj = factors.corner_pressure_away / 1.0
            
            home_exp *= combined * home_cpi_adj
            away_exp *= combined * away_cpi_adj
        
        return home_exp, away_exp
    
    def simulate_corners(
        self,
        home_lambda: float,
        away_lambda: float
    ) -> Dict[str, Any]:
        home_corners = np.random.poisson(lam=home_lambda, size=self.num_sims)
        away_corners = np.random.poisson(lam=away_lambda, size=self.num_sims)
        total_corners = home_corners + away_corners
        corner_diff = home_corners - away_corners
        
        results = {
            "home_corners_raw": home_corners,
            "away_corners_raw": away_corners,
            "total_corners_raw": total_corners,
            "corner_diff_raw": corner_diff,
        }
        
        for line in MATCH_CORNER_LINES:
            over_key = f"CORNERS_OVER_{str(line).replace('.', '_')}"
            under_key = f"CORNERS_UNDER_{str(line).replace('.', '_')}"
            results[over_key] = float((total_corners > line).mean())
            results[under_key] = float((total_corners < line).mean())
        
        for line in TEAM_CORNER_LINES:
            home_over_key = f"HOME_CORNERS_OVER_{str(line).replace('.', '_')}"
            away_over_key = f"AWAY_CORNERS_OVER_{str(line).replace('.', '_')}"
            results[home_over_key] = float((home_corners > line).mean())
            results[away_over_key] = float((away_corners > line).mean())
        
        for line in HANDICAP_LINES:
            if line >= 0:
                line_str = f"+{str(abs(line)).replace('.', '_')}"
            else:
                line_str = f"-{str(abs(line)).replace('.', '_')}"
            
            home_hc_key = f"CORNERS_HC_HOME_{line_str}"
            away_hc_key = f"CORNERS_HC_AWAY_{line_str}"
            
            results[home_hc_key] = float(((corner_diff + line) > 0).mean())
            results[away_hc_key] = float(((-corner_diff + line) > 0).mean())
        
        results["home_most_corners"] = float((home_corners > away_corners).mean())
        results["away_most_corners"] = float((away_corners > home_corners).mean())
        results["avg_total_corners"] = float(total_corners.mean())
        results["avg_home_corners"] = float(home_corners.mean())
        results["avg_away_corners"] = float(away_corners.mean())
        results["std_total_corners"] = float(total_corners.std())
        
        return results


class CornersEngine:
    
    def __init__(self, num_sims: int = 10000):
        self.match_config = MATCH_CORNERS_CONFIG
        self.team_config = TEAM_CORNERS_CONFIG
        self.handicap_config = HANDICAP_CORNERS_CONFIG
        self.model = SyndicateCornersModel(num_sims)
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"🔢 Syndicate Corners Engine v2.0 initialized (match: {self.match_config.max_per_day}/day)")
    
    def classify_trust_tier(
        self,
        ev: float,
        confidence: float,
        config,
        sim_approved: bool = True
    ) -> str:
        if sim_approved and ev >= config.l1_min_ev and confidence >= config.l1_min_confidence:
            return "L1_HIGH_TRUST"
        elif sim_approved and ev >= config.l2_min_ev and confidence >= config.l2_min_confidence:
            return "L2_MEDIUM_TRUST"
        elif ev >= config.l3_min_ev and confidence >= config.l3_min_confidence:
            return "L3_SOFT_VALUE"
        return "REJECTED"
    
    def find_match_corner_value(
        self,
        match: str,
        home_team: str,
        away_team: str,
        league: str,
        corner_sim: Dict,
        odds_dict: Dict[str, float],
        match_date: Optional[str] = None,
        factors: Optional[CornerFactors] = None
    ) -> List[BetCandidate]:
        candidates = []
        
        for line in MATCH_CORNER_LINES:
            over_key = f"CORNERS_OVER_{str(line).replace('.', '_')}"
            under_key = f"CORNERS_UNDER_{str(line).replace('.', '_')}"
            
            for market_key in [over_key, under_key]:
                p_model = corner_sim.get(market_key, 0.0)
                odds = odds_dict.get(market_key)
                
                if odds is None:
                    continue
                
                if not (self.match_config.min_odds <= odds <= self.match_config.max_odds):
                    continue
                
                if p_model < self.match_config.min_confidence:
                    continue
                
                ev = (p_model * odds) - 1.0
                
                if ev < self.match_config.min_ev:
                    continue
                
                sim_approved = ev >= 0.03
                tier = self.classify_trust_tier(ev, p_model, self.match_config, sim_approved)
                
                if tier == "REJECTED":
                    continue
                
                selection_text = get_market_label(market_key)
                
                metadata = {
                    "avg_corners": corner_sim.get("avg_total_corners", 10.0),
                    "std_corners": corner_sim.get("std_total_corners", 3.0),
                }
                if factors:
                    metadata["factors"] = factors.to_dict()
                
                candidate = BetCandidate(
                    match=match,
                    market=market_key,
                    selection=selection_text,
                    odds=odds,
                    ev_sim=ev,
                    ev_model=ev,
                    confidence=p_model,
                    disagreement=0.0,
                    approved=sim_approved,
                    tier=tier,
                    market_type="CORNERS",
                    product="CORNERS_MATCH",
                    league=league,
                    home_team=home_team,
                    away_team=away_team,
                    match_date=match_date or self.today,
                    metadata=metadata
                )
                candidates.append(candidate)
                
                logger.debug(
                    f"🔢 Corner Match: {home_team} vs {away_team} | {selection_text} @ {odds} | "
                    f"p={p_model:.1%} EV={ev:.1%} | {tier}"
                )
        
        return candidates
    
    def find_team_corner_value(
        self,
        match: str,
        home_team: str,
        away_team: str,
        league: str,
        corner_sim: Dict,
        odds_dict: Dict[str, float],
        match_date: Optional[str] = None,
        factors: Optional[CornerFactors] = None
    ) -> List[BetCandidate]:
        candidates = []
        
        for line in TEAM_CORNER_LINES:
            home_key = f"HOME_CORNERS_OVER_{str(line).replace('.', '_')}"
            away_key = f"AWAY_CORNERS_OVER_{str(line).replace('.', '_')}"
            
            for market_key in [home_key, away_key]:
                p_model = corner_sim.get(market_key, 0.0)
                odds = odds_dict.get(market_key)
                
                if odds is None:
                    continue
                
                if not (self.team_config.min_odds <= odds <= self.team_config.max_odds):
                    continue
                
                if p_model < self.team_config.min_confidence:
                    continue
                
                ev = (p_model * odds) - 1.0
                
                if ev < self.team_config.min_ev:
                    continue
                
                sim_approved = ev >= 0.03
                tier = self.classify_trust_tier(ev, p_model, self.team_config, sim_approved)
                
                if tier == "REJECTED":
                    continue
                
                if "HOME" in market_key:
                    selection_text = f"{home_team} Over {line} Corners"
                else:
                    selection_text = f"{away_team} Over {line} Corners"
                
                metadata = {
                    "avg_home": corner_sim.get("avg_home_corners", 5.0),
                    "avg_away": corner_sim.get("avg_away_corners", 5.0),
                }
                if factors:
                    metadata["factors"] = factors.to_dict()
                
                candidate = BetCandidate(
                    match=match,
                    market=market_key,
                    selection=selection_text,
                    odds=odds,
                    ev_sim=ev,
                    ev_model=ev,
                    confidence=p_model,
                    disagreement=0.0,
                    approved=sim_approved,
                    tier=tier,
                    market_type="CORNERS",
                    product="CORNERS_TEAM",
                    league=league,
                    home_team=home_team,
                    away_team=away_team,
                    match_date=match_date or self.today,
                    metadata=metadata
                )
                candidates.append(candidate)
        
        return candidates
    
    def find_corner_handicap_value(
        self,
        match: str,
        home_team: str,
        away_team: str,
        league: str,
        corner_sim: Dict,
        odds_dict: Dict[str, float],
        match_date: Optional[str] = None,
        factors: Optional[CornerFactors] = None
    ) -> List[BetCandidate]:
        candidates = []
        
        for line in HANDICAP_LINES:
            if line >= 0:
                line_str = f"+{str(abs(line)).replace('.', '_')}"
            else:
                line_str = f"-{str(abs(line)).replace('.', '_')}"
            
            home_hc_key = f"CORNERS_HC_HOME_{line_str}"
            away_hc_key = f"CORNERS_HC_AWAY_{line_str}"
            
            for market_key, is_home in [
                (home_hc_key, True),
                (away_hc_key, False)
            ]:
                p_model = corner_sim.get(market_key, 0.0)
                odds = odds_dict.get(market_key)
                
                if odds is None:
                    continue
                
                if not (self.handicap_config.min_odds <= odds <= self.handicap_config.max_odds):
                    continue
                
                if p_model < self.handicap_config.min_confidence:
                    continue
                
                ev = (p_model * odds) - 1.0
                
                if ev < self.handicap_config.min_ev:
                    continue
                
                sim_approved = ev >= 0.03
                tier = self.classify_trust_tier(ev, p_model, self.handicap_config, sim_approved)
                
                if tier == "REJECTED":
                    continue
                
                team = home_team if is_home else away_team
                selection_text = f"{team} Corners {'+' if line >= 0 else ''}{line}"
                
                metadata = {
                    "handicap_line": line,
                    "avg_diff": corner_sim.get("avg_home_corners", 5) - corner_sim.get("avg_away_corners", 5),
                }
                if factors:
                    metadata["factors"] = factors.to_dict()
                
                candidate = BetCandidate(
                    match=match,
                    market=market_key,
                    selection=selection_text,
                    odds=odds,
                    ev_sim=ev,
                    ev_model=ev,
                    confidence=p_model,
                    disagreement=0.0,
                    approved=sim_approved,
                    tier=tier,
                    market_type="CORNERS_HANDICAP",
                    product="CORNERS_HANDICAP",
                    league=league,
                    home_team=home_team,
                    away_team=away_team,
                    match_date=match_date or self.today,
                    metadata=metadata
                )
                candidates.append(candidate)
        
        return candidates
    
    def find_all_corner_value(
        self,
        match: str,
        home_team: str,
        away_team: str,
        league: str,
        home_xg: float,
        away_xg: float,
        odds_dict: Dict[str, float],
        match_date: Optional[str] = None,
        home_form_corners: Optional[float] = None,
        away_form_corners: Optional[float] = None,
        home_stats: Optional[Dict] = None,
        away_stats: Optional[Dict] = None,
        referee_stats: Optional[Dict] = None,
        weather: Optional[Dict] = None,
        match_importance: float = 1.0
    ) -> Tuple[List[BetCandidate], List[BetCandidate], List[BetCandidate]]:
        home_stats = home_stats or {}
        away_stats = away_stats or {}
        
        factors = self.model.compute_all_factors(
            home_stats, away_stats,
            referee_stats, weather,
            match_importance
        )
        
        league_avg = LEAGUE_CORNER_AVGS.get(league, LEAGUE_CORNER_AVGS["default"])
        
        home_exp, away_exp = self.model.estimate_corners(
            home_xg=home_xg,
            away_xg=away_xg,
            home_form_corners=home_form_corners,
            away_form_corners=away_form_corners,
            league_avg_corners=league_avg,
            factors=factors
        )
        
        corner_sim = self.model.simulate_corners(home_exp, away_exp)
        
        match_bets = self.find_match_corner_value(
            match, home_team, away_team, league, corner_sim, odds_dict, match_date, factors
        )
        
        team_bets = self.find_team_corner_value(
            match, home_team, away_team, league, corner_sim, odds_dict, match_date, factors
        )
        
        handicap_bets = self.find_corner_handicap_value(
            match, home_team, away_team, league, corner_sim, odds_dict, match_date, factors
        )
        
        logger.debug(
            f"🔢 {home_team} vs {away_team} | Factors: pace={factors.pace_factor:.2f} "
            f"wing={factors.wing_play_index:.2f} ref={factors.referee_bias:.2f} "
            f"weather={factors.weather_factor:.2f} | Exp corners: {home_exp:.1f} + {away_exp:.1f}"
        )
        
        return match_bets, team_bets, handicap_bets
    
    def apply_daily_filter(
        self,
        match_candidates: List[BetCandidate],
        team_candidates: List[BetCandidate],
        handicap_candidates: Optional[List[BetCandidate]] = None
    ) -> Tuple[List[BetCandidate], List[BetCandidate], List[BetCandidate]]:
        def filter_by_tier(candidates, max_count):
            l1 = sorted([c for c in candidates if c.tier == "L1_HIGH_TRUST"], key=lambda x: -x.ev_sim)
            l2 = sorted([c for c in candidates if c.tier == "L2_MEDIUM_TRUST"], key=lambda x: -x.ev_sim)
            l3 = sorted([c for c in candidates if c.tier == "L3_SOFT_VALUE"], key=lambda x: -x.ev_sim)
            
            selected = l1[:max(2, max_count // 2)]
            remaining = max_count - len(selected)
            selected.extend(l2[:remaining])
            remaining = max_count - len(selected)
            selected.extend(l3[:remaining])
            
            return selected
        
        match_selected = filter_by_tier(match_candidates, self.match_config.max_per_day)
        team_selected = filter_by_tier(team_candidates, self.team_config.max_per_day)
        
        handicap_selected = []
        if handicap_candidates:
            handicap_selected = filter_by_tier(handicap_candidates, self.handicap_config.max_per_day)
        
        return match_selected, team_selected, handicap_selected
    
    def get_summary(
        self,
        match_bets: List[BetCandidate],
        team_bets: List[BetCandidate],
        handicap_bets: Optional[List[BetCandidate]] = None
    ) -> Dict:
        handicap_bets = handicap_bets or []
        all_bets = match_bets + team_bets + handicap_bets
        tier_counts = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0}
        
        for b in all_bets:
            if b.tier in tier_counts:
                tier_counts[b.tier] += 1
        
        avg_ev = sum(b.ev_sim for b in all_bets) / len(all_bets) if all_bets else 0
        
        return {
            "product": "CORNERS",
            "total": len(all_bets),
            "match_corners": len(match_bets),
            "team_corners": len(team_bets),
            "handicap_corners": len(handicap_bets),
            "by_tier": tier_counts,
            "avg_ev": round(avg_ev, 4),
            "max_match_per_day": self.match_config.max_per_day,
            "max_team_per_day": self.team_config.max_per_day,
            "max_handicap_per_day": self.handicap_config.max_per_day,
        }


def run_corners_cycle(
    fixtures: List[Dict],
    odds_data: Dict,
    team_stats: Optional[Dict] = None,
    referee_data: Optional[Dict] = None,
    weather_data: Optional[Dict] = None
) -> Tuple[List[BetCandidate], List[BetCandidate], List[BetCandidate]]:
    engine = CornersEngine()
    all_match = []
    all_team = []
    all_handicap = []
    
    team_stats = team_stats or {}
    referee_data = referee_data or {}
    weather_data = weather_data or {}
    
    for fixture in fixtures:
        fixture_id = fixture.get("fixture_id", "")
        home_team = fixture.get("home_team", "Home")
        away_team = fixture.get("away_team", "Away")
        league = fixture.get("league", "Unknown")
        match_date = fixture.get("match_date", engine.today)
        
        home_xg = fixture.get("home_xg", 1.5)
        away_xg = fixture.get("away_xg", 1.2)
        
        odds_snapshot = odds_data.get(fixture_id, {})
        if not odds_snapshot:
            continue
        
        home_stats = team_stats.get(home_team, {})
        away_stats = team_stats.get(away_team, {})
        referee_stats = referee_data.get(fixture.get("referee_id"), {})
        weather = weather_data.get(fixture_id, {})
        
        match_bets, team_bets, hc_bets = engine.find_all_corner_value(
            match=f"{home_team} vs {away_team}",
            home_team=home_team,
            away_team=away_team,
            league=league,
            home_xg=home_xg,
            away_xg=away_xg,
            odds_dict=odds_snapshot,
            match_date=match_date,
            home_stats=home_stats,
            away_stats=away_stats,
            referee_stats=referee_stats,
            weather=weather
        )
        
        all_match.extend(match_bets)
        all_team.extend(team_bets)
        all_handicap.extend(hc_bets)
    
    match_sel, team_sel, hc_sel = engine.apply_daily_filter(all_match, all_team, all_handicap)
    
    logger.info(
        f"🔢 CORNERS ENGINE: {len(match_sel)} match + {len(team_sel)} team + {len(hc_sel)} handicap = "
        f"{len(match_sel) + len(team_sel) + len(hc_sel)} total picks"
    )
    
    return match_sel, team_sel, hc_sel


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    engine = CornersEngine()
    
    mock_odds = {
        "CORNERS_OVER_8_5": 1.85,
        "CORNERS_UNDER_8_5": 1.95,
        "CORNERS_OVER_9_5": 2.10,
        "CORNERS_UNDER_9_5": 1.75,
        "CORNERS_OVER_10_5": 2.50,
        "CORNERS_UNDER_10_5": 1.55,
        "CORNERS_OVER_11_5": 3.00,
        "HOME_CORNERS_OVER_4_5": 1.90,
        "AWAY_CORNERS_OVER_4_5": 2.05,
        "HOME_CORNERS_OVER_5_5": 2.40,
        "CORNERS_HC_HOME_-1_5": 1.95,
        "CORNERS_HC_AWAY_+1_5": 1.85,
    }
    
    home_stats = {
        "passes_per_minute": 9.5,
        "attacks_per_90": 120,
        "dangerous_attacks_per_90": 60,
        "crosses_per_90": 18,
        "wide_zone_touches": 50,
        "flank_attack_pct": 0.40,
        "xg_from_corners": 0.35,
        "comeback_frequency": 0.18,
    }
    
    away_stats = {
        "passes_per_minute": 7.5,
        "attacks_per_90": 95,
        "dangerous_attacks_per_90": 45,
        "crosses_per_90": 14,
        "wide_zone_touches": 35,
        "flank_attack_pct": 0.32,
    }
    
    referee_stats = {
        "corners_per_match": 11.2,
        "fouls_near_box_per_match": 6,
    }
    
    weather = {
        "wind_speed": 20,
        "is_rain": False,
        "pitch_condition": "good",
    }
    
    match_bets, team_bets, hc_bets = engine.find_all_corner_value(
        match="Liverpool vs Chelsea",
        home_team="Liverpool",
        away_team="Chelsea",
        league="Premier League",
        home_xg=1.8,
        away_xg=1.2,
        odds_dict=mock_odds,
        home_stats=home_stats,
        away_stats=away_stats,
        referee_stats=referee_stats,
        weather=weather
    )
    
    print("\n" + "=" * 60)
    print("SYNDICATE CORNERS ENGINE v2.0 TEST")
    print("=" * 60)
    
    print("\nMatch Corner Bets:")
    for c in match_bets:
        print(f"  [{c.tier}] {c.selection} @ {c.odds} | EV: {c.ev_sim:.1%} | p={c.confidence:.1%}")
    
    print("\nTeam Corner Bets:")
    for c in team_bets:
        print(f"  [{c.tier}] {c.selection} @ {c.odds} | EV: {c.ev_sim:.1%}")
    
    print("\nCorner Handicap Bets:")
    for c in hc_bets:
        print(f"  [{c.tier}] {c.selection} @ {c.odds} | EV: {c.ev_sim:.1%}")
    
    print(f"\n{engine.get_summary(match_bets, team_bets, hc_bets)}")

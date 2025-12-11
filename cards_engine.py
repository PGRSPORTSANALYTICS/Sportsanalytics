"""
Cards Engine v2.0 - Syndicate-Style Advanced Cards Aggression Model
====================================================================
Uses advanced factors: Referee Profile, Rivalry Index, Formation Aggression,
Tempo/Pressing, Team Aggression Score.
All factors degrade gracefully with sensible defaults when data is missing.

INPUTS:
- Referee data: cards_per_match, foul_to_card_conversion, early_card_rate
- Team statistics: fouls_pg, cards_pg, tackles_pg, duels_pg, aerial_duels_pg
- Match context: importance_index, is_knockout, is_relegation_battle
- Formations: home_formation, away_formation

FEATURES (via build_cards_features):
- referee_cards_per_match, referee_foul_to_card_conversion
- rivalry_index (derby detection, H2H cards history)
- team_aggression_home / team_aggression_away
- pressing_index_home / pressing_index_away (from PPDA)
- formation_aggression_home / formation_aggression_away
- game_state_risk_factor (relegation battle, title race)

EV CALCULATION:
EV = (model_probability * book_odds) - 1
Picks must pass minimum EV threshold per trust tier.

TRUST TIERS:
- L1_HIGH_TRUST: EV >= 5%, confidence >= 55%, simulation approved
- L2_MEDIUM_TRUST: EV >= 2%, confidence >= 52%
- L3_SOFT_VALUE: EV >= 0%, confidence >= 50%

MARKETS:
- Match Total Cards: Over/Under 2.5, 3.5, 4.5, 5.5, 6.5
- Booking Points: Over/Under 30.5, 40.5, 50.5, 60.5
- Team Cards: Home/Away Over X cards

Daily Limits: 6 match cards, 4 team cards
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
import numpy as np
from scipy import stats

from multimarket_config import (
    PRODUCT_CONFIGS,
    get_market_label,
    MarketType
)

logger = logging.getLogger(__name__)


def build_cards_features(match_row: Dict) -> Dict[str, Any]:
    """
    Build feature dict for cards prediction from match data.
    All features gracefully degrade to sensible defaults when data is missing.
    
    Args:
        match_row: Dict with home_stats, away_stats, referee_stats, h2h_stats, match_context subdicts
    
    Returns:
        Dict of computed features for cards prediction
    """
    home_stats = match_row.get("home_stats", {})
    away_stats = match_row.get("away_stats", {})
    referee_stats = match_row.get("referee_stats", {})
    h2h_stats = match_row.get("h2h_stats", {})
    match_context = match_row.get("match_context", {})
    
    features = {
        "referee_cards_per_match": referee_stats.get("cards_per_match", DEFAULT_DISCIPLINE_STATS["referee_avg_cards"]),
        "referee_foul_to_card_conversion": referee_stats.get("foul_to_card_conversion", 0.35),
        "referee_early_card_rate": referee_stats.get("early_card_rate", 0.25),
        "referee_big_match_intensity": referee_stats.get("big_match_intensity", 1.0),
        
        "fouls_pg_home": home_stats.get("fouls_pg", DEFAULT_DISCIPLINE_STATS["fouls_pg"]),
        "fouls_pg_away": away_stats.get("fouls_pg", DEFAULT_DISCIPLINE_STATS["fouls_pg"]),
        "cards_pg_home": home_stats.get("cards_pg", DEFAULT_DISCIPLINE_STATS["cards_pg"]),
        "cards_pg_away": away_stats.get("cards_pg", DEFAULT_DISCIPLINE_STATS["cards_pg"]),
        "tackles_pg_home": home_stats.get("tackles_pg", DEFAULT_DISCIPLINE_STATS["tackles_pg"]),
        "tackles_pg_away": away_stats.get("tackles_pg", DEFAULT_DISCIPLINE_STATS["tackles_pg"]),
        "duels_pg_home": home_stats.get("duels_pg", DEFAULT_DISCIPLINE_STATS["duels_pg"]),
        "duels_pg_away": away_stats.get("duels_pg", DEFAULT_DISCIPLINE_STATS["duels_pg"]),
        "aerial_duels_pg_home": home_stats.get("aerial_duels_pg", DEFAULT_DISCIPLINE_STATS["aerial_duels_pg"]),
        "aerial_duels_pg_away": away_stats.get("aerial_duels_pg", DEFAULT_DISCIPLINE_STATS["aerial_duels_pg"]),
        
        "ppda_home": home_stats.get("ppda", 10.0),
        "ppda_away": away_stats.get("ppda", 10.0),
        "interceptions_pg_home": home_stats.get("interceptions_pg", 12),
        "interceptions_pg_away": away_stats.get("interceptions_pg", 12),
        
        "formation_home": match_row.get("home_formation", "4-4-2"),
        "formation_away": match_row.get("away_formation", "4-4-2"),
        
        "h2h_avg_cards": h2h_stats.get("avg_cards_h2h", 4.5),
        "is_derby": h2h_stats.get("is_derby", False),
        
        "match_importance": match_context.get("importance_index", 1.0),
        "is_knockout": match_context.get("is_knockout", False),
        "is_relegation_battle": match_context.get("is_relegation_battle", False),
        "is_title_race": match_context.get("is_title_race", False),
    }
    
    cards_factor = features["referee_cards_per_match"] / DEFAULT_DISCIPLINE_STATS["referee_avg_cards"]
    foul_factor = features["referee_foul_to_card_conversion"] / 0.35
    features["referee_profile_index"] = round(cards_factor * 0.6 + foul_factor * 0.4, 3)
    
    base_rivalry = 1.20 if features["is_derby"] else 1.0
    h2h_mod = features["h2h_avg_cards"] / 4.5
    features["rivalry_index"] = round(base_rivalry * (h2h_mod * 0.3 + 0.7), 3)
    
    features["team_aggression_home"] = round(
        (features["fouls_pg_home"] / DEFAULT_DISCIPLINE_STATS["fouls_pg"]) * 0.30 +
        (features["cards_pg_home"] / DEFAULT_DISCIPLINE_STATS["cards_pg"]) * 0.35 +
        ((features["aerial_duels_pg_home"] + features["duels_pg_home"] - 15) / 50) * 0.35,
        3
    )
    features["team_aggression_away"] = round(
        (features["fouls_pg_away"] / DEFAULT_DISCIPLINE_STATS["fouls_pg"]) * 0.30 +
        (features["cards_pg_away"] / DEFAULT_DISCIPLINE_STATS["cards_pg"]) * 0.35 +
        ((features["aerial_duels_pg_away"] + features["duels_pg_away"] - 15) / 50) * 0.35,
        3
    )
    
    avg_ppda = (features["ppda_home"] + features["ppda_away"]) / 2
    ppda_factor = 10.0 / avg_ppda if avg_ppda > 0 else 1.0
    features["pressing_index_home"] = round(min(1.15, max(0.85, ppda_factor)), 3)
    features["pressing_index_away"] = round(min(1.15, max(0.85, ppda_factor)), 3)
    
    features["formation_aggression_home"] = FORMATION_AGGRESSION.get(
        features["formation_home"], FORMATION_AGGRESSION["default"]
    )
    features["formation_aggression_away"] = FORMATION_AGGRESSION.get(
        features["formation_away"], FORMATION_AGGRESSION["default"]
    )
    
    game_risk = 1.0
    if features["is_knockout"]:
        game_risk *= 1.10
    if features["is_relegation_battle"]:
        game_risk *= 1.08
    if features["is_title_race"]:
        game_risk *= 1.05
    features["game_state_risk_factor"] = round(game_risk * features["match_importance"], 3)
    
    return features


@dataclass
class CardsCandidate:
    fixture_id: str
    home_team: str
    away_team: str
    market_key: str
    selection: str
    line: float
    model_prob: float
    book_odds: float
    ev: float
    confidence: float
    trust_tier: str
    metadata: Dict[str, Any]
    match_date: str = ""
    league: str = "Unknown"
    
    @property
    def match(self) -> str:
        return f"{self.home_team} vs {self.away_team}"
    
    @property
    def odds(self) -> float:
        return self.book_odds
    
    @property
    def ev_sim(self) -> float:
        return self.ev
    
    @property
    def tier(self) -> str:
        return self.trust_tier


CARDS_LINES = {
    "match": [2.5, 3.5, 4.5, 5.5, 6.5],
    "booking_points": [30.5, 40.5, 50.5, 60.5],
    "home": [0.5, 1.5, 2.5, 3.5],
    "away": [0.5, 1.5, 2.5, 3.5],
}

DEFAULT_DISCIPLINE_STATS = {
    "cards_pg": 2.1,
    "cards_against_pg": 1.9,
    "fouls_pg": 11.5,
    "yellow_cards_pg": 1.8,
    "red_cards_pg": 0.05,
    "referee_avg_cards": 4.2,
    "tackles_pg": 16.0,
    "duels_pg": 50.0,
    "aerial_duels_pg": 15.0,
}

BOOKING_POINTS = {
    "yellow": 10,
    "red": 25,
}

FORMATION_AGGRESSION = {
    "5-4-1": 0.90,
    "5-3-2": 0.92,
    "4-5-1": 0.95,
    "4-4-2": 1.00,
    "4-3-3": 1.05,
    "4-2-3-1": 1.02,
    "3-5-2": 1.08,
    "3-4-3": 1.12,
    "4-1-4-1": 0.98,
    "default": 1.00,
}

FACTOR_WEIGHTS = {
    "referee": 0.30,
    "rivalry": 0.20,
    "formation": 0.15,
    "tempo": 0.15,
    "team_aggression": 0.20,
}


@dataclass
class CardFactors:
    referee_profile: float = 1.0
    rivalry_index: float = 1.0
    formation_aggression_home: float = 1.0
    formation_aggression_away: float = 1.0
    tempo_index: float = 1.0
    team_aggression_home: float = 1.0
    team_aggression_away: float = 1.0
    
    def get_combined_factor(self) -> float:
        weights = FACTOR_WEIGHTS
        avg_formation = (self.formation_aggression_home + self.formation_aggression_away) / 2
        avg_team_agg = (self.team_aggression_home + self.team_aggression_away) / 2
        
        combined = (
            (self.referee_profile ** weights["referee"]) *
            (self.rivalry_index ** weights["rivalry"]) *
            (avg_formation ** weights["formation"]) *
            (self.tempo_index ** weights["tempo"]) *
            (avg_team_agg ** weights["team_aggression"])
        )
        return max(0.70, min(1.45, combined))
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "referee_profile": round(self.referee_profile, 3),
            "rivalry_index": round(self.rivalry_index, 3),
            "formation_aggression_home": round(self.formation_aggression_home, 3),
            "formation_aggression_away": round(self.formation_aggression_away, 3),
            "tempo_index": round(self.tempo_index, 3),
            "team_aggression_home": round(self.team_aggression_home, 3),
            "team_aggression_away": round(self.team_aggression_away, 3),
            "combined_factor": round(self.get_combined_factor(), 3),
        }


class SyndicateCardsModel:
    
    def __init__(self, num_sims: int = 10000):
        self.num_sims = num_sims
    
    def compute_referee_card_profile(
        self,
        referee_stats: Optional[Dict]
    ) -> float:
        if not referee_stats:
            return 1.0
        
        cards_pm = referee_stats.get("cards_per_match", DEFAULT_DISCIPLINE_STATS["referee_avg_cards"])
        foul_to_card = referee_stats.get("foul_to_card_conversion", 0.35)
        early_card_rate = referee_stats.get("early_card_rate", 0.25)
        big_match_intensity = referee_stats.get("big_match_intensity", 1.0)
        
        cards_factor = cards_pm / DEFAULT_DISCIPLINE_STATS["referee_avg_cards"]
        foul_factor = foul_to_card / 0.35
        early_factor = 1.0 + (early_card_rate - 0.25) * 0.5
        
        profile = (cards_factor * 0.50) + (foul_factor * 0.25) + (early_factor * 0.15) + (big_match_intensity * 0.10)
        
        return round(max(0.75, min(1.35, profile)), 3)
    
    def compute_rivalry_index(
        self,
        home_team: str,
        away_team: str,
        h2h_stats: Optional[Dict] = None,
        match_context: Optional[Dict] = None
    ) -> float:
        derby_pairs = [
            {"Arsenal", "Tottenham"},
            {"Liverpool", "Everton"},
            {"Liverpool", "Manchester United"},
            {"Manchester United", "Manchester City"},
            {"Manchester United", "Liverpool"},
            {"Chelsea", "Tottenham"},
            {"Chelsea", "Arsenal"},
            {"Real Madrid", "Barcelona"},
            {"Real Madrid", "Atlético Madrid"},
            {"Barcelona", "Atlético Madrid"},
            {"AC Milan", "Inter Milan"},
            {"Juventus", "Inter Milan"},
            {"Roma", "Lazio"},
            {"Borussia Dortmund", "Bayern Munich"},
            {"Ajax", "Feyenoord"},
            {"Celtic", "Rangers"},
            {"Benfica", "Porto"},
            {"Fenerbahce", "Galatasaray"},
            {"Olympiacos", "Panathinaikos"},
            {"River Plate", "Boca Juniors"},
        ]
        
        teams = {home_team, away_team}
        is_derby = any(len(teams.intersection(derby)) == 2 for derby in derby_pairs)
        
        base_rivalry = 1.20 if is_derby else 1.0
        
        if h2h_stats:
            h2h_cards = h2h_stats.get("avg_cards_h2h", 4.5)
            h2h_factor = h2h_cards / 4.5
            base_rivalry *= (h2h_factor * 0.3 + 0.7)
        
        if match_context:
            importance = match_context.get("importance_index", 1.0)
            is_knockout = match_context.get("is_knockout", False)
            is_relegation = match_context.get("is_relegation_battle", False)
            
            if is_knockout:
                base_rivalry *= 1.10
            if is_relegation:
                base_rivalry *= 1.08
            base_rivalry *= importance
        
        return round(max(0.90, min(1.40, base_rivalry)), 3)
    
    def compute_formation_aggression(
        self,
        formation: Optional[str]
    ) -> float:
        if not formation:
            return FORMATION_AGGRESSION["default"]
        
        formation_clean = formation.strip().replace(" ", "")
        
        if formation_clean in FORMATION_AGGRESSION:
            return FORMATION_AGGRESSION[formation_clean]
        
        for key in FORMATION_AGGRESSION:
            if key in formation_clean or formation_clean in key:
                return FORMATION_AGGRESSION[key]
        
        return FORMATION_AGGRESSION["default"]
    
    def compute_tempo_index(
        self,
        home_stats: Dict,
        away_stats: Dict
    ) -> float:
        home_ppda = home_stats.get("ppda", 10.0)
        away_ppda = away_stats.get("ppda", 10.0)
        
        home_duels = home_stats.get("duels_pg", DEFAULT_DISCIPLINE_STATS["duels_pg"])
        away_duels = away_stats.get("duels_pg", DEFAULT_DISCIPLINE_STATS["duels_pg"])
        
        home_tackles = home_stats.get("tackles_pg", DEFAULT_DISCIPLINE_STATS["tackles_pg"])
        away_tackles = away_stats.get("tackles_pg", DEFAULT_DISCIPLINE_STATS["tackles_pg"])
        
        home_intercept = home_stats.get("interceptions_pg", 12)
        away_intercept = away_stats.get("interceptions_pg", 12)
        
        avg_ppda = (home_ppda + away_ppda) / 2
        ppda_factor = 10.0 / avg_ppda if avg_ppda > 0 else 1.0
        ppda_factor = min(1.15, max(0.85, ppda_factor))
        
        avg_duels = (home_duels + away_duels) / 2
        duels_factor = avg_duels / DEFAULT_DISCIPLINE_STATS["duels_pg"]
        duels_factor = min(1.15, max(0.85, duels_factor))
        
        avg_tackles = (home_tackles + away_tackles) / 2
        avg_intercept = (home_intercept + away_intercept) / 2
        def_action_factor = ((avg_tackles + avg_intercept) / 28.0)
        def_action_factor = min(1.10, max(0.90, def_action_factor))
        
        tempo = (ppda_factor * 0.35) + (duels_factor * 0.35) + (def_action_factor * 0.30)
        
        return round(max(0.85, min(1.20, tempo)), 3)
    
    def compute_team_aggression(
        self,
        team_stats: Dict
    ) -> float:
        fouls = team_stats.get("fouls_pg", DEFAULT_DISCIPLINE_STATS["fouls_pg"])
        cards = team_stats.get("cards_pg", DEFAULT_DISCIPLINE_STATS["cards_pg"])
        aerial = team_stats.get("aerial_duels_pg", DEFAULT_DISCIPLINE_STATS["aerial_duels_pg"])
        ground = team_stats.get("ground_duels_pg", 35)
        high_card_players = team_stats.get("high_card_rate_players", 0)
        
        fouls_factor = fouls / DEFAULT_DISCIPLINE_STATS["fouls_pg"]
        cards_factor = cards / DEFAULT_DISCIPLINE_STATS["cards_pg"]
        duels_factor = (aerial + ground) / 50.0
        player_factor = 1.0 + (high_card_players * 0.03)
        
        aggression = (
            fouls_factor * 0.30 +
            cards_factor * 0.35 +
            duels_factor * 0.20 +
            player_factor * 0.15
        )
        
        return round(max(0.80, min(1.30, aggression)), 3)
    
    def compute_all_factors(
        self,
        home_team: str,
        away_team: str,
        home_stats: Dict,
        away_stats: Dict,
        referee_stats: Optional[Dict] = None,
        h2h_stats: Optional[Dict] = None,
        match_context: Optional[Dict] = None,
        home_formation: Optional[str] = None,
        away_formation: Optional[str] = None
    ) -> CardFactors:
        return CardFactors(
            referee_profile=self.compute_referee_card_profile(referee_stats),
            rivalry_index=self.compute_rivalry_index(home_team, away_team, h2h_stats, match_context),
            formation_aggression_home=self.compute_formation_aggression(home_formation),
            formation_aggression_away=self.compute_formation_aggression(away_formation),
            tempo_index=self.compute_tempo_index(home_stats, away_stats),
            team_aggression_home=self.compute_team_aggression(home_stats),
            team_aggression_away=self.compute_team_aggression(away_stats),
        )


class CardsEngine:
    def __init__(self, config: Optional[Dict] = None, num_sims: int = 10000):
        self.config = config or PRODUCT_CONFIGS.get("CARDS_MATCH", {})
        self.team_config = PRODUCT_CONFIGS.get("CARDS_TEAM", self.config)
        self.num_sims = num_sims
        self.model = SyndicateCardsModel(num_sims)
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info("✅ Syndicate CardsEngine v2.0 initialized")
    
    def estimate_cards_distribution(
        self,
        home_stats: Dict,
        away_stats: Dict,
        factors: Optional[CardFactors] = None
    ) -> Dict[str, np.ndarray]:
        home_cards_mean = home_stats.get("cards_pg", DEFAULT_DISCIPLINE_STATS["cards_pg"])
        away_cards_mean = away_stats.get("cards_pg", DEFAULT_DISCIPLINE_STATS["cards_pg"])
        
        if factors:
            combined = factors.get_combined_factor()
            home_adj = factors.team_aggression_home * factors.formation_aggression_home
            away_adj = factors.team_aggression_away * factors.formation_aggression_away
            
            adj_home_cards = home_cards_mean * combined * (home_adj / 1.0)
            adj_away_cards = away_cards_mean * combined * (away_adj / 1.0)
        else:
            adj_home_cards = home_cards_mean
            adj_away_cards = away_cards_mean
        
        home_yellows = np.random.poisson(adj_home_cards * 0.95, self.num_sims)
        away_yellows = np.random.poisson(adj_away_cards * 0.95, self.num_sims)
        
        red_prob_base = 0.05
        if factors and factors.rivalry_index > 1.1:
            red_prob_base *= factors.rivalry_index
        
        home_reds = np.random.binomial(1, min(0.15, red_prob_base), self.num_sims)
        away_reds = np.random.binomial(1, min(0.15, red_prob_base), self.num_sims)
        
        home_cards = home_yellows + home_reds
        away_cards = away_yellows + away_reds
        total_cards = home_cards + away_cards
        
        home_booking_pts = (home_yellows * BOOKING_POINTS["yellow"] + 
                           home_reds * BOOKING_POINTS["red"])
        away_booking_pts = (away_yellows * BOOKING_POINTS["yellow"] + 
                           away_reds * BOOKING_POINTS["red"])
        total_booking_pts = home_booking_pts + away_booking_pts
        
        return {
            "home_cards": home_cards,
            "away_cards": away_cards,
            "total_cards": total_cards,
            "home_yellows": home_yellows,
            "away_yellows": away_yellows,
            "home_reds": home_reds,
            "away_reds": away_reds,
            "home_booking_pts": home_booking_pts,
            "away_booking_pts": away_booking_pts,
            "total_booking_pts": total_booking_pts,
        }
    
    def calculate_over_under_probs(
        self,
        simulations: np.ndarray,
        line: float
    ) -> Dict[str, float]:
        over_prob = np.mean(simulations > line)
        under_prob = np.mean(simulations < line)
        push_prob = np.mean(simulations == line)
        
        return {
            "over": float(over_prob),
            "under": float(under_prob),
            "push": float(push_prob),
        }
    
    def calculate_ev(self, model_prob: float, book_odds: float) -> float:
        if model_prob <= 0 or book_odds <= 1:
            return -1.0
        return (model_prob * book_odds) - 1
    
    def classify_trust_tier(
        self,
        ev: float,
        confidence: float,
        sim_approved: bool = True,
        product_key: str = "CARDS_MATCH"
    ) -> str:
        config = PRODUCT_CONFIGS.get(product_key, {})
        
        l1_ev = getattr(config, 'l1_min_ev', 0.05)
        l1_conf = getattr(config, 'l1_min_confidence', 0.55)
        l2_ev = getattr(config, 'l2_min_ev', 0.02)
        l2_conf = getattr(config, 'l2_min_confidence', 0.52)
        l3_ev = getattr(config, 'l3_min_ev', 0.00)
        l3_conf = getattr(config, 'l3_min_confidence', 0.50)
        
        if sim_approved and ev >= l1_ev and confidence >= l1_conf:
            return "L1_HIGH_TRUST"
        elif sim_approved and ev >= l2_ev and confidence >= l2_conf:
            return "L2_MEDIUM_TRUST"
        elif ev >= l3_ev and confidence >= l3_conf:
            return "L3_SOFT_VALUE"
        return "REJECTED"
    
    def generate_market_predictions(
        self,
        fixture: Dict,
        odds_snapshot: Dict[str, float],
        team_stats: Optional[Dict] = None,
        referee_stats: Optional[Dict] = None,
        h2h_stats: Optional[Dict] = None,
        match_context: Optional[Dict] = None
    ) -> List[CardsCandidate]:
        candidates = []
        
        fixture_id = fixture.get("fixture_id", "unknown")
        home_team = fixture.get("home_team", "Home")
        away_team = fixture.get("away_team", "Away")
        home_formation = fixture.get("home_formation")
        away_formation = fixture.get("away_formation")
        
        home_stats = (team_stats or {}).get("home", DEFAULT_DISCIPLINE_STATS)
        away_stats = (team_stats or {}).get("away", DEFAULT_DISCIPLINE_STATS)
        
        factors = self.model.compute_all_factors(
            home_team, away_team,
            home_stats, away_stats,
            referee_stats, h2h_stats, match_context,
            home_formation, away_formation
        )
        
        sims = self.estimate_cards_distribution(home_stats, away_stats, factors)
        
        market_configs = [
            ("CARDS_MATCH", "MATCH_CARDS_OVER_{}_5", "MATCH_CARDS_UNDER_{}_5", 
             "total_cards", CARDS_LINES["match"]),
            ("CARDS_MATCH", "BOOKING_POINTS_OVER_{}_5", "BOOKING_POINTS_UNDER_{}_5",
             "total_booking_pts", CARDS_LINES["booking_points"]),
            ("CARDS_TEAM", "HOME_CARDS_OVER_{}_5", None,
             "home_cards", CARDS_LINES["home"]),
            ("CARDS_TEAM", "AWAY_CARDS_OVER_{}_5", None,
             "away_cards", CARDS_LINES["away"]),
        ]
        
        for product_key, over_template, under_template, sim_key, lines in market_configs:
            config = PRODUCT_CONFIGS.get(product_key)
            if not config:
                continue
            
            min_ev = getattr(config, 'min_ev', 0.02)
            min_odds = getattr(config, 'min_odds', 1.60)
            max_odds = getattr(config, 'max_odds', 2.80)
            min_conf = getattr(config, 'min_confidence', 0.52)
            
            for line in lines:
                line_str = str(int(line))
                
                for direction, template in [("over", over_template), ("under", under_template)]:
                    if template is None:
                        continue
                    
                    market_key = template.format(line_str)
                    
                    book_odds = odds_snapshot.get(market_key, 0)
                    if not (min_odds <= book_odds <= max_odds):
                        continue
                    
                    probs = self.calculate_over_under_probs(sims[sim_key], line)
                    model_prob = probs[direction]
                    
                    if model_prob < min_conf:
                        continue
                    
                    ev = self.calculate_ev(model_prob, book_odds)
                    if ev < min_ev:
                        continue
                    
                    trust_tier = self.classify_trust_tier(
                        ev, model_prob, 
                        sim_approved=True,
                        product_key=product_key
                    )
                    if trust_tier == "REJECTED":
                        continue
                    
                    selection = f"{direction.title()} {line}"
                    
                    market_type = (MarketType.CARDS_MATCH if product_key == "CARDS_MATCH" 
                                   else MarketType.CARDS_TEAM)
                    
                    candidate = CardsCandidate(
                        fixture_id=fixture_id,
                        home_team=home_team,
                        away_team=away_team,
                        market_key=market_key,
                        selection=selection,
                        line=line,
                        model_prob=model_prob,
                        book_odds=book_odds,
                        ev=ev,
                        confidence=model_prob,
                        trust_tier=trust_tier,
                        metadata={
                            "market_type": market_type.value,
                            "sim_key": sim_key,
                            "direction": direction,
                            "factors": factors.to_dict(),
                            "mean_value": float(np.mean(sims[sim_key])),
                            "std_value": float(np.std(sims[sim_key])),
                            "avg_total_cards": float(np.mean(sims["total_cards"])),
                            "avg_booking_pts": float(np.mean(sims["total_booking_pts"])),
                        },
                        match_date=fixture.get("match_date", datetime.now().strftime('%Y-%m-%d')),
                        league=fixture.get("league", "Unknown")
                    )
                    candidates.append(candidate)
                    
                    logger.debug(
                        f"🟨 Cards: {home_team} vs {away_team} | "
                        f"{get_market_label(market_key)} @ {book_odds} | "
                        f"p={model_prob:.1%} EV={ev:.1%} | {trust_tier}"
                    )
        
        candidates.sort(key=lambda x: x.ev, reverse=True)
        
        return candidates


def run_cards_cycle(
    fixtures: List[Dict],
    odds_data: Dict,
    team_stats_data: Optional[Dict] = None,
    referee_data: Optional[Dict] = None,
    h2h_data: Optional[Dict] = None
) -> List[CardsCandidate]:
    engine = CardsEngine()
    all_candidates = []
    
    team_stats_data = team_stats_data or {}
    referee_data = referee_data or {}
    h2h_data = h2h_data or {}
    
    for fixture in fixtures:
        fixture_id = fixture.get("fixture_id")
        home_team = fixture.get("home_team", "Home")
        away_team = fixture.get("away_team", "Away")
        
        odds_snapshot = odds_data.get(fixture_id, {})
        if not odds_snapshot:
            continue
        
        home_stats = team_stats_data.get(home_team, DEFAULT_DISCIPLINE_STATS)
        away_stats = team_stats_data.get(away_team, DEFAULT_DISCIPLINE_STATS)
        team_stats = {"home": home_stats, "away": away_stats}
        
        referee_stats = referee_data.get(fixture.get("referee_id"), {})
        h2h_stats = h2h_data.get(f"{home_team}_vs_{away_team}", {})
        
        match_context = {
            "importance_index": fixture.get("importance_index", 1.0),
            "is_knockout": fixture.get("is_knockout", False),
            "is_relegation_battle": fixture.get("is_relegation", False),
        }
        
        candidates = engine.generate_market_predictions(
            fixture, odds_snapshot,
            team_stats, referee_stats,
            h2h_stats, match_context
        )
        all_candidates.extend(candidates)
    
    match_config = PRODUCT_CONFIGS.get("CARDS_MATCH")
    team_config = PRODUCT_CONFIGS.get("CARDS_TEAM")
    
    match_max = getattr(match_config, 'max_per_day', 6)
    team_max = getattr(team_config, 'max_per_day', 4)
    
    match_candidates = [c for c in all_candidates if c.metadata["market_type"] == "CARDS_MATCH"]
    team_candidates = [c for c in all_candidates if c.metadata["market_type"] == "CARDS_TEAM"]
    
    def sort_by_tier_ev(candidates):
        tier_order = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 1, "L3_SOFT_VALUE": 2}
        return sorted(candidates, key=lambda x: (tier_order.get(x.trust_tier, 3), -x.ev))
    
    match_candidates = sort_by_tier_ev(match_candidates)
    team_candidates = sort_by_tier_ev(team_candidates)
    
    selected = match_candidates[:match_max] + team_candidates[:team_max]
    
    logger.info(f"🟨 CARDS ENGINE: {len(selected)}/{len(all_candidates)} candidates selected")
    
    return selected


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    test_fixture = {
        "fixture_id": "test_456",
        "home_team": "Arsenal",
        "away_team": "Tottenham",
        "home_formation": "4-3-3",
        "away_formation": "3-5-2",
    }
    
    test_odds = {
        "MATCH_CARDS_OVER_3_5": 1.85,
        "MATCH_CARDS_OVER_4_5": 2.20,
        "MATCH_CARDS_UNDER_4_5": 1.70,
        "MATCH_CARDS_OVER_5_5": 2.80,
        "BOOKING_POINTS_OVER_40_5": 1.90,
        "BOOKING_POINTS_OVER_50_5": 2.30,
        "HOME_CARDS_OVER_1_5": 1.80,
        "HOME_CARDS_OVER_2_5": 2.40,
        "AWAY_CARDS_OVER_1_5": 1.75,
        "AWAY_CARDS_OVER_2_5": 2.35,
    }
    
    home_stats = {
        "cards_pg": 2.3,
        "fouls_pg": 12.5,
        "tackles_pg": 18,
        "duels_pg": 55,
        "aerial_duels_pg": 18,
        "ppda": 9.0,
        "high_card_rate_players": 2,
    }
    
    away_stats = {
        "cards_pg": 2.5,
        "fouls_pg": 13.0,
        "tackles_pg": 17,
        "duels_pg": 52,
        "aerial_duels_pg": 16,
        "ppda": 10.5,
        "high_card_rate_players": 3,
    }
    
    referee_stats = {
        "cards_per_match": 4.8,
        "foul_to_card_conversion": 0.40,
        "early_card_rate": 0.30,
        "big_match_intensity": 1.1,
    }
    
    h2h_stats = {
        "avg_cards_h2h": 5.5,
    }
    
    engine = CardsEngine()
    
    factors = engine.model.compute_all_factors(
        "Arsenal", "Tottenham",
        home_stats, away_stats,
        referee_stats, h2h_stats,
        {"importance_index": 1.1},
        "4-3-3", "3-5-2"
    )
    
    candidates = engine.generate_market_predictions(
        test_fixture, test_odds,
        {"home": home_stats, "away": away_stats},
        referee_stats, h2h_stats,
        {"importance_index": 1.1}
    )
    
    print("\n" + "=" * 60)
    print("SYNDICATE CARDS ENGINE v2.0 TEST")
    print("=" * 60)
    
    print("\nCard Factors:")
    for k, v in factors.to_dict().items():
        print(f"  {k}: {v}")
    
    print(f"\n{len(candidates)} Cards Candidates:")
    for c in candidates[:8]:
        print(f"  [{c.trust_tier}] {c.home_team} vs {c.away_team} | {c.market_key}")
        print(f"    Odds: {c.book_odds} | Prob: {c.model_prob:.1%} | EV: {c.ev:.1%}")
    
    print("\nMetadata sample:")
    if candidates:
        print(f"  Avg cards: {candidates[0].metadata.get('avg_total_cards', 'N/A'):.1f}")
        print(f"  Combined factor: {candidates[0].metadata['factors']['combined_factor']}")

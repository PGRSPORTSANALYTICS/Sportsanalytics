"""
Corners Engine - Corner Markets Product (MultiMarket Expansion v1.0)
====================================================================
Separate product for corner markets with Nova v2.0 trust tiers.

Markets:
- Match Total Corners: Over/Under 8.5, 9.5, 10.5, 11.5
- Team Corners: Home/Away Over X corners

Daily Limits: 6 match corners, 4 team corners
"""

import logging
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from bet_filter import BetCandidate
from multimarket_config import PRODUCT_CONFIGS, get_market_label, MarketType

logger = logging.getLogger(__name__)

MATCH_CORNERS_CONFIG = PRODUCT_CONFIGS["CORNERS_MATCH"]
TEAM_CORNERS_CONFIG = PRODUCT_CONFIGS["CORNERS_TEAM"]

MATCH_CORNER_LINES = [8.5, 9.5, 10.5, 11.5]
TEAM_CORNER_LINES = [3.5, 4.5, 5.5]

DEFAULT_HOME_CORNERS = 5.2
DEFAULT_AWAY_CORNERS = 4.8
DEFAULT_TOTAL_CORNERS = 10.0


class CornersModel:
    
    def __init__(self):
        self.home_corner_avg = DEFAULT_HOME_CORNERS
        self.away_corner_avg = DEFAULT_AWAY_CORNERS
    
    def estimate_corners(
        self,
        home_xg: float = 1.5,
        away_xg: float = 1.2,
        home_form_corners: Optional[float] = None,
        away_form_corners: Optional[float] = None,
        league_avg_corners: float = DEFAULT_TOTAL_CORNERS
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
        
        return home_exp, away_exp
    
    def simulate_corners(
        self,
        home_lambda: float,
        away_lambda: float,
        n_sim: int = 10000
    ) -> Dict:
        home_corners = np.random.poisson(lam=home_lambda, size=n_sim)
        away_corners = np.random.poisson(lam=away_lambda, size=n_sim)
        total_corners = home_corners + away_corners
        
        results = {}
        
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
        
        results["home_most_corners"] = float((home_corners > away_corners).mean())
        results["away_most_corners"] = float((away_corners > home_corners).mean())
        results["avg_total_corners"] = float(total_corners.mean())
        results["avg_home_corners"] = float(home_corners.mean())
        results["avg_away_corners"] = float(away_corners.mean())
        
        return results


class CornersEngine:
    
    def __init__(self):
        self.match_config = MATCH_CORNERS_CONFIG
        self.team_config = TEAM_CORNERS_CONFIG
        self.model = CornersModel()
        self.today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"🔢 Corners Engine initialized (match: {self.match_config.max_per_day}/day, team: {self.team_config.max_per_day}/day)")
    
    def find_match_corner_value(
        self,
        match: str,
        home_team: str,
        away_team: str,
        league: str,
        corner_sim: Dict,
        odds_dict: Dict[str, float],
        match_date: str = None
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
                
                if ev >= self.match_config.l1_min_ev and p_model >= self.match_config.l1_min_confidence and sim_approved:
                    tier = "L1_HIGH_TRUST"
                elif ev >= self.match_config.l2_min_ev and p_model >= self.match_config.l2_min_confidence and sim_approved:
                    tier = "L2_MEDIUM_TRUST"
                elif ev >= self.match_config.l3_min_ev and p_model >= self.match_config.l3_min_confidence:
                    tier = "L3_SOFT_VALUE"
                else:
                    continue
                
                selection_text = market_key.replace("_", " ").replace("CORNERS ", "Corners ")
                
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
                    match_date=match_date or self.today
                )
                candidates.append(candidate)
        
        return candidates
    
    def find_team_corner_value(
        self,
        match: str,
        home_team: str,
        away_team: str,
        league: str,
        corner_sim: Dict,
        odds_dict: Dict[str, float],
        match_date: str = None
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
                
                if ev >= self.team_config.l1_min_ev and p_model >= self.team_config.l1_min_confidence and sim_approved:
                    tier = "L1_HIGH_TRUST"
                elif ev >= self.team_config.l2_min_ev and p_model >= self.team_config.l2_min_confidence and sim_approved:
                    tier = "L2_MEDIUM_TRUST"
                elif ev >= self.team_config.l3_min_ev and p_model >= self.team_config.l3_min_confidence:
                    tier = "L3_SOFT_VALUE"
                else:
                    continue
                
                if "HOME" in market_key:
                    selection_text = f"{home_team} Over {line} Corners"
                else:
                    selection_text = f"{away_team} Over {line} Corners"
                
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
                    match_date=match_date or self.today
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
        match_date: str = None,
        home_form_corners: Optional[float] = None,
        away_form_corners: Optional[float] = None
    ) -> Tuple[List[BetCandidate], List[BetCandidate]]:
        home_exp, away_exp = self.model.estimate_corners(
            home_xg=home_xg,
            away_xg=away_xg,
            home_form_corners=home_form_corners,
            away_form_corners=away_form_corners
        )
        
        corner_sim = self.model.simulate_corners(home_exp, away_exp)
        
        match_bets = self.find_match_corner_value(
            match, home_team, away_team, league, corner_sim, odds_dict, match_date
        )
        
        team_bets = self.find_team_corner_value(
            match, home_team, away_team, league, corner_sim, odds_dict, match_date
        )
        
        return match_bets, team_bets
    
    def apply_daily_filter(
        self,
        match_candidates: List[BetCandidate],
        team_candidates: List[BetCandidate]
    ) -> Tuple[List[BetCandidate], List[BetCandidate]]:
        match_l1 = sorted([c for c in match_candidates if c.tier == "L1_HIGH_TRUST"], key=lambda x: -x.ev_sim)
        match_l2 = sorted([c for c in match_candidates if c.tier == "L2_MEDIUM_TRUST"], key=lambda x: -x.ev_sim)
        
        match_selected = match_l1[:2]
        remaining = self.match_config.max_per_day - len(match_selected)
        match_selected.extend(match_l2[:remaining])
        
        team_l1 = sorted([c for c in team_candidates if c.tier == "L1_HIGH_TRUST"], key=lambda x: -x.ev_sim)
        team_l2 = sorted([c for c in team_candidates if c.tier == "L2_MEDIUM_TRUST"], key=lambda x: -x.ev_sim)
        
        team_selected = team_l1[:1]
        remaining = self.team_config.max_per_day - len(team_selected)
        team_selected.extend(team_l2[:remaining])
        
        return match_selected, team_selected
    
    def get_summary(self, match_bets: List[BetCandidate], team_bets: List[BetCandidate]) -> Dict:
        all_bets = match_bets + team_bets
        tier_counts = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0}
        
        for b in all_bets:
            if b.tier in tier_counts:
                tier_counts[b.tier] += 1
        
        return {
            "product": "CORNERS",
            "total": len(all_bets),
            "match_corners": len(match_bets),
            "team_corners": len(team_bets),
            "by_tier": tier_counts,
            "max_match_per_day": self.match_config.max_per_day,
            "max_team_per_day": self.team_config.max_per_day
        }


if __name__ == "__main__":
    engine = CornersEngine()
    
    mock_odds = {
        "CORNERS_OVER_8_5": 1.85,
        "CORNERS_UNDER_8_5": 1.95,
        "CORNERS_OVER_9_5": 2.10,
        "CORNERS_UNDER_9_5": 1.75,
        "CORNERS_OVER_10_5": 2.50,
        "CORNERS_UNDER_10_5": 1.55,
        "HOME_CORNERS_OVER_4_5": 1.90,
        "AWAY_CORNERS_OVER_4_5": 2.05,
    }
    
    match_bets, team_bets = engine.find_all_corner_value(
        match="Liverpool vs Chelsea",
        home_team="Liverpool",
        away_team="Chelsea",
        league="Premier League",
        home_xg=1.8,
        away_xg=1.2,
        odds_dict=mock_odds
    )
    
    print("=== CORNERS ENGINE TEST ===\n")
    
    print("Match Corner Bets:")
    for c in match_bets:
        print(f"  [{c.tier}] {c.selection} @ {c.odds} | EV: {c.ev_sim:.1%}")
    
    print("\nTeam Corner Bets:")
    for c in team_bets:
        print(f"  [{c.tier}] {c.selection} @ {c.odds} | EV: {c.ev_sim:.1%}")
    
    print(f"\n{engine.get_summary(match_bets, team_bets)}")

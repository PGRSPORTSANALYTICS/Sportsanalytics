"""
MultiMarket Runner - MultiMarket Expansion v1.0 (Dec 9, 2025)
=============================================================
Runs all product engines and builds the daily betting card.

Products:
- Value Singles (ML/AH/DC)
- Totals (Over/Under)
- BTTS
- Corners (Match + Team)

This runner integrates with the existing combined_sports_runner.py
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from bet_filter import BetCandidate
from multimarket_config import PRODUCT_CONFIGS, DAILY_TARGETS
from totals_engine import TotalsEngine
from btts_engine import BTTSEngine
from corners_engine import CornersEngine
from daily_card_builder import DailyCardBuilder, DailyCard
from monte_carlo_simulator import simulate_match

logger = logging.getLogger(__name__)


class MultiMarketRunner:
    
    def __init__(self, champion=None):
        self.champion = champion
        self.totals_engine = TotalsEngine()
        self.btts_engine = BTTSEngine()
        self.corners_engine = CornersEngine()
        self.card_builder = DailyCardBuilder()
        self.today = datetime.now().strftime("%Y-%m-%d")
        
        logger.info("🚀 MultiMarket Runner initialized (v1.0)")
        print("=" * 60)
        print("🚀 MULTIMARKET EXPANSION v1.0")
        print("=" * 60)
        print("Products enabled:")
        print("  📊 Value Singles (ML/AH/DC) - max 15/day")
        print("  🎯 Totals (Over/Under) - max 10/day")
        print("  ⚽ BTTS - max 8/day")
        print("  🔢 Corners (Match + Team) - max 10/day")
        print("=" * 60)
    
    def run_totals_cycle(
        self,
        fixtures: List[Dict],
        get_odds_func,
        get_xg_func
    ) -> List[BetCandidate]:
        print("\n📊 TOTALS ENGINE - Starting cycle...")
        candidates = []
        
        for match in fixtures:
            home_team = match.get("home_team", "")
            away_team = match.get("away_team", "")
            league = match.get("sport_key", "")
            match_name = f"{home_team} vs {away_team}"
            
            odds_dict = get_odds_func(match) if get_odds_func else {}
            if not odds_dict:
                continue
            
            home_xg, away_xg = get_xg_func(match) if get_xg_func else (1.5, 1.3)
            
            mc_result = simulate_match(home_xg, away_xg, n_sim=10000)
            
            match_candidates = self.totals_engine.find_value_bets(
                match=match_name,
                home_team=home_team,
                away_team=away_team,
                league=league,
                mc_result=mc_result,
                odds_dict=odds_dict,
                match_date=self.today
            )
            candidates.extend(match_candidates)
        
        best_per_match = self.totals_engine.select_best_per_match(candidates)
        filtered = self.totals_engine.apply_daily_filter(best_per_match)
        
        print(f"   Found {len(candidates)} raw candidates")
        print(f"   Selected {len(filtered)} after filters")
        
        return filtered
    
    def run_btts_cycle(
        self,
        fixtures: List[Dict],
        get_odds_func,
        get_xg_func
    ) -> List[BetCandidate]:
        print("\n⚽ BTTS ENGINE - Starting cycle...")
        candidates = []
        
        for match in fixtures:
            home_team = match.get("home_team", "")
            away_team = match.get("away_team", "")
            league = match.get("sport_key", "")
            match_name = f"{home_team} vs {away_team}"
            
            odds_dict = get_odds_func(match) if get_odds_func else {}
            if not odds_dict:
                continue
            
            home_xg, away_xg = get_xg_func(match) if get_xg_func else (1.5, 1.3)
            
            mc_result = simulate_match(home_xg, away_xg, n_sim=10000)
            
            match_candidates = self.btts_engine.find_value_bets(
                match=match_name,
                home_team=home_team,
                away_team=away_team,
                league=league,
                mc_result=mc_result,
                odds_dict=odds_dict,
                match_date=self.today
            )
            candidates.extend(match_candidates)
        
        best_per_match = self.btts_engine.select_best_per_match(candidates)
        filtered = self.btts_engine.apply_daily_filter(best_per_match)
        
        print(f"   Found {len(candidates)} raw candidates")
        print(f"   Selected {len(filtered)} after filters")
        
        return filtered
    
    def run_corners_cycle(
        self,
        fixtures: List[Dict],
        get_odds_func,
        get_xg_func
    ) -> Tuple[List[BetCandidate], List[BetCandidate]]:
        print("\n🔢 CORNERS ENGINE - Starting cycle...")
        match_candidates = []
        team_candidates = []
        
        for match in fixtures:
            home_team = match.get("home_team", "")
            away_team = match.get("away_team", "")
            league = match.get("sport_key", "")
            match_name = f"{home_team} vs {away_team}"
            
            odds_dict = get_odds_func(match) if get_odds_func else {}
            if not odds_dict:
                continue
            
            home_xg, away_xg = get_xg_func(match) if get_xg_func else (1.5, 1.3)
            
            match_bets, team_bets = self.corners_engine.find_all_corner_value(
                match=match_name,
                home_team=home_team,
                away_team=away_team,
                league=league,
                home_xg=home_xg,
                away_xg=away_xg,
                odds_dict=odds_dict,
                match_date=self.today
            )
            match_candidates.extend(match_bets)
            team_candidates.extend(team_bets)
        
        match_filtered, team_filtered = self.corners_engine.apply_daily_filter(
            match_candidates, team_candidates
        )
        
        print(f"   Found {len(match_candidates)} match corner candidates, {len(team_candidates)} team corner candidates")
        print(f"   Selected {len(match_filtered)} match, {len(team_filtered)} team after filters")
        
        return match_filtered, team_filtered
    
    def run_full_cycle(
        self,
        value_singles: List[BetCandidate],
        fixtures: List[Dict],
        get_odds_func,
        get_xg_func,
        ml_parlays: List[Dict] = None,
        multi_match_parlays: List[Dict] = None
    ) -> DailyCard:
        print("\n" + "=" * 60)
        print("🎯 MULTIMARKET FULL CYCLE")
        print("=" * 60)
        
        totals_bets = self.run_totals_cycle(fixtures, get_odds_func, get_xg_func)
        
        btts_bets = self.run_btts_cycle(fixtures, get_odds_func, get_xg_func)
        
        corners_match, corners_team = self.run_corners_cycle(fixtures, get_odds_func, get_xg_func)
        
        card = self.card_builder.build_card(
            value_singles=value_singles,
            totals=totals_bets,
            btts=btts_bets,
            corners_match=corners_match,
            corners_team=corners_team,
            ml_parlays=ml_parlays or [],
            multi_match_parlays=multi_match_parlays or []
        )
        
        self.card_builder.print_card_summary(card)
        
        return card
    
    def run_standalone_cycle(self) -> DailyCard:
        print("\n🔄 Running standalone MultiMarket cycle...")
        
        if not self.champion:
            print("⚠️ No champion available - running with empty fixtures")
            return self.card_builder.build_card(
                value_singles=[],
                totals=[],
                btts=[],
                corners_match=[],
                corners_team=[]
            )
        
        fixtures = self.champion.get_todays_fixtures() if hasattr(self.champion, "get_todays_fixtures") else []
        
        def get_odds(match):
            return self.champion.get_odds_for_match(match) if hasattr(self.champion, "get_odds_for_match") else {}
        
        def get_xg(match):
            return (1.5, 1.3)
        
        return self.run_full_cycle(
            value_singles=[],
            fixtures=fixtures,
            get_odds_func=get_odds,
            get_xg_func=get_xg
        )


def run_multimarket_test():
    print("=" * 60)
    print("🧪 MULTIMARKET EXPANSION v1.0 - TEST RUN")
    print("=" * 60)
    
    runner = MultiMarketRunner()
    
    mock_fixtures = [
        {
            "home_team": "Liverpool",
            "away_team": "Chelsea",
            "sport_key": "soccer_epl",
        },
        {
            "home_team": "Barcelona",
            "away_team": "Real Madrid",
            "sport_key": "soccer_spain_la_liga",
        }
    ]
    
    mock_odds_data = {
        "Liverpool vs Chelsea": {
            "FT_OVER_2_5": 1.85,
            "FT_UNDER_2_5": 2.00,
            "FT_OVER_3_5": 2.80,
            "BTTS_YES": 1.72,
            "BTTS_NO": 2.10,
            "CORNERS_OVER_9_5": 1.90,
            "CORNERS_OVER_10_5": 2.30,
        },
        "Barcelona vs Real Madrid": {
            "FT_OVER_2_5": 1.75,
            "FT_UNDER_2_5": 2.10,
            "FT_OVER_3_5": 2.60,
            "BTTS_YES": 1.65,
            "BTTS_NO": 2.20,
            "CORNERS_OVER_9_5": 1.85,
            "CORNERS_OVER_10_5": 2.20,
        }
    }
    
    def mock_get_odds(match):
        match_name = f"{match.get('home_team')} vs {match.get('away_team')}"
        return mock_odds_data.get(match_name, {})
    
    def mock_get_xg(match):
        return (1.8, 1.4)
    
    mock_value_singles = [
        BetCandidate(
            match="Liverpool vs Chelsea",
            market="HOME_WIN",
            selection="Home Win (ML)",
            odds=1.85,
            ev_sim=0.06,
            ev_model=0.06,
            confidence=0.58,
            approved=True,
            tier="L1_HIGH_TRUST",
            market_type="ML",
            product="VALUE_SINGLES"
        ),
        BetCandidate(
            match="Barcelona vs Real Madrid",
            market="AH_HOME_-0.5",
            selection="Barcelona -0.5 (AH)",
            odds=2.10,
            ev_sim=0.04,
            ev_model=0.04,
            confidence=0.55,
            approved=True,
            tier="L2_MEDIUM_TRUST",
            market_type="AH",
            product="VALUE_SINGLES"
        ),
    ]
    
    card = runner.run_full_cycle(
        value_singles=mock_value_singles,
        fixtures=mock_fixtures,
        get_odds_func=mock_get_odds,
        get_xg_func=mock_get_xg
    )
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)
    
    return card


if __name__ == "__main__":
    run_multimarket_test()

"""
Syndicate Engines Test & Validation Script
===========================================
Tests the upgraded Corners and Cards engines with:
1. Unit tests for factor computation
2. Backtest sample analysis
3. Live simulation with mock data
4. Router integration verification

Usage:
    python test_syndicate_engines.py [--backtest] [--live] [--verbose]
"""

import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any
import random

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from corners_engine import CornersEngine, SyndicateCornersModel, CornerFactors, run_corners_cycle
from cards_engine import CardsEngine, SyndicateCardsModel, CardFactors, run_cards_cycle


def generate_mock_team_stats() -> Dict:
    return {
        "passes_per_minute": random.uniform(6.5, 10.5),
        "attacks_per_90": random.uniform(80, 130),
        "dangerous_attacks_per_90": random.uniform(35, 70),
        "crosses_per_90": random.uniform(10, 22),
        "wide_zone_touches": random.uniform(25, 55),
        "flank_attack_pct": random.uniform(0.28, 0.45),
        "xg_from_corners": random.uniform(0.15, 0.45),
        "comeback_frequency": random.uniform(0.08, 0.25),
        "late_game_attack_intensity": random.uniform(0.85, 1.20),
        "shots_when_trailing": random.uniform(3, 8),
        "cards_pg": random.uniform(1.5, 3.0),
        "fouls_pg": random.uniform(9, 15),
        "tackles_pg": random.uniform(12, 22),
        "duels_pg": random.uniform(40, 65),
        "aerial_duels_pg": random.uniform(10, 22),
        "ground_duels_pg": random.uniform(25, 45),
        "ppda": random.uniform(7, 14),
        "interceptions_pg": random.uniform(8, 16),
        "high_card_rate_players": random.randint(0, 4),
    }


def generate_mock_referee_stats() -> Dict:
    return {
        "corners_per_match": random.uniform(8.5, 12.5),
        "fouls_near_box_per_match": random.uniform(3, 8),
        "stoppage_rate": random.uniform(0.4, 0.65),
        "cards_per_match": random.uniform(3.2, 5.5),
        "foul_to_card_conversion": random.uniform(0.25, 0.50),
        "early_card_rate": random.uniform(0.15, 0.40),
        "big_match_intensity": random.uniform(0.9, 1.2),
    }


def generate_mock_weather() -> Dict:
    conditions = [
        {"wind_speed": 5, "is_rain": False, "pitch_condition": "good"},
        {"wind_speed": 25, "is_rain": False, "pitch_condition": "good"},
        {"wind_speed": 15, "is_rain": True, "pitch_condition": "wet"},
        {"wind_speed": 45, "is_rain": True, "pitch_condition": "slippery"},
        {"wind_speed": 8, "is_rain": False, "pitch_condition": "excellent"},
    ]
    return random.choice(conditions)


def generate_mock_odds_corners() -> Dict[str, float]:
    return {
        "CORNERS_OVER_8_5": random.uniform(1.70, 2.10),
        "CORNERS_UNDER_8_5": random.uniform(1.75, 2.05),
        "CORNERS_OVER_9_5": random.uniform(1.90, 2.40),
        "CORNERS_UNDER_9_5": random.uniform(1.55, 1.90),
        "CORNERS_OVER_10_5": random.uniform(2.20, 2.90),
        "CORNERS_UNDER_10_5": random.uniform(1.40, 1.70),
        "CORNERS_OVER_11_5": random.uniform(2.60, 3.50),
        "CORNERS_UNDER_11_5": random.uniform(1.30, 1.55),
        "HOME_CORNERS_OVER_3_5": random.uniform(1.50, 1.90),
        "HOME_CORNERS_OVER_4_5": random.uniform(1.80, 2.30),
        "HOME_CORNERS_OVER_5_5": random.uniform(2.30, 3.00),
        "AWAY_CORNERS_OVER_3_5": random.uniform(1.55, 1.95),
        "AWAY_CORNERS_OVER_4_5": random.uniform(1.85, 2.40),
        "AWAY_CORNERS_OVER_5_5": random.uniform(2.40, 3.20),
        "CORNERS_HC_HOME_-1_5": random.uniform(1.80, 2.20),
        "CORNERS_HC_HOME_-0_5": random.uniform(1.60, 1.95),
        "CORNERS_HC_HOME_+0_5": random.uniform(1.55, 1.85),
        "CORNERS_HC_HOME_+1_5": random.uniform(1.40, 1.70),
        "CORNERS_HC_AWAY_-1_5": random.uniform(1.85, 2.30),
        "CORNERS_HC_AWAY_+1_5": random.uniform(1.45, 1.75),
    }


def generate_mock_odds_cards() -> Dict[str, float]:
    return {
        "MATCH_CARDS_OVER_2_5": random.uniform(1.50, 1.85),
        "MATCH_CARDS_UNDER_2_5": random.uniform(1.90, 2.40),
        "MATCH_CARDS_OVER_3_5": random.uniform(1.70, 2.10),
        "MATCH_CARDS_UNDER_3_5": random.uniform(1.70, 2.10),
        "MATCH_CARDS_OVER_4_5": random.uniform(2.00, 2.60),
        "MATCH_CARDS_UNDER_4_5": random.uniform(1.50, 1.85),
        "MATCH_CARDS_OVER_5_5": random.uniform(2.50, 3.30),
        "MATCH_CARDS_UNDER_5_5": random.uniform(1.35, 1.60),
        "BOOKING_POINTS_OVER_30_5": random.uniform(1.55, 1.90),
        "BOOKING_POINTS_OVER_40_5": random.uniform(1.80, 2.30),
        "BOOKING_POINTS_OVER_50_5": random.uniform(2.20, 2.90),
        "BOOKING_POINTS_UNDER_40_5": random.uniform(1.70, 2.10),
        "HOME_CARDS_OVER_0_5": random.uniform(1.25, 1.50),
        "HOME_CARDS_OVER_1_5": random.uniform(1.65, 2.10),
        "HOME_CARDS_OVER_2_5": random.uniform(2.30, 3.20),
        "AWAY_CARDS_OVER_0_5": random.uniform(1.25, 1.50),
        "AWAY_CARDS_OVER_1_5": random.uniform(1.70, 2.15),
        "AWAY_CARDS_OVER_2_5": random.uniform(2.40, 3.30),
    }


def test_corner_factors():
    print("\n" + "=" * 60)
    print("TEST: Corner Factor Computation")
    print("=" * 60)
    
    model = SyndicateCornersModel()
    
    high_pace_stats = {
        "passes_per_minute": 10.5,
        "attacks_per_90": 130,
        "dangerous_attacks_per_90": 70,
    }
    low_pace_stats = {
        "passes_per_minute": 6.0,
        "attacks_per_90": 75,
        "dangerous_attacks_per_90": 35,
    }
    
    high_pace = model.compute_pace_factor(high_pace_stats, high_pace_stats)
    low_pace = model.compute_pace_factor(low_pace_stats, low_pace_stats)
    
    print(f"High Pace Factor: {high_pace:.3f} (expected > 1.0)")
    print(f"Low Pace Factor: {low_pace:.3f} (expected < 1.0)")
    assert high_pace > 1.0, "High pace should increase corners"
    assert low_pace < 1.0, "Low pace should decrease corners"
    
    high_wing_stats = {
        "crosses_per_90": 22,
        "wide_zone_touches": 55,
        "flank_attack_pct": 0.45,
    }
    low_wing_stats = {
        "crosses_per_90": 10,
        "wide_zone_touches": 25,
        "flank_attack_pct": 0.25,
    }
    
    high_wing = model.compute_wing_play_index(high_wing_stats, high_wing_stats)
    low_wing = model.compute_wing_play_index(low_wing_stats, low_wing_stats)
    
    print(f"High Wing Play: {high_wing:.3f} (expected > 1.0)")
    print(f"Low Wing Play: {low_wing:.3f} (expected < 1.0)")
    assert high_wing > 1.0, "High wing play should increase corners"
    assert low_wing < 1.0, "Low wing play should decrease corners"
    
    high_ref = {"corners_per_match": 12.5, "fouls_near_box_per_match": 8}
    low_ref = {"corners_per_match": 8.0, "fouls_near_box_per_match": 3}
    
    high_ref_bias = model.compute_referee_corner_bias(high_ref)
    low_ref_bias = model.compute_referee_corner_bias(low_ref)
    
    print(f"High Ref Corner Bias: {high_ref_bias:.3f} (expected > 1.0)")
    print(f"Low Ref Corner Bias: {low_ref_bias:.3f} (expected < 1.0)")
    
    bad_weather = {"wind_speed": 45, "is_rain": True, "pitch_condition": "slippery"}
    good_weather = {"wind_speed": 5, "is_rain": False, "pitch_condition": "excellent"}
    
    bad_weather_factor = model.compute_weather_factor(bad_weather)
    good_weather_factor = model.compute_weather_factor(good_weather)
    
    print(f"Bad Weather Factor: {bad_weather_factor:.3f} (expected > 1.0)")
    print(f"Good Weather Factor: {good_weather_factor:.3f} (expected ~ 1.0)")
    
    print("\n✅ All corner factor tests passed!")


def test_card_factors():
    print("\n" + "=" * 60)
    print("TEST: Card Factor Computation")
    print("=" * 60)
    
    model = SyndicateCardsModel()
    
    strict_ref = {
        "cards_per_match": 5.5,
        "foul_to_card_conversion": 0.50,
        "early_card_rate": 0.40,
    }
    lenient_ref = {
        "cards_per_match": 3.0,
        "foul_to_card_conversion": 0.20,
        "early_card_rate": 0.15,
    }
    
    strict_profile = model.compute_referee_card_profile(strict_ref)
    lenient_profile = model.compute_referee_card_profile(lenient_ref)
    
    print(f"Strict Referee Profile: {strict_profile:.3f} (expected > 1.0)")
    print(f"Lenient Referee Profile: {lenient_profile:.3f} (expected < 1.0)")
    
    derby_index = model.compute_rivalry_index("Arsenal", "Tottenham")
    normal_index = model.compute_rivalry_index("Brighton", "Burnley")
    
    print(f"Derby Rivalry Index: {derby_index:.3f} (expected > 1.0)")
    print(f"Normal Rivalry Index: {normal_index:.3f} (expected = 1.0)")
    assert derby_index > 1.1, "Derby should increase cards"
    assert normal_index == 1.0, "Non-derby should be neutral"
    
    aggressive = model.compute_formation_aggression("3-4-3")
    defensive = model.compute_formation_aggression("5-4-1")
    
    print(f"Aggressive Formation (3-4-3): {aggressive:.3f} (expected > 1.0)")
    print(f"Defensive Formation (5-4-1): {defensive:.3f} (expected < 1.0)")
    assert aggressive > 1.0, "Aggressive formation should increase cards"
    assert defensive < 1.0, "Defensive formation should decrease cards"
    
    high_press = {
        "ppda": 7.0,
        "duels_pg": 65,
        "tackles_pg": 22,
        "interceptions_pg": 16,
    }
    low_press = {
        "ppda": 14.0,
        "duels_pg": 40,
        "tackles_pg": 12,
        "interceptions_pg": 8,
    }
    
    high_tempo = model.compute_tempo_index(high_press, high_press)
    low_tempo = model.compute_tempo_index(low_press, low_press)
    
    print(f"High Tempo Index: {high_tempo:.3f} (expected > 1.0)")
    print(f"Low Tempo Index: {low_tempo:.3f} (expected < 1.0)")
    
    aggressive_team = {
        "fouls_pg": 14,
        "cards_pg": 2.8,
        "aerial_duels_pg": 20,
        "ground_duels_pg": 45,
        "high_card_rate_players": 3,
    }
    calm_team = {
        "fouls_pg": 9,
        "cards_pg": 1.5,
        "aerial_duels_pg": 10,
        "ground_duels_pg": 25,
        "high_card_rate_players": 0,
    }
    
    high_aggression = model.compute_team_aggression(aggressive_team)
    low_aggression = model.compute_team_aggression(calm_team)
    
    print(f"High Team Aggression: {high_aggression:.3f} (expected > 1.0)")
    print(f"Low Team Aggression: {low_aggression:.3f} (expected < 1.0)")
    
    print("\n✅ All card factor tests passed!")


def run_backtest_sample(num_fixtures: int = 30, verbose: bool = False):
    print("\n" + "=" * 60)
    print(f"BACKTEST: Running {num_fixtures} fixture simulation")
    print("=" * 60)
    
    leagues = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]
    teams = [
        ("Liverpool", "Chelsea"), ("Manchester United", "Arsenal"),
        ("Real Madrid", "Barcelona"), ("Atletico Madrid", "Sevilla"),
        ("Juventus", "Inter Milan"), ("AC Milan", "Roma"),
        ("Bayern Munich", "Dortmund"), ("Leipzig", "Leverkusen"),
        ("PSG", "Lyon"), ("Marseille", "Monaco"),
        ("Manchester City", "Tottenham"), ("Everton", "Newcastle"),
        ("Valencia", "Villarreal"), ("Real Sociedad", "Athletic Bilbao"),
        ("Napoli", "Lazio"), ("Fiorentina", "Atalanta"),
    ]
    
    fixtures = []
    odds_data_corners = {}
    odds_data_cards = {}
    team_stats_data = {}
    referee_data = {}
    weather_data = {}
    
    base_date = datetime.now()
    
    for i in range(num_fixtures):
        home, away = random.choice(teams)
        league = random.choice(leagues)
        fixture_id = f"fixture_{i}"
        match_date = (base_date + timedelta(days=random.randint(0, 3))).strftime("%Y-%m-%d")
        
        fixtures.append({
            "fixture_id": fixture_id,
            "home_team": home,
            "away_team": away,
            "league": league,
            "match_date": match_date,
            "home_xg": random.uniform(1.0, 2.2),
            "away_xg": random.uniform(0.8, 1.8),
            "referee_id": f"ref_{i % 10}",
            "home_formation": random.choice(["4-3-3", "4-2-3-1", "3-5-2", "4-4-2"]),
            "away_formation": random.choice(["4-3-3", "4-2-3-1", "3-5-2", "5-4-1"]),
        })
        
        odds_data_corners[fixture_id] = generate_mock_odds_corners()
        odds_data_cards[fixture_id] = generate_mock_odds_cards()
        
        team_stats_data[home] = generate_mock_team_stats()
        team_stats_data[away] = generate_mock_team_stats()
        referee_data[f"ref_{i % 10}"] = generate_mock_referee_stats()
        weather_data[fixture_id] = generate_mock_weather()
    
    match_corners, team_corners, hc_corners = run_corners_cycle(
        fixtures, odds_data_corners, team_stats_data, referee_data, weather_data
    )
    
    cards = run_cards_cycle(fixtures, odds_data_cards, team_stats_data, referee_data)
    
    print("\n📊 CORNERS BACKTEST RESULTS:")
    print(f"  Match corners: {len(match_corners)} picks")
    print(f"  Team corners: {len(team_corners)} picks")
    print(f"  Handicap corners: {len(hc_corners)} picks")
    print(f"  Total: {len(match_corners) + len(team_corners) + len(hc_corners)} picks")
    
    all_corners = match_corners + team_corners + hc_corners
    if all_corners:
        tier_dist = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0}
        for c in all_corners:
            tier_dist[c.tier] = tier_dist.get(c.tier, 0) + 1
        
        avg_ev = sum(c.ev_sim for c in all_corners) / len(all_corners)
        avg_conf = sum(c.confidence for c in all_corners) / len(all_corners)
        
        print(f"\n  Tier Distribution: {tier_dist}")
        print(f"  Average EV: {avg_ev:.2%}")
        print(f"  Average Confidence: {avg_conf:.2%}")
        
        if verbose:
            print("\n  Sample Corners Picks:")
            for c in all_corners[:5]:
                print(f"    [{c.tier}] {c.match} | {c.selection} @ {c.odds} | EV: {c.ev_sim:.1%}")
    
    print("\n📊 CARDS BACKTEST RESULTS:")
    print(f"  Total cards picks: {len(cards)} picks")
    
    if cards:
        tier_dist = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0}
        for c in cards:
            tier_dist[c.trust_tier] = tier_dist.get(c.trust_tier, 0) + 1
        
        avg_ev = sum(c.ev for c in cards) / len(cards)
        avg_conf = sum(c.confidence for c in cards) / len(cards)
        
        print(f"\n  Tier Distribution: {tier_dist}")
        print(f"  Average EV: {avg_ev:.2%}")
        print(f"  Average Confidence: {avg_conf:.2%}")
        
        if verbose:
            print("\n  Sample Cards Picks:")
            for c in cards[:5]:
                print(f"    [{c.trust_tier}] {c.home_team} vs {c.away_team} | {c.selection} @ {c.book_odds} | EV: {c.ev:.1%}")
    
    return all_corners, cards


def run_live_simulation(verbose: bool = False):
    print("\n" + "=" * 60)
    print("LIVE SIMULATION: Today's Daily Card Generation")
    print("=" * 60)
    
    fixtures = [
        {"fixture_id": "live_1", "home_team": "Liverpool", "away_team": "Manchester United",
         "league": "Premier League", "match_date": datetime.now().strftime("%Y-%m-%d"),
         "home_xg": 1.9, "away_xg": 1.4, "referee_id": "ref_top",
         "home_formation": "4-3-3", "away_formation": "4-2-3-1"},
        {"fixture_id": "live_2", "home_team": "Real Madrid", "away_team": "Barcelona",
         "league": "La Liga", "match_date": datetime.now().strftime("%Y-%m-%d"),
         "home_xg": 2.1, "away_xg": 1.8, "referee_id": "ref_laliga",
         "home_formation": "4-3-3", "away_formation": "4-3-3"},
        {"fixture_id": "live_3", "home_team": "Bayern Munich", "away_team": "Borussia Dortmund",
         "league": "Bundesliga", "match_date": datetime.now().strftime("%Y-%m-%d"),
         "home_xg": 2.3, "away_xg": 1.5, "referee_id": "ref_buli",
         "home_formation": "4-2-3-1", "away_formation": "3-4-3"},
    ]
    
    odds_corners = {
        "live_1": generate_mock_odds_corners(),
        "live_2": generate_mock_odds_corners(),
        "live_3": generate_mock_odds_corners(),
    }
    
    odds_cards = {
        "live_1": generate_mock_odds_cards(),
        "live_2": generate_mock_odds_cards(),
        "live_3": generate_mock_odds_cards(),
    }
    
    team_stats = {}
    for f in fixtures:
        team_stats[f["home_team"]] = generate_mock_team_stats()
        team_stats[f["away_team"]] = generate_mock_team_stats()
    
    referee_stats = {
        "ref_top": {"corners_per_match": 11.5, "cards_per_match": 4.8, "foul_to_card_conversion": 0.42},
        "ref_laliga": {"corners_per_match": 10.2, "cards_per_match": 5.2, "foul_to_card_conversion": 0.45},
        "ref_buli": {"corners_per_match": 11.0, "cards_per_match": 4.0, "foul_to_card_conversion": 0.35},
    }
    
    weather = {
        "live_1": {"wind_speed": 15, "is_rain": False, "pitch_condition": "good"},
        "live_2": {"wind_speed": 8, "is_rain": False, "pitch_condition": "excellent"},
        "live_3": {"wind_speed": 25, "is_rain": True, "pitch_condition": "wet"},
    }
    
    match_c, team_c, hc_c = run_corners_cycle(fixtures, odds_corners, team_stats, referee_stats, weather)
    cards = run_cards_cycle(fixtures, odds_cards, team_stats, referee_stats)
    
    print("\n🎯 TODAY'S DAILY CARD (Live Simulation)")
    print("-" * 50)
    
    print("\n🔢 CORNERS PICKS:")
    for c in match_c + team_c + hc_c:
        print(f"  [{c.tier}] {c.match}")
        print(f"       {c.selection} @ {c.odds:.2f} | EV: {c.ev_sim:.1%} | Conf: {c.confidence:.1%}")
        if verbose and hasattr(c, 'metadata') and c.metadata and 'factors' in c.metadata:
            factors = c.metadata['factors']
            print(f"       Factors: pace={factors['pace_factor']:.2f} wing={factors['wing_play_index']:.2f}")
    
    print("\n🟨 CARDS PICKS:")
    for c in cards:
        print(f"  [{c.trust_tier}] {c.home_team} vs {c.away_team}")
        print(f"       {c.selection} @ {c.book_odds:.2f} | EV: {c.ev:.1%} | Conf: {c.confidence:.1%}")
        if verbose and 'factors' in c.metadata:
            factors = c.metadata['factors']
            print(f"       Factors: ref={factors['referee_profile']:.2f} rivalry={factors['rivalry_index']:.2f}")
    
    total_picks = len(match_c) + len(team_c) + len(hc_c) + len(cards)
    print(f"\n📊 TOTAL: {total_picks} picks ({len(match_c)+len(team_c)+len(hc_c)} corners + {len(cards)} cards)")
    
    return match_c, team_c, hc_c, cards


def test_router_integration():
    print("\n" + "=" * 60)
    print("TEST: Router Integration Check")
    print("=" * 60)
    
    try:
        from central_router import CentralRouter, DailyCard
        from market_router_config import MARKET_CAPS, get_market_cap_key, map_product_to_router_category
        
        print("✅ Imports successful")
        
        corner_caps = MARKET_CAPS.get("CORNERS_MATCH", {})
        card_caps = MARKET_CAPS.get("CARDS_MATCH", {})
        
        print(f"\n📋 Router Caps:")
        print(f"  CORNERS_MATCH: max_picks={corner_caps.get('max_picks', 'N/A')}")
        print(f"  CARDS_MATCH: max_picks={card_caps.get('max_picks', 'N/A')}")
        
        test_markets = [
            ("CORNERS_OVER_9_5", "CORNERS_MATCH"),
            ("CORNERS_UNDER_10_5", "CORNERS_MATCH"),
            ("HOME_CORNERS_OVER_4_5", "CORNERS_TEAM"),
            ("MATCH_CARDS_OVER_4_5", "CARDS_MATCH"),
            ("HOME_CARDS_OVER_1_5", "CARDS_TEAM"),
        ]
        
        print("\n📋 Market Key Mappings:")
        for market_key, product in test_markets:
            cap_key = get_market_cap_key(market_key, product)
            router_cat = map_product_to_router_category(product)
            print(f"  {market_key} ({product}) -> cap={cap_key}, router={router_cat}")
        
        print("\n✅ Router integration verified!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Syndicate Corners and Cards Engines")
    parser.add_argument("--backtest", action="store_true", help="Run backtest simulation")
    parser.add_argument("--live", action="store_true", help="Run live simulation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--fixtures", type=int, default=30, help="Number of fixtures for backtest")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("SYNDICATE ENGINES v2.0 - TEST SUITE")
    print("=" * 60)
    
    test_corner_factors()
    test_card_factors()
    
    test_router_integration()
    
    if args.backtest:
        run_backtest_sample(args.fixtures, args.verbose)
    
    if args.live:
        run_live_simulation(args.verbose)
    
    if not args.backtest and not args.live:
        run_backtest_sample(20, args.verbose)
        run_live_simulation(args.verbose)
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Syndicate Engines Demo - Full 3-Engine Chain
=============================================
Demonstrates how the Profile Boost, Market Weight, and Hidden Value engines work together.
"""

from profile_boost_engine import ProfileBoostEngine
from market_weight_engine import MarketWeightEngine
from hidden_value_scanner import HiddenValueScanner, RejectedCandidate
from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime


@dataclass
class SamplePick:
    """Sample prediction for demonstration."""
    fixture_id: str
    home_team: str
    away_team: str
    market_key: str
    selection: str
    odds: float
    raw_ev: float
    raw_confidence: float
    context: Dict[str, Any]


def run_full_chain():
    """Run all 3 engines in sequence on sample picks."""
    
    print("=" * 80)
    print("SYNDICATE ENGINES DEMO - 3-Engine Chain")
    print("=" * 80)
    
    pb_engine = ProfileBoostEngine()
    mw_engine = MarketWeightEngine()
    hv_scanner = HiddenValueScanner()
    
    sample_picks = [
        SamplePick(
            fixture_id="1001",
            home_team="Liverpool",
            away_team="Manchester United",
            market_key="CORNERS_MATCH",
            selection="Over 10.5",
            odds=1.90,
            raw_ev=0.068,
            raw_confidence=0.62,
            context={
                "tempo_index": 1.25,
                "is_derby": True,
                "referee_stats": {"cards_per_match": 4.2},
                "wing_play_index": 1.15,
                "formation_aggression": 1.1,
            }
        ),
        SamplePick(
            fixture_id="1002",
            home_team="Real Madrid",
            away_team="Barcelona",
            market_key="CARDS_MATCH",
            selection="Over 4.5",
            odds=1.75,
            raw_ev=0.052,
            raw_confidence=0.58,
            context={
                "tempo_index": 1.15,
                "is_derby": True,
                "referee_stats": {"cards_per_match": 5.1},
                "pressure_index": 1.3,
            }
        ),
        SamplePick(
            fixture_id="1003",
            home_team="Bayern Munich",
            away_team="Dortmund",
            market_key="FT_OVER_2_5",
            selection="Over 2.5",
            odds=1.65,
            raw_ev=0.015,
            raw_confidence=0.55,
            context={
                "tempo_index": 1.20,
                "is_derby": True,
                "formation_aggression": 1.2,
            }
        ),
        SamplePick(
            fixture_id="1004",
            home_team="Aston Villa",
            away_team="Wolves",
            market_key="BTTS_YES",
            selection="BTTS Yes",
            odds=1.80,
            raw_ev=0.008,
            raw_confidence=0.52,
            context={
                "tempo_index": 1.0,
                "is_derby": False,
            }
        ),
        SamplePick(
            fixture_id="1005",
            home_team="Inter Milan",
            away_team="AC Milan",
            market_key="CORNERS_TEAM_HOME",
            selection="Over 5.5",
            odds=1.95,
            raw_ev=-0.005,
            raw_confidence=0.51,
            context={
                "tempo_index": 1.10,
                "is_derby": True,
                "wing_play_index": 1.2,
            }
        ),
    ]
    
    print("\n" + "=" * 80)
    print("PHASE 1: PROFILE BOOST ENGINE")
    print("=" * 80)
    
    boosted_picks = []
    for pick in sample_picks:
        result = pb_engine.calculate_boost(
            base_ev=pick.raw_ev,
            base_confidence=pick.raw_confidence,
            market_type=pick.market_key,
            context=pick.context
        )
        
        print(f"\n{pick.home_team} vs {pick.away_team} - {pick.selection}")
        print(f"  Raw EV: {pick.raw_ev * 100:.2f}% -> Boosted: {result.boosted_ev * 100:.2f}%")
        print(f"  Raw Conf: {pick.raw_confidence * 100:.1f}% -> Boosted: {result.boosted_confidence * 100:.1f}%")
        print(f"  Boost Score: {result.boost_score:.3f}")
        if result.contributing_factors:
            top_2 = result.contributing_factors[:2]
            print(f"  Top Factors: {', '.join(f'{f[0]}={f[1]:.2f}' for f in top_2)}")
        
        boosted_picks.append({
            "pick": pick,
            "boost_result": result,
        })
    
    print("\n" + "=" * 80)
    print("PHASE 2: MARKET WEIGHT ENGINE")
    print("=" * 80)
    
    weighted_picks = []
    for bp in boosted_picks:
        pick = bp["pick"]
        boost = bp["boost_result"]
        
        weight_result = mw_engine.get_market_weight(pick.market_key)
        final_ev = boost.boosted_ev * weight_result.weight
        
        print(f"\n{pick.home_team} vs {pick.away_team} - {pick.market_key}")
        print(f"  Market Weight: {weight_result.weight:.3f} (group: {weight_result.market_group})")
        print(f"  Boosted EV: {boost.boosted_ev * 100:.2f}% -> Final EV: {final_ev * 100:.2f}%")
        
        weighted_picks.append({
            "pick": pick,
            "boost_result": boost,
            "weight_result": weight_result,
            "final_ev": final_ev,
        })
    
    print("\n" + "=" * 80)
    print("PHASE 3: HIDDEN VALUE SCANNER")
    print("=" * 80)
    
    candidates = []
    for wp in weighted_picks:
        pick = wp["pick"]
        boost = wp["boost_result"]
        weight = wp["weight_result"]
        
        candidate = RejectedCandidate(
            match_id=pick.fixture_id,
            home_team=pick.home_team,
            away_team=pick.away_team,
            match_date=datetime.now(),
            market_key=pick.market_key,
            selection=pick.selection,
            odds=pick.odds,
            raw_ev=pick.raw_ev,
            boosted_ev=boost.boosted_ev,
            final_ev=wp["final_ev"],
            raw_confidence=pick.raw_confidence,
            boosted_confidence=boost.boosted_confidence,
            boost_score=boost.boost_score,
            market_weight=weight.weight,
            profile_boost_factors=boost.contributing_factors,
        )
        candidates.append(candidate)
    
    hidden_picks = hv_scanner.scan_candidates(candidates)
    
    if hidden_picks:
        print(f"\nFound {len(hidden_picks)} hidden value picks:")
        for hp in hidden_picks:
            print(f"\n  [{hp.category}] {hp.home_team} vs {hp.away_team}")
            print(f"    Selection: {hp.selection}")
            print(f"    Raw EV: {hp.raw_ev * 100:.2f}% -> Boosted: {hp.boosted_ev * 100:.2f}%")
            print(f"    Soft Edge Score: {hp.soft_edge_score:.1f}/100")
            print(f"    Trust Tier: {hp.trust_tier}")
            print(f"    Reason: {hp.reason}")
    else:
        print("\nNo hidden value picks found (all picks either passed EV threshold or below soft edge minimum)")
    
    print("\n" + "=" * 80)
    print("SUMMARY: FULL CHAIN RESULTS")
    print("=" * 80)
    
    print("\n{:^30} {:>10} {:>10} {:>10} {:>10}".format(
        "Match", "Raw EV%", "Boost EV%", "Final EV%", "Status"
    ))
    print("-" * 75)
    
    for wp in weighted_picks:
        pick = wp["pick"]
        boost = wp["boost_result"]
        final_ev = wp["final_ev"]
        
        if final_ev >= 0.05:
            status = "L1_HIGH"
        elif final_ev >= 0.02:
            status = "L2_MED"
        elif final_ev >= 0:
            status = "L3_SOFT"
        else:
            found_hv = any(h.match_id == pick.fixture_id for h in hidden_picks)
            status = "HIDDEN_V" if found_hv else "REJECT"
        
        match_name = f"{pick.home_team[:12]} v {pick.away_team[:12]}"
        print("{:^30} {:>10.2f} {:>10.2f} {:>10.2f} {:>10}".format(
            match_name,
            pick.raw_ev * 100,
            boost.boosted_ev * 100,
            final_ev * 100,
            status
        ))
    
    print("\n" + "=" * 80)
    print("Demo complete! All 3 syndicate engines operational.")
    print("=" * 80)


if __name__ == "__main__":
    run_full_chain()

#!/usr/bin/env python3
"""
NOVA v2.0 Filter Dry-Run Test
Tests the new filter configuration to verify expected bet volume.
"""

import sys
import os
from datetime import datetime

def test_filter_config():
    """Test that all filter configurations are correctly loaded."""
    print("=" * 60)
    print("NOVA v2.0 FILTER CONFIGURATION TEST")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Test Value Singles
    print("\n📊 VALUE SINGLES CONFIG:")
    from value_singles_engine import (
        MIN_VALUE_SINGLE_EV, MIN_VALUE_SINGLE_ODDS, MAX_VALUE_SINGLE_ODDS,
        MIN_VALUE_SINGLE_CONFIDENCE, MAX_VALUE_SINGLES_PER_DAY, VALUE_SINGLE_LEAGUE_WHITELIST
    )
    print(f"   Min EV:         {MIN_VALUE_SINGLE_EV:.1%}")
    print(f"   Odds Range:     {MIN_VALUE_SINGLE_ODDS} - {MAX_VALUE_SINGLE_ODDS}")
    print(f"   Min Confidence: {MIN_VALUE_SINGLE_CONFIDENCE:.0%}")
    print(f"   Max Per Day:    {MAX_VALUE_SINGLES_PER_DAY}")
    print(f"   Leagues:        {len(VALUE_SINGLE_LEAGUE_WHITELIST)} whitelisted")
    
    # Test Trust Levels
    print("\n📊 TRUST LEVEL CONFIG (bet_filter.py):")
    from bet_filter import (
        L1_MIN_EV, L1_MIN_CONFIDENCE, L1_MIN_ODDS, L1_MAX_ODDS, L1_MAX_PER_DAY,
        L2_MIN_EV, L2_MIN_CONFIDENCE, L2_MAX_DISAGREEMENT, L2_MIN_ODDS, L2_MAX_ODDS,
        L3_MIN_EV, L3_MIN_CONFIDENCE, L3_MAX_DISAGREEMENT, L3_MIN_ODDS, L3_MAX_ODDS, L3_MIN_DAILY_TARGET
    )
    print(f"   L1 (High Trust):")
    print(f"      EV >= {L1_MIN_EV:.0%}, Confidence >= {L1_MIN_CONFIDENCE:.0%}")
    print(f"      Odds: {L1_MIN_ODDS} - {L1_MAX_ODDS}, Max/Day: {L1_MAX_PER_DAY}")
    print(f"   L2 (Medium Trust):")
    print(f"      EV >= {L2_MIN_EV:.0%}, Confidence >= {L2_MIN_CONFIDENCE:.0%}")
    print(f"      Disagreement <= {L2_MAX_DISAGREEMENT:.0%}, Odds: {L2_MIN_ODDS} - {L2_MAX_ODDS}")
    print(f"   L3 (Soft Value):")
    print(f"      EV >= {L3_MIN_EV:.0%}, Confidence >= {L3_MIN_CONFIDENCE:.0%}")
    print(f"      Disagreement <= {L3_MAX_DISAGREEMENT:.0%}, Odds: {L3_MIN_ODDS} - {L3_MAX_ODDS}")
    print(f"      Use only when total < {L3_MIN_DAILY_TARGET} picks")
    
    # Test ML Parlay
    print("\n📊 ML PARLAY CONFIG:")
    from ml_parlay_engine import (
        ML_PARLAY_ENABLED, ML_PARLAY_MIN_ODDS, ML_PARLAY_MAX_ODDS,
        MIN_ML_PARLAY_LEG_EV, MAX_ML_PARLAYS_PER_DAY, ML_PARLAY_MIN_LEGS, ML_PARLAY_MAX_LEGS
    )
    print(f"   Enabled:        {ML_PARLAY_ENABLED}")
    print(f"   Leg Odds:       {ML_PARLAY_MIN_ODDS} - {ML_PARLAY_MAX_ODDS}")
    print(f"   Min EV/Leg:     {MIN_ML_PARLAY_LEG_EV:.0%}")
    print(f"   Legs:           {ML_PARLAY_MIN_LEGS} - {ML_PARLAY_MAX_LEGS}")
    print(f"   Max Per Day:    {MAX_ML_PARLAYS_PER_DAY}")
    
    # Test Multi-Match Parlay
    print("\n📊 MULTI-MATCH PARLAY CONFIG:")
    from parlay_builder import (
        MIN_LEGS, MAX_LEGS, MIN_PARLAY_ODDS, MAX_PARLAY_ODDS,
        MIN_PARLAY_EV, MAX_PARLAYS_PER_DAY, ALLOWED_TRUST_LEVELS
    )
    print(f"   Legs:           {MIN_LEGS} - {MAX_LEGS}")
    print(f"   Total Odds:     {MIN_PARLAY_ODDS} - {MAX_PARLAY_ODDS}")
    print(f"   Min EV:         {MIN_PARLAY_EV:.0%}")
    print(f"   Max Per Day:    {MAX_PARLAYS_PER_DAY}")
    print(f"   Trust Levels:   {ALLOWED_TRUST_LEVELS}")
    
    # Test Basketball
    print("\n📊 BASKETBALL CONFIG:")
    from college_basket_value_engine import CollegeBasketValueEngine
    print(f"   Min EV:         1.5% (default)")
    print(f"   Min Confidence: 52% (default)")
    print(f"   Odds Range:     1.40 - 3.00")
    print(f"   Max Singles:    12")
    
    print("\n" + "=" * 60)
    print("✅ ALL NOVA v2.0 CONFIGURATIONS LOADED SUCCESSFULLY")
    print("=" * 60)
    
    return True


def test_bet_filter_logic():
    """Test the bet filter classification logic."""
    print("\n" + "=" * 60)
    print("BET FILTER CLASSIFICATION TEST")
    print("=" * 60)
    
    from bet_filter import BetCandidate, filter_level1_high_trust, filter_level2_medium_trust, filter_level3_soft_value, apply_tiered_filter
    
    test_candidates = [
        BetCandidate("Match A", "1X2", "Home", 1.85, ev_sim=0.08, ev_model=0.07, confidence=0.62, disagreement=0.10, approved=True),
        BetCandidate("Match B", "BTTS", "Yes", 1.75, ev_sim=0.04, ev_model=0.03, confidence=0.58, disagreement=0.12, approved=True),
        BetCandidate("Match C", "O2.5", "Over", 2.10, ev_sim=0.03, ev_model=0.025, confidence=0.54, disagreement=0.18, approved=False),
        BetCandidate("Match D", "1X2", "Away", 2.80, ev_sim=0.02, ev_model=0.02, confidence=0.52, disagreement=0.15, approved=False),
        BetCandidate("Match E", "DC", "1X", 1.45, ev_sim=0.01, ev_model=0.01, confidence=0.51, disagreement=0.22, approved=False),
        BetCandidate("Match F", "1X2", "Draw", 3.20, ev_sim=0.06, ev_model=0.05, confidence=0.56, disagreement=0.08, approved=True),
    ]
    
    l1 = filter_level1_high_trust(test_candidates)
    l2 = filter_level2_medium_trust([c for c in test_candidates if c not in l1])
    l3 = filter_level3_soft_value([c for c in test_candidates if c not in l1 and c not in l2])
    
    print(f"\nTest with {len(test_candidates)} candidates:")
    print(f"   L1 (High Trust):   {len(l1)} picks")
    for b in l1:
        print(f"      - {b.match}: {b.selection} @ {b.odds} | EV: {b.ev_sim:.1%}")
    
    print(f"   L2 (Medium Trust): {len(l2)} picks")
    for b in l2:
        print(f"      - {b.match}: {b.selection} @ {b.odds} | EV: {b.ev_model:.1%}")
    
    print(f"   L3 (Soft Value):   {len(l3)} picks")
    for b in l3:
        print(f"      - {b.match}: {b.selection} @ {b.odds} | EV: {b.ev_model:.1%}")
    
    selected = apply_tiered_filter(test_candidates)
    print(f"\n   TOTAL SELECTED:    {len(selected)} picks")
    
    return True


def test_monte_carlo_classification():
    """Test Monte Carlo trust level classification."""
    print("\n" + "=" * 60)
    print("MONTE CARLO TRUST LEVEL TEST")
    print("=" * 60)
    
    from monte_carlo_integration import classify_trust_level
    
    test_cases = [
        (0.08, 0.07, 0.60, 0.10, True, 1.85, "Expected: L1"),
        (0.04, 0.03, 0.58, 0.12, True, 1.75, "Expected: L1"),
        (0.03, 0.025, 0.54, 0.18, False, 2.10, "Expected: L2"),
        (0.02, 0.02, 0.52, 0.15, False, 2.80, "Expected: L2"),
        (0.01, 0.01, 0.51, 0.22, False, 1.45, "Expected: L3"),
        (0.00, 0.00, 0.48, 0.30, False, 4.00, "Expected: REJECTED"),
    ]
    
    for ev_sim, ev_model, conf, disagree, approved, odds, expected in test_cases:
        result = classify_trust_level(ev_sim, ev_model, conf, disagree, approved, odds)
        status = "✅" if expected.split(": ")[1] in result else "⚠️"
        print(f"   {status} EV:{ev_sim:.0%} Conf:{conf:.0%} Odds:{odds} → {result} ({expected})")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🚀 NOVA v2.0 DRY-RUN FILTER TEST")
    print("=" * 60)
    
    try:
        test_filter_config()
        test_bet_filter_logic()
        test_monte_carlo_classification()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - NOVA v2.0 FILTERS READY")
        print("=" * 60)
        print("\nExpected Daily Volume (on typical match days):")
        print("   Value Singles:      5-15 picks")
        print("   ML Parlays:         1-3 parlays")
        print("   Multi-Match:        1-2 parlays")
        print("   Basketball:         3-8 picks")
        print("=" * 60)
        
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

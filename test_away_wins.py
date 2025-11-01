"""
Quick test to verify away win logic
Simulates Burnley vs Arsenal scenario
"""

# Burnley stats (weak home team)
home_goals_per_game = 0.8  # Weak attack
home_conceded_per_game = 1.8  # Weak defense
home_clean_sheet_rate = 15  # Rarely keeps clean sheets

# Arsenal stats (strong away team)
away_goals_per_game = 2.2  # Very strong attack
away_conceded_per_game = 0.5  # Strong defense  
away_clean_sheet_rate = 55  # Often keeps clean sheets

# Calculate match characteristics
home_very_strong_attack = home_goals_per_game > 2.0
home_weak_attack = home_goals_per_game < 1.0
home_very_weak_defense = home_conceded_per_game > 1.8

away_very_strong_attack = away_goals_per_game > 2.0
away_weak_attack = away_goals_per_game < 1.0
away_very_weak_defense = away_conceded_per_game > 1.8

both_score_regularly = home_goals_per_game >= 1.3 and away_goals_per_game >= 0.8

print("🏟️ BURNLEY vs ARSENAL TEST")
print("=" * 50)
print("\n📊 TEAM STATS:")
print(f"Burnley (Home): {home_goals_per_game}g/gm, {home_conceded_per_game} conceded/gm")
print(f"Arsenal (Away): {away_goals_per_game}g/gm, {away_conceded_per_game} conceded/gm")

print("\n🧠 MATCH CHARACTERISTICS:")
print(f"Home weak attack: {home_weak_attack}")
print(f"Away very strong attack: {away_very_strong_attack}")
print(f"Home weak defense: {home_very_weak_defense}")
print(f"Away clean sheet %: {away_clean_sheet_rate}%")

# Test score 0-2 (Arsenal away win)
print("\n🎯 TESTING SCORE: 0-2 (Arsenal wins)")
data_match_score = 0

if away_very_strong_attack:
    data_match_score += 40
    print(f"  ✅ Away very strong attack: +40 → {data_match_score}")
if home_weak_attack:
    data_match_score += 50
    print(f"  ✅ Home weak attack: +50 → {data_match_score}")
if away_clean_sheet_rate > 40:
    data_match_score += 30
    print(f"  ✅ Away keeps clean sheets: +30 → {data_match_score}")
if home_very_weak_defense and home_weak_attack:
    data_match_score += 25
    print(f"  ✅ Home weak defense + attack: +25 → {data_match_score}")

print(f"\n🏆 FINAL MATCH SCORE: {data_match_score}/200")
print(f"Threshold: 90 → {'✅ PASSES' if data_match_score >= 90 else '❌ FAILS'}")

# Test score 2-1 (Burnley home win) for comparison
print("\n🎯 TESTING SCORE: 2-1 (Burnley wins) - OLD SYSTEM")
data_match_score_21 = 0
if both_score_regularly:
    data_match_score_21 += 50
    print(f"  Both score regularly: {both_score_regularly} → {data_match_score_21}")
else:
    print(f"  Both score regularly: {both_score_regularly} → 0 (Arsenal 2.2, Burnley 0.8)")

print(f"\n🏆 FINAL MATCH SCORE: {data_match_score_21}/200")
print(f"Threshold: 90 → {'✅ PASSES' if data_match_score_21 >= 90 else '❌ FAILS'}")

print("\n" + "=" * 50)
print("🎯 RESULT: System should pick 0-2 (Arsenal) over 2-1 (Burnley)")
print(f"0-2 score: {data_match_score} vs 2-1 score: {data_match_score_21}")
print(f"Winner: {'0-2 ARSENAL ✅' if data_match_score > data_match_score_21 else '2-1 BURNLEY ❌'}")

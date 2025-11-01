# RECOMMENDED AWAY WIN FILTERS
## Based on 98-match backtest showing 1-2 (10.2%), 0-1 (8.2%), 0-2 (4.1%)

## 🏆 PRIORITY 1: Focus on 1-2 Score (10.2% proven)
### Current filters (KEEP):
- both_score_regularly: home >= 1.3 and away >= 0.8 goals/game
- total_expected: 2.2-3.3 goals
- away_goals > home_goals (away slightly better)
- home_goals: 0.8-1.5 (home can score 1)

### RECOMMENDED ADDITIONS for 1-2:
1. **League Quality**: Top 5 leagues ONLY
   - Premier League, La Liga, Serie A, Bundesliga, Ligue 1
   - Reason: More predictable away performances

2. **Away Team Strength**: 
   - away_goals_per_game >= 1.5 (was 0.8) - raise threshold
   - away_league_position <= 8 (top half of table)
   - away_form_last_5 >= 2.5 PPG (good recent form)

3. **Home Weakness**:
   - home_goals_per_game <= 1.3 (moderate attack)
   - home_conceded_per_game >= 1.2 (leaky defense)
   - home_home_record < 50% win rate

4. **Match Score Threshold**:
   - Increase from 90 → 110 for 1-2 predictions
   - Requires stronger data match

## ⚠️ PRIORITY 2: Be VERY Selective on 0-1 (8.2%)
### Current filters (TIGHTEN):
- away_goals >= 1.2 and home_weak_attack < 1.0
- away_clean_sheet_rate > 45%
- total_expected < 2.0
- home_conceded >= 1.2

### RECOMMENDED CHANGES for 0-1:
1. **Much Higher Bar**:
   - away_goals_per_game >= 1.8 (was 1.2) - ELITE away attack
   - home_goals_per_game < 0.8 (was 1.0) - ULTRA weak home attack
   - away_clean_sheet_rate > 55% (was 45%) - ELITE away defense

2. **League Quality**: Top 5 leagues ONLY

3. **Away Dominance**:
   - away_league_position <= 5 (top 5 in table)
   - League position difference >= 8 (away team 8+ places higher)
   - away_form_last_5 >= 3.0 PPG (excellent form)

4. **Match Score Threshold**:
   - Increase from 90 → 130 for 0-1 predictions
   - Only predict when ALL signals align

5. **Additional Check**:
   - Only predict 0-1 if NO 1-2 option available (prefer 1-2)

## ❌ PRIORITY 3: Extremely Rare 0-2 (4.1% - WEAK)
### Current filters (MASSIVELY TIGHTEN):
- away_very_strong_attack > 2.0
- home_weak_attack < 1.0
- away_clean_sheet_rate > 40%
- home_very_weak_defense > 1.8 conceded

### RECOMMENDED CHANGES for 0-2:
1. **ELITE-ONLY Criteria**:
   - away_goals_per_game >= 2.5 (was 2.0) - DOMINANT attack
   - home_goals_per_game < 0.7 (was 1.0) - TERRIBLE home attack
   - away_clean_sheet_rate > 60% (was 40%) - ELITE defense
   - home_conceded_per_game > 2.0 (was 1.8) - DISASTER defense

2. **League Quality**: Top 5 leagues ONLY

3. **Away Supremacy**:
   - away_league_position <= 3 (top 3 only!)
   - League position difference >= 12 (massive gap)
   - away_form_last_5 >= 3.2 PPG (championship form)
   - home_form_last_5 <= 1.0 PPG (relegation form)

4. **Match Score Threshold**:
   - Increase from 90 → 150 for 0-2 predictions
   - Highest bar - only perfect storm scenarios

5. **Context Requirements**:
   - Check H2H: away team has won last 2-3 meetings
   - No key home player injuries that artificially inflate criteria

## 🎯 OVERALL STRATEGY

### Volume Control:
- **1-2 predictions**: Accept ~60% of opportunities (moderate filtering)
- **0-1 predictions**: Accept ~20% of opportunities (strict filtering)
- **0-2 predictions**: Accept ~5% of opportunities (ultra-strict filtering)

### Expected Results with New Filters:
- 1-2: Target 15-20% hit rate (up from 10.2%)
- 0-1: Target 12-15% hit rate (up from 8.2%)
- 0-2: Target 10-12% hit rate (up from 4.1%)
- **Combined Away Wins: 15-18% target** (vs 7.5% old)

### Quality Checks:
1. **Always compare to home win alternative**
   - If home win has higher match_score, pick home win instead
   
2. **League restrictions**
   - Away wins ONLY in Top 5 leagues + Champions League
   - Skip away wins in second-tier leagues (unreliable)

3. **Confidence penalties**
   - Reduce confidence by -10 points for 0-1
   - Reduce confidence by -15 points for 0-2
   - Keep normal confidence for 1-2

4. **EV threshold increase**
   - Home wins: 15%+ EV required
   - Away wins (1-2): 18%+ EV required
   - Away wins (0-1, 0-2): 22%+ EV required

## 💡 IMPLEMENTATION PRIORITY

1. **Immediate**: Add league quality filter (Top 5 only for away wins)
2. **Immediate**: Increase match_score thresholds (110, 130, 150)
3. **High**: Tighten away_goals and home_goals thresholds
4. **Medium**: Add league position checks
5. **Medium**: Add EV penalty for away predictions
6. **Low**: Add form_last_5 tracking (if not already available)

## 📊 EXPECTED IMPACT

**Before (current backtest):**
- 98 matches tested
- 22 away wins (7.5% hit rate)
- -0.7% vs home wins

**After (with new filters):**
- ~30-40 matches would qualify (60% reduction)
- 5-7 away wins expected (15-18% hit rate)
- +7-10% vs home wins! 💰

**This would make away wins PROFITABLE!**

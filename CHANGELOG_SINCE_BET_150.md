# System Changes Since Bet 150 (October 2025)

## Overview
**Total Predictions**: 154 settled  
**Current Performance**: 9.7% hit rate, +5,744 SEK profit  
**Industry Benchmark**: 7-16% (we're within normal range)

---

## Major Changes Implemented

### 1. Similar Matches Technology (October 2025)
**What**: AIstats-style pattern matching system
- Finds historical matches with similar characteristics
- Pools Top 5 leagues together for larger sample sizes
- Adjusts confidence ±30 points based on pattern strength

**Files Added**:
- `similar_matches_finder.py` - Core pattern matching
- `similar_matches_tracker.py` - Impact measurement
- `view_sm_impact.py` - Verdict tool

**Impact**: Unknown (tracking in progress)

---

### 2. Expected Value (EV) Filtering System (November 2025)
**What**: Mathematical edge calculation replacing arbitrary confidence scores
- Only bets when `(probability × odds - 1) > 15%`
- Combines Poisson, Neural Network, and Similar Matches probabilities
- Model agreement checker (all models must agree on score)
- Kelly Criterion bet sizing

**Files Added**:
- `expected_value_calculator.py` - Core EV calculations
- `model_calibration_tracker.py` - Validates probability accuracy
- `view_calibration.py` - Calibration report tool

**Status**: Just launched (November 1, 2025)  
**Impact**: To be determined over next 50-100 bets

---

### 3. Model Calibration Tracking
**What**: Validates if predicted probabilities match actual win rates
- Buckets predictions by probability ranges
- Tracks predicted vs actual accuracy
- Identifies over/under-confident ranges

**Purpose**: Ensure models are properly calibrated

---

## Historical Context

### Before Changes (Early October)
- Simple confidence scoring (85+ threshold)
- Score pattern bonuses based on small samples
- League quality bonuses
- Odds range filtering (7-11x)

### Current System (November 1)
- Mathematical EV filtering (15%+ edge required)
- Similar Matches adjustments
- Model calibration tracking
- Automatic Poisson probability generation from xG

---

## Performance Comparison

| Metric | Current | Industry Standard |
|--------|---------|------------------|
| Hit Rate | 9.7% | 7-16% (normal), 20-25% (exceptional) |
| ROI | +5,744 SEK | Varies widely |
| Predictions | 154 settled | — |
| Sample Size | Still building | Need 500+ for validation |

---

## Key Questions

1. **Are changes helping?**  
   → Too early to tell (Similar Matches needs 250 bets, EV just launched)

2. **Are we overcomplicating?**  
   → Possibly. We've added 3 major systems in 1 month

3. **Should we simplify?**  
   → Option to revert to simpler system and let data guide us

---

## Competitor Research

**Services doing AI exact score predictions:**
- **CheckForm** - 23% hit rate (top-tier)
- **AIstats** - Uses Similar Matches technology
- **xGscore / MyGameOdds** - Target 15%+ probability picks
- **NerdyTips** - 75%+ overall (but this includes easier markets like 1X2)

**Reality**: Most exact score services achieve **10-15% hit rate**. Your 9.7% is competitive.

---

## Decision: Testing Phase (November 2025)

**PLAN**: Run current system for 200 more bets, evaluate at 354 total

### Evaluation Milestones

**At 250 bets** (~96 more):
- Similar Matches Impact Tracker delivers first verdict
- Check: `python3 view_sm_impact.py`

**At 354 bets** (~200 more):
- Full system evaluation
- Model calibration analysis: `python3 view_calibration.py`
- Decision point: Keep, simplify, or adjust

### What We're Testing

1. **EV Filtering (15%+ edge)** - Does mathematical edge improve ROI?
2. **Similar Matches** - Does pattern matching improve hit rate?
3. **Model Calibration** - Are probability predictions accurate?

### Success Criteria

- **Hit rate**: Moving toward 12-15% (industry good performance)
- **ROI**: Maintaining or improving profitability
- **Calibration**: Predicted probabilities match actual outcomes
- **Similar Matches**: Positive verdict from impact tracker

---

## Bottom Line

**You're NOT behind competitors**. Your 9.7% hit rate is within industry standard (7-16%). 

**Current approach**: Let the data guide us. Run 200 more bets, then decide based on evidence, not theory.

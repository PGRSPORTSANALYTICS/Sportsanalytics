#!/usr/bin/env python3
"""
View SGP Calibration Statistics
Shows how well the SGP prediction model is calibrated
"""

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/real_football.db")

def view_calibration():
    """Display current calibration stats and history"""
    
    print("="*80)
    print("📊 SGP SELF-LEARNING CALIBRATION REPORT")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get current calibration parameters
    print("\n🎯 CURRENT CALIBRATION PARAMETERS")
    print("-"*80)
    
    params = cursor.execute('SELECT param_name, param_value, updated_timestamp FROM sgp_calibration').fetchall()
    
    updated = "Unknown"
    if params:
        for name, value, timestamp in params:
            try:
                dt = datetime.fromtimestamp(timestamp)
                updated = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass
            
            if name == 'a':
                print(f"  📐 Slope (a):        {value:.4f}  (1.0 = no adjustment)")
            elif name == 'b':
                print(f"  📏 Intercept (b):    {value:.4f}  (0.0 = no adjustment)")
            elif name == 'brier_ewm':
                status = "🟢 GOOD" if value < 0.18 else "🟡 FAIR" if value < 0.24 else "🔴 POOR"
                print(f"  📊 Brier Score:      {value:.4f}  {status}")
            
        print(f"\n  📅 Last Updated:     {updated}")
    else:
        print("  ℹ️  No calibration data yet (system uses identity mapping: p_out = p_in)")
    
    # Get calibration effect examples
    print("\n\n🔄 CALIBRATION EXAMPLES (How predictions are adjusted)")
    print("-"*80)
    
    from sgp_self_learner import SGPSelfLearner
    learner = SGPSelfLearner()
    
    test_probs = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    print("  Model Probability → Calibrated Probability")
    print()
    for p in test_probs:
        p_cal = learner.adjust_probability(p)
        change = ((p_cal - p) / p * 100) if p > 0 else 0
        arrow = "⬆️" if change > 1 else "⬇️" if change < -1 else "➡️"
        print(f"  {p:.1%} → {p_cal:.1%}  {arrow} ({change:+.1f}%)")
    
    # Get dynamic Kelly sizing
    print("\n\n💰 DYNAMIC KELLY SIZING")
    print("-"*80)
    kelly = learner.get_dynamic_kelly()
    brier = learner.calibrator.brier_ewm
    
    if brier < 0.18:
        status = "✅ AGGRESSIVE (good calibration → higher stakes)"
    elif brier < 0.24:
        status = "📊 NORMAL (medium calibration → standard stakes)"
    else:
        status = "⚠️ CONSERVATIVE (poor calibration → reduced stakes)"
    
    print(f"  Kelly Multiplier:    {kelly:.3f}")
    print(f"  Status:              {status}")
    print(f"  Brier Score:         {brier:.4f}")
    
    # Get calibration history
    print("\n\n📈 CALIBRATION HISTORY (Last 20 updates)")
    print("-"*80)
    
    history = cursor.execute('''
        SELECT timestamp, predicted_prob, actual_outcome, a_param, b_param, brier_score
        FROM sgp_calibration_history
        ORDER BY timestamp DESC
        LIMIT 20
    ''').fetchall()
    
    if history:
        print("  Date       | Pred  | Actual | Slope  | Brier  | Result")
        print("  " + "-"*70)
        for ts, pred, actual, a, b, brier in history:
            try:
                dt = datetime.fromtimestamp(ts)
                date_str = dt.strftime('%m/%d %H:%M')
            except:
                date_str = "Unknown"
            
            result_icon = "✅ WIN" if actual == 1 else "❌ LOSS"
            print(f"  {date_str} | {pred:.3f} | {result_icon:6s} | {a:.4f} | {brier:.4f}")
    else:
        print("  ℹ️  No calibration history yet")
    
    # Get correlation learning stats
    print("\n\n🔗 LEARNED CORRELATIONS BETWEEN BET LEGS")
    print("-"*80)
    
    correlations = cursor.execute('''
        SELECT leg_pair, both_win, both_lose, learned_correlation, sample_count
        FROM sgp_leg_correlations
        WHERE sample_count >= 5
        ORDER BY sample_count DESC
        LIMIT 10
    ''').fetchall()
    
    if correlations:
        print("  Leg Pair                                    | Correlation | Samples")
        print("  " + "-"*74)
        for pair, both_win, both_lose, corr, samples in correlations:
            # Shorten leg pair names for display
            display_pair = pair.replace('_UNDER_GOALS', '').replace('OVER', 'O').replace('UNDER', 'U')
            display_pair = display_pair[:45].ljust(45)
            
            corr_str = f"{corr:+.3f}"
            corr_icon = "🟢" if corr > 0.3 else "🟡" if corr > 0.1 else "⚪"
            
            print(f"  {display_pair} | {corr_icon} {corr_str:7s} | {samples:3d}")
    else:
        print("  ℹ️  Not enough settled parlays yet to learn correlations (need 5+)")
    
    # Overall performance stats
    print("\n\n📊 OVERALL SGP PERFORMANCE")
    print("-"*80)
    
    stats = cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(profit_loss) as profit
        FROM sgp_predictions
        WHERE result IS NOT NULL
    ''').fetchone()
    
    if stats and stats[0] > 0:
        total, wins, profit = stats
        hit_rate = (wins / total * 100) if total > 0 else 0
        
        print(f"  Total Settled:       {total}")
        print(f"  Wins:                {wins}")
        print(f"  Hit Rate:            {hit_rate:.1f}%")
        print(f"  Total Profit/Loss:   {profit:+.0f} SEK")
        
        # Quality assessment
        if total >= 20:
            if hit_rate >= 35:
                quality = "🟢 EXCELLENT - System performing above target!"
            elif hit_rate >= 30:
                quality = "🟢 GOOD - On track for profitability"
            elif hit_rate >= 25:
                quality = "🟡 FAIR - Needs improvement"
            else:
                quality = "🔴 POOR - Calibration helping but more data needed"
            print(f"\n  Quality:             {quality}")
    else:
        print("  ℹ️  No settled SGP predictions yet")
    
    print("\n" + "="*80)
    
    conn.close()


if __name__ == "__main__":
    view_calibration()

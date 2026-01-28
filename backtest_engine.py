"""
================================================================================
ISOLATED HISTORICAL BACKTEST ENGINE
================================================================================
CRITICAL: This backtest is 100% SEPARATED from live results, learning data,
and any existing ROI/units tracking. All outputs are BACKTEST ONLY.

Author: PGR System
Date: January 28, 2026
Purpose: Risk and stability analysis for potential public launch
================================================================================
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

BACKTEST_LABEL = "⚠️ BACKTEST ONLY - NOT LIVE RESULTS ⚠️"

INITIAL_BANKROLL_SEK = 10000
UNIT_SIZE = 0.01  # 1% of initial bankroll = 100 SEK per unit

VOLUME_CAPS = [20, 30, 50]  # Scenario A, B, C
STOP_LOSS_LEVELS = [-10, -15, None]  # Daily stop-loss in units

MARKETS_INCLUDED = ['CARDS', 'CORNERS']
MARKETS_SECONDARY = ['UNDER']  # Include if available

BACKTEST_START = '2025-12-11'
BACKTEST_END = '2026-01-27'


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(os.environ['DATABASE_URL'])


def fetch_historical_bets() -> pd.DataFrame:
    """Fetch all settled bets for backtest period - ISOLATED QUERY.
    
    NOTE: UNDER market checked but has 0 bets in backtest period.
    Only CARDS and CORNERS have sufficient data for analysis.
    """
    conn = get_db_connection()
    all_markets = MARKETS_INCLUDED + MARKETS_SECONDARY
    
    query = """
    SELECT 
        id,
        product as market_type,
        odds,
        stake,
        norm_result as result,
        DATE(created_at) as bet_date,
        created_at,
        home_team,
        away_team,
        ev,
        selection
    FROM normalized_bets
    WHERE norm_result IN ('WON', 'LOST')
      AND product = ANY(%s)
      AND DATE(created_at) >= %s
      AND DATE(created_at) <= %s
    ORDER BY created_at ASC
    """
    df = pd.read_sql(query, conn, params=(all_markets, BACKTEST_START, BACKTEST_END))
    conn.close()
    
    df['won'] = df['result'] == 'WON'
    df['bet_date'] = pd.to_datetime(df['bet_date'])
    
    if 'UNDER' not in df['market_type'].unique():
        print("NOTE: UNDER market has 0 bets in backtest period - excluded from analysis")
    
    return df


def run_backtest_scenario(
    bets_df: pd.DataFrame,
    daily_cap: int,
    daily_stop_loss: Optional[float]
) -> Dict:
    """
    Run a single backtest scenario with specified parameters.
    Uses FLAT STAKING: 1 unit = 1% of initial bankroll (constant).
    """
    
    results = {
        'daily_cap': daily_cap,
        'stop_loss': daily_stop_loss,
        'bets_placed': 0,
        'bets_won': 0,
        'bets_lost': 0,
        'total_units': 0.0,
        'daily_pnl': {},
        'equity_curve': [],
        'max_drawdown_units': 0.0,
        'max_drawdown_pct': 0.0,
        'worst_day_units': 0.0,
        'days_worse_than_5': 0,
        'days_worse_than_10': 0,
        'days_worse_than_15': 0,
        'market_stats': {},
        'skipped_volume': 0,
        'skipped_stoploss': 0
    }
    
    cumulative_units = 0.0
    peak_units = 0.0
    max_dd = 0.0
    
    for market in MARKETS_INCLUDED:
        results['market_stats'][market] = {'bets': 0, 'won': 0, 'units': 0.0}
    
    dates = sorted(bets_df['bet_date'].unique())
    
    for date in dates:
        day_bets = bets_df[bets_df['bet_date'] == date].copy()
        day_bets = day_bets.sort_values('ev', ascending=False)
        
        daily_units = 0.0
        daily_count = 0
        stop_triggered = False
        
        for _, bet in day_bets.iterrows():
            if daily_count >= daily_cap:
                results['skipped_volume'] += 1
                continue
            
            if daily_stop_loss is not None and daily_units <= daily_stop_loss:
                stop_triggered = True
                results['skipped_stoploss'] += 1
                continue
            
            stake_units = 1.0
            
            if bet['won']:
                profit = stake_units * (bet['odds'] - 1)
                results['bets_won'] += 1
            else:
                profit = -stake_units
                results['bets_lost'] += 1
            
            daily_units += profit
            cumulative_units += profit
            results['bets_placed'] += 1
            daily_count += 1
            
            market = bet['market_type']
            if market in results['market_stats']:
                results['market_stats'][market]['bets'] += 1
                results['market_stats'][market]['units'] += profit
                if bet['won']:
                    results['market_stats'][market]['won'] += 1
            
            results['equity_curve'].append({
                'date': str(date.date()),
                'cumulative_units': round(cumulative_units, 2),
                'bet_id': bet['id']
            })
            
            if cumulative_units > peak_units:
                peak_units = cumulative_units
            dd = peak_units - cumulative_units
            if dd > max_dd:
                max_dd = dd
        
        date_str = str(date.date())
        results['daily_pnl'][date_str] = round(daily_units, 2)
        
        if daily_units < results['worst_day_units']:
            results['worst_day_units'] = daily_units
        
        if daily_units < -5:
            results['days_worse_than_5'] += 1
        if daily_units < -10:
            results['days_worse_than_10'] += 1
        if daily_units < -15:
            results['days_worse_than_15'] += 1
    
    results['total_units'] = round(cumulative_units, 2)
    results['max_drawdown_units'] = round(max_dd, 2)
    results['max_drawdown_pct'] = round(100 * max_dd / (INITIAL_BANKROLL_SEK / 100), 2) if max_dd > 0 else 0
    results['worst_day_units'] = round(results['worst_day_units'], 2)
    
    final_bankroll = INITIAL_BANKROLL_SEK + (cumulative_units * 100)
    results['final_bankroll_sek'] = round(final_bankroll, 2)
    results['roi_pct'] = round(100 * (final_bankroll - INITIAL_BANKROLL_SEK) / INITIAL_BANKROLL_SEK, 2)
    
    if results['bets_placed'] > 0:
        results['hit_rate'] = round(100 * results['bets_won'] / results['bets_placed'], 1)
    else:
        results['hit_rate'] = 0.0
    
    daily_pnls = list(results['daily_pnl'].values())
    results['avg_daily_pnl'] = round(np.mean(daily_pnls), 2) if daily_pnls else 0.0
    results['trading_days'] = len(daily_pnls)
    
    for market, stats in results['market_stats'].items():
        if stats['bets'] > 0:
            stats['hit_rate'] = round(100 * stats['won'] / stats['bets'], 1)
            stats['units'] = round(stats['units'], 2)
        else:
            stats['hit_rate'] = 0.0
    
    return results


def generate_report(all_scenarios: List[Dict]) -> str:
    """Generate comprehensive backtest report."""
    
    report = []
    report.append("=" * 80)
    report.append(BACKTEST_LABEL)
    report.append("=" * 80)
    report.append("")
    report.append("ISOLATED HISTORICAL BACKTEST REPORT")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("-" * 80)
    report.append("BACKTEST CONFIGURATION")
    report.append("-" * 80)
    report.append(f"Period: {BACKTEST_START} to {BACKTEST_END}")
    report.append(f"Initial Bankroll: {INITIAL_BANKROLL_SEK:,} SEK")
    report.append(f"Stake Model: FLAT STAKING (1 unit = 1% = 100 SEK)")
    report.append(f"Markets: {', '.join(MARKETS_INCLUDED)}")
    report.append("")
    report.append("ASSUMPTIONS:")
    report.append("- Perfect execution at closing odds")
    report.append("- No slippage or CLV modeling")
    report.append("- EV-prioritized selection when volume capped")
    report.append("- Daily stop-loss checked after each bet")
    report.append("")
    
    report.append("=" * 80)
    report.append("SCENARIO RESULTS")
    report.append("=" * 80)
    
    for scenario in all_scenarios:
        cap = scenario['daily_cap']
        sl = scenario['stop_loss']
        sl_str = f"{sl}u" if sl else "None"
        
        report.append("")
        report.append(f"┌{'─' * 76}┐")
        report.append(f"│ SCENARIO: Volume Cap {cap}/day, Stop-Loss {sl_str:>6}".ljust(77) + "│")
        report.append(f"├{'─' * 76}┤")
        report.append(f"│ Total Units (BACKTEST): {scenario['total_units']:+.2f}u".ljust(77) + "│")
        report.append(f"│ Final Bankroll: {scenario['final_bankroll_sek']:,.0f} SEK ({scenario['roi_pct']:+.1f}% ROI)".ljust(77) + "│")
        report.append(f"│ Bets Placed: {scenario['bets_placed']} ({scenario['hit_rate']:.1f}% hit rate)".ljust(77) + "│")
        report.append(f"├{'─' * 76}┤")
        report.append(f"│ RISK METRICS:".ljust(77) + "│")
        report.append(f"│   Max Drawdown: {scenario['max_drawdown_units']:.2f}u ({scenario['max_drawdown_pct']:.1f}%)".ljust(77) + "│")
        report.append(f"│   Worst Single Day: {scenario['worst_day_units']:.2f}u".ljust(77) + "│")
        report.append(f"│   Avg Daily P/L: {scenario['avg_daily_pnl']:+.2f}u".ljust(77) + "│")
        report.append(f"│   Trading Days: {scenario['trading_days']}".ljust(77) + "│")
        report.append(f"├{'─' * 76}┤")
        report.append(f"│ LOSING DAYS DISTRIBUTION:".ljust(77) + "│")
        report.append(f"│   Days worse than -5u:  {scenario['days_worse_than_5']:>3}".ljust(77) + "│")
        report.append(f"│   Days worse than -10u: {scenario['days_worse_than_10']:>3}".ljust(77) + "│")
        report.append(f"│   Days worse than -15u: {scenario['days_worse_than_15']:>3}".ljust(77) + "│")
        report.append(f"├{'─' * 76}┤")
        report.append(f"│ MARKET BREAKDOWN:".ljust(77) + "│")
        for market, stats in scenario['market_stats'].items():
            report.append(f"│   {market}: {stats['bets']} bets, {stats['hit_rate']:.1f}% hit, {stats['units']:+.2f}u".ljust(77) + "│")
        if scenario['skipped_volume'] > 0 or scenario['skipped_stoploss'] > 0:
            report.append(f"├{'─' * 76}┤")
            report.append(f"│ FILTERED OUT:".ljust(77) + "│")
            if scenario['skipped_volume'] > 0:
                report.append(f"│   Volume cap: {scenario['skipped_volume']} bets skipped".ljust(77) + "│")
            if scenario['skipped_stoploss'] > 0:
                report.append(f"│   Stop-loss: {scenario['skipped_stoploss']} bets skipped".ljust(77) + "│")
        report.append(f"└{'─' * 76}┘")
    
    report.append("")
    report.append("=" * 80)
    report.append("COMPARATIVE SUMMARY")
    report.append("=" * 80)
    
    summary_data = []
    for s in all_scenarios:
        sl_str = f"{s['stop_loss']}u" if s['stop_loss'] else "None"
        summary_data.append({
            'Config': f"Cap {s['daily_cap']}, SL {sl_str}",
            'Units': s['total_units'],
            'ROI%': s['roi_pct'],
            'MaxDD': s['max_drawdown_units'],
            'WorstDay': s['worst_day_units'],
            'HitRate': s['hit_rate'],
            'Risk Score': round(abs(s['max_drawdown_units']) / max(s['total_units'], 1), 2) if s['total_units'] > 0 else 999
        })
    
    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values('Risk Score')
    
    report.append("")
    report.append(f"{'Config':<25} {'Units':>8} {'ROI%':>8} {'MaxDD':>8} {'Worst':>8} {'Hit%':>8} {'Risk':>8}")
    report.append("-" * 80)
    for _, row in summary_df.iterrows():
        report.append(f"{row['Config']:<25} {row['Units']:>+8.1f} {row['ROI%']:>+7.1f}% {row['MaxDD']:>8.1f} {row['WorstDay']:>8.1f} {row['HitRate']:>7.1f}% {row['Risk Score']:>8.2f}")
    
    report.append("")
    report.append("=" * 80)
    report.append("IMPORTANT OBSERVATIONS")
    report.append("=" * 80)
    report.append("")
    
    stoploss_triggered = any(s['skipped_stoploss'] > 0 for s in all_scenarios)
    if not stoploss_triggered:
        report.append("⚠️ STOP-LOSS NOTE: No daily stop-loss was triggered during the backtest period.")
        report.append("   This means all stop-loss scenarios produced IDENTICAL results.")
        report.append("   System never experienced a single day with losses exceeding -10 units.")
        report.append("   This is positive for stability but means stop-loss scenarios cannot be")
        report.append("   differentiated in this historical period.")
        report.append("")
    
    report.append("=" * 80)
    report.append("BACKTEST INSIGHTS – NOT LIVE RESULTS")
    report.append("=" * 80)
    report.append("")
    
    best_growth = max(all_scenarios, key=lambda x: x['total_units'])
    best_risk = min(all_scenarios, key=lambda x: abs(x['max_drawdown_units']) / max(x['total_units'], 0.1) if x['total_units'] > 0 else 999)
    most_stable = min(all_scenarios, key=lambda x: x['days_worse_than_10'])
    
    report.append("1. BEST BALANCE BETWEEN GROWTH AND DRAWDOWN:")
    sl_str = f"{best_risk['stop_loss']}u" if best_risk['stop_loss'] else "None"
    report.append(f"   → Volume Cap {best_risk['daily_cap']}/day, Stop-Loss {sl_str}")
    report.append(f"   → {best_risk['total_units']:+.1f}u profit with {best_risk['max_drawdown_units']:.1f}u max drawdown")
    report.append(f"   → Risk ratio: {abs(best_risk['max_drawdown_units']) / max(best_risk['total_units'], 0.1):.2f}")
    report.append("")
    
    report.append("2. RECOMMENDED FOR PUBLIC LAUNCH:")
    conservative = [s for s in all_scenarios if s['daily_cap'] <= 30 and s['days_worse_than_10'] <= 2]
    if conservative:
        rec = max(conservative, key=lambda x: x['total_units'])
        sl_str = f"{rec['stop_loss']}u" if rec['stop_loss'] else "None"
        report.append(f"   → Volume Cap {rec['daily_cap']}/day, Stop-Loss {sl_str}")
        report.append(f"   → Reasoning: Controlled volume with acceptable drawdown variance")
        report.append(f"   → Only {rec['days_worse_than_10']} days exceeding -10u loss")
    else:
        sl_str = f"{most_stable['stop_loss']}u" if most_stable['stop_loss'] else "None"
        report.append(f"   → Volume Cap {most_stable['daily_cap']}/day, Stop-Loss {sl_str}")
        report.append(f"   → This scenario has fewest severe losing days ({most_stable['days_worse_than_10']})")
    report.append("")
    
    report.append("3. RISK BEHAVIOR TO COMMUNICATE TO USERS:")
    avg_worst = np.mean([s['worst_day_units'] for s in all_scenarios])
    avg_dd = np.mean([s['max_drawdown_units'] for s in all_scenarios])
    report.append(f"   → Expect occasional losing days of {abs(avg_worst):.0f}+ units")
    report.append(f"   → Maximum drawdown can reach {abs(avg_dd):.0f}+ units before recovery")
    report.append(f"   → System requires patience through variance periods")
    report.append(f"   → Historical hit rate: ~{np.mean([s['hit_rate'] for s in all_scenarios]):.0f}%")
    report.append("")
    
    report.append("=" * 80)
    report.append(BACKTEST_LABEL)
    report.append("=" * 80)
    
    return "\n".join(report)


def save_equity_curves(all_scenarios: List[Dict]):
    """Save equity curve data for visualization."""
    curves = {}
    for scenario in all_scenarios:
        sl_str = f"{scenario['stop_loss']}u" if scenario['stop_loss'] else "None"
        key = f"Cap{scenario['daily_cap']}_SL{sl_str}"
        curves[key] = scenario['equity_curve']
    
    with open('backtest_equity_curves.json', 'w') as f:
        json.dump(curves, f, indent=2)
    print("Equity curves saved to: backtest_equity_curves.json")


def run_full_backtest():
    """Execute complete isolated backtest."""
    print("=" * 60)
    print(BACKTEST_LABEL)
    print("=" * 60)
    print()
    print("Fetching historical data...")
    
    bets_df = fetch_historical_bets()
    print(f"Loaded {len(bets_df)} settled bets for backtest")
    print(f"Date range: {bets_df['bet_date'].min()} to {bets_df['bet_date'].max()}")
    print(f"Markets: {bets_df['market_type'].value_counts().to_dict()}")
    print()
    
    all_scenarios = []
    
    for cap in VOLUME_CAPS:
        for stop_loss in STOP_LOSS_LEVELS:
            sl_str = f"{stop_loss}u" if stop_loss else "None"
            print(f"Running scenario: Cap {cap}/day, Stop-Loss {sl_str}...")
            
            result = run_backtest_scenario(bets_df, cap, stop_loss)
            all_scenarios.append(result)
            
            print(f"  → {result['total_units']:+.1f}u | {result['bets_placed']} bets | {result['hit_rate']:.1f}% hit")
    
    print()
    print("Generating report...")
    report = generate_report(all_scenarios)
    
    with open('backtest_report.txt', 'w') as f:
        f.write(report)
    print("Report saved to: backtest_report.txt")
    
    save_equity_curves(all_scenarios)
    
    print()
    print(report)
    
    return all_scenarios


if __name__ == "__main__":
    run_full_backtest()

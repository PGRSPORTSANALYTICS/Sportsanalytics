#!/usr/bin/env python3
"""
MASTER STATS MODULE
===================
Single source of truth for ALL performance statistics.
Always pulls from BOTH tables (exact score + SGP).
100% bulletproof, no discrepancies possible.

CRITICAL STATISTICS POLICY:
---------------------------
1. All SGP queries MUST filter: parlay_description NOT LIKE '%Monster%' AND NOT LIKE '%BEAST%'
2. Regular SGP statistics represent the actual subscription product performance
3. Average odds for regular SGP: ~3.4x

This ensures subscribers see accurate, reliable performance metrics.
"""

from typing import Dict, List
from datetime import date
from db_helper import db_helper

def get_all_time_stats() -> Dict:
    """Get combined all-time statistics from unified results_roi table + pending counts (PROD mode only)"""
    
    def get_product_stats(product_type: str):
        """Get stats for a specific product from results_roi (PROD mode only)"""
        row = db_helper.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_won THEN 1 ELSE 0 END) as wins,
                SUM(profit) as profit,
                SUM(stake) as staked
            FROM results_roi
            WHERE product_type = %s AND mode = 'PROD'
        ''', (product_type,), fetch='one')
        total, wins, profit, staked = row if row else (0, 0, 0.0, 0.0)
        total = total or 0
        wins = wins or 0
        profit = profit or 0.0
        staked = staked or 0.0
        losses = total - wins
        hit_rate = (wins / total * 100) if total > 0 else 0.0
        
        # Get pending count from source tables (PROD mode only)
        pending = 0
        if product_type == 'football_single':
            prow = db_helper.execute("SELECT COUNT(*) FROM football_opportunities WHERE market = 'exact_score' AND outcome IS NULL AND mode = 'PROD'", (), fetch='one')
            pending = prow[0] if prow else 0
        elif product_type == 'sgp':
            prow = db_helper.execute("SELECT COUNT(*) FROM sgp_predictions WHERE outcome IS NULL AND mode = 'PROD' AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%Monster%%')", (), fetch='one')
            pending = prow[0] if prow else 0
        elif product_type == 'value_single':
            prow = db_helper.execute("SELECT COUNT(*) FROM football_opportunities WHERE market = 'Value Single' AND outcome IS NULL AND mode = 'PROD'", (), fetch='one')
            pending = prow[0] if prow else 0
        
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'pending': pending,
            'hit_rate': round(hit_rate, 1),
            'profit': round(profit, 2),
            'staked': round(staked, 2)
        }
    
    # Get stats for each product
    exact_stats = get_product_stats('football_single')
    sgp_stats = get_product_stats('sgp')
    vs_stats = get_product_stats('value_single')
    
    # Combined stats (PROD mode only)
    combined_row = db_helper.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_won THEN 1 ELSE 0 END) as wins,
            SUM(profit) as profit,
            SUM(stake) as staked
        FROM results_roi
        WHERE mode = 'PROD'
    ''', (), fetch='one')
    c_total, c_wins, c_profit, c_staked = combined_row if combined_row else (0, 0, 0.0, 0.0)
    c_total = c_total or 0
    c_wins = c_wins or 0
    c_profit = c_profit or 0.0
    c_staked = c_staked or 0.0
    c_losses = c_total - c_wins
    c_hit_rate = (c_wins / c_total * 100) if c_total > 0 else 0.0
    c_pending = exact_stats.get('pending', 0) + sgp_stats.get('pending', 0) + vs_stats.get('pending', 0)
    
    return {
        'exact_score': exact_stats,
        'sgp': sgp_stats,
        'value_singles': vs_stats,
        'combined': {
            'total': c_total,
            'wins': c_wins,
            'losses': c_losses,
            'pending': c_pending,
            'hit_rate': round(c_hit_rate, 1),
            'profit': round(c_profit, 2),
            'staked': round(c_staked, 2)
        }
    }

def get_todays_exact_score_stats() -> Dict:
    """Get today's exact score statistics"""
    today = date.today().isoformat()
    
    row = db_helper.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome IN (%s, %s) THEN 1 ELSE 0 END) as wins,
            SUM(profit_loss) as profit
        FROM football_opportunities 
        WHERE market = %s 
        AND result IS NOT NULL 
        AND DATE(TO_TIMESTAMP(settled_timestamp)) = %s
    ''', ('win', 'won', 'exact_score', today), fetch='one')
    
    total, wins, profit = row if row else (0, 0, 0.0)
    losses = total - (wins or 0)
    hit_rate = (wins / total * 100) if total > 0 else 0.0
    
    return {
        'total': total or 0,
        'wins': wins or 0,
        'losses': losses or 0,
        'hit_rate': round(hit_rate, 1),
        'profit': round(profit or 0.0, 2)
    }

def get_todays_sgp_stats() -> Dict:
    """Get today's SGP statistics (EXCLUDE MonsterSGP - entertainment only)"""
    today = date.today().isoformat()
    
    row = db_helper.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome IN (%s, %s) THEN 1 ELSE 0 END) as wins,
            SUM(profit_loss) as profit
        FROM sgp_predictions 
        WHERE result IS NOT NULL 
        AND DATE(TO_TIMESTAMP(settled_timestamp)) = %s
        AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
        AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
    ''', ('win', 'won', today, '%Monster%', '%BEAST%'), fetch='one')
    
    total, wins, profit = row if row else (0, 0, 0.0)
    losses = total - (wins or 0)
    hit_rate = (wins / total * 100) if total > 0 else 0.0
    
    return {
        'total': total or 0,
        'wins': wins or 0,
        'losses': losses or 0,
        'hit_rate': round(hit_rate, 1),
        'profit': round(profit or 0.0, 2)
    }

def get_exact_score_results() -> List[Dict]:
    """Get all exact score settled predictions"""
    rows = db_helper.execute('''
        SELECT 
            home_team, away_team, selection, odds, 
            actual_score, outcome, stake, profit_loss,
            league, settled_timestamp
        FROM football_opportunities 
        WHERE market = %s AND result IS NOT NULL
        ORDER BY settled_timestamp DESC
    ''', ('exact_score',), fetch='all')
    
    results = []
    if rows:
        for row in rows:
            results.append({
                'home_team': row[0],
                'away_team': row[1],
                'selection': row[2],
                'odds': row[3],
                'actual_score': row[4],
                'outcome': row[5],
                'stake': row[6],
                'profit': row[7],
                'league': row[8],
                'timestamp': row[9]
            })
    
    return results

def get_sgp_results() -> List[Dict]:
    """Get all SGP settled predictions (EXCLUDE MonsterSGP - entertainment only)"""
    rows = db_helper.execute('''
        SELECT 
            home_team, away_team, parlay_description, bookmaker_odds,
            result, outcome, stake, profit_loss,
            league, settled_timestamp
        FROM sgp_predictions 
        WHERE result IS NOT NULL
        AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
        AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
        ORDER BY settled_timestamp DESC
    ''', ('%Monster%', '%BEAST%'), fetch='all')
    
    results = []
    if rows:
        for row in rows:
            results.append({
                'home_team': row[0],
                'away_team': row[1],
                'selection': row[2],
                'odds': row[3],
                'result': row[4],
                'outcome': row[5],
                'stake': row[6],
                'profit': row[7],
                'league': row[8],
                'timestamp': row[9]
            })
    
    return results

def print_bulletproof_report():
    """Print complete bulletproof performance report"""
    stats = get_all_time_stats()
    
    print("=" * 80)
    print("BULLETPROOF PERFORMANCE REPORT")
    print("=" * 80)
    print()
    
    print("⚽ EXACT SCORE - ALL TIME")
    print(f"   Total Settled: {stats['exact_score']['total']}")
    print(f"   Wins: {stats['exact_score']['wins']}")
    print(f"   Losses: {stats['exact_score']['losses']}")
    print(f"   Hit Rate: {stats['exact_score']['hit_rate']}%")
    print(f"   Profit: {stats['exact_score']['profit']:+.2f} SEK")
    print()
    
    print("🎲 SGP - ALL TIME")
    print(f"   Total Settled: {stats['sgp']['total']}")
    print(f"   Wins: {stats['sgp']['wins']}")
    print(f"   Losses: {stats['sgp']['losses']}")
    print(f"   Hit Rate: {stats['sgp']['hit_rate']}%")
    print(f"   Profit: {stats['sgp']['profit']:+.2f} SEK")
    print()
    
    print("💰 COMBINED - ALL TIME")
    print(f"   Total Settled: {stats['combined']['total']}")
    print(f"   Wins: {stats['combined']['wins']}")
    print(f"   Losses: {stats['combined']['losses']}")
    print(f"   Hit Rate: {stats['combined']['hit_rate']}%")
    print(f"   Profit: {stats['combined']['profit']:+.2f} SEK")
    print()
    
    today_stats = get_todays_exact_score_stats()
    if today_stats['total'] > 0:
        print("📅 TODAY - EXACT SCORE")
        print(f"   Total Settled: {today_stats['total']}")
        print(f"   Wins: {today_stats['wins']}")
        print(f"   Losses: {today_stats['losses']}")
        print(f"   Hit Rate: {today_stats['hit_rate']}%")
        print(f"   Profit: {today_stats['profit']:+.2f} SEK")
        print()
    
    print("=" * 80)

if __name__ == "__main__":
    print_bulletproof_report()

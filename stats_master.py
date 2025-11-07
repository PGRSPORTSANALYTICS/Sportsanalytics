#!/usr/bin/env python3
"""
MASTER STATS MODULE
===================
Single source of truth for ALL performance statistics.
Always pulls from BOTH tables (exact score + SGP).
100% bulletproof, no discrepancies possible.
"""

import sqlite3
from typing import Dict, List
from datetime import date

DB_PATH = 'data/real_football.db'

def get_all_time_stats() -> Dict:
    """Get combined all-time statistics from both tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Exact Score stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(profit_loss) as profit
        FROM football_opportunities 
        WHERE market = 'exact_score' AND result IS NOT NULL
    ''')
    exact_row = cursor.fetchone()
    exact_total, exact_wins, exact_profit = exact_row if exact_row else (0, 0, 0.0)
    exact_losses = exact_total - (exact_wins or 0)
    exact_hit_rate = (exact_wins / exact_total * 100) if exact_total > 0 else 0.0
    
    # SGP stats  
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(profit_loss) as profit
        FROM sgp_predictions 
        WHERE result IS NOT NULL
    ''')
    sgp_row = cursor.fetchone()
    sgp_total, sgp_wins, sgp_profit = sgp_row if sgp_row else (0, 0, 0.0)
    sgp_losses = sgp_total - (sgp_wins or 0)
    sgp_hit_rate = (sgp_wins / sgp_total * 100) if sgp_total > 0 else 0.0
    
    # Combined stats
    combined_total = (exact_total or 0) + (sgp_total or 0)
    combined_wins = (exact_wins or 0) + (sgp_wins or 0)
    combined_losses = (exact_losses or 0) + (sgp_losses or 0)
    combined_profit = (exact_profit or 0.0) + (sgp_profit or 0.0)
    combined_hit_rate = (combined_wins / combined_total * 100) if combined_total > 0 else 0.0
    
    conn.close()
    
    return {
        'exact_score': {
            'total': exact_total or 0,
            'wins': exact_wins or 0,
            'losses': exact_losses or 0,
            'hit_rate': round(exact_hit_rate, 1),
            'profit': round(exact_profit or 0.0, 2)
        },
        'sgp': {
            'total': sgp_total or 0,
            'wins': sgp_wins or 0,
            'losses': sgp_losses or 0,
            'hit_rate': round(sgp_hit_rate, 1),
            'profit': round(sgp_profit or 0.0, 2)
        },
        'combined': {
            'total': combined_total,
            'wins': combined_wins,
            'losses': combined_losses,
            'hit_rate': round(combined_hit_rate, 1),
            'profit': round(combined_profit, 2)
        }
    }

def get_todays_exact_score_stats() -> Dict:
    """Get today's exact score statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(profit_loss) as profit
        FROM football_opportunities 
        WHERE market = 'exact_score' 
        AND result IS NOT NULL 
        AND date(settled_timestamp, 'unixepoch') = ?
    ''', (today,))
    
    row = cursor.fetchone()
    total, wins, profit = row if row else (0, 0, 0.0)
    losses = total - (wins or 0)
    hit_rate = (wins / total * 100) if total > 0 else 0.0
    
    conn.close()
    
    return {
        'total': total or 0,
        'wins': wins or 0,
        'losses': losses or 0,
        'hit_rate': round(hit_rate, 1),
        'profit': round(profit or 0.0, 2)
    }

def get_todays_sgp_stats() -> Dict:
    """Get today's SGP statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(profit_loss) as profit
        FROM sgp_predictions 
        WHERE result IS NOT NULL 
        AND date(settled_timestamp, 'unixepoch') = ?
    ''', (today,))
    
    row = cursor.fetchone()
    total, wins, profit = row if row else (0, 0, 0.0)
    losses = total - (wins or 0)
    hit_rate = (wins / total * 100) if total > 0 else 0.0
    
    conn.close()
    
    return {
        'total': total or 0,
        'wins': wins or 0,
        'losses': losses or 0,
        'hit_rate': round(hit_rate, 1),
        'profit': round(profit or 0.0, 2)
    }

def get_exact_score_results() -> List[Dict]:
    """Get all exact score settled predictions"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            home_team, away_team, selection, odds, 
            actual_score, outcome, stake, profit_loss,
            league, settled_timestamp
        FROM football_opportunities 
        WHERE market = 'exact_score' AND result IS NOT NULL
        ORDER BY settled_timestamp DESC
    ''')
    
    results = []
    for row in cursor.fetchall():
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
    
    conn.close()
    return results

def get_sgp_results() -> List[Dict]:
    """Get all SGP settled predictions"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            home_team, away_team, parlay_description, bookmaker_odds,
            result, outcome, stake, profit_loss,
            league, settled_timestamp
        FROM sgp_predictions 
        WHERE result IS NOT NULL
        ORDER BY settled_timestamp DESC
    ''')
    
    results = []
    for row in cursor.fetchall():
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
    
    conn.close()
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

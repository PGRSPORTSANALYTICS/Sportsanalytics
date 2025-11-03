#!/usr/bin/env python3
"""
Per-League Performance Tracker
Shows hit rate, ROI, and prediction count for each league
"""

import sqlite3
from typing import List, Dict
import sys

def get_league_performance() -> List[Dict]:
    """Get performance stats per league"""
    conn = sqlite3.connect('data/real_football.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            league,
            COUNT(*) as total_predictions,
            SUM(CASE WHEN outcome IN ('won', 'win') THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome IN ('lost', 'loss') THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN outcome IS NULL THEN 1 ELSE 0 END) as pending,
            SUM(stake) as total_staked,
            SUM(CASE WHEN outcome IN ('won', 'win') THEN stake * (odds - 1) 
                     WHEN outcome IN ('lost', 'loss') THEN -stake 
                     ELSE 0 END) as net_profit,
            AVG(odds) as avg_odds,
            AVG(confidence) as avg_confidence
        FROM football_opportunities
        WHERE market = 'exact_score'
        GROUP BY league
        ORDER BY total_predictions DESC
    ''')
    
    leagues = []
    for row in cursor.fetchall():
        settled = row[2] + row[3]  # wins + losses
        win_rate = (row[2] / settled * 100) if settled > 0 else 0
        roi = (row[6] / row[5] * 100) if row[5] > 0 else 0
        
        leagues.append({
            'league': row[0],
            'total': row[1],
            'wins': row[2],
            'losses': row[3],
            'pending': row[4],
            'settled': settled,
            'win_rate': win_rate,
            'total_staked': row[5],
            'net_profit': row[6],
            'roi': roi,
            'avg_odds': row[7],
            'avg_confidence': row[8]
        })
    
    conn.close()
    return leagues

def print_league_performance():
    """Print formatted league performance table"""
    leagues = get_league_performance()
    
    if not leagues:
        print("❌ No predictions found")
        return
    
    print("\n" + "="*100)
    print("📊 PER-LEAGUE PERFORMANCE TRACKER")
    print("="*100)
    print(f"{'League':<30} {'Total':<8} {'Settled':<8} {'Wins':<6} {'Hit%':<8} {'ROI%':<10} {'Profit':<12} {'Avg Odds':<10}")
    print("-"*100)
    
    total_predictions = 0
    total_wins = 0
    total_settled = 0
    total_staked = 0
    total_profit = 0
    
    for league in leagues:
        total_predictions += league['total']
        total_wins += league['wins']
        total_settled += league['settled']
        total_staked += league['total_staked'] or 0
        total_profit += league['net_profit'] or 0
        
        # Color coding for hit rate
        if league['settled'] >= 10:
            if league['win_rate'] >= 20:
                status = "🟢"
            elif league['win_rate'] >= 15:
                status = "🟡"
            else:
                status = "🔴"
        else:
            status = "⚪"  # Not enough data
        
        print(f"{status} {league['league']:<28} "
              f"{league['total']:<8} "
              f"{league['settled']:<8} "
              f"{league['wins']:<6} "
              f"{league['win_rate']:<7.1f}% "
              f"{league['roi']:<9.1f}% "
              f"{league['net_profit']:<11.0f} SEK "
              f"{league['avg_odds']:<9.1f}x")
    
    print("-"*100)
    overall_win_rate = (total_wins / total_settled * 100) if total_settled > 0 else 0
    overall_roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    
    print(f"{'OVERALL':<30} "
          f"{total_predictions:<8} "
          f"{total_settled:<8} "
          f"{total_wins:<6} "
          f"{overall_win_rate:<7.1f}% "
          f"{overall_roi:<9.1f}% "
          f"{total_profit:<11.0f} SEK")
    print("="*100)
    
    print("\n📈 LEGEND:")
    print("  🟢 Strong (20%+ hit rate, 10+ settled)")
    print("  🟡 Good (15-20% hit rate, 10+ settled)")
    print("  🔴 Weak (<15% hit rate, 10+ settled)")
    print("  ⚪ Early (Less than 10 settled predictions)")
    print("\n💡 TIP: Remove leagues with 🔴 after 20+ settled predictions\n")

if __name__ == '__main__':
    print_league_performance()

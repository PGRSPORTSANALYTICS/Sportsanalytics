#!/usr/bin/env python3
"""
UNIFIED BET TRACKING SERVICE
============================
Single source of truth for all betting results across all products.
Simplifies ROI calculations and ensures data consistency.
"""

from datetime import datetime
from typing import Optional, Dict, List
from db_helper import db_helper


class BetTracker:
    """Unified bet tracking for all product types"""
    
    PRODUCT_TYPES = [
        'football_single',  # Exact Score predictions
        'sgp',              # Same Game Parlays
        'value_single',     # Value Singles (1X2, O/U, BTTS)
        'womens_1x2',       # Women's Match Winner
        'basket_single',    # College Basketball singles
        'basket_parlay'     # College Basketball parlays
    ]
    
    @staticmethod
    def record_result(product_type: str, bet_id: int, stake: float, 
                      odds: float, is_won: bool) -> Dict:
        """Record a bet result in unified tracking table"""
        payout = stake * odds if is_won else 0
        profit = payout - stake
        
        db_helper.execute('''
            INSERT INTO bet_results (product_type, bet_id, stake, payout, profit, is_won, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_type, bet_id) 
            DO UPDATE SET stake = EXCLUDED.stake, payout = EXCLUDED.payout, 
                          profit = EXCLUDED.profit, is_won = EXCLUDED.is_won
        ''', (product_type, bet_id, stake, payout, profit, is_won, datetime.now()))
        
        return {
            'product_type': product_type,
            'bet_id': bet_id,
            'stake': stake,
            'payout': payout,
            'profit': profit,
            'is_won': is_won
        }
    
    @staticmethod
    def get_product_stats(product_type: Optional[str] = None) -> Dict:
        """Get stats for a specific product or all products"""
        if product_type:
            row = db_helper.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_won THEN 1 ELSE 0 END) as wins,
                    SUM(stake) as staked,
                    SUM(profit) as profit
                FROM bet_results
                WHERE product_type = %s
            ''', (product_type,), fetch='one')
        else:
            row = db_helper.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_won THEN 1 ELSE 0 END) as wins,
                    SUM(stake) as staked,
                    SUM(profit) as profit
                FROM bet_results
            ''', (), fetch='one')
        
        total, wins, staked, profit = row if row else (0, 0, 0, 0)
        total = total or 0
        wins = wins or 0
        staked = staked or 0
        profit = profit or 0
        
        return {
            'total': total,
            'wins': wins,
            'losses': total - wins,
            'staked': round(staked, 2),
            'profit': round(profit, 2),
            'roi': round((profit / staked * 100), 1) if staked > 0 else 0,
            'hit_rate': round((wins / total * 100), 1) if total > 0 else 0
        }
    
    @staticmethod
    def get_all_stats() -> Dict:
        """Get stats grouped by product type"""
        rows = db_helper.execute('''
            SELECT 
                product_type,
                COUNT(*) as total,
                SUM(CASE WHEN is_won THEN 1 ELSE 0 END) as wins,
                SUM(stake) as staked,
                SUM(profit) as profit
            FROM bet_results
            GROUP BY product_type
        ''', (), fetch='all')
        
        stats = {}
        for row in rows or []:
            product_type, total, wins, staked, profit = row
            total = total or 0
            wins = wins or 0
            staked = staked or 0
            profit = profit or 0
            
            stats[product_type] = {
                'total': total,
                'wins': wins,
                'losses': total - wins,
                'staked': round(staked, 2),
                'profit': round(profit, 2),
                'roi': round((profit / staked * 100), 1) if staked > 0 else 0,
                'hit_rate': round((wins / total * 100), 1) if total > 0 else 0
            }
        
        return stats


def migrate_existing_data():
    """Migrate existing bet data from all product tables"""
    print("🔄 Migrating existing bet data to unified tracking...")
    
    migrated = 0
    
    # Migrate Exact Score predictions
    exact_rows = db_helper.execute('''
        SELECT id, stake, odds, outcome
        FROM football_opportunities
        WHERE market = 'exact_score' AND outcome IN ('win', 'won', 'loss', 'lost')
    ''', (), fetch='all')
    
    for row in exact_rows or []:
        bet_id, stake, odds, outcome = row
        is_won = outcome in ('win', 'won')
        BetTracker.record_result('football_single', bet_id, stake or 100, odds or 10, is_won)
        migrated += 1
    
    print(f"  ✅ Migrated {len(exact_rows or [])} Exact Score bets")
    
    # Migrate SGP predictions (exclude Monster/BEAST)
    sgp_rows = db_helper.execute('''
        SELECT id, stake, bookmaker_odds, outcome
        FROM sgp_predictions
        WHERE outcome IN ('win', 'won', 'loss', 'lost')
          AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%Monster%%')
          AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%BEAST%%')
    ''', (), fetch='all')
    
    for row in sgp_rows or []:
        bet_id, stake, odds, outcome = row
        is_won = outcome in ('win', 'won')
        BetTracker.record_result('sgp', bet_id, stake or 160, odds or 3, is_won)
        migrated += 1
    
    print(f"  ✅ Migrated {len(sgp_rows or [])} SGP bets")
    
    # Migrate Value Singles
    vs_rows = db_helper.execute('''
        SELECT id, stake, odds, outcome
        FROM football_opportunities
        WHERE market = 'Value Single' AND outcome IN ('win', 'won', 'loss', 'lost')
    ''', (), fetch='all')
    
    for row in vs_rows or []:
        bet_id, stake, odds, outcome = row
        is_won = outcome in ('win', 'won')
        BetTracker.record_result('value_single', bet_id, stake or 100, odds or 2, is_won)
        migrated += 1
    
    print(f"  ✅ Migrated {len(vs_rows or [])} Value Singles bets")
    
    # Migrate Women's 1X2
    try:
        women_rows = db_helper.execute('''
            SELECT id, stake, odds, outcome
            FROM women_match_winner_predictions
            WHERE outcome IN ('win', 'won', 'loss', 'lost')
        ''', (), fetch='all')
        
        for row in women_rows or []:
            bet_id, stake, odds, outcome = row
            is_won = outcome in ('win', 'won')
            BetTracker.record_result('womens_1x2', bet_id, stake or 100, odds or 2, is_won)
            migrated += 1
        
        print(f"  ✅ Migrated {len(women_rows or [])} Women's 1X2 bets")
    except Exception as e:
        print(f"  ⚠️ Women's 1X2 table not found or empty: {e}")
    
    # Migrate College Basketball
    try:
        basket_rows = db_helper.execute('''
            SELECT id, stake, odds, status, is_parlay
            FROM basketball_predictions
            WHERE status IN ('won', 'lost')
        ''', (), fetch='all')
        
        for row in basket_rows or []:
            bet_id, stake, odds, status, is_parlay = row
            is_won = status == 'won'
            product_type = 'basket_parlay' if is_parlay else 'basket_single'
            BetTracker.record_result(product_type, bet_id, stake or 100, odds or 2, is_won)
            migrated += 1
        
        print(f"  ✅ Migrated {len(basket_rows or [])} College Basketball bets")
    except Exception as e:
        print(f"  ⚠️ Basketball table not found or empty: {e}")
    
    print(f"\n✅ Total migrated: {migrated} bets")
    
    # Show summary
    all_stats = BetTracker.get_all_stats()
    print("\n📊 UNIFIED BET TRACKING SUMMARY:")
    print("=" * 50)
    for product, stats in all_stats.items():
        print(f"  {product}: {stats['total']} bets | {stats['hit_rate']}% hit | {stats['roi']:+.1f}% ROI | {stats['profit']:+.0f} SEK")
    
    combined = BetTracker.get_product_stats()
    print("-" * 50)
    print(f"  TOTAL: {combined['total']} bets | {combined['hit_rate']}% hit | {combined['roi']:+.1f}% ROI | {combined['profit']:+.0f} SEK")


if __name__ == '__main__':
    migrate_existing_data()

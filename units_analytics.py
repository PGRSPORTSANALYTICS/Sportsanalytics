"""
Units Analytics Module - ROI + Units Tracking Mode
===================================================
Created: December 9, 2025

Analytics now run in Unit ROI mode. All picks are evaluated using a flat 1 unit 
stake for performance tracking. This allows high bet volume without tying results 
to a specific bankroll size. Real-money stakes (if any) are tracked separately.

Core Concepts:
- 1 unit = base stake for ALL AI bets in the analytics layer
- Every win = (odds - 1) units profit
- Every loss = -1 unit
- ROI = Total units won / Total units staked
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy import create_engine, text
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

ANALYTICS_STAKE_UNITS = 1.0
SIMULATED_STARTING_BANKROLL_UNITS = 100.0
DYNAMIC_STAKING_ENABLED = False


@dataclass
class ProductROI:
    """ROI statistics for a single product."""
    product_name: str
    bets_count: int
    wins: int
    losses: int
    pushes: int
    units_staked: float
    units_won: float
    roi_pct: float
    hit_rate_pct: float


@dataclass
class OverallROI:
    """Overall ROI statistics across all products."""
    total_bets: int
    total_wins: int
    total_losses: int
    total_pushes: int
    total_units_staked: float
    total_units_won: float
    overall_roi_pct: float
    overall_hit_rate_pct: float
    simulated_bankroll_units: float
    products: Dict[str, ProductROI]


def calculate_profit_units(odds: float, outcome: str) -> float:
    """
    Calculate profit in units for a single bet.
    
    Args:
        odds: Decimal odds (e.g., 1.85, 2.50)
        outcome: 'won', 'lost', 'void', 'push', 'pending'
    
    Returns:
        Profit in units:
        - Win: (odds - 1) * 1.0
        - Loss: -1.0
        - Push/Void: 0.0
        - Pending: 0.0
    """
    outcome_lower = str(outcome).lower().strip()
    
    if outcome_lower in ('won', 'win', 'w', '1'):
        return (float(odds) - 1.0) * ANALYTICS_STAKE_UNITS
    elif outcome_lower in ('lost', 'loss', 'l', '0'):
        return -ANALYTICS_STAKE_UNITS
    elif outcome_lower in ('void', 'push', 'cancelled', 'refund'):
        return 0.0
    else:
        return 0.0


def get_database_engine():
    """Get SQLAlchemy engine for database connection."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set")
    return create_engine(db_url)


def calculate_units_roi_from_bets(bets_df: pd.DataFrame) -> Dict:
    """
    Calculate units-based ROI from a DataFrame of bets.
    
    Expected columns: odds, outcome (and optionally: product, stake)
    
    Returns dict with:
    - bets_count, wins, losses, pushes
    - units_staked, units_won
    - roi_pct, hit_rate_pct
    """
    if bets_df.empty:
        return {
            'bets_count': 0,
            'wins': 0,
            'losses': 0,
            'pushes': 0,
            'units_staked': 0.0,
            'units_won': 0.0,
            'roi_pct': 0.0,
            'hit_rate_pct': 0.0
        }
    
    settled = bets_df[bets_df['outcome'].str.lower().isin(
        ['won', 'win', 'lost', 'loss', 'void', 'push', 'w', 'l', '1', '0']
    )].copy()
    
    if settled.empty:
        return {
            'bets_count': len(bets_df),
            'wins': 0,
            'losses': 0,
            'pushes': 0,
            'units_staked': float(len(bets_df)) * ANALYTICS_STAKE_UNITS,
            'units_won': 0.0,
            'roi_pct': 0.0,
            'hit_rate_pct': 0.0
        }
    
    settled['outcome_lower'] = settled['outcome'].str.lower().str.strip()
    
    wins = len(settled[settled['outcome_lower'].isin(['won', 'win', 'w', '1'])])
    losses = len(settled[settled['outcome_lower'].isin(['lost', 'loss', 'l', '0'])])
    pushes = len(settled[settled['outcome_lower'].isin(['void', 'push', 'cancelled', 'refund'])])
    
    settled['profit_units'] = settled.apply(
        lambda row: calculate_profit_units(row['odds'], row['outcome']),
        axis=1
    )
    
    units_staked = float(len(settled)) * ANALYTICS_STAKE_UNITS
    units_won = settled['profit_units'].sum()
    
    roi_pct = (units_won / units_staked * 100) if units_staked > 0 else 0.0
    hit_rate_pct = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
    
    return {
        'bets_count': len(settled),
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'units_staked': units_staked,
        'units_won': units_won,
        'roi_pct': roi_pct,
        'hit_rate_pct': hit_rate_pct
    }


def get_overall_units_roi() -> OverallROI:
    """
    Calculate overall units-based ROI across all products.
    
    Returns OverallROI dataclass with complete statistics.
    """
    engine = get_database_engine()
    products = {}
    
    total_bets = 0
    total_wins = 0
    total_losses = 0
    total_pushes = 0
    total_units_staked = 0.0
    total_units_won = 0.0
    
    with engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT 
                    odds, 
                    outcome,
                    'Value Singles' as product
                FROM bets 
                WHERE LOWER(outcome) IN ('won', 'win', 'lost', 'loss', 'void', 'push')
                  AND bet_type NOT LIKE '%exact%'
                  AND bet_type NOT LIKE '%parlay%'
            """))
            vs_rows = result.fetchall()
            
            if vs_rows:
                vs_df = pd.DataFrame(vs_rows, columns=['odds', 'outcome', 'product'])
                vs_stats = calculate_units_roi_from_bets(vs_df)
                products['Value Singles'] = ProductROI(
                    product_name='Value Singles',
                    bets_count=vs_stats['bets_count'],
                    wins=vs_stats['wins'],
                    losses=vs_stats['losses'],
                    pushes=vs_stats['pushes'],
                    units_staked=vs_stats['units_staked'],
                    units_won=vs_stats['units_won'],
                    roi_pct=vs_stats['roi_pct'],
                    hit_rate_pct=vs_stats['hit_rate_pct']
                )
                total_bets += vs_stats['bets_count']
                total_wins += vs_stats['wins']
                total_losses += vs_stats['losses']
                total_pushes += vs_stats['pushes']
                total_units_staked += vs_stats['units_staked']
                total_units_won += vs_stats['units_won']
        except Exception as e:
            print(f"Error fetching Value Singles: {e}")
        
        try:
            result = conn.execute(text("""
                SELECT 
                    total_odds as odds, 
                    status as outcome,
                    'ML Parlays' as product
                FROM ml_parlay_predictions 
                WHERE LOWER(status) IN ('won', 'win', 'lost', 'loss', 'void', 'push')
            """))
            ml_rows = result.fetchall()
            
            if ml_rows:
                ml_df = pd.DataFrame(ml_rows, columns=['odds', 'outcome', 'product'])
                ml_stats = calculate_units_roi_from_bets(ml_df)
                products['ML Parlays'] = ProductROI(
                    product_name='ML Parlays',
                    bets_count=ml_stats['bets_count'],
                    wins=ml_stats['wins'],
                    losses=ml_stats['losses'],
                    pushes=ml_stats['pushes'],
                    units_staked=ml_stats['units_staked'],
                    units_won=ml_stats['units_won'],
                    roi_pct=ml_stats['roi_pct'],
                    hit_rate_pct=ml_stats['hit_rate_pct']
                )
                total_bets += ml_stats['bets_count']
                total_wins += ml_stats['wins']
                total_losses += ml_stats['losses']
                total_pushes += ml_stats['pushes']
                total_units_staked += ml_stats['units_staked']
                total_units_won += ml_stats['units_won']
        except Exception as e:
            print(f"Error fetching ML Parlays: {e}")
        
        try:
            result = conn.execute(text("""
                SELECT 
                    odds, 
                    result as outcome,
                    'Basketball' as product
                FROM basketball_predictions 
                WHERE LOWER(result) IN ('won', 'win', 'lost', 'loss', 'void', 'push')
            """))
            bb_rows = result.fetchall()
            
            if bb_rows:
                bb_df = pd.DataFrame(bb_rows, columns=['odds', 'outcome', 'product'])
                bb_stats = calculate_units_roi_from_bets(bb_df)
                products['Basketball'] = ProductROI(
                    product_name='Basketball',
                    bets_count=bb_stats['bets_count'],
                    wins=bb_stats['wins'],
                    losses=bb_stats['losses'],
                    pushes=bb_stats['pushes'],
                    units_staked=bb_stats['units_staked'],
                    units_won=bb_stats['units_won'],
                    roi_pct=bb_stats['roi_pct'],
                    hit_rate_pct=bb_stats['hit_rate_pct']
                )
                total_bets += bb_stats['bets_count']
                total_wins += bb_stats['wins']
                total_losses += bb_stats['losses']
                total_pushes += bb_stats['pushes']
                total_units_staked += bb_stats['units_staked']
                total_units_won += bb_stats['units_won']
        except Exception as e:
            print(f"Error fetching Basketball: {e}")
    
    overall_roi_pct = (total_units_won / total_units_staked * 100) if total_units_staked > 0 else 0.0
    overall_hit_rate = (total_wins / (total_wins + total_losses) * 100) if (total_wins + total_losses) > 0 else 0.0
    simulated_bankroll = SIMULATED_STARTING_BANKROLL_UNITS + total_units_won
    
    return OverallROI(
        total_bets=total_bets,
        total_wins=total_wins,
        total_losses=total_losses,
        total_pushes=total_pushes,
        total_units_staked=total_units_staked,
        total_units_won=total_units_won,
        overall_roi_pct=overall_roi_pct,
        overall_hit_rate_pct=overall_hit_rate,
        simulated_bankroll_units=simulated_bankroll,
        products=products
    )


def print_units_roi_summary():
    """Print a summary of units-based ROI to console."""
    try:
        roi = get_overall_units_roi()
        
        print("\n" + "=" * 60)
        print("📊 UNITS ROI ANALYTICS SUMMARY")
        print("=" * 60)
        print(f"Mode: Flat 1 unit stake per bet (analytics only)")
        print("-" * 60)
        
        sign = "+" if roi.total_units_won >= 0 else ""
        print(f"Total ROI:           {sign}{roi.overall_roi_pct:.1f}%")
        print(f"Total Profit:        {sign}{roi.total_units_won:.1f} units")
        print(f"Hit Rate:            {roi.overall_hit_rate_pct:.1f}%")
        print(f"Bets Tracked:        {roi.total_bets}")
        print(f"Simulated Bankroll:  {roi.simulated_bankroll_units:.1f}u (started at 100u)")
        
        print("\n" + "-" * 60)
        print("PER-PRODUCT BREAKDOWN:")
        print("-" * 60)
        
        for name, prod in roi.products.items():
            sign = "+" if prod.units_won >= 0 else ""
            print(f"\n{name}:")
            print(f"  ROI: {sign}{prod.roi_pct:.1f}% | Units Won: {sign}{prod.units_won:.1f}u")
            print(f"  Bets: {prod.bets_count} | Hit Rate: {prod.hit_rate_pct:.1f}%")
            print(f"  W/L/P: {prod.wins}/{prod.losses}/{prod.pushes}")
        
        print("\n" + "=" * 60)
        
        return roi
        
    except Exception as e:
        print(f"Error calculating ROI summary: {e}")
        return None


def format_roi_display(roi_pct: float) -> str:
    """Format ROI for display with + sign for positive values."""
    sign = "+" if roi_pct >= 0 else ""
    return f"{sign}{roi_pct:.1f}% ROI"


def format_units_display(units: float) -> str:
    """Format units for display with + sign for positive values."""
    sign = "+" if units >= 0 else ""
    return f"{sign}{units:.1f} units"


if __name__ == "__main__":
    print_units_roi_summary()

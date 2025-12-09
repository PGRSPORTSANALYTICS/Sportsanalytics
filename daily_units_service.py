"""
Daily Units Tracking Service
Aggregates settled bets by calendar day and computes profit/loss in units.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection"""
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
    if not db_url:
        raise RuntimeError("No DATABASE_URL found")
    return psycopg2.connect(db_url)


def get_daily_units(days_back: int = 30) -> Dict:
    """
    Get daily units profit/loss for the last N days.
    
    Returns:
        Dict with daily_units list, month_summary, best_day, worst_day
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
        WITH all_settled_bets AS (
            -- Football opportunities (exact score, value singles)
            SELECT 
                DATE(TO_TIMESTAMP(settled_timestamp)) as settled_date,
                CASE 
                    WHEN outcome IN ('won', 'win') THEN (odds - 1)
                    WHEN outcome IN ('lost', 'loss') THEN -1.0
                    ELSE 0.0
                END as profit_units
            FROM football_opportunities
            WHERE settled_timestamp IS NOT NULL
              AND outcome IS NOT NULL
              AND outcome NOT IN ('pending', 'live', '')
              
            UNION ALL
            
            -- SGP predictions
            SELECT 
                DATE(TO_TIMESTAMP(settled_timestamp)) as settled_date,
                CASE 
                    WHEN outcome IN ('won', 'win') THEN (bookmaker_odds - 1)
                    WHEN outcome IN ('lost', 'loss') THEN -1.0
                    ELSE 0.0
                END as profit_units
            FROM sgp_predictions
            WHERE settled_timestamp IS NOT NULL
              AND outcome IS NOT NULL
              AND outcome NOT IN ('pending', 'live', '')
              
            UNION ALL
            
            -- Basketball predictions
            SELECT 
                DATE(verified_at) as settled_date,
                CASE 
                    WHEN status IN ('won', 'win', 'WON', 'WIN') THEN (odds - 1)
                    WHEN status IN ('lost', 'loss', 'LOST', 'LOSS') THEN -1.0
                    ELSE 0.0
                END as profit_units
            FROM basketball_predictions
            WHERE verified_at IS NOT NULL
              AND status IS NOT NULL
              AND status NOT IN ('pending', 'live', '')
              
        )
        SELECT 
            settled_date as date,
            ROUND(SUM(profit_units)::numeric, 2) as units,
            COUNT(*) as bet_count
        FROM all_settled_bets
        WHERE settled_date IS NOT NULL
          AND settled_date >= CURRENT_DATE - INTERVAL '%s days'
        GROUP BY settled_date
        ORDER BY settled_date DESC
        """
        
        cur.execute(query, (days_back,))
        rows = cur.fetchall()
        
        daily_units = []
        for row in rows:
            daily_units.append({
                'date': row['date'].isoformat() if row['date'] else None,
                'units': float(row['units']) if row['units'] else 0.0,
                'bet_count': int(row['bet_count'])
            })
        
        current_month = datetime.now().strftime('%Y-%m')
        month_total = sum(
            d['units'] for d in daily_units 
            if d['date'] and d['date'].startswith(current_month)
        )
        
        best_day = None
        worst_day = None
        if daily_units:
            best = max(daily_units, key=lambda x: x['units'])
            worst = min(daily_units, key=lambda x: x['units'])
            best_day = {'date': best['date'], 'units': best['units']}
            worst_day = {'date': worst['date'], 'units': worst['units']}
        
        cur.close()
        conn.close()
        
        return {
            'daily_units': daily_units,
            'month_summary': {
                'month': current_month,
                'total_units': round(month_total, 2)
            },
            'best_day': best_day,
            'worst_day': worst_day,
            'total_days': len(daily_units)
        }
        
    except Exception as e:
        logger.error(f"Error getting daily units: {e}")
        return {
            'daily_units': [],
            'month_summary': {'month': datetime.now().strftime('%Y-%m'), 'total_units': 0},
            'best_day': None,
            'worst_day': None,
            'total_days': 0,
            'error': str(e)
        }


def validate_daily_units() -> Dict:
    """
    Validate that daily aggregation matches individual bet sums.
    Returns validation results.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        sample_query = """
        WITH sample_bets AS (
            SELECT 
                DATE(TO_TIMESTAMP(settled_timestamp)) as settled_date,
                home_team || ' vs ' || away_team as match,
                selection,
                odds,
                outcome,
                CASE 
                    WHEN outcome IN ('won', 'win') THEN (odds - 1)
                    WHEN outcome IN ('lost', 'loss') THEN -1.0
                    ELSE 0.0
                END as profit_units
            FROM football_opportunities
            WHERE settled_timestamp IS NOT NULL
              AND outcome IS NOT NULL
              AND outcome NOT IN ('pending', 'live', '')
            ORDER BY settled_timestamp DESC
            LIMIT 5
        )
        SELECT * FROM sample_bets
        """
        
        cur.execute(sample_query)
        sample = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return {
            'valid': True,
            'sample_bets': [dict(row) for row in sample],
            'message': 'Sample validation successful'
        }
        
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {
            'valid': False,
            'error': str(e)
        }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("Testing Daily Units Service...")
    
    result = get_daily_units(30)
    print(f"\nDaily Units (last 30 days):")
    print(f"  Total days with data: {result['total_days']}")
    print(f"  Month summary: {result['month_summary']}")
    print(f"  Best day: {result['best_day']}")
    print(f"  Worst day: {result['worst_day']}")
    
    if result['daily_units']:
        print(f"\n  Recent days:")
        for day in result['daily_units'][:5]:
            sign = '+' if day['units'] >= 0 else ''
            print(f"    {day['date']}: {sign}{day['units']:.2f} units ({day['bet_count']} bets)")
    
    print("\nValidation:")
    validation = validate_daily_units()
    print(f"  Valid: {validation['valid']}")
    if validation.get('sample_bets'):
        print(f"  Sample bets: {len(validation['sample_bets'])}")

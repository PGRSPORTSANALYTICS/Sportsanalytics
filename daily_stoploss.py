"""
Daily Soft Stop-Loss Module
===========================
Implements a -5 unit daily stop-loss for production betting.
- Stops NEW bets when daily loss reaches -5u
- Pending/running bets are NOT affected (soft stop-loss)
- Resets at midnight UTC
- All timestamps use UTC (created_at and settled_at are stored as timestamptz)
"""

import os
import logging
from datetime import datetime, timezone
from typing import Tuple
import psycopg2

logger = logging.getLogger(__name__)

DAILY_STOPLOSS_UNITS = -5.0  # Single source of truth for stop-loss threshold


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(os.environ['DATABASE_URL'])


def get_todays_pnl() -> Tuple[float, int, int]:
    """
    Get today's settled P/L in units.
    
    Returns:
        Tuple of (total_units, wins, losses)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    cursor.execute("""
        SELECT 
            COALESCE(SUM(
                CASE 
                    WHEN norm_result = 'WON' THEN (odds - 1) * 1.0
                    WHEN norm_result = 'LOST' THEN -1.0
                    ELSE 0
                END
            ), 0) as total_units,
            COUNT(CASE WHEN norm_result = 'WON' THEN 1 END) as wins,
            COUNT(CASE WHEN norm_result = 'LOST' THEN 1 END) as losses
        FROM normalized_bets
        WHERE DATE(settled_at) = %s
          AND norm_result IN ('WON', 'LOST')
          AND product IN ('CARDS', 'CORNERS', 'VALUE_SINGLE')
    """, (today,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if result:
        return float(result[0] or 0), int(result[1] or 0), int(result[2] or 0)
    return 0.0, 0, 0


def get_todays_pending_exposure() -> Tuple[float, int]:
    """
    Get today's pending bet exposure (unsettled bets).
    
    Returns:
        Tuple of (max_loss_exposure, pending_count)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    cursor.execute("""
        SELECT 
            COUNT(*) as pending_count,
            COALESCE(SUM(1.0), 0) as exposure
        FROM normalized_bets
        WHERE DATE(created_at) = %s
          AND (norm_result IS NULL OR norm_result = 'PENDING')
          AND product IN ('CARDS', 'CORNERS', 'VALUE_SINGLE')
    """, (today,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if result:
        return float(result[1] or 0), int(result[0] or 0)
    return 0.0, 0


def is_stoploss_triggered() -> Tuple[bool, float, str]:
    """
    Check if daily stop-loss has been triggered.
    
    Returns:
        Tuple of (triggered, current_pnl, message)
    """
    settled_pnl, wins, losses = get_todays_pnl()
    pending_exposure, pending_count = get_todays_pending_exposure()
    
    worst_case = settled_pnl - pending_exposure
    
    if settled_pnl <= DAILY_STOPLOSS_UNITS:
        message = f"🛑 STOP-LOSS TRIGGERED: Today's settled P/L is {settled_pnl:+.1f}u (limit: {DAILY_STOPLOSS_UNITS}u). No new bets allowed."
        logger.warning(message)
        return True, settled_pnl, message
    
    if worst_case <= DAILY_STOPLOSS_UNITS:
        message = f"⚠️ STOP-LOSS WARNING: Settled {settled_pnl:+.1f}u + {pending_count} pending = worst case {worst_case:+.1f}u. Approaching limit."
        logger.info(message)
        return False, settled_pnl, message
    
    message = f"✅ Daily P/L: {settled_pnl:+.1f}u ({wins}W/{losses}L), {pending_count} pending. Stop-loss not triggered."
    return False, settled_pnl, message


def can_place_new_bet(product: str = "GENERAL") -> Tuple[bool, str]:
    """
    Check if a new bet can be placed based on daily stop-loss.
    
    Args:
        product: The betting product (for logging)
        
    Returns:
        Tuple of (can_place, reason)
    """
    triggered, pnl, message = is_stoploss_triggered()
    
    if triggered:
        logger.warning(f"🛑 [{product}] Bet blocked by daily stop-loss at {pnl:+.1f}u")
        return False, message
    
    return True, message


def log_stoploss_status():
    """Log current stop-loss status (for scheduled checks)."""
    triggered, pnl, message = is_stoploss_triggered()
    logger.info(f"📊 Stop-Loss Status: {message}")
    return triggered, pnl

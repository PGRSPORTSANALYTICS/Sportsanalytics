#!/usr/bin/env python3
"""
Re-verify all October 2025 predictions to populate actual_score field
"""
import sqlite3
import sys
import logging
from verify_results import RealResultVerifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reverify_october():
    """Re-verify all October predictions that have outcome but no actual_score"""
    
    db_path = 'data/real_football.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) 
        FROM football_opportunities 
        WHERE outcome IN ('won', 'lost')
        AND (actual_score IS NULL OR actual_score = '')
        AND match_date < '2025-11-01'
    """)
    total = cursor.fetchone()[0]
    
    print(f"\n{'='*70}")
    print(f"🔄 RE-VERIFICATION OF {total} OCTOBER PREDICTIONS")
    print(f"{'='*70}\n")
    
    cursor.execute("""
        UPDATE football_opportunities 
        SET outcome = NULL, 
            profit_loss = NULL,
            status = 'pending'
        WHERE outcome IN ('won', 'lost')
        AND (actual_score IS NULL OR actual_score = '')
        AND match_date < '2025-11-01'
    """)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Reset {total} predictions to pending status")
    print(f"🔍 Starting verification with updated code...\n")
    
    verifier = RealResultVerifier(db_path=db_path)
    verifier.verify_pending_tips()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) 
        FROM football_opportunities 
        WHERE outcome IN ('won', 'lost')
        AND actual_score IS NOT NULL 
        AND actual_score != ''
    """)
    verified = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) 
        FROM football_opportunities 
        WHERE outcome IN ('won', 'lost')
        AND (actual_score IS NULL OR actual_score = '')
    """)
    still_missing = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n{'='*70}")
    print(f"📊 RE-VERIFICATION COMPLETE")
    print(f"{'='*70}")
    print(f"✅ With actual_score: {verified}")
    print(f"⚠️  Still missing: {still_missing}")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    try:
        reverify_october()
    except Exception as e:
        logger.error(f"❌ Re-verification failed: {e}")
        sys.exit(1)

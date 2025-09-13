#!/usr/bin/env python3
"""
Automated Result Verification Scheduler
=====================================
Runs verification every 6 hours to check for completed matches.
Only processes REAL results - no simulated data.
"""

import schedule
import time
import logging
from verify_results import RealResultVerifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_verification():
    """Run real result verification"""
    logger.info("🔄 Running scheduled real result verification...")
    
    try:
        verifier = RealResultVerifier()
        stats = verifier.verify_pending_tips()
        
        logger.info(f"✅ Verification complete - Verified: {stats['verified']}, Failed: {stats['failed']}")
        
        if stats['verified'] > 0:
            logger.info(f"🎉 {stats['verified']} tips verified with REAL results!")
            
    except Exception as e:
        logger.error(f"❌ Verification error: {e}")

if __name__ == "__main__":
    logger.info("🚀 Starting automated verification scheduler")
    logger.info("🔒 REAL RESULTS ONLY - No fake data")
    
    # Schedule verification every 6 hours
    schedule.every(6).hours.do(run_verification)
    
    # Run once immediately
    run_verification()
    
    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(3600)  # Check every hour
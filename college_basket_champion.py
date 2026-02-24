#!/usr/bin/env python3
"""
College Basketball Champion - Automated NCAAB Value Finder
Runs continuously to generate value picks for college basketball
"""

import logging
import time
import schedule
from datetime import datetime
from college_basket_value_engine import CollegeBasketValueEngine, OddsAPIClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_prediction_cycle():
    """Run one cycle of NCAAB value picking"""
    logger.info("="*60)
    logger.info("🏀 COLLEGE BASKETBALL VALUE CYCLE STARTING")
    logger.info("="*60)
    
    try:
        client = OddsAPIClient()
        engine = CollegeBasketValueEngine(
            client=client,
            max_singles=6,
            min_odds=1.75,   # Win machine: tight odds window
            max_odds=2.00,   # Win machine: high hit-rate zone
            allow_parlays=False
        )
        
        logger.info("📊 Fetching NCAAB games and analyzing value...")
        picks = engine.generate_value_singles()
        
        if picks:
            saved_count = engine.save_picks(picks)
            logger.info(f"✅ Cycle complete: {saved_count} NCAAB picks saved")
            
            singles = [p for p in picks if "PARLAY" not in p.match]
            parlays = [p for p in picks if "PARLAY" in p.match]
            
            logger.info(f"   Singles: {len(singles)} | Parlays: {len(parlays)}")
            
            if singles:
                top_single = singles[0]
                logger.info(f"   Top Single: {top_single.selection} @ {top_single.odds:.2f} ({top_single.ev*100:.1f}% EV)")
            
            if parlays:
                top_parlay = parlays[0]
                logger.info(f"   Top Parlay: {top_parlay.market} @ {top_parlay.odds:.2f} ({top_parlay.ev*100:.1f}% EV)")
        else:
            logger.info("📊 No qualifying picks in this cycle")
            
    except Exception as e:
        logger.error(f"❌ Error in prediction cycle: {e}", exc_info=True)
    
    logger.info("="*60)
    logger.info(f"⏰ Next run scheduled in 2 hours")
    logger.info("="*60)


def main():
    """Main loop for NCAAB value picking"""
    logger.info("🚀 College Basketball WIN MACHINE v3.0 Starting...")
    logger.info("🏀 Sport: NCAAB (College Basketball)")
    logger.info("🎰 Mode: WIN MACHINE - No EV filter, fair prob validation only")
    logger.info("🎯 Odds Range: 1.75 - 2.00 (tight win zone)")
    logger.info("🔄 Prediction cycle: Every 2 hours")
    logger.info("="*60)
    
    run_prediction_cycle()
    
    schedule.every(2).hours.do(run_prediction_cycle)
    
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()

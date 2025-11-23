#!/usr/bin/env python3
"""
Women's 1X2 Champion - Automated Match Winner Predictions
Runs continuously to generate predictions for women's football matches
"""

import logging
import time
import schedule
from datetime import datetime
from women_1x2_predictor import Women1X2Predictor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_prediction_cycle():
    """Run one cycle of women's 1X2 predictions"""
    logger.info("="*60)
    logger.info("👩⚽ WOMEN'S 1X2 PREDICTION CYCLE STARTING")
    logger.info("="*60)
    
    try:
        predictor = Women1X2Predictor(mode='TRAIN')
        
        # Generate predictions
        predictions = predictor.generate_predictions()
        
        if predictions:
            # Save to database
            saved_count = predictor.save_predictions(predictions)
            logger.info(f"✅ Cycle complete: {saved_count} women's 1X2 predictions saved")
        else:
            logger.info("📊 No qualifying predictions in this cycle")
            
    except Exception as e:
        logger.error(f"❌ Error in prediction cycle: {e}", exc_info=True)
    
    logger.info("="*60)
    logger.info(f"⏰ Next run scheduled in 1 hour")
    logger.info("="*60)


def main():
    """Main loop for women's 1X2 predictions"""
    logger.info("🚀 Women's 1X2 Champion Starting...")
    logger.info("📅 Mode: TRAIN (3% EV threshold)")
    logger.info("🔄 Prediction cycle: Every 1 hour")
    logger.info("="*60)
    
    # Run immediately on startup
    run_prediction_cycle()
    
    # Schedule hourly runs
    schedule.every(1).hours.do(run_prediction_cycle)
    
    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()

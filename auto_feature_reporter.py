"""
Automated Feature Importance Reporter
Activates once 100+ settled predictions with features are available
"""

import sqlite3
import logging
from datetime import datetime
from feature_analytics import FeatureAnalytics
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AutoFeatureReporter:
    """Automatically generates feature importance reports when enough data is available"""
    
    def __init__(self, db_path: str = 'data/real_football.db'):
        self.db_path = db_path
        self.analytics = FeatureAnalytics(db_path)
        self.min_samples = 100
        self.report_interval_samples = 50
    
    def check_and_report(self):
        """Check if we have enough data, generate report if threshold reached"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) as settled_count
                FROM feature_logs
                WHERE outcome IN ('won', 'win', 'lost', 'loss')
            """)
            
            settled_count = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT MAX(last_updated) as last_report
                FROM feature_importance
            """)
            
            last_report = cursor.fetchone()[0]
            conn.close()
            
            logger.info(f"📊 Current settled predictions with features: {settled_count}/{self.min_samples}")
            
            if settled_count < self.min_samples:
                logger.info(f"⏳ Need {self.min_samples - settled_count} more settled predictions before first report")
                return False
            
            should_generate = False
            
            if last_report is None:
                logger.info("🎯 MILESTONE REACHED! Generating first feature importance report...")
                should_generate = True
            else:
                cursor.execute("""
                    SELECT COUNT(*) as new_settled
                    FROM feature_logs
                    WHERE outcome IN ('won', 'win', 'lost', 'loss')
                    AND created_at > ?
                """, (last_report,))
                
                new_settled = cursor.fetchone()[0]
                
                if new_settled >= self.report_interval_samples:
                    logger.info(f"🔄 {new_settled} new predictions settled, regenerating report...")
                    should_generate = True
            
            if should_generate:
                self._generate_report()
                return True
            else:
                logger.info(f"✅ Feature importance up to date ({settled_count} total samples)")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error checking feature report status: {e}")
            return False
    
    def _generate_report(self):
        """Generate and save feature importance report"""
        try:
            logger.info("🚀 Calculating feature importance from settled predictions...")
            
            importance_df = self.analytics.calculate_feature_importance()
            
            if len(importance_df) == 0:
                logger.warning("⚠️ No feature importance data calculated")
                return
            
            self.analytics.save_importance_to_db()
            
            logger.info(f"✅ Feature importance calculated for {len(importance_df)} features")
            
            self._print_top_features(importance_df)
            
        except Exception as e:
            logger.error(f"❌ Error generating feature report: {e}")
    
    def _print_top_features(self, importance_df: pd.DataFrame):
        """Print summary of top features"""
        logger.info("\n" + "="*60)
        logger.info("📊 TOP 10 MOST IMPORTANT FEATURES FOR WINNING PREDICTIONS")
        logger.info("="*60)
        
        top_features = importance_df.nlargest(10, 'importance_score')
        
        for i, (idx, row) in enumerate(top_features.iterrows(), 1):
            logger.info(f"\n{i}. {row['feature_name']}")
            logger.info(f"   Category: {row['category']}")
            logger.info(f"   Win Avg: {row['win_avg']:.3f} | Loss Avg: {row['loss_avg']:.3f}")
            logger.info(f"   Relative Diff: {row['relative_diff_pct']:.1f}%")
            logger.info(f"   Importance Score: {row['importance_score']:.2f}")
            logger.info(f"   Sample Size: {row['sample_size']} predictions")
        
        logger.info("\n" + "="*60)
        
        by_category = importance_df.groupby('category')['importance_score'].mean().sort_values(ascending=False)
        
        logger.info("📊 FEATURE CATEGORIES BY IMPORTANCE")
        logger.info("="*60)
        
        for category, avg_importance in by_category.items():
            count = len(importance_df[importance_df['category'] == category])
            logger.info(f"   {category}: {avg_importance:.2f} avg ({count} features)")
        
        logger.info("="*60 + "\n")
    
    def get_report_status(self) -> dict:
        """Get current status of feature analysis"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) as total_logged,
                       SUM(CASE WHEN outcome IN ('won','win','lost','loss') THEN 1 ELSE 0 END) as settled,
                       SUM(CASE WHEN outcome IN ('won','win') THEN 1 ELSE 0 END) as wins,
                       AVG(data_completeness) as avg_completeness
                FROM feature_logs
            """)
            
            row = cursor.fetchone()
            
            cursor.execute("SELECT COUNT(*) FROM feature_importance")
            importance_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT MAX(last_updated) FROM feature_importance")
            last_updated = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_logged': row[0] or 0,
                'settled': row[1] or 0,
                'wins': row[2] or 0,
                'avg_completeness': row[3] or 0,
                'importance_features_analyzed': importance_count,
                'last_report': last_updated,
                'ready_for_first_report': (row[1] or 0) >= self.min_samples,
                'needed_for_first_report': max(0, self.min_samples - (row[1] or 0))
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting report status: {e}")
            return {}


if __name__ == "__main__":
    logger.info("🚀 Starting Automated Feature Importance Reporter")
    
    reporter = AutoFeatureReporter()
    
    status = reporter.get_report_status()
    logger.info(f"\n📊 FEATURE ANALYSIS STATUS:")
    logger.info(f"   Total predictions logged: {status.get('total_logged', 0)}")
    logger.info(f"   Settled predictions: {status.get('settled', 0)}")
    logger.info(f"   Wins: {status.get('wins', 0)}")
    logger.info(f"   Average data completeness: {status.get('avg_completeness', 0):.1f}%")
    logger.info(f"   Features analyzed: {status.get('importance_features_analyzed', 0)}")
    
    if status.get('ready_for_first_report'):
        logger.info(f"   ✅ READY for feature importance analysis!")
    else:
        logger.info(f"   ⏳ Need {status.get('needed_for_first_report', 0)} more settled predictions")
    
    if status.get('last_report'):
        logger.info(f"   Last report: {status.get('last_report')}")
    
    logger.info("\n")
    
    reporter.check_and_report()
    
    logger.info("✅ Feature reporter check complete")

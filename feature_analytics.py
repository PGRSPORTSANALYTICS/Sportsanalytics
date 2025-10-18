"""
Feature Analytics Module
Tracks and analyzes which features contribute to prediction success
"""

import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

class FeatureAnalytics:
    """Tracks feature values and analyzes their correlation with prediction outcomes"""
    
    def __init__(self, db_path: str = 'data/real_football.db'):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Create feature tracking tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id TEXT NOT NULL,
                match_id TEXT NOT NULL,
                home_team TEXT,
                away_team TEXT,
                predicted_score TEXT,
                actual_score TEXT,
                outcome TEXT,
                features_json TEXT,
                quality_score REAL,
                data_completeness REAL,
                created_at TEXT,
                created_timestamp INTEGER
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_importance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name TEXT NOT NULL,
                category TEXT,
                win_correlation REAL,
                loss_correlation REAL,
                importance_score REAL,
                sample_size INTEGER,
                last_updated TEXT,
                UNIQUE(feature_name)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ Feature analytics database initialized")
    
    def log_prediction_features(
        self,
        prediction_id: str,
        match_id: str,
        home_team: str,
        away_team: str,
        predicted_score: str,
        features: Dict,
        quality_score: float = 0.0
    ):
        """Log all feature values for a prediction"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Calculate data completeness (% of features with real values)
            total_features = len(features)
            non_default_features = sum(1 for v in features.values() if v not in [0, 0.0, None, ''])
            data_completeness = (non_default_features / total_features * 100) if total_features > 0 else 0
            
            cursor.execute("""
                INSERT INTO feature_logs (
                    prediction_id, match_id, home_team, away_team,
                    predicted_score, features_json, quality_score,
                    data_completeness, created_at, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prediction_id,
                match_id,
                home_team,
                away_team,
                predicted_score,
                json.dumps(features),
                quality_score,
                data_completeness,
                datetime.now().isoformat(),
                int(datetime.now().timestamp())
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"📊 Logged {len(features)} features for prediction {prediction_id} (quality: {quality_score:.0f}%, completeness: {data_completeness:.0f}%)")
            
        except Exception as e:
            logger.error(f"❌ Failed to log features: {e}")
    
    def update_prediction_outcome(self, prediction_id: str, actual_score: str, outcome: str):
        """Update the outcome when a prediction is settled"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE feature_logs
                SET actual_score = ?, outcome = ?
                WHERE prediction_id = ?
            """, (actual_score, outcome, prediction_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Updated outcome for {prediction_id}: {actual_score} ({outcome})")
            
        except Exception as e:
            logger.error(f"❌ Failed to update outcome: {e}")
    
    def calculate_feature_importance(self) -> pd.DataFrame:
        """Calculate which features correlate with wins vs losses"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get all settled predictions with features
            query = """
                SELECT prediction_id, outcome, features_json, quality_score
                FROM feature_logs
                WHERE outcome IN ('won', 'win', 'lost', 'loss')
            """
            
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            if len(df) == 0:
                logger.warning("⚠️ No settled predictions to analyze")
                return pd.DataFrame()
            
            # Parse features
            all_features = {}
            for idx, row in df.iterrows():
                features = json.loads(row['features_json'])
                outcome_binary = 1 if row['outcome'] in ['won', 'win'] else 0
                
                for feature_name, feature_value in features.items():
                    if feature_name not in all_features:
                        all_features[feature_name] = {'wins': [], 'losses': []}
                    
                    if outcome_binary == 1:
                        all_features[feature_name]['wins'].append(feature_value)
                    else:
                        all_features[feature_name]['losses'].append(feature_value)
            
            # Calculate correlations and importance
            importance_data = []
            
            for feature_name, data in all_features.items():
                if len(data['wins']) > 0 and len(data['losses']) > 0:
                    win_mean = np.mean([v for v in data['wins'] if isinstance(v, (int, float))])
                    loss_mean = np.mean([v for v in data['losses'] if isinstance(v, (int, float))])
                    
                    # Normalize difference
                    if loss_mean != 0:
                        relative_diff = ((win_mean - loss_mean) / abs(loss_mean)) * 100
                    else:
                        relative_diff = 0
                    
                    # Categorize feature
                    category = self._categorize_feature(feature_name)
                    
                    importance_data.append({
                        'feature_name': feature_name,
                        'category': category,
                        'win_avg': win_mean,
                        'loss_avg': loss_mean,
                        'difference': win_mean - loss_mean,
                        'relative_diff_pct': relative_diff,
                        'importance_score': abs(relative_diff),
                        'sample_size': len(data['wins']) + len(data['losses']),
                        'win_count': len(data['wins']),
                        'loss_count': len(data['losses'])
                    })
            
            importance_df = pd.DataFrame(importance_data)
            
            if len(importance_df) > 0:
                importance_df = importance_df.sort_values('importance_score', ascending=False)
                logger.info(f"📊 Calculated importance for {len(importance_df)} features")
            
            return importance_df
            
        except Exception as e:
            logger.error(f"❌ Failed to calculate feature importance: {e}")
            return pd.DataFrame()
    
    def _categorize_feature(self, feature_name: str) -> str:
        """Categorize feature by type"""
        name_lower = feature_name.lower()
        
        if 'form' in name_lower or 'win_rate' in name_lower or 'ppg' in name_lower:
            return 'Team Form'
        elif 'h2h' in name_lower or 'head' in name_lower:
            return 'Head-to-Head'
        elif 'xg' in name_lower or 'goals' in name_lower:
            return 'Expected Goals'
        elif 'odds' in name_lower or 'movement' in name_lower:
            return 'Odds Movement'
        elif 'standing' in name_lower or 'rank' in name_lower or 'position' in name_lower:
            return 'League Standings'
        elif 'injury' in name_lower or 'lineup' in name_lower:
            return 'Injuries/Lineup'
        elif 'confidence' in name_lower or 'quality' in name_lower or 'edge' in name_lower:
            return 'Prediction Metrics'
        else:
            return 'Other'
    
    def get_top_features(self, n: int = 10, category: Optional[str] = None) -> pd.DataFrame:
        """Get top N most important features"""
        importance_df = self.calculate_feature_importance()
        
        if len(importance_df) == 0:
            return pd.DataFrame()
        
        if category:
            importance_df = importance_df[importance_df['category'] == category]
        
        return importance_df.head(n)
    
    def get_feature_performance_summary(self) -> Dict:
        """Get summary statistics about feature performance"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Overall stats
            stats_query = """
                SELECT 
                    COUNT(*) as total_logged,
                    COUNT(CASE WHEN outcome IN ('won', 'win') THEN 1 END) as wins,
                    COUNT(CASE WHEN outcome IN ('lost', 'loss') THEN 1 END) as losses,
                    AVG(quality_score) as avg_quality,
                    AVG(data_completeness) as avg_completeness
                FROM feature_logs
            """
            
            stats = pd.read_sql_query(stats_query, conn).iloc[0].to_dict()
            
            # Quality distribution
            quality_dist = """
                SELECT 
                    CASE 
                        WHEN quality_score >= 80 THEN 'High (80+)'
                        WHEN quality_score >= 60 THEN 'Medium (60-79)'
                        WHEN quality_score >= 40 THEN 'Low (40-59)'
                        ELSE 'Very Low (<40)'
                    END as quality_tier,
                    COUNT(*) as count,
                    COUNT(CASE WHEN outcome IN ('won', 'win') THEN 1 END) as wins,
                    COUNT(CASE WHEN outcome IN ('lost', 'loss') THEN 1 END) as losses
                FROM feature_logs
                WHERE outcome IS NOT NULL AND outcome != ''
                GROUP BY quality_tier
            """
            
            quality_tiers = pd.read_sql_query(quality_dist, conn)
            
            conn.close()
            
            return {
                'overall': stats,
                'quality_tiers': quality_tiers.to_dict('records')
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get performance summary: {e}")
            return {}
    
    def save_importance_to_db(self):
        """Save calculated feature importance back to database"""
        try:
            importance_df = self.calculate_feature_importance()
            
            if len(importance_df) == 0:
                return
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for _, row in importance_df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO feature_importance (
                        feature_name, category, win_correlation, loss_correlation,
                        importance_score, sample_size, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['feature_name'],
                    row['category'],
                    row['win_avg'],
                    row['loss_avg'],
                    row['importance_score'],
                    row['sample_size'],
                    datetime.now().isoformat()
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Saved {len(importance_df)} feature importance scores to database")
            
        except Exception as e:
            logger.error(f"❌ Failed to save feature importance: {e}")


if __name__ == "__main__":
    # Test the analytics system
    logging.basicConfig(level=logging.INFO)
    
    analytics = FeatureAnalytics()
    
    # Test logging
    test_features = {
        'home_xg': 1.8,
        'away_xg': 1.2,
        'home_form_win_rate': 0.6,
        'away_form_win_rate': 0.4,
        'h2h_over_2.5_rate': 0.7,
        'quality_score': 75.0
    }
    
    analytics.log_prediction_features(
        prediction_id='test_001',
        match_id='match_123',
        home_team='Team A',
        away_team='Team B',
        predicted_score='2-1',
        features=test_features,
        quality_score=75.0
    )
    
    print("\n📊 Feature Analytics System Ready!")

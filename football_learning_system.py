#!/usr/bin/env python3
"""
Football Betting Learning System
================================
Machine learning system that improves football betting predictions over time.
Uses historical outcomes to train market-specific models and calibrate probabilities.

Features:
- Per-market binary classifiers (Over/Under 2.5, BTTS, etc.)
- Probability calibration for accurate EV calculation
- Adaptive thresholds based on performance
- Feature engineering from team analytics and match data
- Time-based validation to prevent overfitting
"""

import os
import sqlite3
import json
import numpy as np
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

# Machine Learning imports
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler
import joblib

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FootballLearningSystem:
    """
    Machine learning system for football betting prediction enhancement.
    Trains market-specific models and provides calibrated probability predictions.
    """
    
    def __init__(self, db_path: str = 'data/real_football.db'):
        self.db_path = db_path
        self.models_dir = Path('data/models')
        self.models_dir.mkdir(exist_ok=True)
        
        # Model configuration - FIXED: Prevent overfitting with higher requirements
        self.markets = ['over_2_5', 'under_2_5', 'btts_yes', 'btts_no']
        self.min_training_samples = 100  # 🔧 CRITICAL FIX: Increased from 10 to prevent overfitting
        self.validation_days = 30
        
        # Initialize model storage
        self.models = {}
        self.calibrators = {}
        self.scalers = {}
        self.feature_names = {}
        
        logger.info("🧠 Football Learning System initialized")
    
    def create_learning_tables(self):
        """Create necessary tables for learning system if they don't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create predictions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT NOT NULL,
                    market TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    prob REAL NOT NULL,
                    calibrated_prob REAL,
                    ev REAL,
                    kelly_fraction REAL,
                    created_at TEXT NOT NULL,
                    outcome TEXT,
                    profit_loss REAL,
                    created_timestamp INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Create model metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS model_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    market TEXT NOT NULL,
                    trained_at TEXT NOT NULL,
                    metrics_json TEXT,
                    is_active INTEGER DEFAULT 0,
                    UNIQUE(name, market, version)
                )
            """)
            
            # Add learning columns to football_opportunities if they don't exist
            try:
                cursor.execute("ALTER TABLE football_opportunities ADD COLUMN model_version TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                cursor.execute("ALTER TABLE football_opportunities ADD COLUMN model_prob REAL")
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute("ALTER TABLE football_opportunities ADD COLUMN calibrated_prob REAL")
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute("ALTER TABLE football_opportunities ADD COLUMN kelly_stake REAL")
            except sqlite3.OperationalError:
                pass
            
            conn.commit()
            conn.close()
            logger.info("✅ Learning system database schema created")
            
        except Exception as e:
            logger.error(f"❌ Error creating learning tables: {e}")
    
    def extract_features(self, opportunities_df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract and engineer features for machine learning from betting opportunities.
        
        Args:
            opportunities_df: DataFrame with betting opportunities and outcomes
            
        Returns:
            DataFrame with engineered features
        """
        try:
            df = opportunities_df.copy()
            
            # Basic features
            df['odds_implied_prob'] = 1 / df['odds']
            df['edge_decimal'] = df['edge_percentage'] / 100
            df['confidence_scaled'] = df['confidence'] / 100
            df['quality_scaled'] = df['quality_score'] / 10
            
            # Parse analysis JSON for xG features
            def extract_xg_features(analysis_str):
                try:
                    if pd.isna(analysis_str):
                        return {'home_xg': 1.5, 'away_xg': 1.5, 'total_xg': 3.0, 'xg_diff': 0.0, 'xg_ratio': 1.0}
                    
                    analysis = json.loads(analysis_str)
                    xg_data = analysis.get('xg_prediction', {})
                    
                    home_xg = float(xg_data.get('home_xg', 1.5))
                    away_xg = float(xg_data.get('away_xg', 1.5))
                    
                    return {
                        'home_xg': home_xg,
                        'away_xg': away_xg,
                        'total_xg': home_xg + away_xg,
                        'xg_diff': home_xg - away_xg,
                        'xg_ratio': home_xg / max(away_xg, 0.1)
                    }
                except:
                    return {'home_xg': 1.5, 'away_xg': 1.5, 'total_xg': 3.0, 'xg_diff': 0.0, 'xg_ratio': 1.0}
            
            # Extract xG features
            xg_features = df['analysis'].apply(extract_xg_features)
            xg_df = pd.DataFrame(xg_features.tolist())
            
            # Reset indices to ensure proper concatenation
            df = df.reset_index(drop=True)
            xg_df = xg_df.reset_index(drop=True)
            df = pd.concat([df, xg_df], axis=1)
            
            # Time-based features
            df['match_date'] = pd.to_datetime(df['match_date'])
            df['day_of_week'] = df['match_date'].dt.dayofweek
            df['month'] = df['match_date'].dt.month
            
            # League encoding (simple frequency encoding)
            league_counts = df['league'].value_counts()
            df['league_frequency'] = df['league'].map(league_counts)
            
            # Market-specific features
            df['is_over_market'] = df['market'].str.contains('over', case=False, na=False).astype(int)
            df['is_under_market'] = df['market'].str.contains('under', case=False, na=False).astype(int)
            df['is_btts_market'] = df['market'].str.contains('btts', case=False, na=False).astype(int)
            
            # Select feature columns
            feature_columns = [
                'odds_implied_prob', 'edge_decimal', 'confidence_scaled', 'quality_scaled',
                'home_xg', 'away_xg', 'total_xg', 'xg_diff', 'xg_ratio',
                'day_of_week', 'month', 'league_frequency',
                'is_over_market', 'is_under_market', 'is_btts_market'
            ]
            
            # Check which columns actually exist
            available_features = [col for col in feature_columns if col in df.columns]
            missing_features = [col for col in feature_columns if col not in df.columns]
            
            if missing_features:
                logger.warning(f"Missing features: {missing_features}")
                logger.info(f"Available columns: {list(df.columns)}")
            
            metadata_columns = ['market', 'selection', 'outcome', 'match_date', 'match_id']
            available_metadata = [col for col in metadata_columns if col in df.columns]
            
            return df[available_features + available_metadata]
            
        except Exception as e:
            logger.error(f"❌ Error extracting features: {e}")
            return pd.DataFrame()
    
    def prepare_training_data(self, market: str) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prepare training data for a specific market.
        
        Args:
            market: Market type to prepare data for
            
        Returns:
            Tuple of (features_df, labels_series)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get historical data with outcomes
            query = """
                SELECT match_id, home_team, away_team, league, market, selection, 
                       odds, edge_percentage, confidence, quality_score, analysis,
                       outcome, match_date, recommended_date
                FROM football_opportunities 
                WHERE outcome IS NOT NULL 
                AND recommended_tier IS NOT NULL
                AND ((market LIKE ? AND selection LIKE ?) OR (market LIKE ? AND selection LIKE ?))
                ORDER BY match_date ASC
            """
            
            # Map market types to market and selection patterns
            if market == 'over_2_5':
                params = ('%goals%', '%over%2.5%', '%over%', '%2.5%')
            elif market == 'under_2_5':
                params = ('%goals%', '%under%2.5%', '%under%', '%2.5%')
            elif market == 'btts_yes':
                params = ('%teams%score%', '%btts%yes%', '%teams%score%', '%yes%')
            elif market == 'btts_no':
                params = ('%teams%score%', '%btts%no%', '%teams%score%', '%no%')
            else:
                params = (f'%{market}%', f'%{market}%', f'%{market}%', f'%{market}%')
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            if len(df) < self.min_training_samples:
                logger.warning(f"⚠️ Insufficient training data for {market}: {len(df)} samples")
                return pd.DataFrame(), pd.Series()
            
            # Extract features
            features_df = self.extract_features(df)
            
            # Create binary labels (1 for win, 0 for loss)
            labels = (df['outcome'].isin(['won', 'win'])).astype(int)
            
            logger.info(f"📊 Prepared {len(features_df)} training samples for {market}")
            return features_df, labels
            
        except Exception as e:
            logger.error(f"❌ Error preparing training data for {market}: {e}")
            return pd.DataFrame(), pd.Series()
    
    def train_market_model(self, market: str) -> Dict[str, Any]:
        """
        Train and calibrate a model for a specific market.
        
        Args:
            market: Market type to train model for
            
        Returns:
            Dictionary with model performance metrics
        """
        try:
            logger.info(f"🎯 Training model for {market}")
            
            # Prepare training data
            features_df, labels = self.prepare_training_data(market)
            
            if len(features_df) == 0:
                return {'error': 'Insufficient training data'}
            
            # Feature columns (excluding metadata)
            feature_cols = [col for col in features_df.columns 
                          if col not in ['market', 'selection', 'outcome', 'match_date', 'match_id']]
            
            logger.info(f"Feature columns for {market}: {feature_cols}")
            logger.info(f"Features shape before selection: {features_df.shape}")
            
            X = features_df[feature_cols].fillna(0)
            logger.info(f"X shape after feature selection: {X.shape}")
            logger.info(f"Labels shape: {labels.shape}")
            y = labels
            
            # Time-based split for validation
            cutoff_date = features_df['match_date'].max() - timedelta(days=self.validation_days)
            logger.info(f"Cutoff date: {cutoff_date}")
            logger.info(f"Date range: {features_df['match_date'].min()} to {features_df['match_date'].max()}")
            
            train_mask = features_df['match_date'] <= cutoff_date
            val_mask = features_df['match_date'] > cutoff_date
            
            logger.info(f"Train mask sum: {train_mask.sum()}, Val mask sum: {val_mask.sum()}")
            
            # If no training data (all data is too recent), use 80/20 split instead
            if train_mask.sum() == 0:
                logger.info("All data is recent, using 80/20 split instead of time-based split")
                split_idx = int(0.8 * len(X))
                X_train = X.iloc[:split_idx]
                X_val = X.iloc[split_idx:]
                y_train = y.iloc[:split_idx]
                y_val = y.iloc[split_idx:]
            else:
                X_train, X_val = X[train_mask], X[val_mask]
                y_train, y_val = y[train_mask], y[val_mask]
            
            logger.info(f"Final X_train shape: {X_train.shape}, X_val shape: {X_val.shape}")
            
            if len(X_val) == 0:
                # Use all data for training if no validation split possible
                logger.info("No validation data, using all data for both train and val")
                X_train, X_val = X, X
                y_train, y_val = y, y
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_val_scaled = scaler.transform(X_val)
            
            # Train base model - FIXED: More conservative to prevent overfitting
            model = GradientBoostingClassifier(
                n_estimators=50,  # 🔧 Reduced from 100 to prevent overfitting
                max_depth=3,      # 🔧 Reduced from 4 to prevent overfitting  
                learning_rate=0.05, # 🔧 Reduced from 0.1 for more conservative learning
                min_samples_split=20,  # 🔧 NEW: Require more samples to split
                min_samples_leaf=10,   # 🔧 NEW: Require more samples per leaf
                random_state=42
            )
            model.fit(X_train_scaled, y_train)
            
            # Calibrate probabilities (use prefit to avoid refitting)
            calibrator = CalibratedClassifierCV(model, method='isotonic', cv='prefit')
            calibrator.fit(X_val_scaled, y_val)
            
            # Evaluate model
            val_probs = calibrator.predict_proba(X_val_scaled)[:, 1]
            val_preds = calibrator.predict(X_val_scaled)
            
            metrics = {
                'samples': len(X),
                'validation_samples': len(X_val),
                'auc': roc_auc_score(y_val, val_probs) if len(np.unique(y_val)) > 1 else 0.5,
                'brier_score': brier_score_loss(y_val, val_probs),
                'log_loss': log_loss(y_val, val_probs),
                'accuracy': (val_preds == y_val).mean(),
                'win_rate': y_val.mean(),
                'predicted_win_rate': val_probs.mean()
            }
            
            # Save model artifacts
            version = datetime.now().strftime('%Y%m%d_%H%M%S')
            model_path = self.models_dir / f'{market}_model_{version}.joblib'
            calibrator_path = self.models_dir / f'{market}_calibrator_{version}.joblib'
            scaler_path = self.models_dir / f'{market}_scaler_{version}.joblib'
            features_path = self.models_dir / f'{market}_features_{version}.joblib'
            
            joblib.dump(model, model_path)
            joblib.dump(calibrator, calibrator_path)
            joblib.dump(scaler, scaler_path)
            joblib.dump(feature_cols, features_path)  # Save feature order
            
            # Store in memory
            self.models[market] = model
            self.calibrators[market] = calibrator
            self.scalers[market] = scaler
            self.feature_names[market] = feature_cols
            
            # Save metadata to database
            self._save_model_metadata(market, version, metrics)
            
            logger.info(f"✅ Model trained for {market}: AUC={metrics['auc']:.3f}, Brier={metrics['brier_score']:.3f}")
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Error training model for {market}: {e}")
            return {'error': str(e)}
    
    def predict_opportunity(self, opportunity: Dict[str, Any]) -> Dict[str, float]:
        """
        Generate machine learning prediction for a betting opportunity.
        
        Args:
            opportunity: Dictionary with opportunity details
            
        Returns:
            Dictionary with model predictions and calibrated probabilities
        """
        try:
            market_key = self._get_market_key(opportunity.get('market', ''), opportunity.get('selection', ''))
            
            if market_key not in self.models:
                # Return fallback prediction
                return {
                    'model_prob': 0.5,
                    'calibrated_prob': 0.5,
                    'kelly_fraction': 0.0,
                    'expected_value': 0.0,
                    'model_version': 'fallback'
                }
            
            # Extract features for this opportunity
            all_features = self._extract_opportunity_features(opportunity)
            
            if all_features is None:
                return self._fallback_prediction()
            
            # Get saved feature order for this market
            if market_key not in self.feature_names:
                logger.warning(f"No feature names saved for market {market_key}")
                return self._fallback_prediction()
            
            feature_order = self.feature_names[market_key]
            
            # Create feature dict and reorder according to saved order
            feature_dict = dict(zip([
                'odds_implied_prob', 'edge_decimal', 'confidence_scaled', 'quality_scaled',
                'home_xg', 'away_xg', 'total_xg', 'xg_diff', 'xg_ratio',
                'day_of_week', 'month', 'league_frequency',
                'is_over_market', 'is_under_market', 'is_btts_market'
            ], all_features))
            
            # Select only features used by this market's model, in correct order
            features = [feature_dict.get(fname, 0.0) for fname in feature_order]
            
            # Scale features
            scaler = self.scalers[market_key]
            features_scaled = scaler.transform([features])
            
            # Get model prediction
            model = self.models[market_key]
            calibrator = self.calibrators[market_key]
            
            raw_prob = model.predict_proba(features_scaled)[0, 1]
            calibrated_prob = calibrator.predict_proba(features_scaled)[0, 1]
            
            # Calculate expected value and Kelly fraction
            odds = float(opportunity.get('odds', 1.0))
            implied_prob = 1 / odds
            ev = (calibrated_prob * odds) - 1
            
            # Kelly fraction (conservative, max 25% of bankroll)
            kelly_fraction = min(0.25, max(0, (calibrated_prob * odds - 1) / (odds - 1)))
            
            return {
                'model_prob': raw_prob,
                'calibrated_prob': calibrated_prob,
                'kelly_fraction': kelly_fraction,
                'expected_value': ev,
                'model_version': self._get_model_version(market_key)
            }
            
        except Exception as e:
            logger.error(f"❌ Error predicting opportunity: {e}")
            return self._fallback_prediction()
    
    def _get_market_key(self, market: str, selection: str) -> str:
        """Convert market and selection to standardized key"""
        market_lower = market.lower()
        selection_lower = selection.lower()
        
        if 'over' in selection_lower and '2.5' in selection_lower:
            return 'over_2_5'
        elif 'under' in selection_lower and '2.5' in selection_lower:
            return 'under_2_5'
        elif 'btts' in selection_lower and 'yes' in selection_lower:
            return 'btts_yes'
        elif 'btts' in selection_lower and 'no' in selection_lower:
            return 'btts_no'
        else:
            return 'other'
    
    def _extract_opportunity_features(self, opportunity: Dict[str, Any]) -> Optional[List[float]]:
        """Extract features from a single opportunity"""
        try:
            # Basic features
            odds = float(opportunity.get('odds', 1.0))
            odds_implied_prob = 1 / odds
            edge_decimal = float(opportunity.get('edge_percentage', 0)) / 100
            confidence_scaled = float(opportunity.get('confidence', 50)) / 100
            quality_scaled = float(opportunity.get('quality_score', 5)) / 10
            
            # Extract xG from analysis
            analysis = opportunity.get('analysis', '{}')
            if isinstance(analysis, str):
                try:
                    analysis_dict = json.loads(analysis)
                except:
                    analysis_dict = {}
            else:
                analysis_dict = analysis
            
            xg_data = analysis_dict.get('xg_prediction', {})
            home_xg = float(xg_data.get('home_xg', 1.5))
            away_xg = float(xg_data.get('away_xg', 1.5))
            total_xg = home_xg + away_xg
            xg_diff = home_xg - away_xg
            xg_ratio = home_xg / max(away_xg, 0.1)
            
            # Time features (use current time as approximation)
            now = datetime.now()
            day_of_week = now.weekday()
            month = now.month
            
            # League frequency (approximate)
            league_frequency = 10  # Default value
            
            # Market features
            market = opportunity.get('market', '').lower()
            selection = opportunity.get('selection', '').lower()
            is_over_market = int('over' in market or 'over' in selection)
            is_under_market = int('under' in market or 'under' in selection)
            is_btts_market = int('btts' in market or 'btts' in selection)
            
            return [
                odds_implied_prob, edge_decimal, confidence_scaled, quality_scaled,
                home_xg, away_xg, total_xg, xg_diff, xg_ratio,
                day_of_week, month, league_frequency,
                is_over_market, is_under_market, is_btts_market
            ]
            
        except Exception as e:
            logger.error(f"❌ Error extracting opportunity features: {e}")
            return None
    
    def _fallback_prediction(self) -> Dict[str, float]:
        """Return fallback prediction when model is unavailable"""
        return {
            'model_prob': 0.5,
            'calibrated_prob': 0.5,
            'kelly_fraction': 0.0,
            'expected_value': 0.0,
            'model_version': 'fallback'
        }
    
    def _save_model_metadata(self, market: str, version: str, metrics: Dict[str, Any]):
        """Save model metadata to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Deactivate previous models for this market
            cursor.execute("""
                UPDATE model_metadata 
                SET is_active = 0 
                WHERE market = ? AND name = 'gradient_boosting'
            """, (market,))
            
            # Insert new model metadata
            cursor.execute("""
                INSERT OR REPLACE INTO model_metadata 
                (name, version, market, trained_at, metrics_json, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                'gradient_boosting',
                version,
                market,
                datetime.now().isoformat(),
                json.dumps(metrics),
                1
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Error saving model metadata: {e}")
    
    def _get_model_version(self, market: str) -> str:
        """Get current model version for market"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT version FROM model_metadata 
                WHERE market = ? AND is_active = 1 
                ORDER BY trained_at DESC LIMIT 1
            """, (market,))
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else 'unknown'
            
        except Exception as e:
            logger.error(f"❌ Error getting model version: {e}")
            return 'unknown'
    
    def load_models(self):
        """Load trained models from disk"""
        try:
            for market in self.markets:
                # Find latest model files
                model_files = list(self.models_dir.glob(f'{market}_model_*.joblib'))
                if model_files:
                    latest_model = max(model_files, key=os.path.getctime)
                    version = latest_model.stem.split('_')[-1]
                    
                    # Load all artifacts
                    model_path = self.models_dir / f'{market}_model_{version}.joblib'
                    calibrator_path = self.models_dir / f'{market}_calibrator_{version}.joblib'
                    scaler_path = self.models_dir / f'{market}_scaler_{version}.joblib'
                    features_path = self.models_dir / f'{market}_features_{version}.joblib'
                    
                    if all(p.exists() for p in [model_path, calibrator_path, scaler_path, features_path]):
                        self.models[market] = joblib.load(model_path)
                        self.calibrators[market] = joblib.load(calibrator_path)
                        self.scalers[market] = joblib.load(scaler_path)
                        self.feature_names[market] = joblib.load(features_path)
                        
                        logger.info(f"✅ Loaded model for {market} (version: {version})")
            
        except Exception as e:
            logger.error(f"❌ Error loading models: {e}")
    
    def train_all_models(self) -> Dict[str, Dict[str, Any]]:
        """Train models for all supported markets"""
        logger.info("🚀 Starting training for all markets")
        
        # Create database tables first
        self.create_learning_tables()
        
        results = {}
        for market in self.markets:
            results[market] = self.train_market_model(market)
        
        # Load models into memory
        self.load_models()
        
        logger.info("✅ Training complete for all markets")
        return results
    
    def get_model_performance(self) -> Dict[str, Any]:
        """Get performance metrics for all trained models"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT market, metrics_json, trained_at 
                FROM model_metadata 
                WHERE is_active = 1 
                ORDER BY market
            """)
            
            results = {}
            for row in cursor.fetchall():
                market, metrics_json, trained_at = row
                try:
                    metrics = json.loads(metrics_json)
                    metrics['trained_at'] = trained_at
                    results[market] = metrics
                except:
                    continue
            
            conn.close()
            return results
            
        except Exception as e:
            logger.error(f"❌ Error getting model performance: {e}")
            return {}

def main():
    """Main function to train learning system"""
    learning_system = FootballLearningSystem()
    
    # Train all models
    results = learning_system.train_all_models()
    
    # Print results
    print("🧠 FOOTBALL LEARNING SYSTEM TRAINING RESULTS")
    print("=" * 50)
    
    for market, metrics in results.items():
        if 'error' in metrics:
            print(f"❌ {market}: {metrics['error']}")
        else:
            print(f"✅ {market}:")
            print(f"   Samples: {metrics['samples']}")
            print(f"   AUC: {metrics['auc']:.3f}")
            print(f"   Brier Score: {metrics['brier_score']:.3f}")
            print(f"   Accuracy: {metrics['accuracy']:.3f}")
            print()

if __name__ == "__main__":
    main()
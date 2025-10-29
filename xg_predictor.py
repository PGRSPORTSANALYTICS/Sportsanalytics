"""
XGBoost Expected Goals (xG) Predictor
Predicts lambda values for Poisson distribution
"""
import sqlite3
import json
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import joblib
import os
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class ExpectedGoalsPredictor:
    """
    Trains XGBoost to predict expected goals (λ) for Poisson distribution
    This is the professional approach used by top AI systems
    """
    
    def __init__(self):
        self.model_home = None
        self.model_away = None
        self.scaler = None
        self.feature_names = None
        self.league_avg_goals = {}
        
    def extract_training_data(self):
        """Extract settled matches with actual goals scored"""
        conn = sqlite3.connect('data/real_football.db')
        
        query = """
            SELECT 
                home_team, away_team, selection, odds, confidence, 
                league, outcome, analysis, match_date
            FROM football_opportunities 
            WHERE outcome IN ('won', 'lost')
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        logger.info(f"✅ Loaded {len(df)} settled matches for xG training")
        return df
    
    def engineer_xg_features(self, df):
        """Extract features that predict expected goals"""
        features = []
        
        for idx, row in df.iterrows():
            try:
                analysis = json.loads(row['analysis']) if row['analysis'] else {}
                xg_pred = analysis.get('xg_prediction', {})
                home_form = analysis.get('home_form', {})
                away_form = analysis.get('away_form', {})
                h2h = analysis.get('h2h', {})
                
                # Extract actual goals from result
                score = row['selection'].split(':')[-1].strip() if ':' in row['selection'] else row['selection']
                try:
                    actual_home, actual_away = map(int, score.split('-'))
                except:
                    continue  # Skip if can't parse score
                
                feat = {
                    # TARGET: Actual goals scored
                    'home_goals': actual_home,
                    'away_goals': actual_away,
                    
                    # xG features (our calculated xG)
                    'home_xg': xg_pred.get('home_xg', 1.5),
                    'away_xg': xg_pred.get('away_xg', 1.2),
                    'total_xg': xg_pred.get('total_xg', 2.7),
                    'xg_diff': xg_pred.get('home_xg', 1.5) - xg_pred.get('away_xg', 1.2),
                    
                    # Form features (goals per match)
                    'home_goals_scored_avg': home_form.get('goals_per_match', 1.5),
                    'home_goals_conceded_avg': home_form.get('goals_conceded_per_match', 1.2),
                    'away_goals_scored_avg': away_form.get('goals_per_match', 1.2),
                    'away_goals_conceded_avg': away_form.get('goals_conceded_per_match', 1.5),
                    
                    # Team strength
                    'home_win_rate': home_form.get('win_rate', 0.5),
                    'away_win_rate': away_form.get('win_rate', 0.4),
                    'home_ppg': home_form.get('points_per_game', 1.5),
                    'away_ppg': away_form.get('points_per_game', 1.2),
                    
                    # H2H patterns
                    'h2h_home_goals_avg': h2h.get('home_goals_avg', 1.5),
                    'h2h_away_goals_avg': h2h.get('away_goals_avg', 1.2),
                    'h2h_total_goals_avg': h2h.get('total_goals_avg', 2.7),
                    
                    # League context
                    'league': row['league'],
                }
                
                features.append(feat)
                
            except Exception as e:
                logger.warning(f"Error processing row {idx}: {e}")
                continue
        
        features_df = pd.DataFrame(features)
        
        # Calculate league averages
        for league in features_df['league'].unique():
            league_mask = features_df['league'] == league
            self.league_avg_goals[league] = {
                'home': features_df.loc[league_mask, 'home_goals'].mean(),
                'away': features_df.loc[league_mask, 'away_goals'].mean()
            }
        
        logger.info(f"✅ Engineered features from {len(features_df)} matches")
        logger.info(f"   Leagues: {list(self.league_avg_goals.keys())}")
        
        return features_df
    
    def train_xgboost_models(self, features_df):
        """Train separate XGBoost models for home and away goals"""
        
        # Prepare features (drop targets and league)
        X = features_df.drop(['home_goals', 'away_goals', 'league'], axis=1)
        y_home = features_df['home_goals']
        y_away = features_df['away_goals']
        
        # Split data chronologically
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_home_train, y_home_test = y_home.iloc[:split_idx], y_home.iloc[split_idx:]
        y_away_train, y_away_test = y_away.iloc[:split_idx], y_away.iloc[split_idx:]
        
        logger.info(f"📊 Training on {len(X_train)} matches, testing on {len(X_test)}")
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        self.feature_names = X.columns.tolist()
        
        # Train XGBoost for home goals
        logger.info("🤖 Training XGBoost for HOME goals...")
        self.model_home = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            objective='count:poisson'  # Poisson regression for count data!
        )
        self.model_home.fit(X_train_scaled, y_home_train)
        
        # Train XGBoost for away goals
        logger.info("🤖 Training XGBoost for AWAY goals...")
        self.model_away = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            objective='count:poisson'
        )
        self.model_away.fit(X_train_scaled, y_away_train)
        
        # Evaluate
        home_pred = self.model_home.predict(X_test_scaled)
        away_pred = self.model_away.predict(X_test_scaled)
        
        home_mae = np.mean(np.abs(home_pred - y_home_test))
        away_mae = np.mean(np.abs(away_pred - y_away_test))
        
        logger.info(f"✅ Home goals MAE: {home_mae:.3f}")
        logger.info(f"✅ Away goals MAE: {away_mae:.3f}")
        logger.info(f"   Actual avg: Home {y_home_test.mean():.2f}, Away {y_away_test.mean():.2f}")
        logger.info(f"   Predicted avg: Home {home_pred.mean():.2f}, Away {away_pred.mean():.2f}")
        
        return home_mae, away_mae
    
    def predict_expected_goals(self, match_features: Dict) -> Tuple[float, float]:
        """
        Predict expected goals (lambda) for a match
        
        Args:
            match_features: Dict with same features used in training
            
        Returns:
            (lambda_home, lambda_away) - Expected goals for Poisson
        """
        if self.model_home is None or self.model_away is None:
            raise ValueError("Models not trained yet! Call train() first")
        
        # Build feature vector
        X = pd.DataFrame([match_features])[self.feature_names]
        X_scaled = self.scaler.transform(X)
        
        # Predict
        lambda_home = float(self.model_home.predict(X_scaled)[0])
        lambda_away = float(self.model_away.predict(X_scaled)[0])
        
        # Ensure positive values
        lambda_home = max(0.3, lambda_home)  # Minimum 0.3 goals
        lambda_away = max(0.3, lambda_away)
        
        return lambda_home, lambda_away
    
    def save_models(self, path: str = 'data/models/xg_predictor.pkl'):
        """Save trained models"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        joblib.dump({
            'model_home': self.model_home,
            'model_away': self.model_away,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'league_avg_goals': self.league_avg_goals
        }, path)
        
        logger.info(f"✅ Models saved to {path}")
    
    def load_models(self, path: str = 'data/models/xg_predictor.pkl'):
        """Load trained models"""
        if os.path.exists(path):
            data = joblib.load(path)
            self.model_home = data['model_home']
            self.model_away = data['model_away']
            self.scaler = data['scaler']
            self.feature_names = data['feature_names']
            self.league_avg_goals = data['league_avg_goals']
            logger.info(f"✅ Models loaded from {path}")
            return True
        return False


if __name__ == '__main__':
    print("="*80)
    print("XGBOOST EXPECTED GOALS PREDICTOR - TRAINING")
    print("="*80)
    
    predictor = ExpectedGoalsPredictor()
    
    # Extract training data
    df = predictor.extract_training_data()
    
    # Engineer features
    features_df = predictor.engineer_xg_features(df)
    
    if len(features_df) > 20:  # Need at least 20 matches
        # Train models
        home_mae, away_mae = predictor.train_xgboost_models(features_df)
        
        # Save models
        predictor.save_models()
        
        print("\n" + "="*80)
        print("✅ XGBoost xG Predictor Ready")
        print("="*80)
        print(f"Home goals MAE: {home_mae:.3f}")
        print(f"Away goals MAE: {away_mae:.3f}")
        print(f"Models saved and ready for Poisson integration")
    else:
        print(f"\n❌ Need at least 20 matches, got {len(features_df)}")

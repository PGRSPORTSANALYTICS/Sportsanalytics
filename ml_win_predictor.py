"""
Machine Learning Win Predictor for Exact Scores
Trains on 153 real outcomes to predict which bets will win
"""
import sqlite3
import json
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, precision_recall_curve
import joblib
import os

def extract_features_from_db():
    """Extract all 153 bets with full features"""
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
    
    print(f"✅ Loaded {len(df)} settled bets")
    print(f"   Wins: {(df['outcome']=='won').sum()}")
    print(f"   Losses: {(df['outcome']=='lost').sum()}")
    
    return df

def engineer_features(df):
    """Extract numeric features from analysis JSON"""
    features = []
    
    for idx, row in df.iterrows():
        try:
            analysis = json.loads(row['analysis']) if row['analysis'] else {}
            xg_pred = analysis.get('xg_prediction', {})
            home_form = analysis.get('home_form', {})
            away_form = analysis.get('away_form', {})
            h2h = analysis.get('h2h', {})
            
            # Extract predicted score
            score = row['selection'].split(':')[-1].strip() if ':' in row['selection'] else row['selection']
            
            feat = {
                # Target
                'won': 1 if row['outcome'] == 'won' else 0,
                
                # Basic
                'odds': row['odds'],
                'confidence': row['confidence'],
                
                # xG features
                'home_xg': xg_pred.get('home_xg', 0),
                'away_xg': xg_pred.get('away_xg', 0),
                'total_xg': xg_pred.get('total_xg', 0),
                'xg_diff': xg_pred.get('home_xg', 0) - xg_pred.get('away_xg', 0),
                
                # Form features
                'home_win_rate': home_form.get('win_rate', 0),
                'away_win_rate': away_form.get('win_rate', 0),
                'home_ppg': home_form.get('points_per_game', 0),
                'away_ppg': away_form.get('points_per_game', 0),
                
                # H2H features  
                'h2h_over25': h2h.get('over_2_5_rate', 0),
                'h2h_btts': h2h.get('btts_rate', 0),
                
                # Score encoding
                'is_2_0': 1 if score == '2-0' else 0,
                'is_2_1': 1 if score == '2-1' else 0,
                'is_1_0': 1 if score == '1-0' else 0,
                'is_1_1': 1 if score == '1-1' else 0,
                'is_0_1': 1 if score == '0-1' else 0,
                
                # League encoding (top leagues)
                'is_ligue1': 1 if row['league'] == 'Ligue 1' else 0,
                'is_europa': 1 if row['league'] == 'Europa League' else 0,
                'is_belgian': 1 if row['league'] == 'Belgian First Division' else 0,
                'is_seria': 1 if row['league'] == 'Serie A' else 0,
                'is_epl': 1 if row['league'] == 'Premier League' else 0,
            }
            
            features.append(feat)
            
        except Exception as e:
            print(f"Error processing row {idx}: {e}")
            continue
    
    features_df = pd.DataFrame(features)
    print(f"\n✅ Engineered {len(features_df.columns)-1} features")
    print(f"   Features: {[c for c in features_df.columns if c != 'won']}")
    
    return features_df

def train_ml_model(features_df):
    """Train classifier to predict wins"""
    
    # Prepare data
    X = features_df.drop('won', axis=1)
    y = features_df['won']
    
    # Chronological split (last 20% for test)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"\n📊 Train: {len(X_train)} bets ({y_train.sum()} wins)")
    print(f"📊 Test: {len(X_test)} bets ({y_test.sum()} wins)")
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Train models with class balancing
    models = {
        'GradientBoosting': GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            random_state=42
        ),
        'LogisticRegression': LogisticRegression(
            class_weight='balanced',
            max_iter=1000,
            random_state=42
        )
    }
    
    best_model = None
    best_score = 0
    
    for name, model in models.items():
        print(f"\n🤖 Training {name}...")
        model.fit(X_train_scaled, y_train)
        
        # Get probabilities
        y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
        
        # Find optimal threshold for top 20%
        threshold = np.percentile(y_pred_proba, 80)  # Top 20%
        y_pred = (y_pred_proba >= threshold).astype(int)
        
        # Calculate precision at top 20%
        if y_pred.sum() > 0:
            precision = y_test[y_pred == 1].sum() / y_pred.sum()
            recall = y_test[y_pred == 1].sum() / y_test.sum() if y_test.sum() > 0 else 0
            
            print(f"   Top 20% threshold: {threshold:.3f}")
            print(f"   Precision: {precision:.1%} (hit rate)")
            print(f"   Recall: {recall:.1%} (% of wins caught)")
            print(f"   Would bet on: {y_pred.sum()} / {len(y_pred)} predictions")
            
            if precision > best_score:
                best_score = precision
                best_model = (name, model, scaler, threshold)
    
    if best_model:
        name, model, scaler, threshold = best_model
        print(f"\n🏆 Best model: {name}")
        print(f"   Expected hit rate: {best_score:.1%}")
        print(f"   Threshold: {threshold:.3f}")
        
        # Save model
        os.makedirs('data/models', exist_ok=True)
        joblib.dump({
            'model': model,
            'scaler': scaler,
            'threshold': threshold,
            'feature_names': X.columns.tolist()
        }, 'data/models/win_predictor.pkl')
        
        print(f"\n✅ Model saved to data/models/win_predictor.pkl")
        return model, scaler, threshold, X.columns.tolist()
    
    return None, None, None, None

if __name__ == '__main__':
    print("="*80)
    print("ML WIN PREDICTOR - Training on 153 Real Outcomes")
    print("="*80)
    
    # Extract data
    df = extract_features_from_db()
    
    # Engineer features
    features_df = engineer_features(df)
    
    # Train model
    model, scaler, threshold, feature_names = train_ml_model(features_df)
    
    if model:
        print("\n" + "="*80)
        print("✅ ML SYSTEM READY")
        print("="*80)
        print(f"Next: Integrate into real_football_champion.py")
        print(f"Only predictions with win_probability >= {threshold:.3f} will be saved")
    else:
        print("\n❌ Training failed")


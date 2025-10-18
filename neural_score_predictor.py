"""
🧠 NEURAL NETWORK EXACT SCORE PREDICTOR
Deep learning model for better exact score predictions
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import tensorflow/keras, fall back gracefully if not available
try:
    from tensorflow import keras
    from tensorflow.keras import layers, models, callbacks
    from tensorflow.keras.utils import to_categorical
    KERAS_AVAILABLE = True
except ImportError:
    KERAS_AVAILABLE = False
    logger.warning("⚠️ TensorFlow not available. Neural network predictions disabled.")


class NeuralScorePredictor:
    """
    Neural network model for exact score prediction
    Uses multi-output classification for home and away goals
    """
    
    def __init__(self, model_dir: str = 'data/models/neural'):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.max_goals = 6  # Predict scores 0-6 for each team
        self.feature_scaler = None
        
        if not KERAS_AVAILABLE:
            logger.warning("⚠️ Neural network disabled - TensorFlow not installed")
    
    def create_model(self, input_dim: int) -> models.Model:
        """
        Create neural network architecture for score prediction
        
        Architecture:
        - Shared dense layers for feature extraction
        - Separate outputs for home and away goals (0-6)
        - Total possible predictions: 7x7 = 49 exact scores
        """
        if not KERAS_AVAILABLE:
            return None
        
        # Input layer
        inputs = layers.Input(shape=(input_dim,))
        
        # Shared feature extraction
        x = layers.Dense(128, activation='relu')(inputs)
        x = layers.BatchNormalization()(x)
        x = layers.Dropout(0.3)(x)
        
        x = layers.Dense(64, activation='relu')(x)
        x = layers.BatchNormalization()(x)
        x = layers.Dropout(0.3)(x)
        
        x = layers.Dense(32, activation='relu')(x)
        x = layers.BatchNormalization()(x)
        x = layers.Dropout(0.2)(x)
        
        # Separate branches for home and away goals
        home_branch = layers.Dense(16, activation='relu')(x)
        home_goals = layers.Dense(self.max_goals + 1, activation='softmax', name='home_goals')(home_branch)
        
        away_branch = layers.Dense(16, activation='relu')(x)
        away_goals = layers.Dense(self.max_goals + 1, activation='softmax', name='away_goals')(away_branch)
        
        # Create model with two outputs
        model = models.Model(inputs=inputs, outputs=[home_goals, away_goals])
        
        # Compile with separate losses for each output
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss={
                'home_goals': 'categorical_crossentropy',
                'away_goals': 'categorical_crossentropy'
            },
            metrics=['accuracy']
        )
        
        logger.info("✅ Neural network model created")
        return model
    
    def prepare_data(self, X: np.ndarray, y_home: np.ndarray = None, 
                    y_away: np.ndarray = None) -> Tuple:
        """
        Prepare data for neural network training/prediction
        
        Args:
            X: Feature matrix
            y_home: Home goals (0-6+)
            y_away: Away goals (0-6+)
            
        Returns:
            Prepared data for model
        """
        # Scale features
        if self.feature_scaler is None:
            from sklearn.preprocessing import StandardScaler
            self.feature_scaler = StandardScaler()
            X_scaled = self.feature_scaler.fit_transform(X)
        else:
            X_scaled = self.feature_scaler.transform(X)
        
        if y_home is None or y_away is None:
            return X_scaled, None, None
        
        # Cap goals at max_goals (treat 6+ as 6)
        y_home_capped = np.clip(y_home, 0, self.max_goals)
        y_away_capped = np.clip(y_away, 0, self.max_goals)
        
        # Convert to categorical (one-hot encoding)
        y_home_cat = to_categorical(y_home_capped, num_classes=self.max_goals + 1)
        y_away_cat = to_categorical(y_away_capped, num_classes=self.max_goals + 1)
        
        return X_scaled, y_home_cat, y_away_cat
    
    def train(self, X_train: np.ndarray, y_home_train: np.ndarray, y_away_train: np.ndarray,
             X_val: np.ndarray = None, y_home_val: np.ndarray = None, y_away_val: np.ndarray = None,
             epochs: int = 50, batch_size: int = 32) -> Dict:
        """
        Train the neural network model
        
        Returns:
            Training history
        """
        if not KERAS_AVAILABLE:
            logger.error("❌ Cannot train - TensorFlow not available")
            return {}
        
        # Prepare data
        X_train_scaled, y_home_cat, y_away_cat = self.prepare_data(X_train, y_home_train, y_away_train)
        
        # Create model if not exists
        if self.model is None:
            self.model = self.create_model(X_train_scaled.shape[1])
        
        # Prepare validation data if provided
        validation_data = None
        if X_val is not None and y_home_val is not None and y_away_val is not None:
            X_val_scaled, y_home_val_cat, y_away_val_cat = self.prepare_data(X_val, y_home_val, y_away_val)
            validation_data = (
                X_val_scaled,
                {'home_goals': y_home_val_cat, 'away_goals': y_away_val_cat}
            )
        
        # Early stopping to prevent overfitting
        early_stop = callbacks.EarlyStopping(
            monitor='val_loss' if validation_data else 'loss',
            patience=10,
            restore_best_weights=True
        )
        
        # Train model
        logger.info(f"🧠 Training neural network for {epochs} epochs...")
        history = self.model.fit(
            X_train_scaled,
            {'home_goals': y_home_cat, 'away_goals': y_away_cat},
            validation_data=validation_data,
            epochs=epochs,
            batch_size=batch_size,
            callbacks=[early_stop],
            verbose=0
        )
        
        logger.info("✅ Neural network training complete")
        
        return history.history
    
    def predict_score_probabilities(self, X: np.ndarray) -> List[Dict[str, float]]:
        """
        Predict probability distribution for exact scores
        
        Returns:
            List of dicts with exact score probabilities
            e.g., {'2-1': 0.15, '1-1': 0.12, ...}
        """
        if not KERAS_AVAILABLE or self.model is None:
            return self._fallback_predictions(X.shape[0])
        
        # Prepare features
        X_scaled, _, _ = self.prepare_data(X)
        
        # Get predictions
        home_probs, away_probs = self.model.predict(X_scaled, verbose=0)
        
        # Combine into exact score probabilities
        predictions = []
        for i in range(len(X)):
            score_probs = {}
            
            # Calculate probability for each exact score
            for home_goals in range(self.max_goals + 1):
                for away_goals in range(self.max_goals + 1):
                    score = f"{home_goals}-{away_goals}"
                    # Joint probability = P(home) * P(away)
                    prob = home_probs[i][home_goals] * away_probs[i][away_goals]
                    score_probs[score] = float(prob)
            
            # Sort by probability
            score_probs = dict(sorted(score_probs.items(), key=lambda x: x[1], reverse=True))
            predictions.append(score_probs)
        
        return predictions
    
    def predict_top_scores(self, X: np.ndarray, top_n: int = 5) -> List[List[Tuple[str, float]]]:
        """
        Predict top N most likely exact scores
        
        Returns:
            List of [(score, probability), ...] for each match
        """
        all_probs = self.predict_score_probabilities(X)
        
        top_scores = []
        for probs in all_probs:
            top = list(probs.items())[:top_n]
            top_scores.append(top)
        
        return top_scores
    
    def save_model(self, model_name: str = 'exact_score_nn'):
        """Save trained model to disk"""
        if not KERAS_AVAILABLE or self.model is None:
            return
        
        model_path = self.model_dir / f"{model_name}.h5"
        self.model.save(model_path)
        
        # Save scaler
        if self.feature_scaler is not None:
            import joblib
            scaler_path = self.model_dir / f"{model_name}_scaler.pkl"
            joblib.dump(self.feature_scaler, scaler_path)
        
        logger.info(f"✅ Model saved to {model_path}")
    
    def load_model(self, model_name: str = 'exact_score_nn'):
        """Load trained model from disk"""
        if not KERAS_AVAILABLE:
            return False
        
        model_path = self.model_dir / f"{model_name}.h5"
        
        if not model_path.exists():
            logger.warning(f"⚠️ Model not found: {model_path}")
            return False
        
        try:
            self.model = models.load_model(model_path)
            
            # Load scaler
            import joblib
            scaler_path = self.model_dir / f"{model_name}_scaler.pkl"
            if scaler_path.exists():
                self.feature_scaler = joblib.load(scaler_path)
            
            logger.info(f"✅ Model loaded from {model_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Error loading model: {e}")
            return False
    
    def _fallback_predictions(self, n_samples: int) -> List[Dict[str, float]]:
        """
        Fallback predictions when neural network not available
        Uses Poisson-like distribution based on typical football scores
        """
        common_scores = {
            '1-0': 0.12, '0-1': 0.12,
            '2-0': 0.10, '0-2': 0.10,
            '1-1': 0.09,
            '2-1': 0.08, '1-2': 0.08,
            '0-0': 0.06,
            '3-0': 0.05, '0-3': 0.05,
            '2-2': 0.04,
            '3-1': 0.03, '1-3': 0.03,
            '3-2': 0.02, '2-3': 0.02
        }
        
        return [common_scores] * n_samples


def ensemble_exact_score_prediction(xg_home: float, xg_away: float, 
                                    neural_probs: Dict[str, float] = None,
                                    historical_h2h: Dict[str, float] = None) -> Dict[str, float]:
    """
    🎯 ENSEMBLE EXACT SCORE PREDICTION
    Combines multiple methods for better accuracy:
    1. Poisson distribution based on xG
    2. Neural network probabilities
    3. Historical H2H scores
    
    Returns:
        Dict of {score: probability} with ensemble predictions
    """
    from scipy.stats import poisson
    import numpy as np
    
    # Method 1: Poisson distribution from xG
    poisson_probs = {}
    for home_goals in range(7):
        for away_goals in range(7):
            score = f"{home_goals}-{away_goals}"
            prob_home = poisson.pmf(home_goals, xg_home)
            prob_away = poisson.pmf(away_goals, xg_away)
            poisson_probs[score] = prob_home * prob_away
    
    # Normalize
    total = sum(poisson_probs.values())
    poisson_probs = {k: v/total for k, v in poisson_probs.items()}
    
    # Method 2: Neural network (if available)
    if neural_probs:
        weight_poisson = 0.4
        weight_neural = 0.6
        
        ensemble = {}
        for score in poisson_probs:
            ensemble[score] = (
                weight_poisson * poisson_probs.get(score, 0) +
                weight_neural * neural_probs.get(score, 0)
            )
    else:
        ensemble = poisson_probs
    
    # Method 3: Adjust with H2H if available
    if historical_h2h:
        weight_ensemble = 0.8
        weight_h2h = 0.2
        
        final = {}
        for score in ensemble:
            final[score] = (
                weight_ensemble * ensemble.get(score, 0) +
                weight_h2h * historical_h2h.get(score, 0)
            )
        ensemble = final
    
    # Sort by probability
    ensemble = dict(sorted(ensemble.items(), key=lambda x: x[1], reverse=True))
    
    return ensemble

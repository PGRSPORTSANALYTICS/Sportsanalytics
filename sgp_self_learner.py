#!/usr/bin/env python3
"""
SGP Self-Learning System
Learns from actual SGP results to improve predictions over time

Features:
1. Probability Calibration - Adjusts model probabilities based on actual win rates
2. Correlation Learning - Learns real correlations between bet legs
3. Dynamic Kelly Sizing - Adjusts stakes based on calibration quality
"""

import sqlite3
import time
import math
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, List
from collections import defaultdict

logger = logging.getLogger(__name__)

DB_PATH = Path("data/real_football.db")

class SGPCalibrator:
    """
    Online calibration for SGP probability estimates
    
    Learns if the model is over/under-confident by tracking:
    - Predicted probability vs actual win rate
    - Adjusts future predictions based on historical accuracy
    
    Uses logistic calibration: p_adjusted = sigmoid(a * logit(p_model) + b)
    """
    
    def __init__(self, db_path: Path = DB_PATH, learning_rate: float = 0.01):
        self.db_path = db_path
        self.lr = learning_rate
        self._init_db()
        self._load_params()
    
    def _init_db(self):
        """Initialize calibration database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sgp_calibration (
                param_name TEXT PRIMARY KEY,
                param_value REAL,
                updated_timestamp INTEGER
            )
        ''')
        
        # Track calibration history for analysis
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sgp_calibration_history (
                timestamp INTEGER,
                predicted_prob REAL,
                actual_outcome INTEGER,
                a_param REAL,
                b_param REAL,
                brier_score REAL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _load_params(self):
        """Load calibration parameters from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Default: identity mapping (no adjustment)
        self.a = 1.0
        self.b = 0.0
        self.brier_ewm = 0.25  # Exponentially weighted Brier score
        
        params = cursor.execute(
            'SELECT param_name, param_value FROM sgp_calibration'
        ).fetchall()
        
        for name, value in params:
            if name == 'a':
                self.a = float(value)
            elif name == 'b':
                self.b = float(value)
            elif name == 'brier_ewm':
                self.brier_ewm = float(value)
        
        conn.close()
        logger.info(f"📊 Loaded calibration params: a={self.a:.3f}, b={self.b:.3f}, brier={self.brier_ewm:.3f}")
    
    def _save_params(self):
        """Save calibration parameters to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = int(time.time())
        for name, value in [('a', self.a), ('b', self.b), ('brier_ewm', self.brier_ewm)]:
            cursor.execute(
                'INSERT OR REPLACE INTO sgp_calibration VALUES (?, ?, ?)',
                (name, float(value), timestamp)
            )
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def logit(p: float) -> float:
        """Convert probability to logit (log-odds)"""
        p = max(0.001, min(0.999, p))  # Clamp to avoid infinity
        return math.log(p / (1.0 - p))
    
    @staticmethod
    def sigmoid(z: float) -> float:
        """Convert logit back to probability"""
        z = max(-20, min(20, z))  # Prevent overflow
        return 1.0 / (1.0 + math.exp(-z))
    
    def adjust(self, p_model: float) -> float:
        """
        Apply calibration to model probability
        
        If model is over-confident (predicts 40% but wins 30%), this adjusts down
        If model is under-confident (predicts 20% but wins 30%), this adjusts up
        """
        if not 0.001 <= p_model <= 0.999:
            return max(0.001, min(0.999, p_model))
        
        z = self.logit(p_model)
        z_cal = self.a * z + self.b
        return self.sigmoid(z_cal)
    
    def update(self, p_model: float, won: bool):
        """
        Update calibration parameters based on bet outcome
        
        Uses stochastic gradient descent on log-loss:
        - If bet won but p_model was low → increase future predictions
        - If bet lost but p_model was high → decrease future predictions
        """
        p_adj = self.adjust(p_model)
        y = 1.0 if won else 0.0
        
        # Brier score: (predicted - actual)^2
        brier = (p_adj - y) ** 2
        alpha_brier = 0.1
        self.brier_ewm = alpha_brier * brier + (1 - alpha_brier) * self.brier_ewm
        
        # Gradient descent on log-loss
        z = self.logit(p_model)
        z_cal = self.a * z + self.b
        p_cal = self.sigmoid(z_cal)
        
        # Gradients
        grad = p_cal - y
        da = grad * z * p_cal * (1 - p_cal)
        db = grad * p_cal * (1 - p_cal)
        
        # Update parameters
        self.a -= self.lr * da
        self.b -= self.lr * db
        
        # Constrain a to reasonable range (prevent inversion)
        self.a = max(0.5, min(2.0, self.a))
        
        # Save to database
        self._save_params()
        
        # Log to history
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sgp_calibration_history 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (int(time.time()), p_model, int(won), self.a, self.b, brier))
        conn.commit()
        conn.close()
        
        logger.info(f"📊 Calibration updated: p_model={p_model:.3f} → p_adj={p_adj:.3f}, outcome={won}, brier={self.brier_ewm:.3f}")


class CorrelationLearner:
    """
    Learns actual correlations between SGP bet legs from historical data
    
    Instead of hardcoded correlations (0.35 for Over+BTTS), this learns:
    - How often Over 2.5 and BTTS both win together
    - How often they both lose together
    - Derives the actual correlation from data
    """
    
    def __init__(self, db_path: Path = DB_PATH, min_samples: int = 20):
        self.db_path = db_path
        self.min_samples = min_samples
        self._init_db()
    
    def _init_db(self):
        """Initialize correlation tracking database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sgp_leg_correlations (
                leg_pair TEXT PRIMARY KEY,
                both_win INTEGER DEFAULT 0,
                both_lose INTEGER DEFAULT 0,
                leg1_win_leg2_lose INTEGER DEFAULT 0,
                leg1_lose_leg2_win INTEGER DEFAULT 0,
                learned_correlation REAL,
                sample_count INTEGER,
                updated_timestamp INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _make_leg_key(self, leg1_type: str, leg2_type: str) -> str:
        """Create consistent key for leg pair (alphabetical order)"""
        legs = sorted([leg1_type, leg2_type])
        return f"{legs[0]}||{legs[1]}"
    
    def update_from_parlay(self, legs_outcomes: List[Tuple[str, bool]]):
        """
        Update correlation statistics from a settled parlay
        
        Args:
            legs_outcomes: List of (leg_type, won) tuples
                e.g., [("OVER_2.5", True), ("BTTS", True), ("HOME_WIN", False)]
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update all pairwise correlations
        n = len(legs_outcomes)
        for i in range(n):
            for j in range(i + 1, n):
                leg1_type, leg1_won = legs_outcomes[i]
                leg2_type, leg2_won = legs_outcomes[j]
                
                key = self._make_leg_key(leg1_type, leg2_type)
                
                # Get current stats
                row = cursor.execute(
                    'SELECT both_win, both_lose, leg1_win_leg2_lose, leg1_lose_leg2_win, sample_count FROM sgp_leg_correlations WHERE leg_pair = ?',
                    (key,)
                ).fetchone()
                
                if row:
                    both_win, both_lose, l1_win_l2_lose, l1_lose_l2_win, count = row
                else:
                    both_win = both_lose = l1_win_l2_lose = l1_lose_l2_win = count = 0
                
                # Update counts
                if leg1_won and leg2_won:
                    both_win += 1
                elif not leg1_won and not leg2_won:
                    both_lose += 1
                elif leg1_won and not leg2_won:
                    l1_win_l2_lose += 1
                else:  # leg2_won and not leg1_won
                    l1_lose_l2_win += 1
                
                count += 1
                
                # Calculate correlation (Pearson correlation coefficient for binary data)
                total = both_win + both_lose + l1_win_l2_lose + l1_lose_l2_win
                if total > 0:
                    p11 = both_win / total  # P(both win)
                    p10 = l1_win_l2_lose / total
                    p01 = l1_lose_l2_win / total
                    p00 = both_lose / total
                    
                    # Marginal probabilities
                    p1 = p11 + p10  # P(leg1 wins)
                    p2 = p11 + p01  # P(leg2 wins)
                    
                    # Correlation = (E[XY] - E[X]E[Y]) / sqrt(Var[X]Var[Y])
                    # For binary: correlation = (p11 - p1*p2) / sqrt(p1*(1-p1)*p2*(1-p2))
                    numerator = p11 - p1 * p2
                    denominator = math.sqrt(p1 * (1 - p1) * p2 * (1 - p2)) if p1 * (1 - p1) * p2 * (1 - p2) > 0 else 1e-6
                    correlation = numerator / denominator
                    
                    # Clamp to [-1, 1]
                    correlation = max(-1.0, min(1.0, correlation))
                else:
                    correlation = 0.0
                
                # Save to database
                cursor.execute('''
                    INSERT OR REPLACE INTO sgp_leg_correlations 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (key, both_win, both_lose, l1_win_l2_lose, l1_lose_l2_win, 
                      correlation, count, int(time.time())))
        
        conn.commit()
        conn.close()
    
    def get_correlation(self, leg1_type: str, leg2_type: str, default: float = 0.3) -> float:
        """
        Get learned correlation between two leg types
        
        Returns learned value if enough samples, otherwise default
        """
        key = self._make_leg_key(leg1_type, leg2_type)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        row = cursor.execute(
            'SELECT learned_correlation, sample_count FROM sgp_leg_correlations WHERE leg_pair = ?',
            (key,)
        ).fetchone()
        
        conn.close()
        
        if row and row[1] >= self.min_samples:
            return float(row[0])
        else:
            return default


class SGPSelfLearner:
    """
    Main integration class for SGP self-learning
    
    Combines calibration and correlation learning to improve SGP predictions
    """
    
    def __init__(self, safe_kelly_base: float = 0.25):
        self.calibrator = SGPCalibrator(DB_PATH)
        self.correlation_learner = CorrelationLearner(DB_PATH)
        self.safe_kelly_base = safe_kelly_base
        logger.info("✅ SGP Self-Learner initialized")
    
    def get_dynamic_kelly(self) -> float:
        """
        Adaptive Kelly sizing based on calibration quality
        
        - Poor calibration (Brier > 0.24) → reduce stake to 60% of base
        - Good calibration (Brier < 0.18) → increase stake to 125% of base
        - Medium calibration → use base Kelly
        """
        brier = self.calibrator.brier_ewm
        
        if brier > 0.24:  # Poor calibration
            multiplier = self.safe_kelly_base * 0.6
            status = "⚠️ CONSERVATIVE"
        elif brier < 0.18:  # Good calibration
            multiplier = self.safe_kelly_base * 1.25
            status = "✅ AGGRESSIVE"
        else:
            multiplier = self.safe_kelly_base
            status = "📊 NORMAL"
        
        kelly = min(0.5, max(0.1, multiplier))
        logger.info(f"🎯 Kelly sizing: {kelly:.3f} ({status}, Brier={brier:.3f})")
        return kelly
    
    def adjust_probability(self, p_model: float) -> float:
        """Apply calibration to model probability"""
        return self.calibrator.adjust(p_model)
    
    def get_leg_correlation(self, leg1_type: str, leg2_type: str, default: float = 0.3) -> float:
        """Get learned correlation between bet legs"""
        return self.correlation_learner.get_correlation(leg1_type, leg2_type, default)
    
    def update_from_settlement(self, parlay_probability: float, legs_outcomes: List[Tuple[str, bool]], parlay_won: bool):
        """
        Update all learning components when a parlay settles
        
        Args:
            parlay_probability: Model's predicted probability
            legs_outcomes: List of (leg_type, won) tuples for each leg
            parlay_won: Whether the entire parlay won
        """
        # Update calibration
        self.calibrator.update(parlay_probability, parlay_won)
        
        # Update correlations
        self.correlation_learner.update_from_parlay(legs_outcomes)
        
        logger.info(f"🔄 Self-learning updated: p={parlay_probability:.3f}, won={parlay_won}")
    
    def get_calibration_stats(self) -> Dict:
        """Get current calibration statistics"""
        return {
            'a_param': self.calibrator.a,
            'b_param': self.calibrator.b,
            'brier_score': self.calibrator.brier_ewm,
            'kelly_multiplier': self.get_dynamic_kelly()
        }


if __name__ == "__main__":
    # Test self-learning system
    logging.basicConfig(level=logging.INFO)
    
    learner = SGPSelfLearner()
    
    # Simulate some bet outcomes
    print("\n📊 Testing calibration...")
    for i in range(10):
        p_model = 0.35  # Model predicts 35%
        won = i < 3  # Actual: 30% win rate (over-confident)
        learner.update_from_settlement(p_model, [("OVER_2.5", won), ("BTTS", won)], won)
    
    # Check adjustment
    adjusted = learner.adjust_probability(0.35)
    print(f"\n✅ Model says 35%, calibrated to: {adjusted:.1%}")
    print(f"📊 Calibration stats: {learner.get_calibration_stats()}")

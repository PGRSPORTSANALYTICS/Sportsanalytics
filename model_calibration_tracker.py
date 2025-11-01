#!/usr/bin/env python3
"""
Model Calibration Tracker
Checks if model probabilities match actual win rates
"""
import sqlite3
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

class ModelCalibrationTracker:
    """
    Track prediction probabilities vs actual results to check model calibration
    
    Example:
    - Model predicted 20% probability → Did 20% of those actually win?
    - If yes = well calibrated
    - If actual is 10% = model overconfident
    - If actual is 30% = model underconfident
    """
    
    def __init__(self, db_path: str = 'data/real_football.db'):
        self.db_path = db_path
        self._init_tracking_table()
    
    def _init_tracking_table(self):
        """Create calibration tracking table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_calibration (
                suggestion_id TEXT PRIMARY KEY,
                prediction_date TEXT,
                match_info TEXT,
                predicted_score TEXT,
                actual_score TEXT,
                
                -- Model probabilities
                ensemble_probability REAL,
                poisson_probability REAL,
                neural_probability REAL,
                similar_matches_probability REAL,
                
                -- Expected Value data
                odds REAL,
                expected_value REAL,
                ev_percentage REAL,
                
                -- Model agreement
                model_agreement INTEGER,
                models_used INTEGER,
                
                -- Result
                is_settled INTEGER DEFAULT 0,
                is_win INTEGER DEFAULT 0,
                
                -- Bookmaker comparison
                bookmaker_implied_prob REAL,
                probability_difference REAL,
                
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ Model calibration tracker initialized")
    
    def track_prediction(
        self,
        suggestion_id: str,
        match_info: str,
        predicted_score: str,
        ensemble_prob: float,
        individual_probs: Dict[str, float],
        odds: float,
        ev_data: Dict
    ):
        """Track a prediction with its probability estimates"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO model_calibration
            (suggestion_id, prediction_date, match_info, predicted_score,
             ensemble_probability, poisson_probability, neural_probability,
             similar_matches_probability, odds, expected_value, ev_percentage,
             model_agreement, models_used, bookmaker_implied_prob, probability_difference)
            VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            suggestion_id,
            match_info,
            predicted_score,
            ensemble_prob,
            individual_probs.get('poisson', 0.0),
            individual_probs.get('neural', 0.0),
            individual_probs.get('similar_matches', 0.0),
            odds,
            ev_data.get('expected_value', 0.0),
            ev_data.get('ev_percentage', 0.0),
            1 if ev_data.get('model_agreement', False) else 0,
            ev_data.get('models_used', 1),
            ev_data.get('bookmaker_implied_prob', 0.0),
            ev_data.get('probability_difference', 0.0)
        ))
        
        conn.commit()
        conn.close()
    
    def update_result(self, suggestion_id: str, actual_score: str, is_win: bool):
        """Update with actual result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE model_calibration
            SET actual_score = ?, is_settled = 1, is_win = ?
            WHERE suggestion_id = ?
        """, (actual_score, 1 if is_win else 0, suggestion_id))
        
        conn.commit()
        conn.close()
    
    def get_calibration_report(self, min_predictions: int = 30) -> Dict:
        """
        Generate calibration report
        
        Buckets predictions by probability range and checks actual win rate
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all settled predictions
        cursor.execute("""
            SELECT ensemble_probability, is_win
            FROM model_calibration
            WHERE is_settled = 1
        """)
        
        rows = cursor.fetchall()
        
        if len(rows) < min_predictions:
            conn.close()
            return {
                'status': 'insufficient_data',
                'settled': len(rows),
                'needed': min_predictions
            }
        
        # Group into probability buckets
        buckets = {
            '5-10%': [],
            '10-15%': [],
            '15-20%': [],
            '20-25%': [],
            '25-30%': [],
            '30%+': []
        }
        
        for prob, is_win in rows:
            prob_pct = prob * 100
            
            if prob_pct < 10:
                buckets['5-10%'].append(is_win)
            elif prob_pct < 15:
                buckets['10-15%'].append(is_win)
            elif prob_pct < 20:
                buckets['15-20%'].append(is_win)
            elif prob_pct < 25:
                buckets['20-25%'].append(is_win)
            elif prob_pct < 30:
                buckets['25-30%'].append(is_win)
            else:
                buckets['30%+'].append(is_win)
        
        # Calculate actual win rates per bucket
        calibration_data = {}
        total_calibration_error = 0
        bucket_count = 0
        
        for bucket_name, wins in buckets.items():
            if len(wins) == 0:
                continue
            
            # Expected probability (midpoint of range)
            if bucket_name == '5-10%':
                expected = 7.5
            elif bucket_name == '10-15%':
                expected = 12.5
            elif bucket_name == '15-20%':
                expected = 17.5
            elif bucket_name == '20-25%':
                expected = 22.5
            elif bucket_name == '25-30%':
                expected = 27.5
            else:
                expected = 32.5
            
            actual = (sum(wins) / len(wins)) * 100
            error = abs(expected - actual)
            
            calibration_data[bucket_name] = {
                'expected': expected,
                'actual': round(actual, 1),
                'count': len(wins),
                'wins': sum(wins),
                'error': round(error, 1)
            }
            
            total_calibration_error += error
            bucket_count += 1
        
        avg_error = total_calibration_error / bucket_count if bucket_count > 0 else 0
        
        # Get EV analysis
        cursor.execute("""
            SELECT 
                AVG(expected_value) as avg_ev,
                AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE -1.0 END) as avg_roi,
                COUNT(CASE WHEN expected_value > 0.15 THEN 1 END) as high_ev_bets,
                COUNT(CASE WHEN expected_value > 0.15 AND is_win = 1 THEN 1 END) as high_ev_wins
            FROM model_calibration
            WHERE is_settled = 1
        """)
        
        ev_row = cursor.fetchone()
        
        conn.close()
        
        return {
            'status': 'ready',
            'total_settled': len(rows),
            'calibration_by_bucket': calibration_data,
            'average_calibration_error': round(avg_error, 1),
            'is_well_calibrated': avg_error < 5.0,  # Within 5% is good
            'ev_analysis': {
                'average_ev': round(ev_row[0] * 100, 1) if ev_row[0] else 0,
                'average_roi': round(ev_row[1] * 100, 1) if ev_row[1] else 0,
                'high_ev_bets': ev_row[2] or 0,
                'high_ev_wins': ev_row[3] or 0,
                'high_ev_hit_rate': round((ev_row[3] / ev_row[2] * 100), 1) if ev_row[2] and ev_row[2] > 0 else 0
            }
        }
    
    def print_calibration_report(self, min_predictions: int = 30):
        """Print formatted calibration report"""
        report = self.get_calibration_report(min_predictions)
        
        if report['status'] == 'insufficient_data':
            print(f"\n⏳ Need {report['needed']} settled predictions")
            print(f"📊 Currently have: {report['settled']}\n")
            return
        
        print("\n" + "="*60)
        print("📊 MODEL CALIBRATION REPORT")
        print("="*60)
        
        print(f"\n📈 Total Predictions Analyzed: {report['total_settled']}")
        
        print("\n🎯 PROBABILITY CALIBRATION:")
        print("-" * 60)
        print(f"{'Probability Range':<20} {'Expected':<12} {'Actual':<12} {'Count':<10} {'Error'}")
        print("-" * 60)
        
        for bucket, data in report['calibration_by_bucket'].items():
            print(f"{bucket:<20} {data['expected']:>6.1f}%    "
                  f"{data['actual']:>6.1f}%    "
                  f"{data['count']:>4}      "
                  f"{data['error']:>5.1f}%")
        
        print("-" * 60)
        print(f"Average Calibration Error: {report['average_calibration_error']}%")
        
        if report['is_well_calibrated']:
            print("✅ Models are WELL CALIBRATED (error < 5%)")
        else:
            print("⚠️  Models need calibration adjustment")
        
        print("\n💰 EXPECTED VALUE ANALYSIS:")
        ev = report['ev_analysis']
        print(f"   Average EV: {ev['average_ev']:+.1f}%")
        print(f"   Average ROI: {ev['average_roi']:+.1f}%")
        print(f"   High EV Bets (>15%): {ev['high_ev_bets']}")
        print(f"   High EV Wins: {ev['high_ev_wins']}")
        print(f"   High EV Hit Rate: {ev['high_ev_hit_rate']}%")
        
        print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    tracker = ModelCalibrationTracker()
    tracker.print_calibration_report(min_predictions=30)

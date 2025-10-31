#!/usr/bin/env python3
"""
Similar Matches Impact Tracker
Measures if Similar Matches technology is actually improving hit rate
"""
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class SimilarMatchesTracker:
    """
    Track the impact of Similar Matches on prediction performance
    Compare: WITH vs WITHOUT Similar Matches adjustments
    """
    
    def __init__(self, db_path: str = 'data/real_football.db'):
        self.db_path = db_path
        self._init_tracking_table()
    
    def _init_tracking_table(self):
        """Create tracking table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS similar_matches_impact (
                suggestion_id TEXT PRIMARY KEY,
                prediction_date TEXT,
                match_info TEXT,
                predicted_score TEXT,
                actual_score TEXT,
                
                -- Confidence scores
                base_confidence INTEGER,
                similar_matches_adjustment INTEGER,
                final_confidence INTEGER,
                
                -- Similar Matches data
                similar_matches_found INTEGER,
                pattern_strength INTEGER,
                predicted_score_frequency REAL,
                
                -- Would this prediction pass filters?
                would_pass_without_sm INTEGER,
                did_pass_with_sm INTEGER,
                
                -- Result
                is_settled INTEGER DEFAULT 0,
                is_win INTEGER DEFAULT 0,
                
                -- Tracking
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def track_prediction(
        self,
        suggestion_id: str,
        match_info: str,
        predicted_score: str,
        base_confidence: int,
        sm_adjustment: int,
        final_confidence: int,
        sm_data: Dict
    ):
        """
        Track a prediction with Similar Matches impact data
        
        Args:
            suggestion_id: Unique prediction ID
            match_info: "Team A vs Team B"
            predicted_score: "1-0", "1-1", etc
            base_confidence: Score before SM adjustment
            sm_adjustment: Points added/removed by SM
            final_confidence: Score after SM adjustment
            sm_data: Dict from SimilarMatchesFinder containing:
                - similar_matches_found
                - pattern_strength
                - predicted_score_frequency
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Would prediction pass 85+ threshold without SM?
        would_pass_without = 1 if base_confidence >= 85 else 0
        did_pass_with = 1 if final_confidence >= 85 else 0
        
        cursor.execute("""
            INSERT OR REPLACE INTO similar_matches_impact 
            (suggestion_id, prediction_date, match_info, predicted_score,
             base_confidence, similar_matches_adjustment, final_confidence,
             similar_matches_found, pattern_strength, predicted_score_frequency,
             would_pass_without_sm, did_pass_with_sm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            suggestion_id,
            datetime.now().isoformat(),
            match_info,
            predicted_score,
            base_confidence,
            sm_adjustment,
            final_confidence,
            sm_data.get('matches_found', 0),
            sm_data.get('pattern_strength', 0),
            sm_data.get('predicted_score_frequency', 0.0),
            would_pass_without,
            did_pass_with
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📊 Tracked SM impact: {match_info} | Base: {base_confidence} → Final: {final_confidence} ({sm_adjustment:+d})")
    
    def update_result(self, suggestion_id: str, actual_score: str, is_win: bool):
        """Update prediction with actual result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE similar_matches_impact 
            SET actual_score = ?, is_settled = 1, is_win = ?
            WHERE suggestion_id = ?
        """, (actual_score, 1 if is_win else 0, suggestion_id))
        
        conn.commit()
        conn.close()
    
    def get_impact_report(self, min_predictions: int = 20) -> Dict:
        """
        Generate report comparing WITH vs WITHOUT Similar Matches
        
        Returns:
            Dict with hit rates, ROI, and impact metrics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all settled predictions
        cursor.execute("""
            SELECT 
                COUNT(*) as total_settled,
                SUM(is_win) as total_wins,
                
                -- Predictions that WOULD pass without SM
                SUM(CASE WHEN would_pass_without_sm = 1 THEN 1 ELSE 0 END) as would_pass_count,
                SUM(CASE WHEN would_pass_without_sm = 1 AND is_win = 1 THEN 1 ELSE 0 END) as would_pass_wins,
                
                -- Predictions that DID pass with SM
                SUM(CASE WHEN did_pass_with_sm = 1 THEN 1 ELSE 0 END) as did_pass_count,
                SUM(CASE WHEN did_pass_with_sm = 1 AND is_win = 1 THEN 1 ELSE 0 END) as did_pass_wins,
                
                -- SM saved these predictions (boosted from <85 to 85+)
                SUM(CASE WHEN would_pass_without_sm = 0 AND did_pass_with_sm = 1 THEN 1 ELSE 0 END) as sm_saved,
                SUM(CASE WHEN would_pass_without_sm = 0 AND did_pass_with_sm = 1 AND is_win = 1 THEN 1 ELSE 0 END) as sm_saved_wins,
                
                -- SM blocked these predictions (dropped from 85+ to <85)
                SUM(CASE WHEN would_pass_without_sm = 1 AND did_pass_with_sm = 0 THEN 1 ELSE 0 END) as sm_blocked,
                SUM(CASE WHEN would_pass_without_sm = 1 AND did_pass_with_sm = 0 AND is_win = 0 THEN 1 ELSE 0 END) as sm_blocked_losses
                
            FROM similar_matches_impact
            WHERE is_settled = 1
        """)
        
        row = cursor.fetchone()
        
        if not row or row[0] < min_predictions:
            conn.close()
            return {
                'status': 'insufficient_data',
                'settled': row[0] if row else 0,
                'needed': min_predictions
            }
        
        (total, wins, 
         would_pass, would_pass_wins,
         did_pass, did_pass_wins,
         sm_saved, sm_saved_wins,
         sm_blocked, sm_blocked_losses) = row
        
        # Calculate hit rates
        without_sm_rate = (would_pass_wins / would_pass * 100) if would_pass > 0 else 0
        with_sm_rate = (did_pass_wins / did_pass * 100) if did_pass > 0 else 0
        
        # Calculate impact
        sm_saved_rate = (sm_saved_wins / sm_saved * 100) if sm_saved > 0 else 0
        sm_blocked_accuracy = (sm_blocked_losses / sm_blocked * 100) if sm_blocked > 0 else 0
        
        conn.close()
        
        return {
            'status': 'ready',
            'total_settled': total,
            'total_wins': wins,
            
            'without_sm': {
                'predictions': would_pass,
                'wins': would_pass_wins,
                'hit_rate': round(without_sm_rate, 1)
            },
            
            'with_sm': {
                'predictions': did_pass,
                'wins': did_pass_wins,
                'hit_rate': round(with_sm_rate, 1)
            },
            
            'sm_impact': {
                'saved_predictions': sm_saved,
                'saved_wins': sm_saved_wins,
                'saved_hit_rate': round(sm_saved_rate, 1),
                
                'blocked_predictions': sm_blocked,
                'blocked_correctly': sm_blocked_losses,
                'block_accuracy': round(sm_blocked_accuracy, 1)
            },
            
            'verdict': self._get_verdict(with_sm_rate, without_sm_rate, sm_saved, sm_blocked)
        }
    
    def _get_verdict(self, with_sm: float, without_sm: float, saved: int, blocked: int) -> Dict:
        """Determine if Similar Matches is helping or hurting"""
        
        improvement = with_sm - without_sm
        
        if improvement > 2:
            return {
                'status': 'working',
                'message': f'SM is IMPROVING hit rate by {improvement:+.1f}%',
                'action': 'Keep it enabled'
            }
        elif improvement > 0:
            return {
                'status': 'slight_help',
                'message': f'SM is slightly helping (+{improvement:.1f}%)',
                'action': 'Keep monitoring'
            }
        elif improvement > -2:
            return {
                'status': 'neutral',
                'message': f'SM has minimal impact ({improvement:+.1f}%)',
                'action': 'Need more data'
            }
        else:
            return {
                'status': 'harmful',
                'message': f'SM is HURTING hit rate by {improvement:.1f}%',
                'action': 'Consider disabling'
            }
    
    def print_report(self, min_predictions: int = 20):
        """Print a formatted impact report"""
        report = self.get_impact_report(min_predictions)
        
        if report['status'] == 'insufficient_data':
            print(f"\n⏳ Need {report['needed']} settled predictions")
            print(f"📊 Currently have: {report['settled']}")
            print(f"🎯 Track {report['needed'] - report['settled']} more predictions\n")
            return
        
        print("\n" + "="*60)
        print("📊 SIMILAR MATCHES IMPACT REPORT")
        print("="*60)
        
        print(f"\n📈 TOTAL SETTLED: {report['total_settled']} predictions")
        
        print(f"\n🔴 WITHOUT Similar Matches:")
        print(f"   Predictions: {report['without_sm']['predictions']}")
        print(f"   Wins: {report['without_sm']['wins']}")
        print(f"   Hit Rate: {report['without_sm']['hit_rate']}%")
        
        print(f"\n🟢 WITH Similar Matches:")
        print(f"   Predictions: {report['with_sm']['predictions']}")
        print(f"   Wins: {report['with_sm']['wins']}")
        print(f"   Hit Rate: {report['with_sm']['hit_rate']}%")
        
        diff = report['with_sm']['hit_rate'] - report['without_sm']['hit_rate']
        print(f"\n📊 DIFFERENCE: {diff:+.1f}%")
        
        print(f"\n💡 Similar Matches Impact:")
        impact = report['sm_impact']
        print(f"   Saved {impact['saved_predictions']} predictions (boosted to 85+)")
        print(f"   → {impact['saved_wins']} wins ({impact['saved_hit_rate']}% hit rate)")
        print(f"   Blocked {impact['blocked_predictions']} predictions (dropped below 85)")
        print(f"   → {impact['blocked_correctly']} were losses ({impact['block_accuracy']}% accuracy)")
        
        verdict = report['verdict']
        print(f"\n{'✅' if verdict['status'] == 'working' else '⚠️'} VERDICT: {verdict['message']}")
        print(f"   Action: {verdict['action']}")
        
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    tracker = SimilarMatchesTracker()
    tracker.print_report(min_predictions=20)

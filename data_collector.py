"""
Data Collector - Captures ALL match analysis for AI training
Stores comprehensive data even when bets aren't placed
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
import os

# Database imports
try:
    import psycopg2
    from psycopg2.extras import Json
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

logger = logging.getLogger(__name__)

class DataCollector:
    """
    Collects and stores all match analysis data for AI training.
    This runs independently of betting decisions - capturing data
    on ALL matches analyzed, not just those that qualify for bets.
    """
    
    def __init__(self):
        self.db_url = os.environ.get('DATABASE_URL')
        self.records_collected = 0
        self.session_start = datetime.now()
        logger.info("📊 DataCollector initialized - collecting ALL match data for AI training")
    
    def _get_connection(self):
        """Get database connection"""
        if not HAS_POSTGRES or not self.db_url:
            return None
        try:
            return psycopg2.connect(self.db_url)
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            return None
    
    def collect_match_analysis(
        self,
        # Match identification
        home_team: str,
        away_team: str,
        league: str = None,
        match_date: datetime = None,
        match_id: str = None,
        
        # Form data (home)
        home_form: Dict[str, Any] = None,
        
        # Form data (away)
        away_form: Dict[str, Any] = None,
        
        # Expected goals
        home_xg: float = None,
        away_xg: float = None,
        
        # H2H data
        h2h_data: Dict[str, Any] = None,
        
        # Standings
        standings: Dict[str, Any] = None,
        
        # Odds data
        odds_data: Dict[str, Any] = None,
        
        # Model predictions
        predicted_score: str = None,
        predicted_winner: str = None,
        model_probability: float = None,
        model_confidence: int = None,
        edge_percentage: float = None,
        
        # Ensemble components
        poisson_prob: float = None,
        neural_prob: float = None,
        h2h_weight: float = None,
        
        # Match scoring
        match_score: int = None,
        prediction_quality: int = None,
        
        # Meta
        data_source: str = "combined_engine",
        bet_placed: bool = False,
        analysis_type: str = "exact_score"
    ) -> bool:
        """
        Store comprehensive match analysis data.
        This captures ALL data, whether or not a bet was placed.
        """
        
        conn = self._get_connection()
        if not conn:
            logger.warning("⚠️ No database connection - skipping data collection")
            return False
        
        try:
            cursor = conn.cursor()
            
            # Parse form data
            home_form = home_form or {}
            away_form = away_form or {}
            h2h_data = h2h_data or {}
            standings = standings or {}
            
            # Extract predicted goals from score
            predicted_home_goals = None
            predicted_away_goals = None
            if predicted_score and '-' in predicted_score:
                try:
                    parts = predicted_score.split('-')
                    predicted_home_goals = float(parts[0])
                    predicted_away_goals = float(parts[1])
                except:
                    pass
            
            cursor.execute("""
                INSERT INTO training_data (
                    match_id, home_team, away_team, league, match_date,
                    
                    home_form_goals_scored, home_form_goals_conceded, 
                    home_form_clean_sheets, home_form_ppg,
                    home_form_wins, home_form_draws, home_form_losses,
                    
                    away_form_goals_scored, away_form_goals_conceded,
                    away_form_clean_sheets, away_form_ppg,
                    away_form_wins, away_form_draws, away_form_losses,
                    
                    home_xg, away_xg, total_xg,
                    
                    h2h_matches_count, h2h_home_wins, h2h_away_wins, h2h_draws,
                    h2h_avg_goals, h2h_btts_rate, h2h_over25_rate,
                    
                    home_position, away_position, home_points, away_points,
                    home_goal_diff, away_goal_diff,
                    
                    odds_data,
                    
                    predicted_home_goals, predicted_away_goals,
                    predicted_score, predicted_winner,
                    model_probability, model_confidence, edge_percentage,
                    
                    poisson_probability, neural_probability, h2h_weight,
                    
                    match_score, prediction_quality,
                    
                    data_source, bet_placed, analysis_type
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s
                )
            """, (
                match_id, home_team, away_team, league, match_date,
                
                home_form.get('goals_scored'), home_form.get('goals_conceded'),
                home_form.get('clean_sheets'), home_form.get('ppg'),
                home_form.get('wins'), home_form.get('draws'), home_form.get('losses'),
                
                away_form.get('goals_scored'), away_form.get('goals_conceded'),
                away_form.get('clean_sheets'), away_form.get('ppg'),
                away_form.get('wins'), away_form.get('draws'), away_form.get('losses'),
                
                home_xg, away_xg, 
                (home_xg or 0) + (away_xg or 0) if home_xg or away_xg else None,
                
                h2h_data.get('matches_count'), h2h_data.get('home_wins'),
                h2h_data.get('away_wins'), h2h_data.get('draws'),
                h2h_data.get('avg_goals'), h2h_data.get('btts_rate'),
                h2h_data.get('over25_rate'),
                
                standings.get('home_position'), standings.get('away_position'),
                standings.get('home_points'), standings.get('away_points'),
                standings.get('home_goal_diff'), standings.get('away_goal_diff'),
                
                Json(odds_data) if odds_data else None,
                
                predicted_home_goals, predicted_away_goals,
                predicted_score, predicted_winner,
                model_probability, model_confidence, edge_percentage,
                
                poisson_prob, neural_prob, h2h_weight,
                
                match_score, prediction_quality,
                
                data_source, bet_placed, analysis_type
            ))
            
            conn.commit()
            self.records_collected += 1
            
            logger.debug(f"📊 Collected: {home_team} vs {away_team} ({analysis_type}, bet={bet_placed})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error collecting data: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def collect_value_single(
        self,
        home_team: str,
        away_team: str,
        league: str,
        match_date: datetime,
        market_type: str,
        odds: float,
        model_probability: float,
        edge: float,
        home_xg: float = None,
        away_xg: float = None,
        odds_data: Dict[str, Any] = None,
        bet_placed: bool = False
    ) -> bool:
        """Collect Value Single analysis data"""
        
        # Determine predicted winner based on market
        predicted_winner = None
        if market_type == "HOME_WIN":
            predicted_winner = "home"
        elif market_type == "AWAY_WIN":
            predicted_winner = "away"
        elif market_type == "DRAW":
            predicted_winner = "draw"
        elif "OVER" in market_type:
            predicted_winner = "over"
        elif "UNDER" in market_type:
            predicted_winner = "under"
        
        return self.collect_match_analysis(
            home_team=home_team,
            away_team=away_team,
            league=league,
            match_date=match_date,
            home_xg=home_xg,
            away_xg=away_xg,
            odds_data=odds_data,
            predicted_winner=predicted_winner,
            model_probability=model_probability,
            edge_percentage=edge,
            bet_placed=bet_placed,
            data_source="value_singles",
            analysis_type=f"value_single_{market_type.lower()}"
        )
    
    def collect_sgp(
        self,
        home_team: str,
        away_team: str,
        league: str,
        match_date: datetime,
        legs: List[Dict[str, Any]],
        combined_odds: float,
        combined_probability: float,
        edge: float,
        confidence: int = None,
        bet_placed: bool = False
    ) -> bool:
        """Collect SGP analysis data"""
        
        return self.collect_match_analysis(
            home_team=home_team,
            away_team=away_team,
            league=league,
            match_date=match_date,
            odds_data={"legs": legs, "combined_odds": combined_odds},
            model_probability=combined_probability,
            model_confidence=confidence,
            edge_percentage=edge,
            bet_placed=bet_placed,
            data_source="sgp_engine",
            analysis_type="sgp"
        )
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get data collection statistics"""
        
        conn = self._get_connection()
        if not conn:
            return {"error": "No database connection"}
        
        try:
            cursor = conn.cursor()
            
            # Total records
            cursor.execute("SELECT COUNT(*) FROM training_data")
            total = cursor.fetchone()[0]
            
            # Records by analysis type
            cursor.execute("""
                SELECT analysis_type, COUNT(*), 
                       SUM(CASE WHEN bet_placed THEN 1 ELSE 0 END) as bets
                FROM training_data 
                GROUP BY analysis_type
            """)
            by_type = {row[0]: {"total": row[1], "bets": row[2]} for row in cursor.fetchall()}
            
            # Records with results
            cursor.execute("""
                SELECT COUNT(*) FROM training_data 
                WHERE actual_score IS NOT NULL
            """)
            with_results = cursor.fetchone()[0]
            
            # Accuracy (where we have results)
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN prediction_correct THEN 1 ELSE 0 END) as correct
                FROM training_data 
                WHERE prediction_correct IS NOT NULL
            """)
            accuracy_row = cursor.fetchone()
            accuracy = None
            if accuracy_row[0] > 0:
                accuracy = accuracy_row[1] / accuracy_row[0] * 100
            
            # Today's collection
            cursor.execute("""
                SELECT COUNT(*) FROM training_data 
                WHERE DATE(created_at) = CURRENT_DATE
            """)
            today = cursor.fetchone()[0]
            
            # This session
            cursor.execute("""
                SELECT COUNT(*) FROM training_data 
                WHERE created_at >= %s
            """, (self.session_start,))
            this_session = cursor.fetchone()[0]
            
            return {
                "total_records": total,
                "by_type": by_type,
                "with_results": with_results,
                "accuracy_pct": accuracy,
                "today": today,
                "this_session": this_session
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {"error": str(e)}
        finally:
            conn.close()
    
    def update_results(self, home_team: str, away_team: str, match_date: datetime,
                       actual_home_goals: int, actual_away_goals: int) -> int:
        """Update training data with actual match results"""
        
        conn = self._get_connection()
        if not conn:
            return 0
        
        try:
            cursor = conn.cursor()
            
            actual_score = f"{actual_home_goals}-{actual_away_goals}"
            
            cursor.execute("""
                UPDATE training_data
                SET actual_home_goals = %s,
                    actual_away_goals = %s,
                    actual_score = %s,
                    prediction_correct = (predicted_score = %s)
                WHERE home_team = %s 
                AND away_team = %s
                AND DATE(match_date) = DATE(%s)
                AND actual_score IS NULL
            """, (
                actual_home_goals, actual_away_goals, actual_score, actual_score,
                home_team, away_team, match_date
            ))
            
            updated = cursor.rowcount
            conn.commit()
            
            if updated > 0:
                logger.info(f"📊 Updated {updated} training records with result: {home_team} {actual_score} {away_team}")
            
            return updated
            
        except Exception as e:
            logger.error(f"❌ Error updating results: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()


# Global instance for easy access
_collector = None

def get_collector() -> DataCollector:
    """Get or create the global DataCollector instance"""
    global _collector
    if _collector is None:
        _collector = DataCollector()
    return _collector

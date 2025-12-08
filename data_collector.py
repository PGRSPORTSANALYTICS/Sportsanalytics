"""
Data Collector - Captures ALL match analysis for AI training
Stores comprehensive data even when bets aren't placed
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
import os
import numpy as np

# Database imports using SQLAlchemy (compatible with existing infrastructure)
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _convert_numpy_types(value):
    """Convert numpy types to Python native types for database storage"""
    if value is None:
        return None
    if isinstance(value, (np.integer, np.int64, np.int32)):
        return int(value)
    if isinstance(value, (np.floating, np.float64, np.float32)):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _clean_params(params: dict) -> dict:
    """Clean all parameter values of numpy types"""
    return {k: _convert_numpy_types(v) for k, v in params.items()}

class DataCollector:
    """
    Collects and stores all match analysis data for AI training.
    This runs independently of betting decisions - capturing data
    on ALL matches analyzed, not just those that qualify for bets.
    Uses SQLAlchemy for database operations.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self.db_url = os.environ.get('DATABASE_URL')
        self._engine = None
        self.records_collected = 0
        self.session_start = datetime.now()
        
        if self.db_url:
            try:
                self._engine = create_engine(self.db_url)
                logger.info("📊 DataCollector initialized with SQLAlchemy - collecting ALL match data for AI training")
            except Exception as e:
                logger.error(f"❌ DataCollector: Engine creation failed: {e}")
        else:
            logger.warning("⚠️ DataCollector: No DATABASE_URL found - data collection disabled")
    
    def _get_connection(self):
        """Get database connection using SQLAlchemy with auto-commit context"""
        if not self._engine:
            return None
        try:
            # Use begin() to get a transactional connection that auto-commits
            return self._engine.begin()
        except SQLAlchemyError as e:
            logger.error(f"❌ Database connection error: {e}")
            return None
    
    def _execute_write(self, query: str, params: dict) -> bool:
        """Execute a write operation with proper transaction handling"""
        if not self._engine:
            return False
        try:
            with self._engine.begin() as conn:
                conn.execute(text(query), params)
                return True
        except SQLAlchemyError as e:
            logger.error(f"❌ Write error: {e}")
            return False
    
    def _execute_read(self, query: str, params: dict = None):
        """Execute a read operation"""
        if not self._engine:
            return None
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                return result.fetchall()
        except SQLAlchemyError as e:
            logger.error(f"❌ Read error: {e}")
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
        analysis_type: str = "exact_score",
        
        # Monte Carlo Trust Level (L1/L2/L3)
        trust_level: str = None
    ) -> bool:
        """
        Store comprehensive match analysis data.
        This captures ALL data, whether or not a bet was placed.
        """
        
        if not self._engine:
            logger.warning("⚠️ No database engine - skipping data collection")
            return False
        
        try:
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
            
            # Calculate total xG
            total_xg = None
            if home_xg is not None or away_xg is not None:
                total_xg = (home_xg or 0) + (away_xg or 0)
            
            # Serialize odds_data as JSON string
            odds_json = json.dumps(odds_data) if odds_data else None
            
            params = {
                'match_id': match_id, 'home_team': home_team, 'away_team': away_team,
                'league': league, 'match_date': match_date,
                'home_goals_scored': home_form.get('goals_scored') or home_form.get('goals_per_game'),
                'home_goals_conceded': home_form.get('goals_conceded') or home_form.get('conceded_per_game'),
                'home_clean_sheets': home_form.get('clean_sheets') or home_form.get('clean_sheet_rate'),
                'home_ppg': home_form.get('ppg'),
                'home_wins': home_form.get('wins'), 'home_draws': home_form.get('draws'),
                'home_losses': home_form.get('losses'),
                'away_goals_scored': away_form.get('goals_scored') or away_form.get('goals_per_game'),
                'away_goals_conceded': away_form.get('goals_conceded') or away_form.get('conceded_per_game'),
                'away_clean_sheets': away_form.get('clean_sheets') or away_form.get('clean_sheet_rate'),
                'away_ppg': away_form.get('ppg'),
                'away_wins': away_form.get('wins'), 'away_draws': away_form.get('draws'),
                'away_losses': away_form.get('losses'),
                'home_xg': home_xg, 'away_xg': away_xg, 'total_xg': total_xg,
                'h2h_matches': h2h_data.get('matches_count') or h2h_data.get('total_matches'),
                'h2h_home_wins': h2h_data.get('home_wins'),
                'h2h_away_wins': h2h_data.get('away_wins'),
                'h2h_draws': h2h_data.get('draws'),
                'h2h_avg_goals': h2h_data.get('avg_goals') or h2h_data.get('avg_total_goals'),
                'h2h_btts_rate': h2h_data.get('btts_rate'),
                'h2h_over25_rate': h2h_data.get('over25_rate') or h2h_data.get('over_2_5_rate'),
                'home_pos': standings.get('home_position'),
                'away_pos': standings.get('away_position'),
                'home_pts': standings.get('home_points'),
                'away_pts': standings.get('away_points'),
                'home_gd': standings.get('home_goal_diff'),
                'away_gd': standings.get('away_goal_diff'),
                'odds_data': odds_json,
                'pred_home': predicted_home_goals, 'pred_away': predicted_away_goals,
                'pred_score': predicted_score, 'pred_winner': predicted_winner,
                'model_prob': model_probability, 'model_conf': model_confidence,
                'edge': edge_percentage,
                'poisson': poisson_prob, 'neural': neural_prob, 'h2h_wt': h2h_weight,
                'match_score': match_score, 'pred_quality': prediction_quality,
                'source': data_source, 'bet': bet_placed, 'atype': analysis_type,
                'trust_level': trust_level
            }
            
            # Convert numpy types to native Python types for database compatibility
            params = _clean_params(params)
            
            # Use engine.begin() for auto-commit transaction
            with self._engine.begin() as conn:
                conn.execute(text("""
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
                        
                        data_source, bet_placed, analysis_type, trust_level
                    ) VALUES (
                        :match_id, :home_team, :away_team, :league, :match_date,
                        :home_goals_scored, :home_goals_conceded, :home_clean_sheets, :home_ppg,
                        :home_wins, :home_draws, :home_losses,
                        :away_goals_scored, :away_goals_conceded, :away_clean_sheets, :away_ppg,
                        :away_wins, :away_draws, :away_losses,
                        :home_xg, :away_xg, :total_xg,
                        :h2h_matches, :h2h_home_wins, :h2h_away_wins, :h2h_draws,
                        :h2h_avg_goals, :h2h_btts_rate, :h2h_over25_rate,
                        :home_pos, :away_pos, :home_pts, :away_pts, :home_gd, :away_gd,
                        :odds_data,
                        :pred_home, :pred_away, :pred_score, :pred_winner,
                        :model_prob, :model_conf, :edge,
                        :poisson, :neural, :h2h_wt,
                        :match_score, :pred_quality,
                        :source, :bet, :atype, :trust_level
                    )
                """), params)
            
            # Transaction auto-commits when exiting the with block
            self.records_collected += 1
            logger.debug(f"📊 Collected: {home_team} vs {away_team} ({analysis_type}, bet={bet_placed})")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error collecting data: {e}")
            return False
    
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
        bet_placed: bool = False,
        trust_level: str = None
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
            analysis_type="sgp",
            trust_level=trust_level
        )
    
    def collect_sgp_prediction(
        self,
        home_team: str,
        away_team: str,
        league: str,
        match_date: datetime,
        legs: List[Dict[str, Any]],
        combined_probability: float,
        combined_odds: float,
        edge: float,
        sgp_type: str = "SGP",
        xg_data: Dict[str, Any] = None,
        bet_placed: bool = False,
        trust_level: str = None
    ) -> bool:
        """Collect SGP prediction data for AI training"""
        
        xg_data = xg_data or {}
        
        return self.collect_match_analysis(
            home_team=home_team,
            away_team=away_team,
            league=league,
            match_date=match_date,
            home_xg=xg_data.get('lambda_home'),
            away_xg=xg_data.get('lambda_away'),
            odds_data={"legs": legs, "combined_odds": combined_odds, "sgp_type": sgp_type},
            model_probability=combined_probability,
            edge_percentage=edge * 100 if edge and edge < 1 else edge,
            bet_placed=bet_placed,
            data_source="sgp_engine",
            analysis_type=f"sgp_{sgp_type.lower().replace(' ', '_')}",
            trust_level=trust_level
        )
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get data collection statistics using SQLAlchemy"""
        
        if not self._engine:
            return {"error": "No database engine"}
        
        try:
            with self._engine.connect() as conn:
                # Total records
                result = conn.execute(text("SELECT COUNT(*) FROM training_data"))
                total = result.fetchone()[0]
                
                # Records by analysis type
                result = conn.execute(text("""
                    SELECT analysis_type, COUNT(*), 
                           SUM(CASE WHEN bet_placed THEN 1 ELSE 0 END) as bets
                    FROM training_data 
                    GROUP BY analysis_type
                """))
                by_type = {row[0]: {"total": row[1], "bets": row[2]} for row in result.fetchall()}
                
                # Records with results
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM training_data 
                    WHERE actual_score IS NOT NULL
                """))
                with_results = result.fetchone()[0]
                
                # Accuracy (where we have results)
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN prediction_correct THEN 1 ELSE 0 END) as correct
                    FROM training_data 
                    WHERE prediction_correct IS NOT NULL
                """))
                accuracy_row = result.fetchone()
                accuracy = None
                if accuracy_row[0] and accuracy_row[0] > 0:
                    accuracy = (accuracy_row[1] or 0) / accuracy_row[0] * 100
                
                # Today's collection
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM training_data 
                    WHERE DATE(created_at) = CURRENT_DATE
                """))
                today = result.fetchone()[0]
                
                # This session
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM training_data 
                    WHERE created_at >= :session_start
                """), {'session_start': self.session_start})
                this_session = result.fetchone()[0]
                
                return {
                    "total_records": total,
                    "by_type": by_type,
                    "with_results": with_results,
                    "accuracy_pct": accuracy,
                    "today": today,
                    "this_session": this_session
                }
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {"error": str(e)}
    
    def update_results(self, home_team: str, away_team: str, match_date: datetime,
                       actual_home_goals: int, actual_away_goals: int) -> int:
        """Update training data with actual match results using SQLAlchemy"""
        
        if not self._engine:
            return 0
        
        try:
            actual_score = f"{actual_home_goals}-{actual_away_goals}"
            
            # Use engine.begin() for auto-commit transaction
            with self._engine.begin() as conn:
                result = conn.execute(text("""
                    UPDATE training_data
                    SET actual_home_goals = :home_goals,
                        actual_away_goals = :away_goals,
                        actual_score = :score,
                        prediction_correct = (predicted_score = :score)
                    WHERE home_team = :home 
                    AND away_team = :away
                    AND DATE(match_date) = DATE(:mdate)
                    AND actual_score IS NULL
                """), {
                    'home_goals': actual_home_goals,
                    'away_goals': actual_away_goals,
                    'score': actual_score,
                    'home': home_team,
                    'away': away_team,
                    'mdate': match_date
                })
                updated = result.rowcount
            
            # Transaction auto-commits when exiting the with block
            if updated > 0:
                logger.info(f"📊 Updated {updated} training records with result: {home_team} {actual_score} {away_team}")
            
            return updated
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Error updating results: {e}")
            return 0


    def get_track_record_summary(self) -> Dict[str, Any]:
        """Get overall track record summary pulling from ALL bet sources"""
        if not self._engine:
            return {"error": "No database engine"}
        
        try:
            with self._engine.connect() as conn:
                total_settled = 0
                total_correct = 0
                bets_settled = 0
                bets_correct = 0
                total_records = 0
                
                result = conn.execute(text("SELECT COUNT(*) FROM training_data"))
                total_records = result.fetchone()[0] or 0
                
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as settled,
                        SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins
                    FROM sgp_predictions WHERE status = 'settled'
                """))
                row = result.fetchone()
                if row:
                    sgp_settled = row[0] or 0
                    sgp_wins = row[1] or 0
                    total_settled += sgp_settled
                    total_correct += sgp_wins
                    bets_settled += sgp_settled
                    bets_correct += sgp_wins
                
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as settled,
                        SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins
                    FROM football_opportunities 
                    WHERE market = 'exact_score' AND outcome IN ('WIN', 'LOSS')
                """))
                row = result.fetchone()
                if row:
                    es_settled = row[0] or 0
                    es_wins = row[1] or 0
                    total_settled += es_settled
                    total_correct += es_wins
                    bets_settled += es_settled
                    bets_correct += es_wins
                
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as settled,
                        SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins
                    FROM football_opportunities 
                    WHERE market != 'exact_score' AND outcome IN ('WIN', 'LOSS')
                """))
                row = result.fetchone()
                if row:
                    vs_settled = row[0] or 0
                    vs_wins = row[1] or 0
                    total_settled += vs_settled
                    total_correct += vs_wins
                    bets_settled += vs_settled
                    bets_correct += vs_wins
                
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as settled,
                        SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as wins
                    FROM basketball_predictions WHERE status IN ('won', 'lost')
                """))
                row = result.fetchone()
                if row:
                    bb_settled = row[0] or 0
                    bb_wins = row[1] or 0
                    total_settled += bb_settled
                    total_correct += bb_wins
                    bets_settled += bb_settled
                    bets_correct += bb_wins
                
                preds_settled = 0
                preds_correct = 0
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as settled,
                        SUM(CASE WHEN prediction_correct = true THEN 1 ELSE 0 END) as correct
                    FROM training_data 
                    WHERE bet_placed = false AND actual_score IS NOT NULL
                """))
                row = result.fetchone()
                if row:
                    preds_settled = row[0] or 0
                    preds_correct = row[1] or 0
                
                return {
                    'total_records': total_records,
                    'settled': total_settled,
                    'correct': total_correct,
                    'accuracy_pct': (total_correct / total_settled * 100) if total_settled > 0 else 0,
                    'bets_placed': bets_settled,
                    'bets_settled': bets_settled,
                    'bets_correct': bets_correct,
                    'bets_accuracy_pct': (bets_correct / bets_settled * 100) if bets_settled > 0 else 0,
                    'predictions_only': total_records - bets_settled,
                    'predictions_settled': preds_settled,
                    'predictions_correct': preds_correct,
                    'predictions_accuracy_pct': (preds_correct / preds_settled * 100) if preds_settled > 0 else 0
                }
                
        except SQLAlchemyError as e:
            logger.error(f"❌ Error getting track record summary: {e}")
            return {"error": str(e)}
    
    def get_accuracy_by_type(self) -> List[Dict[str, Any]]:
        """Get accuracy breakdown by analysis type"""
        if not self._engine:
            return []
        
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        analysis_type,
                        COUNT(*) as total,
                        SUM(CASE WHEN actual_score IS NOT NULL THEN 1 ELSE 0 END) as settled,
                        SUM(CASE WHEN prediction_correct = true THEN 1 ELSE 0 END) as correct,
                        AVG(model_probability) as avg_probability,
                        AVG(edge_percentage) as avg_edge
                    FROM training_data
                    GROUP BY analysis_type
                    ORDER BY total DESC
                """))
                
                records = []
                for row in result.fetchall():
                    settled = row[2] or 0
                    correct = row[3] or 0
                    records.append({
                        'type': row[0] or 'Unknown',
                        'total': row[1] or 0,
                        'settled': settled,
                        'correct': correct,
                        'accuracy_pct': (correct / settled * 100) if settled > 0 else 0,
                        'avg_probability': row[4] or 0,
                        'avg_edge': row[5] or 0
                    })
                return records
        except SQLAlchemyError as e:
            logger.error(f"❌ Error getting accuracy by type: {e}")
            return []
    
    def get_accuracy_by_league(self, min_samples: int = 5) -> List[Dict[str, Any]]:
        """Get accuracy breakdown by league (min samples for statistical significance)"""
        if not self._engine:
            return []
        
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        league,
                        COUNT(*) as total,
                        SUM(CASE WHEN actual_score IS NOT NULL THEN 1 ELSE 0 END) as settled,
                        SUM(CASE WHEN prediction_correct = true THEN 1 ELSE 0 END) as correct
                    FROM training_data
                    WHERE league IS NOT NULL AND league != ''
                    GROUP BY league
                    HAVING SUM(CASE WHEN actual_score IS NOT NULL THEN 1 ELSE 0 END) >= :min_samples
                    ORDER BY SUM(CASE WHEN prediction_correct = true THEN 1 ELSE 0 END)::float / 
                             NULLIF(SUM(CASE WHEN actual_score IS NOT NULL THEN 1 ELSE 0 END), 0) DESC
                """), {'min_samples': min_samples})
                
                records = []
                for row in result.fetchall():
                    settled = row[2] or 0
                    correct = row[3] or 0
                    records.append({
                        'league': row[0],
                        'total': row[1] or 0,
                        'settled': settled,
                        'correct': correct,
                        'accuracy_pct': (correct / settled * 100) if settled > 0 else 0
                    })
                return records
        except SQLAlchemyError as e:
            logger.error(f"❌ Error getting accuracy by league: {e}")
            return []
    
    def get_daily_accuracy(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily accuracy for trend analysis"""
        if not self._engine:
            return []
        
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        DATE(match_date) as day,
                        COUNT(*) as total,
                        SUM(CASE WHEN actual_score IS NOT NULL THEN 1 ELSE 0 END) as settled,
                        SUM(CASE WHEN prediction_correct = true THEN 1 ELSE 0 END) as correct
                    FROM training_data
                    WHERE match_date >= CURRENT_DATE - :days
                    GROUP BY DATE(match_date)
                    ORDER BY DATE(match_date) ASC
                """), {'days': days})
                
                records = []
                for row in result.fetchall():
                    settled = row[2] or 0
                    correct = row[3] or 0
                    records.append({
                        'date': row[0],
                        'total': row[1] or 0,
                        'settled': settled,
                        'correct': correct,
                        'accuracy_pct': (correct / settled * 100) if settled > 0 else 0
                    })
                return records
        except SQLAlchemyError as e:
            logger.error(f"❌ Error getting daily accuracy: {e}")
            return []
    
    def get_calibration_data(self, bins: int = 10) -> List[Dict[str, Any]]:
        """Get model calibration data (predicted probability vs actual hit rate)"""
        if not self._engine:
            return []
        
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        FLOOR(model_probability * :bins) / :bins as prob_bin,
                        COUNT(*) as total,
                        SUM(CASE WHEN prediction_correct = true THEN 1 ELSE 0 END) as correct,
                        AVG(model_probability) as avg_predicted
                    FROM training_data
                    WHERE model_probability IS NOT NULL 
                    AND actual_score IS NOT NULL
                    GROUP BY FLOOR(model_probability * :bins)
                    ORDER BY prob_bin ASC
                """), {'bins': bins})
                
                records = []
                for row in result.fetchall():
                    total = row[1] or 0
                    correct = row[2] or 0
                    records.append({
                        'probability_bin': f"{int((row[0] or 0) * 100)}-{int((row[0] or 0) * 100 + 100/bins)}%",
                        'total': total,
                        'correct': correct,
                        'actual_rate': (correct / total * 100) if total > 0 else 0,
                        'predicted_rate': (row[3] or 0) * 100
                    })
                return records
        except SQLAlchemyError as e:
            logger.error(f"❌ Error getting calibration data: {e}")
            return []


# Global instance for easy access
_collector = None

def get_collector() -> DataCollector:
    """Get or create the global DataCollector instance"""
    global _collector
    if _collector is None:
        _collector = DataCollector()
    return _collector

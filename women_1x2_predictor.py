"""
Women's Football 1X2 (Match Winner) Predictor
Generates Home/Draw/Away predictions with EV-based filtering
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
import psycopg2
from psycopg2.extras import execute_values

from db_connection import DatabaseConnection
from women_league_detector import get_women_detector
from api_football_client import APIFootballClient

logger = logging.getLogger(__name__)

# EV thresholds per mode
EV_THRESHOLDS = {
    'TRAIN': 0.03,  # 3% EV during data collection (women's markets are softer)
    'PROD': 0.05    # 5% EV in production
}

# Current operating mode
CURRENT_MODE = 'TRAIN'  # Change to 'PROD' at launch

# League-specific goal averages for women's football
WOMEN_LEAGUE_AVG_GOALS = {
    'default': {'home': 1.5, 'away': 1.2},  # Conservative defaults
    'wsl': {'home': 1.8, 'away': 1.4},  # Women's Super League
    'nwsl': {'home': 1.7, 'away': 1.3},  # US NWSL
}


@dataclass
class Women1X2Prediction:
    """Women's Match Winner prediction"""
    match_id: str
    league: str
    league_id: int
    home_team: str
    away_team: str
    match_date: str
    kickoff_time: str
    selection: str  # 'HOME', 'DRAW', 'AWAY'
    implied_prob: float
    model_prob: float
    odds: float
    ev_percentage: float
    stake: float
    notes: Dict


class Women1X2Predictor:
    """Generate 1X2 predictions for women's football"""
    
    def __init__(self, mode: str = CURRENT_MODE):
        self.mode = mode
        self.ev_threshold = EV_THRESHOLDS[mode]
        self.detector = get_women_detector()
        self.api_client = APIFootballClient()
        
        logger.info(f"🎯 Women's 1X2 Predictor initialized (Mode: {mode}, EV Threshold: {self.ev_threshold:.1%})")
    
    def get_upcoming_women_matches(self) -> List[Dict]:
        """Fetch upcoming women's matches (cached)"""
        logger.info("📅 Fetching women's football matches...")
        
        # Get women's leagues
        women_leagues = self.detector.get_women_leagues()
        
        all_fixtures = []
        for league in women_leagues:
            try:
                # Fetch fixtures using cache (24h TTL)
                fixtures = self.api_client.get_upcoming_fixtures_cached(
                    league_ids=[league['league_id']],
                    days_ahead=7
                )
                
                if fixtures:
                    for fx in fixtures:
                        fx['is_women'] = True
                        fx['league_config'] = league
                        all_fixtures.append(fx)
                        
            except Exception as e:
                logger.error(f"❌ Error fetching {league['league_name']}: {e}")
                continue
        
        logger.info(f"✅ Found {len(all_fixtures)} women's matches")
        return all_fixtures
    
    def get_league_averages(self, league_name: str) -> Dict[str, float]:
        """Get league-specific goal averages"""
        league_key = league_name.lower()
        
        for key in WOMEN_LEAGUE_AVG_GOALS:
            if key in league_key:
                return WOMEN_LEAGUE_AVG_GOALS[key]
        
        return WOMEN_LEAGUE_AVG_GOALS['default']
    
    def calculate_1x2_probabilities(self, fixture: Dict) -> Optional[Dict]:
        """
        Calculate 1X2 probabilities using Poisson distribution
        
        Returns dict with HOME/DRAW/AWAY probabilities
        """
        try:
            home_team = fixture.get('teams', {}).get('home', {}).get('name')
            away_team = fixture.get('teams', {}).get('away', {}).get('name')
            league_name = fixture.get('league', {}).get('name', 'default')
            
            # Get league-specific averages
            league_avgs = self.get_league_averages(league_name)
            home_xg = league_avgs['home']
            away_xg = league_avgs['away']
            
            # Poisson calculation for match outcomes
            from scipy.stats import poisson
            import numpy as np
            
            # Calculate probability matrix (scores 0-5)
            prob_matrix = np.zeros((6, 6))
            for i in range(6):
                for j in range(6):
                    prob_matrix[i][j] = poisson.pmf(i, home_xg) * poisson.pmf(j, away_xg)
            
            # Aggregate probabilities
            home_win_prob = np.sum(np.tril(prob_matrix, -1))  # Home score > Away score
            draw_prob = np.sum(np.diag(prob_matrix))  # Home score = Away score
            away_win_prob = np.sum(np.triu(prob_matrix, 1))  # Away score > Home score
            
            # Normalize to ensure sum = 1.0
            total = home_win_prob + draw_prob + away_win_prob
            
            return {
                'HOME': home_win_prob / total,
                'DRAW': draw_prob / total,
                'AWAY': away_win_prob / total
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculating probabilities: {e}")
            return None
    
    def get_1x2_odds(self, fixture: Dict) -> Optional[Dict]:
        """Get 1X2 odds from bookmakers"""
        try:
            # Try to get odds from The Odds API (cached)
            match_id = str(fixture.get('fixture', {}).get('id'))
            
            # For now, use synthetic odds based on probabilities
            # (Real implementation would fetch from odds API)
            probs = self.calculate_1x2_probabilities(fixture)
            
            if not probs:
                return None
            
            # Convert probabilities to odds with bookmaker margin (~5%)
            margin = 0.05
            
            return {
                'HOME': round(1.0 / (probs['HOME'] * (1 + margin)), 2),
                'DRAW': round(1.0 / (probs['DRAW'] * (1 + margin)), 2),
                'AWAY': round(1.0 / (probs['AWAY'] * (1 + margin)), 2)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting odds: {e}")
            return None
    
    def calculate_ev(self, model_prob: float, odds: float) -> float:
        """Calculate expected value: (model_prob * odds) - 1"""
        return (model_prob * odds) - 1.0
    
    def calculate_kelly_stake(self, model_prob: float, odds: float, bankroll: float = 100.0) -> float:
        """Kelly Criterion stake sizing (fractional Kelly = 25%)"""
        implied_prob = 1.0 / odds
        edge = model_prob - implied_prob
        
        if edge <= 0:
            return 0.0
        
        kelly_fraction = edge / (odds - 1)
        fractional_kelly = kelly_fraction * 0.25  # 25% Kelly
        
        stake = bankroll * fractional_kelly
        return max(min(stake, 10.0), 1.0)  # Cap between $1-$10
    
    def generate_predictions(self) -> List[Women1X2Prediction]:
        """Generate 1X2 predictions for women's matches"""
        logger.info(f"🎯 Generating women's 1X2 predictions (Mode: {self.mode})...")
        
        fixtures = self.get_upcoming_women_matches()
        predictions = []
        
        for fixture in fixtures:
            try:
                # Get probabilities and odds
                probs = self.calculate_1x2_probabilities(fixture)
                odds = self.get_1x2_odds(fixture)
                
                if not probs or not odds:
                    continue
                
                # Find best EV bet
                best_selection = None
                best_ev = -1
                
                for selection in ['HOME', 'DRAW', 'AWAY']:
                    model_prob = probs[selection]
                    selection_odds = odds[selection]
                    ev = self.calculate_ev(model_prob, selection_odds)
                    
                    if ev > best_ev:
                        best_ev = ev
                        best_selection = selection
                
                # Filter by EV threshold
                if best_ev < self.ev_threshold:
                    continue
                
                # Calculate stake
                stake = self.calculate_kelly_stake(
                    probs[best_selection],
                    odds[best_selection]
                )
                
                # Create prediction
                match_info = fixture.get('fixture', {})
                teams = fixture.get('teams', {})
                league_info = fixture.get('league', {})
                
                prediction = Women1X2Prediction(
                    match_id=str(match_info.get('id')),
                    league=league_info.get('name', 'Unknown'),
                    league_id=league_info.get('id'),
                    home_team=teams.get('home', {}).get('name', 'Unknown'),
                    away_team=teams.get('away', {}).get('name', 'Unknown'),
                    match_date=match_info.get('date', '')[:10],
                    kickoff_time=match_info.get('date', ''),
                    selection=best_selection,
                    implied_prob=1.0 / odds[best_selection],
                    model_prob=probs[best_selection],
                    odds=odds[best_selection],
                    ev_percentage=best_ev * 100,
                    stake=stake,
                    notes={
                        'all_probs': probs,
                        'all_odds': odds,
                        'mode': self.mode
                    }
                )
                
                predictions.append(prediction)
                
                logger.info(f"✅ {prediction.home_team} vs {prediction.away_team} | "
                           f"{prediction.selection} @ {prediction.odds} | EV: {prediction.ev_percentage:.1f}%")
                
            except Exception as e:
                logger.error(f"❌ Error processing fixture: {e}")
                continue
        
        logger.info(f"🎯 Generated {len(predictions)} women's 1X2 predictions")
        return predictions
    
    def save_predictions(self, predictions: List[Women1X2Prediction]) -> int:
        """Save predictions to database"""
        if not predictions:
            logger.info("📊 No predictions to save")
            return 0
        
        with DatabaseConnection.get_connection() as conn:
            try:
                cur = conn.cursor()
                
                # Prepare data for batch insert
                data = []
                for pred in predictions:
                    data.append((
                        pred.match_id,
                        pred.league,
                        pred.league_id,
                        pred.home_team,
                        pred.away_team,
                        pred.match_date,
                        pred.kickoff_time,
                        pred.selection,
                        pred.implied_prob,
                        pred.model_prob,
                        pred.odds,
                        pred.ev_percentage,
                        pred.stake,
                        self.mode,
                        psycopg2.extras.Json(pred.notes),
                        'PROD'  # Production mode for ROI tracking
                    ))
                
                # Batch insert with ON CONFLICT DO NOTHING
                execute_values(
                    cur,
                    """
                    INSERT INTO women_match_winner_predictions 
                    (match_id, league, league_id, home_team, away_team, match_date, 
                     kickoff_time, selection, implied_prob, model_prob, odds, 
                     ev_percentage, stake, source_mode, notes, mode)
                    VALUES %s
                    ON CONFLICT (match_id) DO NOTHING
                    """,
                    data
                )
                
                saved_count = cur.rowcount
                logger.info(f"💾 Saved {saved_count} women's 1X2 predictions to database")
                
                return saved_count
                
            except Exception as e:
                logger.error(f"❌ Error saving predictions: {e}")
                return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    predictor = Women1X2Predictor(mode='TRAIN')
    predictions = predictor.generate_predictions()
    saved = predictor.save_predictions(predictions)
    
    print(f"\n{'='*60}")
    print(f"🎯 Women's 1X2 Prediction Summary")
    print(f"{'='*60}")
    print(f"Mode: {predictor.mode}")
    print(f"EV Threshold: {predictor.ev_threshold:.1%}")
    print(f"Predictions Generated: {len(predictions)}")
    print(f"Predictions Saved: {saved}")
    print(f"{'='*60}\n")

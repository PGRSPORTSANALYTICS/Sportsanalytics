#!/usr/bin/env python3
"""
SGP (Same Game Parlay) Predictor
Generates automated SGP predictions using REAL AI probabilities from Poisson/Neural Net
Runs daily in parallel with exact score predictions
"""

import sqlite3
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from scipy.stats import poisson
from scipy.special import erf
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = 'data/real_football.db'

# Correlation heuristics between SGP legs
CORR_RULES = {
    ("OVER_UNDER_GOALS:OVER", "BTTS:YES"): 0.35,
    ("PLAYER_TO_SCORE:TRUE", "OVER_UNDER_GOALS:OVER"): 0.25,
    ("PLAYER_TO_SCORE:TRUE", "BTTS:YES"): 0.20,
    ("OVER_UNDER_GOALS:UNDER", "BTTS:NO"): 0.30,
    ("PLAYER_TO_SCORE:FALSE", "BTTS:NO"): 0.15,
}

class SGPPredictor:
    """Generates Same Game Parlay predictions using real AI probabilities"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self._init_database()
        logger.info("✅ SGP Predictor initialized")
    
    def _init_database(self):
        """Create SGP predictions table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sgp_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,
                match_id TEXT,
                home_team TEXT,
                away_team TEXT,
                league TEXT,
                match_date TEXT,
                kickoff_time TEXT,
                
                -- Parlay legs (stored as JSON-like text)
                legs TEXT,
                parlay_description TEXT,
                
                -- Probabilities and odds
                parlay_probability REAL,
                fair_odds REAL,
                bookmaker_odds REAL,
                ev_percentage REAL,
                
                -- Staking
                stake REAL DEFAULT 160,
                kelly_stake REAL,
                
                -- Status tracking
                status TEXT DEFAULT 'pending',
                outcome TEXT,
                result TEXT,
                payout REAL,
                profit_loss REAL,
                settled_timestamp INTEGER,
                
                -- Model metadata
                model_version TEXT,
                simulations INTEGER DEFAULT 200000,
                correlation_method TEXT DEFAULT 'copula'
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ SGP database schema ready")
    
    def calculate_over_under_prob(self, lambda_home: float, lambda_away: float, line: float = 2.5, over: bool = True) -> float:
        """
        Calculate Over/Under goals probability using Poisson distribution
        
        Args:
            lambda_home: Expected goals for home team (from xG predictor)
            lambda_away: Expected goals for away team (from xG predictor)
            line: Goals line (e.g., 2.5)
            over: True for Over, False for Under
        
        Returns:
            Probability of the outcome
        """
        max_goals = 10
        prob_over = 0.0
        
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                total_goals = h + a
                prob_score = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
                
                if over and total_goals > line:
                    prob_over += prob_score
                elif not over and total_goals < line:
                    prob_over += prob_score
        
        return prob_over
    
    def calculate_btts_prob(self, lambda_home: float, lambda_away: float, btts: bool = True) -> float:
        """
        Calculate BTTS (Both Teams To Score) probability using Poisson
        
        Args:
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            btts: True for BTTS Yes, False for BTTS No
        
        Returns:
            Probability of BTTS outcome
        """
        max_goals = 10
        prob_btts_yes = 0.0
        
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                prob_score = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
                
                if h > 0 and a > 0:
                    prob_btts_yes += prob_score
        
        return prob_btts_yes if btts else (1.0 - prob_btts_yes)
    
    def build_corr_matrix(self, legs: List[Dict[str, Any]]) -> np.ndarray:
        """Build correlation matrix for SGP legs"""
        n = len(legs)
        C = np.eye(n)
        
        keys = [f"{leg['market_type']}:{leg['outcome'].upper()}" for leg in legs]
        
        for i in range(n):
            for j in range(i+1, n):
                corr = CORR_RULES.get((keys[i], keys[j])) or CORR_RULES.get((keys[j], keys[i])) or 0.0
                corr = max(min(corr, 0.8), -0.3)  # Clamp to safe range
                C[i, j] = C[j, i] = corr
        
        # Ensure positive-definite
        for attempt in range(5):
            try:
                _ = np.linalg.cholesky(C)
                return C
            except np.linalg.LinAlgError:
                C = C * 0.95 + np.eye(n) * 0.05
        
        return np.eye(n)  # Fallback to identity
    
    def normal_cdf(self, z: np.ndarray) -> np.ndarray:
        """Standard normal CDF"""
        return 0.5 * (1.0 + erf(z / np.sqrt(2.0)))
    
    def price_parlay_copula(self, legs: List[Dict[str, Any]], simulations: int = 200000) -> float:
        """
        Price SGP using Copula Monte Carlo simulation
        
        Args:
            legs: List of parlay legs with probabilities
            simulations: Number of Monte Carlo simulations
        
        Returns:
            Joint probability of all legs hitting
        """
        n = len(legs)
        if n == 0:
            return 0.0
        
        probs = np.array([leg['probability'] for leg in legs])
        probs = np.clip(probs, 1e-6, 1 - 1e-6)
        
        C = self.build_corr_matrix(legs)
        try:
            L = np.linalg.cholesky(C)
        except np.linalg.LinAlgError:
            L = np.linalg.cholesky((C + C.T) / 2 + np.eye(n) * 1e-6)
        
        z = np.random.normal(size=(simulations, n))
        z_corr = z @ L.T
        u = self.normal_cdf(z_corr)
        
        hits = (u < probs).all(axis=1)
        p_all = hits.mean()
        return float(p_all)
    
    def generate_sgp_for_match(self, match_data: Dict[str, Any], lambda_home: float, lambda_away: float) -> Optional[Dict[str, Any]]:
        """
        Generate SGP prediction for a single match
        
        Args:
            match_data: Match information (teams, league, date, etc.)
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
        
        Returns:
            SGP prediction dict or None if no value found
        """
        # Generate popular SGP combinations
        sgp_combinations = [
            # Over 2.5 + BTTS
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'}
                ],
                'description': 'Over 2.5 Goals + BTTS Yes'
            },
            # Under 2.5 + BTTS No
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'UNDER', 'line': 2.5},
                    {'market_type': 'BTTS', 'outcome': 'NO'}
                ],
                'description': 'Under 2.5 Goals + BTTS No'
            },
            # Over 1.5 + BTTS
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 1.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'}
                ],
                'description': 'Over 1.5 Goals + BTTS Yes'
            },
        ]
        
        best_sgp = None
        best_ev = -100
        
        for sgp in sgp_combinations:
            # Calculate probabilities for each leg
            legs_with_probs = []
            
            for leg in sgp['legs']:
                if leg['market_type'] == 'OVER_UNDER_GOALS':
                    prob = self.calculate_over_under_prob(
                        lambda_home, lambda_away, 
                        leg.get('line', 2.5), 
                        leg['outcome'] == 'OVER'
                    )
                elif leg['market_type'] == 'BTTS':
                    prob = self.calculate_btts_prob(
                        lambda_home, lambda_away,
                        leg['outcome'] == 'YES'
                    )
                else:
                    continue
                
                legs_with_probs.append({
                    'market_type': leg['market_type'],
                    'outcome': leg['outcome'],
                    'probability': prob,
                    'line': leg.get('line')
                })
            
            # Price the parlay using copula
            parlay_prob = self.price_parlay_copula(legs_with_probs)
            fair_odds = 1.0 / max(parlay_prob, 1e-12)
            
            # Estimate bookmaker odds (fair odds * 1.1 margin)
            bookmaker_odds = fair_odds * 0.90  # Bookmaker takes ~10% margin
            
            # Calculate EV
            ev_pct = (bookmaker_odds / fair_odds - 1.0) * 100.0
            
            # Only keep if EV > 5% (lower threshold than exact scores)
            if ev_pct > 5.0 and ev_pct > best_ev:
                best_ev = ev_pct
                best_sgp = {
                    'legs': legs_with_probs,
                    'description': sgp['description'],
                    'parlay_probability': parlay_prob,
                    'fair_odds': fair_odds,
                    'bookmaker_odds': bookmaker_odds,
                    'ev_percentage': ev_pct,
                    'match_data': match_data
                }
        
        return best_sgp
    
    def save_sgp_prediction(self, sgp: Dict[str, Any]):
        """Save SGP prediction to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        match_data = sgp['match_data']
        
        # Format legs as text
        legs_text = " | ".join([
            f"{leg['market_type']} {leg['outcome']}" + 
            (f" ({leg['line']})" if leg.get('line') else "")
            for leg in sgp['legs']
        ])
        
        # Calculate Kelly stake
        kelly_fraction = (sgp['parlay_probability'] * sgp['bookmaker_odds'] - 1.0) / (sgp['bookmaker_odds'] - 1.0)
        kelly_stake = max(0, min(kelly_fraction * 0.5, 0.05)) * 1000  # 5% max, 1000 SEK bankroll
        
        cursor.execute('''
            INSERT INTO sgp_predictions (
                timestamp, match_id, home_team, away_team, league, match_date, kickoff_time,
                legs, parlay_description, parlay_probability, fair_odds, bookmaker_odds, ev_percentage,
                stake, kelly_stake, model_version, simulations, correlation_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            int(datetime.now().timestamp()),
            match_data.get('match_id', ''),
            match_data['home_team'],
            match_data['away_team'],
            match_data.get('league', ''),
            match_data.get('match_date', ''),
            match_data.get('kickoff_time', ''),
            legs_text,
            sgp['description'],
            sgp['parlay_probability'],
            sgp['fair_odds'],
            sgp['bookmaker_odds'],
            sgp['ev_percentage'],
            160.0,  # Default stake
            kelly_stake,
            'v1.0_copula_poisson',
            200000,
            'copula'
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ SGP saved: {match_data['home_team']} vs {match_data['away_team']} | {sgp['description']} | EV: {sgp['ev_percentage']:.1f}%")


def test_sgp_predictor():
    """Test SGP predictor with sample data"""
    predictor = SGPPredictor()
    
    # Test match data
    match_data = {
        'match_id': 'test_001',
        'home_team': 'Manchester City',
        'away_team': 'Liverpool',
        'league': 'Premier League',
        'match_date': '2025-11-10',
        'kickoff_time': '15:00'
    }
    
    # Sample xG values
    lambda_home = 1.8
    lambda_away = 1.5
    
    logger.info(f"Testing SGP for {match_data['home_team']} vs {match_data['away_team']}")
    logger.info(f"Expected goals: Home {lambda_home}, Away {lambda_away}")
    
    sgp = predictor.generate_sgp_for_match(match_data, lambda_home, lambda_away)
    
    if sgp:
        logger.info(f"\n✅ Best SGP found:")
        logger.info(f"   {sgp['description']}")
        logger.info(f"   Probability: {sgp['parlay_probability']:.4f}")
        logger.info(f"   Fair Odds: {sgp['fair_odds']:.2f}")
        logger.info(f"   Bookmaker Odds: {sgp['bookmaker_odds']:.2f}")
        logger.info(f"   EV: {sgp['ev_percentage']:.1f}%")
        
        # Save it
        predictor.save_sgp_prediction(sgp)
        logger.info("✅ SGP saved to database")
    else:
        logger.info("❌ No SGP found with positive EV")


if __name__ == '__main__':
    logger.info("="*80)
    logger.info("SGP PREDICTOR TEST")
    logger.info("="*80)
    test_sgp_predictor()

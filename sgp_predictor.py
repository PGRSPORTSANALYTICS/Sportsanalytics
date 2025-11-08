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

from sgp_self_learner import SGPSelfLearner
from sgp_odds_pricing import OddsPricingService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = 'data/real_football.db'

# Correlation heuristics between SGP legs
CORR_RULES = {
    # Goals correlations
    ("OVER_UNDER_GOALS:OVER", "BTTS:YES"): 0.35,
    ("OVER_UNDER_GOALS:UNDER", "BTTS:NO"): 0.30,
    
    # Player props correlations
    ("PLAYER_TO_SCORE:YES", "OVER_UNDER_GOALS:OVER"): 0.25,
    ("PLAYER_TO_SCORE:YES", "BTTS:YES"): 0.20,
    ("PLAYER_TO_SCORE:YES", "MATCH_RESULT:HOME"): 0.18,
    ("PLAYER_TO_SCORE:YES", "MATCH_RESULT:AWAY"): 0.18,
    ("PLAYER_SHOTS:OVER", "PLAYER_TO_SCORE:YES"): 0.40,
    ("PLAYER_SHOTS:OVER", "OVER_UNDER_GOALS:OVER"): 0.28,
    
    # Half-time/Second half correlations
    ("HALF_TIME_GOALS:OVER", "SECOND_HALF_GOALS:OVER"): 0.25,
    ("HALF_TIME_GOALS:OVER", "OVER_UNDER_GOALS:OVER"): 0.45,
    ("SECOND_HALF_GOALS:OVER", "OVER_UNDER_GOALS:OVER"): 0.50,
    ("HALF_TIME_GOALS:OVER", "BTTS:YES"): 0.30,
    ("SECOND_HALF_GOALS:OVER", "BTTS:YES"): 0.28,
    
    # Corners correlations
    ("CORNERS:OVER", "OVER_UNDER_GOALS:OVER"): 0.40,
    ("CORNERS:OVER", "BTTS:YES"): 0.35,
    ("CORNERS:OVER", "HALF_TIME_GOALS:OVER"): 0.30,
    ("CORNERS:OVER", "SECOND_HALF_GOALS:OVER"): 0.32,
    
    # Negative correlations
    ("PLAYER_TO_SCORE:NO", "BTTS:NO"): 0.15,
    ("OVER_UNDER_GOALS:UNDER", "PLAYER_TO_SCORE:YES"): -0.15,
    ("CORNERS:UNDER", "OVER_UNDER_GOALS:OVER"): -0.20,
    ("HALF_TIME_GOALS:UNDER", "OVER_UNDER_GOALS:OVER"): -0.25,
}

class SGPPredictor:
    """Generates Same Game Parlay predictions using real AI probabilities"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self._init_database()
        self.self_learner = SGPSelfLearner()
        self.odds_pricing = OddsPricingService(parlay_margin=0.07)
        logger.info("✅ SGP Predictor initialized with self-learning and live odds")
    
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
                correlation_method TEXT DEFAULT 'copula',
                
                -- Odds pricing metadata
                pricing_mode TEXT DEFAULT 'simulated',
                pricing_metadata TEXT
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
    
    def calculate_player_to_score_prob(self, player_scoring_rate: float, team_lambda: float, match_duration: int = 90) -> float:
        """
        Calculate probability of a specific player scoring (anytime goalscorer)
        
        Args:
            player_scoring_rate: Player's goals per game (from historical data)
            team_lambda: Team's expected goals for this match (from Poisson xG)
            match_duration: Match minutes (default 90, can adjust for subs)
        
        Returns:
            Probability of player scoring at least once
        """
        # Adjust player rate based on team's expected output for this match
        # If team expected to score more, player's chances increase proportionally
        adjusted_lambda = player_scoring_rate * (team_lambda / 1.5)  # 1.5 = league avg
        
        # Poisson: P(X >= 1) = 1 - P(X = 0) = 1 - e^(-lambda)
        prob_scores = 1.0 - poisson.pmf(0, adjusted_lambda)
        
        # Clamp to realistic range (5-70%)
        return max(0.05, min(0.70, prob_scores))
    
    def calculate_player_shots_prob(self, player_shots_per_game: float, threshold: int = 2) -> float:
        """
        Calculate probability of player achieving X+ shots on target
        
        Args:
            player_shots_per_game: Player's avg shots per game
            threshold: Minimum shots (default 2+)
        
        Returns:
            Probability of player getting threshold+ shots
        """
        # Use Poisson for shot count probability
        lambda_shots = player_shots_per_game
        
        # P(X >= threshold) = 1 - P(X < threshold) = 1 - sum(P(X=k) for k=0 to threshold-1)
        prob_under = sum(poisson.pmf(k, lambda_shots) for k in range(threshold))
        prob_over = 1.0 - prob_under
        
        # Clamp to realistic range
        return max(0.10, min(0.80, prob_over))
    
    def calculate_half_time_goals_prob(self, lambda_home: float, lambda_away: float, line: float = 0.5, over: bool = True) -> float:
        """
        Calculate 1st half goals Over/Under probability
        
        Args:
            lambda_home: Expected goals for home team (full match)
            lambda_away: Expected goals for away team (full match)
            line: Goals line (e.g., 0.5, 1.5)
            over: True for Over, False for Under
        
        Returns:
            Probability of the outcome
        """
        # 1st half typically sees ~45% of total goals
        lambda_home_1h = lambda_home * 0.45
        lambda_away_1h = lambda_away * 0.45
        
        max_goals = 6
        prob_result = 0.0
        
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                total_goals = h + a
                prob_score = poisson.pmf(h, lambda_home_1h) * poisson.pmf(a, lambda_away_1h)
                
                if over and total_goals > line:
                    prob_result += prob_score
                elif not over and total_goals < line:
                    prob_result += prob_score
        
        return prob_result
    
    def calculate_second_half_goals_prob(self, lambda_home: float, lambda_away: float, line: float = 0.5, over: bool = True) -> float:
        """
        Calculate 2nd half goals Over/Under probability
        
        Args:
            lambda_home: Expected goals for home team (full match)
            lambda_away: Expected goals for away team (full match)
            line: Goals line (e.g., 0.5, 1.5)
            over: True for Over, False for Under
        
        Returns:
            Probability of the outcome
        """
        # 2nd half typically sees ~55% of total goals (teams push harder)
        lambda_home_2h = lambda_home * 0.55
        lambda_away_2h = lambda_away * 0.55
        
        max_goals = 6
        prob_result = 0.0
        
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                total_goals = h + a
                prob_score = poisson.pmf(h, lambda_home_2h) * poisson.pmf(a, lambda_away_2h)
                
                if over and total_goals > line:
                    prob_result += prob_score
                elif not over and total_goals < line:
                    prob_result += prob_score
        
        return prob_result
    
    def calculate_corners_prob(self, lambda_home: float, lambda_away: float, line: float = 9.5, over: bool = True) -> float:
        """
        Calculate total corners Over/Under probability
        
        Args:
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            line: Corners line (e.g., 9.5, 10.5, 11.5)
            over: True for Over, False for Under
        
        Returns:
            Probability of the outcome
        """
        # Corners correlate with attacking intensity and xG
        # Typical match: 10-11 corners total (empirical league average)
        # Calibrated formula: total_corners ≈ (total_xG) × 3.0 + 2.5
        # For xG = 2.7: 2.7 × 3.0 + 2.5 = 10.6 corners (matches historical data)
        total_xg = lambda_home + lambda_away
        expected_total_corners = total_xg * 3.0 + 2.5
        
        # Use Poisson distribution for total corners
        max_corners = 25
        prob_result = 0.0
        
        for corners in range(max_corners + 1):
            prob_corners = poisson.pmf(corners, expected_total_corners)
            
            if over and corners > line:
                prob_result += prob_corners
            elif not over and corners < line:
                prob_result += prob_corners
        
        return prob_result
    
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
    
    def generate_sgp_for_match(self, match_data: Dict[str, Any], lambda_home: float, lambda_away: float, 
                              player_data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Generate SGP prediction for a single match
        
        Args:
            match_data: Match information (teams, league, date, etc.)
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            player_data: Optional dict with top scorers data from API-Football
        
        Returns:
            SGP prediction dict or None if no value found
        """
        # Generate popular SGP combinations (goals-only)
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
            # Half-time/Second half combinations
            {
                'legs': [
                    {'market_type': 'HALF_TIME_GOALS', 'outcome': 'OVER', 'line': 0.5},
                    {'market_type': 'SECOND_HALF_GOALS', 'outcome': 'OVER', 'line': 0.5}
                ],
                'description': '1H Over 0.5 + 2H Over 0.5'
            },
            {
                'legs': [
                    {'market_type': 'HALF_TIME_GOALS', 'outcome': 'OVER', 'line': 0.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'}
                ],
                'description': '1H Over 0.5 + BTTS Yes'
            },
            {
                'legs': [
                    {'market_type': 'SECOND_HALF_GOALS', 'outcome': 'OVER', 'line': 1.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'}
                ],
                'description': '2H Over 1.5 + BTTS Yes'
            },
            # Corners combinations
            {
                'legs': [
                    {'market_type': 'CORNERS', 'outcome': 'OVER', 'line': 9.5},
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5}
                ],
                'description': 'Corners Over 9.5 + Over 2.5 Goals'
            },
            {
                'legs': [
                    {'market_type': 'CORNERS', 'outcome': 'OVER', 'line': 10.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'}
                ],
                'description': 'Corners Over 10.5 + BTTS Yes'
            },
            {
                'legs': [
                    {'market_type': 'CORNERS', 'outcome': 'OVER', 'line': 11.5},
                    {'market_type': 'HALF_TIME_GOALS', 'outcome': 'OVER', 'line': 0.5},
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5}
                ],
                'description': 'Corners 11.5+ + 1H Over 0.5 + Over 2.5 (Premium)'
            },
        ]
        
        # Add player prop combinations if player data available
        if player_data and (player_data.get('home_scorers') or player_data.get('away_scorers')):
            # Get top scorer from each team
            top_home = player_data.get('home_scorers', [{}])[0] if player_data.get('home_scorers') else {}
            top_away = player_data.get('away_scorers', [{}])[0] if player_data.get('away_scorers') else {}
            
            # Player prop combinations (6 new types)
            if top_home.get('name') and top_home.get('scoring_rate', 0) > 0.15:  # Min threshold
                home_player = top_home['name']
                sgp_combinations.extend([
                    # Player to Score + Over 2.5
                    {
                        'legs': [
                            {'market_type': 'PLAYER_TO_SCORE', 'outcome': 'YES', 'player': home_player, 'team': 'home'},
                            {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5}
                        ],
                        'description': f'{home_player} to Score + Over 2.5'
                    },
                    # Player to Score + BTTS Yes
                    {
                        'legs': [
                            {'market_type': 'PLAYER_TO_SCORE', 'outcome': 'YES', 'player': home_player, 'team': 'home'},
                            {'market_type': 'BTTS', 'outcome': 'YES'}
                        ],
                        'description': f'{home_player} to Score + BTTS Yes'
                    },
                    # Player Shots 2+ + Over 2.5 + BTTS (3-leg premium)
                    {
                        'legs': [
                            {'market_type': 'PLAYER_SHOTS', 'outcome': 'OVER', 'threshold': 2, 'player': home_player, 'team': 'home'},
                            {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
                            {'market_type': 'BTTS', 'outcome': 'YES'}
                        ],
                        'description': f'{home_player} 2+ Shots + Over 2.5 + BTTS'
                    }
                ])
            
            if top_away.get('name') and top_away.get('scoring_rate', 0) > 0.15:
                away_player = top_away['name']
                sgp_combinations.extend([
                    # Player to Score + Over 2.5
                    {
                        'legs': [
                            {'market_type': 'PLAYER_TO_SCORE', 'outcome': 'YES', 'player': away_player, 'team': 'away'},
                            {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5}
                        ],
                        'description': f'{away_player} to Score + Over 2.5'
                    },
                    # Player to Score + BTTS Yes
                    {
                        'legs': [
                            {'market_type': 'PLAYER_TO_SCORE', 'outcome': 'YES', 'player': away_player, 'team': 'away'},
                            {'market_type': 'BTTS', 'outcome': 'YES'}
                        ],
                        'description': f'{away_player} to Score + BTTS Yes'
                    },
                    # Player Shots 2+ + Over 2.5 + BTTS (3-leg premium)
                    {
                        'legs': [
                            {'market_type': 'PLAYER_SHOTS', 'outcome': 'OVER', 'threshold': 2, 'player': away_player, 'team': 'away'},
                            {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
                            {'market_type': 'BTTS', 'outcome': 'YES'}
                        ],
                        'description': f'{away_player} 2+ Shots + Over 2.5 + BTTS'
                    }
                ])
        
        # Keep top 3 SGPs by EV instead of just 1
        all_sgps = []
        
        for sgp in sgp_combinations:
            # Calculate probabilities for each leg
            legs_with_probs = []
            
            for leg in sgp['legs']:
                prob = None
                
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
                elif leg['market_type'] == 'PLAYER_TO_SCORE':
                    # Get player's scoring rate and team lambda
                    if not player_data:
                        continue
                    
                    team = leg.get('team', 'home')
                    player_name = leg.get('player')
                    scorers = player_data.get(f'{team}_scorers', [])
                    
                    # Find player in scorers list
                    player_stats = next((p for p in scorers if p.get('name') == player_name), None)
                    if not player_stats:
                        continue
                    
                    scoring_rate = player_stats.get('scoring_rate', 0)
                    team_lambda = lambda_home if team == 'home' else lambda_away
                    
                    prob = self.calculate_player_to_score_prob(scoring_rate, team_lambda)
                    
                elif leg['market_type'] == 'PLAYER_SHOTS':
                    # Get player's shots per game
                    if not player_data:
                        continue
                    
                    team = leg.get('team', 'home')
                    player_name = leg.get('player')
                    scorers = player_data.get(f'{team}_scorers', [])
                    
                    # Find player in scorers list
                    player_stats = next((p for p in scorers if p.get('name') == player_name), None)
                    if not player_stats:
                        continue
                    
                    shots_per_game = player_stats.get('shots_per_game', 0)
                    threshold = leg.get('threshold', 2)
                    
                    prob = self.calculate_player_shots_prob(shots_per_game, threshold)
                    
                elif leg['market_type'] == 'HALF_TIME_GOALS':
                    prob = self.calculate_half_time_goals_prob(
                        lambda_home, lambda_away,
                        leg.get('line', 0.5),
                        leg['outcome'] == 'OVER'
                    )
                    
                elif leg['market_type'] == 'SECOND_HALF_GOALS':
                    prob = self.calculate_second_half_goals_prob(
                        lambda_home, lambda_away,
                        leg.get('line', 0.5),
                        leg['outcome'] == 'OVER'
                    )
                    
                elif leg['market_type'] == 'CORNERS':
                    prob = self.calculate_corners_prob(
                        lambda_home, lambda_away,
                        leg.get('line', 9.5),
                        leg['outcome'] == 'OVER'
                    )
                else:
                    continue
                
                if prob is None:
                    continue
                
                legs_with_probs.append({
                    'market_type': leg['market_type'],
                    'outcome': leg['outcome'],
                    'probability': prob,
                    'line': leg.get('line'),
                    'player': leg.get('player'),
                    'threshold': leg.get('threshold')
                })
            
            # Price the parlay using copula
            raw_parlay_prob = self.price_parlay_copula(legs_with_probs)
            
            # Apply self-learning calibration to adjust probability
            parlay_prob = self.self_learner.adjust_probability(raw_parlay_prob)
            fair_odds = 1.0 / max(parlay_prob, 1e-12)
            
            logger.info(f"   📊 Calibrated: {raw_parlay_prob:.3f} → {parlay_prob:.3f}")
            
            # Get REAL bookmaker odds from The Odds API
            bookmaker_odds, pricing_mode, pricing_metadata = self.odds_pricing.price_sgp_parlay(
                home_team=match_data['home_team'],
                away_team=match_data['away_team'],
                league=match_data.get('league', ''),
                legs=legs_with_probs,
                fair_odds=fair_odds
            )
            
            logger.info(f"   💰 Odds pricing: {pricing_mode.upper()} mode → {bookmaker_odds:.2f}x")
            
            # Calculate EV
            ev_pct = (bookmaker_odds / fair_odds - 1.0) * 100.0
            
            # Quality filter: Minimum EV AND minimum odds
            # Reject low-odds parlays (< 2.5x) - not worth the risk
            MIN_EV = 5.0
            MIN_ODDS = 2.5
            
            if ev_pct > MIN_EV and bookmaker_odds >= MIN_ODDS:
                all_sgps.append({
                    'legs': legs_with_probs,
                    'description': sgp['description'],
                    'parlay_probability': parlay_prob,
                    'fair_odds': fair_odds,
                    'bookmaker_odds': bookmaker_odds,
                    'ev_percentage': ev_pct,
                    'match_data': match_data,
                    'pricing_mode': pricing_mode,
                    'pricing_metadata': pricing_metadata
                })
        
        # DEDUPLICATION: Remove duplicate SGP combinations
        # Keep only the highest EV version of each unique description
        unique_sgps = {}
        for sgp in all_sgps:
            desc = sgp['description']
            if desc not in unique_sgps or sgp['ev_percentage'] > unique_sgps[desc]['ev_percentage']:
                unique_sgps[desc] = sgp
        
        # Convert back to list and sort by EV
        deduplicated_sgps = list(unique_sgps.values())
        deduplicated_sgps.sort(key=lambda x: x['ev_percentage'], reverse=True)
        
        logger.info(f"   🎯 Generated {len(all_sgps)} SGPs, deduplicated to {len(deduplicated_sgps)} unique")
        
        # Return top 3 unique SGPs
        return deduplicated_sgps[:3]
    
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
        
        # Calculate Kelly stake with dynamic sizing from self-learner
        kelly_multiplier = self.self_learner.get_dynamic_kelly()
        kelly_fraction = (sgp['parlay_probability'] * sgp['bookmaker_odds'] - 1.0) / (sgp['bookmaker_odds'] - 1.0)
        kelly_stake = max(0, min(kelly_fraction * kelly_multiplier, 0.05)) * 1000  # 5% max, 1000 SEK bankroll
        
        # Convert pricing metadata to JSON string
        import json
        pricing_metadata_str = json.dumps(sgp.get('pricing_metadata', {}))
        
        cursor.execute('''
            INSERT INTO sgp_predictions (
                timestamp, match_id, home_team, away_team, league, match_date, kickoff_time,
                legs, parlay_description, parlay_probability, fair_odds, bookmaker_odds, ev_percentage,
                stake, kelly_stake, model_version, simulations, correlation_method,
                pricing_mode, pricing_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            'v1.0_copula_poisson_live',
            200000,
            'copula',
            sgp.get('pricing_mode', 'simulated'),
            pricing_metadata_str
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

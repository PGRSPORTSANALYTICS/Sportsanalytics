#!/usr/bin/env python3
"""
SGP (Same Game Parlay) Predictor
Generates automated SGP predictions using REAL AI probabilities from Poisson/Neural Net
Runs daily in parallel with exact score predictions
"""

import numpy as np
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from scipy.stats import poisson
from scipy.special import erf
import os

from sgp_self_learner import SGPSelfLearner
from sgp_odds_pricing import OddsPricingService
from db_helper import db_helper
from bankroll_manager import get_bankroll_manager
from discord_notifier import send_bet_to_discord

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    
    # MonsterSGP - 1st Half Only correlations
    ("HALF_TIME_GOALS:OVER", "HALF_TIME_BTTS:YES"): 0.40,
    ("HALF_TIME_GOALS:OVER", "HALF_TIME_CORNERS:OVER"): 0.35,
    ("HALF_TIME_BTTS:YES", "HALF_TIME_CORNERS:OVER"): 0.30,
    ("HALF_TIME_CORNERS:OVER", "HALF_TIME_GOALS:OVER"): 0.35,
    
    # MonsterSGP - Team-Specific Markets correlations
    ("HALF_TIME_GOALS:OVER", "HOME_TEAM_CORNERS:OVER"): 0.38,
    ("HALF_TIME_GOALS:OVER", "HOME_TEAM_SHOTS:OVER"): 0.42,
    ("HOME_TEAM_CORNERS:OVER", "HOME_TEAM_SHOTS:OVER"): 0.45,
    ("HOME_TEAM_CORNERS:OVER", "AWAY_TEAM_CORNERS:UNDER"): 0.25,
    ("HOME_TEAM_SHOTS:OVER", "AWAY_TEAM_SHOTS:UNDER"): 0.28,
    ("HOME_TEAM_CORNERS:OVER", "CORNERS:OVER"): 0.50,
    ("AWAY_TEAM_CORNERS:UNDER", "CORNERS:OVER"): -0.15,
    ("MATCH_RESULT:HOME", "HOME_TEAM_CORNERS:OVER"): 0.35,
    ("MATCH_RESULT:HOME", "HOME_TEAM_SHOTS:OVER"): 0.40,
    ("MATCH_RESULT:HOME", "AWAY_TEAM_CORNERS:UNDER"): 0.30,
    ("MATCH_RESULT:HOME", "AWAY_TEAM_SHOTS:UNDER"): 0.32,
    
    # Negative correlations
    ("PLAYER_TO_SCORE:NO", "BTTS:NO"): 0.15,
    ("OVER_UNDER_GOALS:UNDER", "PLAYER_TO_SCORE:YES"): -0.15,
    ("CORNERS:UNDER", "OVER_UNDER_GOALS:OVER"): -0.20,
    ("HALF_TIME_GOALS:UNDER", "OVER_UNDER_GOALS:OVER"): -0.25,
}

class SGPPredictor:
    """Generates Same Game Parlay predictions using real AI probabilities"""
    
    def __init__(self):
        self._init_database()
        self.self_learner = SGPSelfLearner()
        self.odds_pricing = OddsPricingService(parlay_margin=0.40)  # Realistic SGP margin (Bet365 uses ~45%)
        logger.info("✅ SGP Predictor initialized with self-learning and live odds")
    
    def _init_database(self):
        """Create SGP predictions table"""
        db_helper.execute('''
            CREATE TABLE IF NOT EXISTS sgp_predictions (
                id SERIAL PRIMARY KEY,
                timestamp BIGINT,
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
                stake REAL DEFAULT 480,
                kelly_stake REAL,
                
                -- Status tracking
                status TEXT DEFAULT 'pending',
                outcome TEXT,
                result TEXT,
                payout REAL,
                profit_loss REAL,
                settled_timestamp BIGINT,
                
                -- Model metadata
                model_version TEXT,
                simulations INTEGER DEFAULT 200000,
                correlation_method TEXT DEFAULT 'copula',
                
                -- Odds pricing metadata
                pricing_mode TEXT DEFAULT 'simulated',
                pricing_metadata TEXT
            )
        ''')
        
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
    
    def calculate_half_time_btts_prob(self, lambda_home: float, lambda_away: float, btts: bool = True) -> float:
        """
        Calculate 1st half BTTS probability
        
        Args:
            lambda_home: Expected goals for home team (full match)
            lambda_away: Expected goals for away team (full match)
            btts: True for BTTS Yes, False for BTTS No
        
        Returns:
            Probability of 1st half BTTS outcome
        """
        # 1st half typically sees ~45% of total goals
        lambda_home_1h = lambda_home * 0.45
        lambda_away_1h = lambda_away * 0.45
        
        max_goals = 6
        prob_btts_yes = 0.0
        
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                prob_score = poisson.pmf(h, lambda_home_1h) * poisson.pmf(a, lambda_away_1h)
                
                if h > 0 and a > 0:
                    prob_btts_yes += prob_score
        
        return prob_btts_yes if btts else (1.0 - prob_btts_yes)
    
    def calculate_half_time_corners_prob(self, total_xg: float, line: float = 4.5, over: bool = True) -> float:
        """
        Calculate 1st half corners Over/Under probability
        
        Args:
            total_xg: Total expected goals (home + away)
            line: Corners line (e.g., 4.5, 5.5)
            over: True for Over, False for Under
        
        Returns:
            Probability of the outcome
        """
        # 1st half typically sees ~43% of total corners
        # Calibrated formula: half_corners = total_xg × 1.3 + 1.0
        expected_1h_corners = total_xg * 1.3 + 1.0
        
        # Use Poisson for corner count
        max_corners = 15
        prob_result = 0.0
        
        for c in range(max_corners + 1):
            prob_count = poisson.pmf(c, expected_1h_corners)
            
            if over and c > line:
                prob_result += prob_count
            elif not over and c < line:
                prob_result += prob_count
        
        return max(0.10, min(0.90, prob_result))
    
    def calculate_team_corners_prob(self, team_xg: float, line: float = 8.5, over: bool = True) -> float:
        """
        Calculate team-specific corners Over/Under probability
        
        Args:
            team_xg: Expected goals for this specific team
            line: Corners line (e.g., 8.5, 3.5)
            over: True for Over, False for Under
        
        Returns:
            Probability of the outcome
        """
        # Team corners formula: team_corners = team_xG × 3.5 + 3.0
        # Strong team (2.0 xG) → 10.0 corners, Weak team (0.8 xG) → 5.8 corners
        expected_team_corners = team_xg * 3.5 + 3.0
        
        # Use Poisson for corner count
        max_corners = 20
        prob_result = 0.0
        
        for c in range(max_corners + 1):
            prob_count = poisson.pmf(c, expected_team_corners)
            
            if over and c > line:
                prob_result += prob_count
            elif not over and c < line:
                prob_result += prob_count
        
        return prob_result
    
    def calculate_team_shots_prob(self, team_xg: float, line: float = 27.5, over: bool = True) -> float:
        """
        Calculate team-specific shots Over/Under probability
        
        Args:
            team_xg: Expected goals for this specific team
            line: Shots line (e.g., 27.5, 4.5)
            over: True for Over, False for Under
        
        Returns:
            Probability of the outcome
        """
        # Team shots formula: team_shots = team_xG × 7.0 + 10.0
        # Strong team (2.0 xG) → 24.0 shots, Weak team (0.8 xG) → 15.6 shots
        expected_team_shots = team_xg * 7.0 + 10.0
        
        # Use Poisson for shot count
        max_shots = 50
        prob_result = 0.0
        
        for s in range(max_shots + 1):
            prob_count = poisson.pmf(s, expected_team_shots)
            
            if over and s > line:
                prob_result += prob_count
            elif not over and s < line:
                prob_result += prob_count
        
        return prob_result
    
    def calculate_match_result_prob(self, lambda_home: float, lambda_away: float, outcome: str) -> float:
        """
        Calculate match result (1x2) probability
        
        Args:
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            outcome: 'HOME', 'DRAW', or 'AWAY'
        
        Returns:
            Probability of the outcome
        """
        max_goals = 6
        prob_home = 0.0
        prob_draw = 0.0
        prob_away = 0.0
        
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                prob_score = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
                
                if h > a:
                    prob_home += prob_score
                elif h == a:
                    prob_draw += prob_score
                else:
                    prob_away += prob_score
        
        if outcome == 'HOME':
            return prob_home
        elif outcome == 'DRAW':
            return prob_draw
        else:  # AWAY
            return prob_away
    
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
    
    def get_exact_score_prediction(self, home_team: str, away_team: str) -> Optional[Tuple[int, int]]:
        """
        Check if there's an existing exact score prediction for this match.
        
        Returns:
            Tuple of (home_goals, away_goals) if prediction exists, None otherwise
        """
        try:
            result = db_helper.execute('''
                SELECT selection FROM football_opportunities 
                WHERE home_team = %s AND away_team = %s 
                AND market = 'exact_score'
                AND status = 'pending'
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (home_team, away_team), fetch='one')
            
            if result and result[0]:
                selection = result[0]
                # Parse "Exact Score: 2-1" format
                if ':' in selection:
                    score_part = selection.split(':')[-1].strip()
                    if '-' in score_part:
                        parts = score_part.split('-')
                        if len(parts) == 2:
                            home_goals = int(parts[0].strip())
                            away_goals = int(parts[1].strip())
                            return (home_goals, away_goals)
        except Exception as e:
            logger.debug(f"Error checking exact score prediction: {e}")
        
        return None
    
    def is_sgp_conflicting(self, sgp_combination: Dict, exact_score: Tuple[int, int]) -> bool:
        """
        Check if an SGP combination conflicts with the exact score prediction.
        
        Args:
            sgp_combination: Dict with 'legs' list containing market_type, outcome, line
            exact_score: Tuple of (home_goals, away_goals)
        
        Returns:
            True if the SGP conflicts with the exact score, False if compatible
        """
        home_goals, away_goals = exact_score
        total_goals = home_goals + away_goals
        btts = home_goals > 0 and away_goals > 0
        
        for leg in sgp_combination.get('legs', []):
            market_type = leg.get('market_type')
            outcome = leg.get('outcome')
            line = leg.get('line', 0)
            
            if market_type == 'OVER_UNDER_GOALS':
                if outcome == 'OVER' and total_goals <= line:
                    return True
                if outcome == 'UNDER' and total_goals >= line:
                    return True
                    
            elif market_type == 'BTTS':
                if outcome == 'YES' and not btts:
                    return True
                if outcome == 'NO' and btts:
                    return True
                    
            elif market_type == 'HALF_TIME_GOALS':
                if outcome == 'OVER' and line >= 1.5:
                    ht_expected = total_goals * 0.45
                    if ht_expected < line:
                        return True
                        
            elif market_type == 'SECOND_HALF_GOALS':
                if outcome == 'OVER' and line >= 1.5:
                    sh_expected = total_goals * 0.55
                    if sh_expected < line:
                        return True
        
        return False
    
    def _should_skip_btts_yes(self, match_data: Dict[str, Any], lambda_home: float, lambda_away: float) -> Tuple[bool, str]:
        """
        Check if BTTS Yes should be skipped based on H2H data (NEW: Dec 3, 2025)
        
        Uses blended probability: 60% Poisson + 40% H2H historical rate
        Skips BTTS Yes if blended rate is below threshold (35% for Premier League, 30% others)
        Only applies when we have sufficient H2H data (4+ matches)
        
        Returns:
            Tuple of (should_skip, reason)
        """
        h2h_btts_rate = match_data.get('h2h_btts_rate', 0.5)
        h2h_total_matches = match_data.get('h2h_total_matches', 0)
        league = match_data.get('league', '')
        
        # Only apply filter if we have sufficient H2H data (4+ matches)
        if h2h_total_matches < 4:
            return False, "Insufficient H2H data"
        
        # Calculate Poisson-based BTTS probability
        poisson_btts_prob = self.calculate_btts_prob(lambda_home, lambda_away, btts=True)
        
        # Blend: 60% Poisson model + 40% H2H historical rate
        blended_btts_rate = 0.6 * poisson_btts_prob + 0.4 * h2h_btts_rate
        
        # League-specific threshold (Premier League stricter due to historical poor performance)
        threshold = 0.35 if league == 'Premier League' else 0.30
        
        if blended_btts_rate < threshold:
            home_team = match_data.get('home_team', '')
            away_team = match_data.get('away_team', '')
            reason = f"H2H BTTS filter: {h2h_btts_rate:.0%} H2H rate + {poisson_btts_prob:.0%} model = {blended_btts_rate:.0%} blended < {threshold:.0%} threshold"
            logger.info(f"   🚫 BTTS Yes blocked for {home_team} vs {away_team}: {reason}")
            return True, reason
        
        return False, ""
    
    def _combination_has_btts_yes(self, combo: Dict[str, Any]) -> bool:
        """Check if a combination includes BTTS Yes leg"""
        for leg in combo.get('legs', []):
            if leg.get('market_type') == 'BTTS' and leg.get('outcome') == 'YES':
                return True
        return False
    
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
        home_team = match_data.get('home_team', '')
        away_team = match_data.get('away_team', '')
        
        # Premier League requires higher EV threshold (8%) due to historical -88.7% ROI
        league = match_data.get('league', '')
        
        # Check if BTTS Yes should be filtered based on H2H data (NEW: Dec 3, 2025)
        skip_btts_yes, btts_skip_reason = self._should_skip_btts_yes(match_data, lambda_home, lambda_away)
        
        # Check for conflicting exact score prediction
        exact_score = self.get_exact_score_prediction(home_team, away_team)
        if exact_score:
            logger.info(f"📊 Found exact score prediction {exact_score[0]}-{exact_score[1]} for {home_team} vs {away_team}")
        
        # Generate SGP combinations (max 4 legs, target 10x max odds)
        # GOAL-BASED + TOTAL CORNERS (SofaScore verification enabled)
        sgp_combinations = [
            # ========== SINGLE-LEG SGPs ==========
            
            # Over 2.5 Goals (~1.8x)
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5}
                ],
                'description': 'Over 2.5 Goals'
            },
            
            # REMOVED: Over 3.5 Goals alone - 22% hit rate, -1,042 kr loss
            
            # BTTS Yes (~1.9x)
            {
                'legs': [
                    {'market_type': 'BTTS', 'outcome': 'YES'}
                ],
                'description': 'BTTS Yes'
            },
            
            # BTTS No (~1.9x)
            {
                'legs': [
                    {'market_type': 'BTTS', 'outcome': 'NO'}
                ],
                'description': 'BTTS No'
            },
            
            # ========== 2-LEG COMBOS (~3-5x) ==========
            
            # Over 2.5 + BTTS (~3.5x)
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'}
                ],
                'description': 'Over 2.5 + BTTS'
            },
            
            # Over 3.5 + BTTS (~5x)
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 3.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'}
                ],
                'description': 'Over 3.5 + BTTS'
            },
            
            # Over 2.5 + 1H Over 0.5 (~3x) - 66.7% hit rate!
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
                    {'market_type': 'HALF_TIME_GOALS', 'outcome': 'OVER', 'line': 0.5}
                ],
                'description': 'Over 2.5 + 1H Goal'
            },
            
            # Under 2.5 + BTTS No (~3.5x) - Defensive low-scoring game
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'UNDER', 'line': 2.5},
                    {'market_type': 'BTTS', 'outcome': 'NO'}
                ],
                'description': 'Under 2.5 + BTTS No'
            },
            
            # Under 3.5 + BTTS No (~2.5x) - More likely to hit
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'UNDER', 'line': 3.5},
                    {'market_type': 'BTTS', 'outcome': 'NO'}
                ],
                'description': 'Under 3.5 + BTTS No'
            },
            
            # DISABLED: Corners legs temporarily removed due to low hit rate
            # Over 2.5 + Corners 8.5+ (~3.5x) - DISABLED
            # {
            #     'legs': [
            #         {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
            #         {'market_type': 'CORNERS', 'outcome': 'OVER', 'line': 8.5}
            #     ],
            #     'description': 'Over 2.5 + Corners 8.5+'
            # },
            
            # ========== 3-LEG COMBOS (~5-8x) ==========
            
            # Over 2.5 + BTTS + 1H Over 0.5 (~5x)
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'},
                    {'market_type': 'HALF_TIME_GOALS', 'outcome': 'OVER', 'line': 0.5}
                ],
                'description': 'Over 2.5 + BTTS + 1H Goal'
            },
            
            # Over 3.5 + BTTS + 1H Over 0.5 (~7x)
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 3.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'},
                    {'market_type': 'HALF_TIME_GOALS', 'outcome': 'OVER', 'line': 0.5}
                ],
                'description': 'Over 3.5 + BTTS + 1H Goal'
            },
            
            # Over 2.5 + BTTS + 2H Over 1.5 (~6x)
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'},
                    {'market_type': 'SECOND_HALF_GOALS', 'outcome': 'OVER', 'line': 1.5}
                ],
                'description': 'Over 2.5 + BTTS + 2H Over 1.5'
            },
            
            # ========== 3-LEG CORNERS COMBOS - DISABLED (low hit rate) ==========
            # All corners combos temporarily disabled
            
            # ========== 4-LEG COMBOS (MAX ~10x) ==========
            
            # Over 2.5 + BTTS + 1H + 2H (~8x)
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'},
                    {'market_type': 'HALF_TIME_GOALS', 'outcome': 'OVER', 'line': 0.5},
                    {'market_type': 'SECOND_HALF_GOALS', 'outcome': 'OVER', 'line': 0.5}
                ],
                'description': 'Over 2.5 + BTTS + 1H Over 0.5 + 2H Over 0.5'
            },
            
            # DISABLED: Corners 10.5+ combo - low hit rate
            
            # Over 3.5 + BTTS + 1H + 2H (~10x max)
            {
                'legs': [
                    {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 3.5},
                    {'market_type': 'BTTS', 'outcome': 'YES'},
                    {'market_type': 'HALF_TIME_GOALS', 'outcome': 'OVER', 'line': 0.5},
                    {'market_type': 'SECOND_HALF_GOALS', 'outcome': 'OVER', 'line': 1.5}
                ],
                'description': 'Over 3.5 + BTTS + 1H Over 0.5 + 2H Over 1.5'
            },
            
        ]
        
        # Filter out BTTS Yes combinations if H2H data indicates low scoring (NEW: Dec 3, 2025)
        if skip_btts_yes:
            original_count = len(sgp_combinations)
            sgp_combinations = [
                combo for combo in sgp_combinations 
                if not self._combination_has_btts_yes(combo)
            ]
            filtered_count = original_count - len(sgp_combinations)
            if filtered_count > 0:
                logger.info(f"   🎯 H2H filter removed {filtered_count} BTTS Yes combinations")
        
        # Keep top 3 SGPs by EV instead of just 1
        all_sgps = []
        blocked_count = 0
        
        for sgp in sgp_combinations:
            # DISABLED: Allow SGP even if exact score exists (user request Dec 3, 2025)
            # if exact_score and self.is_sgp_conflicting(sgp, exact_score):
            #     logger.debug(f"⚠️  BLOCKED: {sgp['description']} conflicts with {exact_score[0]}-{exact_score[1]} prediction")
            #     blocked_count += 1
            #     continue
            
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
                    
                elif leg['market_type'] == 'HALF_TIME_BTTS':
                    prob = self.calculate_half_time_btts_prob(
                        lambda_home, lambda_away,
                        leg['outcome'] == 'YES'
                    )
                    
                elif leg['market_type'] == 'HALF_TIME_CORNERS':
                    total_xg = lambda_home + lambda_away
                    prob = self.calculate_half_time_corners_prob(
                        total_xg,
                        leg.get('line', 4.5),
                        leg['outcome'] == 'OVER'
                    )
                    
                elif leg['market_type'] == 'HOME_TEAM_CORNERS':
                    prob = self.calculate_team_corners_prob(
                        lambda_home,
                        leg.get('line', 8.5),
                        leg['outcome'] == 'OVER'
                    )
                    
                elif leg['market_type'] == 'AWAY_TEAM_CORNERS':
                    prob = self.calculate_team_corners_prob(
                        lambda_away,
                        leg.get('line', 3.5),
                        leg['outcome'] == 'OVER'
                    )
                    
                elif leg['market_type'] == 'HOME_TEAM_SHOTS':
                    prob = self.calculate_team_shots_prob(
                        lambda_home,
                        leg.get('line', 27.5),
                        leg['outcome'] == 'OVER'
                    )
                    
                elif leg['market_type'] == 'AWAY_TEAM_SHOTS':
                    prob = self.calculate_team_shots_prob(
                        lambda_away,
                        leg.get('line', 4.5),
                        leg['outcome'] == 'OVER'
                    )
                    
                elif leg['market_type'] == 'MATCH_RESULT':
                    prob = self.calculate_match_result_prob(
                        lambda_home,
                        lambda_away,
                        leg['outcome']
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
            
            # AI-LEARNED FILTER: Based on 653 settled bets analysis (Dec 3, 2025)
            # Data showed: Odds 4-6 = +12.8% edge, Odds 2-4 = -14.8% (losing)
            # 4-DAY TRIAL: Dec 3-7, 2025 - Testing AI-learned optimal odds range
            MIN_ODDS = 4.0   # Raised from 2.5 - skip losing 2-4 zone
            MAX_ODDS = 6.0   # Lowered from 10.0 - avoid 6-10 dead zone
            
            # League-specific EV thresholds (Premier League needs higher due to historical poor ROI)
            league = match_data.get('league', '')
            if 'Premier League' in league:
                min_ev_required = 8.0  # 8% for Premier League (historical -88.7% ROI)
            else:
                min_ev_required = 5.0  # 5% for other leagues
            
            # Assign tier based on odds for display purposes only
            if bookmaker_odds >= 8.0:
                bet_tier = "Jackpot Play"
            elif bookmaker_odds >= 5.0:
                bet_tier = "Premium Parlay"
            elif bookmaker_odds >= 3.5:
                bet_tier = "Value Parlay"
            else:
                bet_tier = "Value Bet"
            
            # Apply filters: EV threshold, min odds, and MAX 10x cap
            if ev_pct > min_ev_required and MIN_ODDS <= bookmaker_odds <= MAX_ODDS:
                all_sgps.append({
                    'legs': legs_with_probs,
                    'description': sgp['description'],
                    'parlay_probability': parlay_prob,
                    'bet_tier': bet_tier,
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
        
        if blocked_count > 0:
            logger.info(f"   🚫 CONFLICT BLOCKED: {blocked_count} SGPs blocked due to exact score prediction")
        logger.info(f"   🎯 Generated {len(all_sgps)} SGPs, deduplicated to {len(deduplicated_sgps)} unique")
        
        # Return top 3 unique SGPs
        return deduplicated_sgps[:3]
    
    def save_sgp_prediction(self, sgp: Dict[str, Any]) -> bool:
        """Save SGP prediction to database - always saves, but tracks if bet was placed"""
        
        match_data = sgp['match_data']
        
        # DUPLICATE CHECK: Prevent duplicate SGPs for same match + parlay
        try:
            existing = db_helper.fetchone('''
                SELECT id FROM sgp_predictions 
                WHERE home_team = %s AND away_team = %s 
                AND parlay_description = %s
                AND DATE(match_date) = DATE(%s)
            ''', (
                match_data['home_team'],
                match_data['away_team'],
                sgp['description'],
                match_data.get('match_date', '')
            ))
            if existing:
                logger.info(f"⏭️ DUPLICATE SKIPPED: {match_data['home_team']} vs {match_data['away_team']} | {sgp['description']}")
                return False
        except Exception as e:
            logger.warning(f"⚠️ Duplicate check failed: {e}")
        
        # PER-MATCH CAP: Max 2 SGPs per match
        MAX_SGP_PER_MATCH = 2
        try:
            match_count = db_helper.fetchone('''
                SELECT COUNT(*) FROM sgp_predictions 
                WHERE home_team = %s AND away_team = %s 
                AND DATE(match_date) = DATE(%s)
                AND (outcome IS NULL OR outcome = 'PENDING' OR outcome = '')
            ''', (
                match_data['home_team'],
                match_data['away_team'],
                match_data.get('match_date', '')
            ))
            if match_count and match_count[0] >= MAX_SGP_PER_MATCH:
                logger.info(f"⚠️ PER-MATCH CAP: {match_data['home_team']} vs {match_data['away_team']} already has {match_count[0]} SGPs (max {MAX_SGP_PER_MATCH})")
                return False
        except Exception as e:
            logger.warning(f"⚠️ Per-match cap check failed: {e}")
        
        # Get dynamic stake (1.2% of bankroll) - same as all other engines
        dynamic_stake = 173.0  # Fallback
        current_bankroll = 30000  # Fallback for kelly calculation
        bet_placed = True
        
        try:
            bankroll_mgr = get_bankroll_manager()
            dynamic_stake = bankroll_mgr.get_dynamic_stake()
            current_bankroll = bankroll_mgr.get_current_bankroll()
            
            # Check bankroll - determines if we actually place the bet
            can_bet, reason = bankroll_mgr.can_place_bet(dynamic_stake)
            if not can_bet:
                bet_placed = False
                logger.warning(f"⛔ BANKROLL LIMIT: {reason} - Prediction saved but NO BET placed")
        except Exception as e:
            logger.warning(f"⚠️ Bankroll check failed: {e} - Using fallback stake")
        
        # Format legs as text
        legs_text = " | ".join([
            f"{leg['market_type']} {leg['outcome']}" + 
            (f" ({leg['line']})" if leg.get('line') else "")
            for leg in sgp['legs']
        ])
        
        # Calculate Kelly stake with dynamic sizing from self-learner
        kelly_multiplier = self.self_learner.get_dynamic_kelly()
        kelly_fraction = (sgp['parlay_probability'] * sgp['bookmaker_odds'] - 1.0) / (sgp['bookmaker_odds'] - 1.0)
        kelly_stake = max(0, min(kelly_fraction * kelly_multiplier, 0.05)) * current_bankroll  # 5% max of current bankroll
        
        # Convert pricing metadata to JSON string
        import json
        pricing_metadata_str = json.dumps(sgp.get('pricing_metadata', {}))
        
        match_date_str = match_data.get('match_date', '')
        match_date_only = match_date_str[:10] if match_date_str else None
        
        result = db_helper.execute('''
            INSERT INTO sgp_predictions (
                timestamp, match_id, home_team, away_team, league, match_date, match_date_only, kickoff_time,
                legs, parlay_description, parlay_probability, fair_odds, bookmaker_odds, ev_percentage,
                stake, kelly_stake, model_version, simulations, correlation_method,
                pricing_mode, pricing_metadata, mode, bet_placed
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (home_team, away_team, parlay_description, match_date_only) DO NOTHING
        ''', (
            int(datetime.now().timestamp()),
            match_data.get('match_id', ''),
            match_data['home_team'],
            match_data['away_team'],
            match_data.get('league', ''),
            match_date_str,
            match_date_only,
            match_data.get('kickoff_time', ''),
            legs_text,
            sgp['description'],
            sgp['parlay_probability'],
            sgp['fair_odds'],
            sgp['bookmaker_odds'],
            sgp['ev_percentage'],
            dynamic_stake if bet_placed else 0,
            kelly_stake if bet_placed else 0,
            'v1.0_copula_poisson_live',
            200000,
            'copula',
            sgp.get('pricing_mode', 'simulated'),
            pricing_metadata_str,
            'PROD',
            bet_placed
        ))
        
        status = "✅ BET PLACED" if bet_placed else "📊 PREDICTION ONLY (no bet)"
        logger.info(f"{status}: {match_data['home_team']} vs {match_data['away_team']} | {sgp['description']} | EV: {sgp['ev_percentage']:.1f}%")
        
        if bet_placed:
            try:
                legs_text = " | ".join([
                    f"{leg['market_type']} {leg['outcome']}" + 
                    (f" ({leg['line']})" if leg.get('line') else "")
                    for leg in sgp['legs']
                ])
                send_bet_to_discord({
                    'league': match_data.get('league', 'SGP'),
                    'home_team': match_data['home_team'],
                    'away_team': match_data['away_team'],
                    'match_date': match_data.get('match_date', ''),
                    'product': 'SGP',
                    'selection': f"{sgp['description']}\nLegs: {legs_text}",
                    'odds': sgp['bookmaker_odds'],
                    'ev': sgp['ev_percentage'],
                    'stake': dynamic_stake
                }, product_type='SGP')
                logger.info("📱 Discord notification sent")
            except Exception as e:
                logger.warning(f"Discord notification failed: {e}")
        
        return bet_placed


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

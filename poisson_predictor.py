"""
Professional Poisson + Dixon-Coles Exact Score Predictor
Industry-standard approach used by top AI betting systems
"""
import numpy as np
from scipy.stats import poisson
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

class PoissonScorePredictor:
    """
    Predicts exact scores using Poisson distribution + Dixon-Coles corrections
    This is the industry standard approach for exact score betting
    """
    
    def __init__(self, rho: float = -0.13):
        """
        Initialize Poisson predictor
        
        Args:
            rho: Dixon-Coles correlation parameter for low-scoring matches
                 Typical values: -0.10 to -0.15
        """
        self.rho = rho
        self.max_goals = 10  # Maximum goals to calculate probabilities for (expanded for diverse scores)
        
    def dixon_coles_correction(self, home_goals: int, away_goals: int, 
                               lambda_home: float, lambda_away: float) -> float:
        """
        Apply Dixon-Coles correction factor for low-scoring matches
        
        Standard Poisson underestimates: 0-0, 1-0, 0-1, 1-1
        This correction improves accuracy by 3-5%
        
        Args:
            home_goals: Home team goals in scoreline
            away_goals: Away team goals in scoreline
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            
        Returns:
            Correction multiplier (typically 0.85 to 1.15)
        """
        if home_goals == 0 and away_goals == 0:
            return 1 - lambda_home * lambda_away * self.rho
        elif home_goals == 0 and away_goals == 1:
            return 1 + lambda_home * self.rho
        elif home_goals == 1 and away_goals == 0:
            return 1 + lambda_away * self.rho
        elif home_goals == 1 and away_goals == 1:
            return 1 - self.rho
        else:
            return 1.0
    
    def calculate_score_probability(self, home_goals: int, away_goals: int,
                                   lambda_home: float, lambda_away: float,
                                   use_dixon_coles: bool = True) -> float:
        """
        Calculate probability of exact score using Poisson distribution
        
        Args:
            home_goals: Predicted home goals
            away_goals: Predicted away goals
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            use_dixon_coles: Apply Dixon-Coles correction
            
        Returns:
            Probability of this exact score (0.0 to 1.0)
        """
        # Basic Poisson probability
        prob_home = poisson.pmf(home_goals, lambda_home)
        prob_away = poisson.pmf(away_goals, lambda_away)
        probability = prob_home * prob_away
        
        # Apply Dixon-Coles correction for low scores
        if use_dixon_coles:
            correction = self.dixon_coles_correction(
                home_goals, away_goals, lambda_home, lambda_away
            )
            probability *= correction
        
        return probability
    
    def generate_score_matrix(self, lambda_home: float, lambda_away: float,
                             use_dixon_coles: bool = True) -> np.ndarray:
        """
        Generate full probability matrix for all possible scores
        
        Args:
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            use_dixon_coles: Apply Dixon-Coles corrections
            
        Returns:
            2D numpy array [home_goals, away_goals] with probabilities
            Example: matrix[2,1] = probability of 2-1 score
        """
        matrix = np.zeros((self.max_goals, self.max_goals))
        
        for home_goals in range(self.max_goals):
            for away_goals in range(self.max_goals):
                matrix[home_goals, away_goals] = self.calculate_score_probability(
                    home_goals, away_goals, lambda_home, lambda_away, use_dixon_coles
                )
        
        # Normalize to ensure probabilities sum to ~1.0
        total_prob = matrix.sum()
        if total_prob > 0:
            matrix = matrix / total_prob
        
        return matrix
    
    def get_top_scores(self, lambda_home: float, lambda_away: float,
                      top_n: int = 10, min_probability: float = 0.02) -> List[Dict]:
        """
        Get most likely exact scores with probabilities
        
        Args:
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            top_n: Number of top scores to return
            min_probability: Minimum probability threshold (default 2%)
            
        Returns:
            List of dicts with score, probability, implied_odds
            Sorted by probability (highest first)
        """
        matrix = self.generate_score_matrix(lambda_home, lambda_away)
        
        results = []
        for home_goals in range(self.max_goals):
            for away_goals in range(self.max_goals):
                prob = matrix[home_goals, away_goals]
                
                if prob >= min_probability:
                    results.append({
                        'score': f'{home_goals}-{away_goals}',
                        'home_goals': home_goals,
                        'away_goals': away_goals,
                        'probability': prob,
                        'implied_odds': 1.0 / prob if prob > 0 else 999.0,
                        'percentage': prob * 100
                    })
        
        # Sort by probability (highest first)
        results.sort(key=lambda x: x['probability'], reverse=True)
        
        return results[:top_n]
    
    def get_most_likely_score(self, lambda_home: float, lambda_away: float) -> Tuple[str, float]:
        """
        Get single most likely exact score
        
        Args:
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            
        Returns:
            (score_string, probability)
            Example: ('2-1', 0.147)
        """
        matrix = self.generate_score_matrix(lambda_home, lambda_away)
        
        # Find position of maximum probability
        max_idx = np.unravel_index(matrix.argmax(), matrix.shape)
        home_goals, away_goals = max_idx
        
        score = f'{home_goals}-{away_goals}'
        probability = matrix[home_goals, away_goals]
        
        return score, probability
    
    def find_value_bets(self, lambda_home: float, lambda_away: float,
                       bookmaker_odds: Dict[str, float],
                       min_edge: float = 0.05) -> List[Dict]:
        """
        Find value bets where Poisson probability > bookmaker implied probability
        
        Args:
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            bookmaker_odds: Dict of {score: odds} from bookmaker
            min_edge: Minimum edge required (5% = 0.05)
            
        Returns:
            List of value bets with edge calculations
        """
        top_scores = self.get_top_scores(lambda_home, lambda_away, top_n=20)
        value_bets = []
        
        for score_info in top_scores:
            score = score_info['score']
            poisson_prob = score_info['probability']
            
            if score in bookmaker_odds:
                bookmaker_odd = bookmaker_odds[score]
                bookmaker_prob = 1.0 / bookmaker_odd
                
                # Edge = our probability - bookmaker probability
                edge = poisson_prob - bookmaker_prob
                edge_pct = edge / bookmaker_prob if bookmaker_prob > 0 else 0
                
                if edge_pct >= min_edge:
                    value_bets.append({
                        'score': score,
                        'poisson_probability': poisson_prob,
                        'poisson_odds': score_info['implied_odds'],
                        'bookmaker_odds': bookmaker_odd,
                        'bookmaker_probability': bookmaker_prob,
                        'edge': edge,
                        'edge_percentage': edge_pct * 100,
                        'expected_value': (poisson_prob * bookmaker_odd) - 1
                    })
        
        # Sort by edge (highest first)
        value_bets.sort(key=lambda x: x['edge_percentage'], reverse=True)
        
        return value_bets
    
    def calculate_market_probabilities(self, lambda_home: float, lambda_away: float) -> Dict:
        """
        Calculate probabilities for common betting markets using Poisson
        
        Args:
            lambda_home: Expected goals for home team
            lambda_away: Expected goals for away team
            
        Returns:
            Dict with probabilities for: 1X2, over/under, BTTS
        """
        matrix = self.generate_score_matrix(lambda_home, lambda_away)
        
        # 1X2 probabilities
        home_win_prob = sum(matrix[h, a] for h in range(self.max_goals) 
                           for a in range(self.max_goals) if h > a)
        draw_prob = sum(matrix[i, i] for i in range(self.max_goals))
        away_win_prob = sum(matrix[h, a] for h in range(self.max_goals) 
                           for a in range(self.max_goals) if a > h)
        
        # Over/Under 2.5 goals
        over_2_5_prob = sum(matrix[h, a] for h in range(self.max_goals) 
                           for a in range(self.max_goals) if h + a > 2.5)
        under_2_5_prob = 1.0 - over_2_5_prob
        
        # Both Teams to Score
        btts_yes_prob = sum(matrix[h, a] for h in range(1, self.max_goals) 
                           for a in range(1, self.max_goals))
        btts_no_prob = 1.0 - btts_yes_prob
        
        return {
            'home_win': home_win_prob,
            'draw': draw_prob,
            'away_win': away_win_prob,
            'over_2_5': over_2_5_prob,
            'under_2_5': under_2_5_prob,
            'btts_yes': btts_yes_prob,
            'btts_no': btts_no_prob
        }


if __name__ == '__main__':
    # Test the Poisson predictor
    print("="*80)
    print("POISSON + DIXON-COLES EXACT SCORE PREDICTOR TEST")
    print("="*80)
    
    predictor = PoissonScorePredictor()
    
    # Example: Home team expected 1.8 goals, Away team expected 1.2 goals
    lambda_home = 1.8
    lambda_away = 1.2
    
    print(f"\nExpected Goals: Home {lambda_home}, Away {lambda_away}")
    print("\nTop 10 Most Likely Scores:")
    print("-" * 80)
    
    top_scores = predictor.get_top_scores(lambda_home, lambda_away, top_n=10)
    
    for i, score_info in enumerate(top_scores, 1):
        print(f"{i:2d}. {score_info['score']:5s} | "
              f"Probability: {score_info['percentage']:5.2f}% | "
              f"Implied Odds: {score_info['implied_odds']:6.2f}x")
    
    print("\n" + "="*80)
    print("✅ Poisson predictor ready for integration")

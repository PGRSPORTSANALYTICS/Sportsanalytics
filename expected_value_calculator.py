#!/usr/bin/env python3
"""
Expected Value Calculator for Exact Score Predictions
Uses proper probability theory instead of arbitrary confidence scores
"""
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class ExpectedValueCalculator:
    """
    Calculate Expected Value and determine if a bet has mathematical edge
    
    Expected Value = (Probability × Odds) - 1
    Only bet when EV > 0.12 (12%+ edge required for long-term profit)
    """
    
    def __init__(self, min_edge: float = 0.12):
        """
        Args:
            min_edge: Minimum edge required to bet (default 12%)
        """
        self.min_edge = min_edge
        logger.info(f"✅ EV Calculator initialized (min edge: {min_edge*100}%)")
    
    def calculate_ev(
        self,
        predicted_score: str,
        odds: float,
        poisson_probs: Dict[str, float],
        neural_probs: Optional[Dict[str, float]] = None,
        similar_matches_probs: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        Calculate Expected Value using ensemble probability
        
        Args:
            predicted_score: The score being predicted (e.g., "2-1")
            odds: Decimal odds for this score
            poisson_probs: Probability distribution from Poisson model
            neural_probs: Probability distribution from neural network
            similar_matches_probs: Probability distribution from similar matches
        
        Returns:
            Dict with:
            - ensemble_probability: Combined probability from all models
            - expected_value: Mathematical edge (positive = good bet)
            - has_edge: True if EV > min_edge
            - model_agreement: True if all models agree on same top score
            - individual_probabilities: Breakdown by model
        """
        try:
            # Collect probabilities for the predicted score from each model
            probabilities = []
            model_breakdown = {}
            
            # 1. Poisson probability (always available)
            poisson_prob = poisson_probs.get(predicted_score, 0.0)
            probabilities.append(poisson_prob)
            model_breakdown['poisson'] = poisson_prob
            
            # 2. Neural network probability (if available)
            if neural_probs:
                neural_prob = neural_probs.get(predicted_score, 0.0)
                probabilities.append(neural_prob)
                model_breakdown['neural'] = neural_prob
            
            # 3. Similar matches probability (if available)
            if similar_matches_probs:
                sm_prob = similar_matches_probs.get(predicted_score, 0.0)
                probabilities.append(sm_prob)
                model_breakdown['similar_matches'] = sm_prob
            
            # Calculate ensemble probability (weighted average)
            # If only Poisson: 100% weight
            # If Poisson + Neural: 60% Poisson, 40% Neural
            # If all three: 40% Poisson, 30% Neural, 30% Similar Matches
            if len(probabilities) == 1:
                ensemble_prob = probabilities[0]
            elif len(probabilities) == 2:
                ensemble_prob = probabilities[0] * 0.6 + probabilities[1] * 0.4
            else:
                ensemble_prob = probabilities[0] * 0.4 + probabilities[1] * 0.3 + probabilities[2] * 0.3
            
            # Calculate Expected Value
            # EV = (Probability × Odds) - 1
            # EV > 0 = profitable bet
            # EV > 0.15 = 15%+ edge (our threshold)
            expected_value = (ensemble_prob * odds) - 1
            
            # Check if we have mathematical edge
            has_edge = expected_value >= self.min_edge
            
            # Check model agreement - do all models predict same score as top choice?
            model_agreement = self._check_model_agreement(
                predicted_score,
                poisson_probs,
                neural_probs,
                similar_matches_probs
            )
            
            # Calculate implied probability from odds (what bookmaker thinks)
            bookmaker_prob = 1 / odds
            prob_difference = ensemble_prob - bookmaker_prob
            
            result = {
                'ensemble_probability': round(ensemble_prob, 4),
                'expected_value': round(expected_value, 4),
                'ev_percentage': round(expected_value * 100, 2),
                'has_edge': has_edge,
                'model_agreement': model_agreement,
                'individual_probabilities': model_breakdown,
                'bookmaker_implied_prob': round(bookmaker_prob, 4),
                'probability_difference': round(prob_difference, 4),
                'models_used': len(probabilities)
            }
            
            if has_edge:
                logger.info(f"✅ {predicted_score} has {expected_value*100:.1f}% edge "
                           f"(Prob: {ensemble_prob*100:.1f}%, Odds: {odds}x, Agreement: {model_agreement})")
            else:
                logger.debug(f"❌ {predicted_score} no edge: {expected_value*100:.1f}% "
                            f"(need {self.min_edge*100}%+)")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error calculating EV: {e}")
            return {
                'ensemble_probability': 0.0,
                'expected_value': -1.0,
                'ev_percentage': -100.0,
                'has_edge': False,
                'model_agreement': False,
                'individual_probabilities': {},
                'bookmaker_implied_prob': 0.0,
                'probability_difference': 0.0,
                'models_used': 0
            }
    
    def _check_model_agreement(
        self,
        predicted_score: str,
        poisson_probs: Dict[str, float],
        neural_probs: Optional[Dict[str, float]],
        similar_matches_probs: Optional[Dict[str, float]]
    ) -> bool:
        """
        Check if all models agree that predicted_score is the top choice
        
        Returns True if all available models rank predicted_score as #1
        """
        try:
            # Get top score from each model
            poisson_top = max(poisson_probs, key=poisson_probs.get) if poisson_probs else None
            
            if neural_probs:
                neural_top = max(neural_probs, key=neural_probs.get)
                if neural_top != predicted_score:
                    return False
            
            if similar_matches_probs:
                sm_top = max(similar_matches_probs, key=similar_matches_probs.get)
                if sm_top != predicted_score:
                    return False
            
            # All models agree if predicted_score matches all top picks
            return poisson_top == predicted_score
            
        except Exception as e:
            logger.warning(f"Could not check model agreement: {e}")
            return False
    
    def calculate_kelly_bet_size(
        self,
        probability: float,
        odds: float,
        bankroll: float,
        kelly_fraction: float = 0.25
    ) -> float:
        """
        Calculate optimal bet size using Kelly Criterion
        
        Kelly % = (Probability × Odds - 1) / (Odds - 1)
        
        Args:
            probability: Your estimated probability of winning
            odds: Decimal odds
            bankroll: Current bankroll
            kelly_fraction: Fraction of Kelly to use (0.25 = quarter Kelly, safer)
        
        Returns:
            Optimal bet size in currency units
        """
        try:
            if probability <= 0 or odds <= 1:
                return 0.0
            
            # Kelly formula
            kelly_percentage = (probability * odds - 1) / (odds - 1)
            
            # Apply safety fraction (quarter Kelly is common)
            kelly_percentage *= kelly_fraction
            
            # Don't bet more than 5% of bankroll on single bet
            kelly_percentage = min(kelly_percentage, 0.05)
            
            # Don't bet if negative Kelly
            if kelly_percentage <= 0:
                return 0.0
            
            bet_size = bankroll * kelly_percentage
            
            return round(bet_size, 2)
            
        except Exception as e:
            logger.error(f"Error calculating Kelly bet size: {e}")
            return 0.0
    
    def get_all_scores_ev(
        self,
        odds_dict: Dict[str, float],
        poisson_probs: Dict[str, float],
        neural_probs: Optional[Dict[str, float]] = None,
        similar_matches_probs: Optional[Dict[str, float]] = None
    ) -> Dict[str, Dict]:
        """
        Calculate EV for all possible scores, return ranked by EV
        
        Returns:
            Dict of {score: ev_data} sorted by expected value
        """
        all_evs = {}
        
        for score, odds in odds_dict.items():
            ev_data = self.calculate_ev(
                predicted_score=score,
                odds=odds,
                poisson_probs=poisson_probs,
                neural_probs=neural_probs,
                similar_matches_probs=similar_matches_probs
            )
            all_evs[score] = ev_data
        
        # Sort by expected value (highest first)
        sorted_evs = dict(sorted(
            all_evs.items(),
            key=lambda x: x[1]['expected_value'],
            reverse=True
        ))
        
        return sorted_evs
    
    def find_best_bet(
        self,
        odds_dict: Dict[str, float],
        poisson_probs: Dict[str, float],
        neural_probs: Optional[Dict[str, float]] = None,
        similar_matches_probs: Optional[Dict[str, float]] = None,
        require_agreement: bool = True
    ) -> Optional[Tuple[str, Dict]]:
        """
        Find the best bet based on Expected Value
        
        Args:
            odds_dict: {score: odds} for all available scores
            poisson_probs: Poisson probability distribution
            neural_probs: Neural network probability distribution
            similar_matches_probs: Similar matches probability distribution
            require_agreement: Only bet if all models agree (recommended)
        
        Returns:
            Tuple of (score, ev_data) for best bet, or None if no edge found
        """
        all_evs = self.get_all_scores_ev(
            odds_dict, poisson_probs, neural_probs, similar_matches_probs
        )
        
        # Find first bet with edge that meets requirements
        for score, ev_data in all_evs.items():
            if ev_data['has_edge']:
                if require_agreement and not ev_data['model_agreement']:
                    logger.info(f"⚠️ {score} has edge but models disagree - skipping")
                    continue
                
                logger.info(f"🎯 BEST BET: {score} with {ev_data['ev_percentage']:.1f}% edge")
                return (score, ev_data)
        
        logger.info("❌ No bets found with sufficient edge")
        return None


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    calc = ExpectedValueCalculator(min_edge=0.15)
    
    # Example: Match with different model predictions
    poisson_probs = {
        '2-1': 0.18,
        '1-1': 0.15,
        '2-0': 0.12,
        '1-0': 0.11
    }
    
    neural_probs = {
        '2-1': 0.22,
        '1-1': 0.14,
        '2-0': 0.13,
        '1-0': 0.10
    }
    
    similar_probs = {
        '2-1': 0.25,
        '1-1': 0.20,
        '2-0': 0.10,
        '1-0': 0.08
    }
    
    odds_dict = {
        '2-1': 11.0,
        '1-1': 6.5,
        '2-0': 9.5,
        '1-0': 7.0
    }
    
    # Find best bet
    best = calc.find_best_bet(odds_dict, poisson_probs, neural_probs, similar_probs)
    
    if best:
        score, ev_data = best
        print(f"\n🎯 BET {score} @ {odds_dict[score]}x")
        print(f"   Probability: {ev_data['ensemble_probability']*100:.1f}%")
        print(f"   Expected Value: {ev_data['ev_percentage']:.1f}%")
        print(f"   Model Agreement: {ev_data['model_agreement']}")
        
        # Calculate bet size
        bet_size = calc.calculate_kelly_bet_size(
            ev_data['ensemble_probability'],
            odds_dict[score],
            bankroll=10000
        )
        print(f"   Suggested bet: {bet_size} SEK (Kelly criterion)")

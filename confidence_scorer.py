"""
Confidence Scoring System for Exact Score Predictions
Scores predictions 0-100 based on proven winning factors
"""

from typing import Dict, Optional
import logging
from scipy.stats import poisson
from similar_matches_finder import SimilarMatchesFinder
from similar_matches_tracker import SimilarMatchesTracker
from expected_value_calculator import ExpectedValueCalculator
from model_calibration_tracker import ModelCalibrationTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Calculate confidence scores for exact score predictions
    Target: Only bet on 85+ confidence predictions for 20-25% hit rate
    """
    
    def __init__(self):
        # LEARNING MODE (Nov 2025): Neutral scoring for ALL scores
        # Let AI learn from diverse data - remove historical bias
        # System will predict ANY score based on xG, odds, and probability
        self.SCORE_PATTERN_SCORES = {
            # Common low-scoring (neutral - let EV decide)
            '0-0': 0,
            '1-0': 0,
            '0-1': 0,
            '1-1': 0,
            '2-0': 0,
            '0-2': 0,
            '2-1': 0,
            '1-2': 0,
            '2-2': 0,
            # Medium-scoring (expanded coverage)
            '3-0': 0,
            '0-3': 0,
            '3-1': 0,
            '1-3': 0,
            '3-2': 0,
            '2-3': 0,
            '3-3': 0,
            # High-scoring (rare but possible)
            '4-0': 0,
            '0-4': 0,
            '4-1': 0,
            '1-4': 0,
            '4-2': 0,
            '2-4': 0,
            '4-3': 0,
            '3-4': 0,
            '4-4': 0,
        }
        
        # REAL DATA: 12-14x = 4 wins (BEST), 10-12x = 2 wins
        # AVOID: 9-11x (4% WR), 13-15x for 2-1 (0% WR)
        self.OPTIMAL_ODDS_MIN = 11.0
        self.OPTIMAL_ODDS_MAX = 14.0  # Extended to 14x based on 4 wins
        self.BEST_ODDS_MIN = 12.0
        self.BEST_ODDS_MAX = 14.0  # 12-14x has most wins
        
        # REAL DATA: Ligue 1 = 25% WR, Serie A/EPL = 0% WR
        self.PREMIUM_LEAGUES = {
            'soccer_france_ligue_one',  # 25% win rate - BEST
            'soccer_uefa_europa_league',  # 50% win rate
            'soccer_belgium_first_div',  # 100% win rate (small sample)
        }
        
        # AVOID these leagues - 0% win rate
        self.AVOID_LEAGUES = {
            'soccer_italy_serie_a',  # 0/16 = 0%
            'soccer_epl',  # 0/4 = 0%
        }
        
        # Initialize Similar Matches Finder (AIstats-style pattern matching)
        try:
            self.similar_finder = SimilarMatchesFinder()
            logger.info("✅ Similar Matches Finder integrated (AIstats technology)")
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize Similar Matches Finder: {e}")
            self.similar_finder = None
        
        # Initialize Impact Tracker to measure SM effectiveness
        try:
            self.sm_tracker = SimilarMatchesTracker()
            logger.info("✅ Similar Matches Impact Tracker initialized")
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize SM Tracker: {e}")
            self.sm_tracker = None
        
        # Initialize Expected Value Calculator (PROBABILITY-BASED FILTERING)
        try:
            self.ev_calculator = ExpectedValueCalculator(min_edge=0.08)  # Require 8%+ edge (learning mode for data collection)
            logger.info("✅ Expected Value Calculator initialized (8%+ edge required for data collection)")
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize EV Calculator: {e}")
            self.ev_calculator = None
        
        # Initialize Model Calibration Tracker
        try:
            self.calibration_tracker = ModelCalibrationTracker()
            logger.info("✅ Model Calibration Tracker initialized")
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize Calibration Tracker: {e}")
            self.calibration_tracker = None
        
        logger.info("✅ Confidence scorer initialized with EV-based filtering")
    
    def calculate_confidence(self, prediction: Dict) -> Dict:
        """
        Calculate 0-100 confidence score for a prediction
        
        Scoring breakdown:
        - Score pattern strength: 0-30 points (1-1 = best)
        - xG alignment bonus/penalty: -15 to +15 points
        - Odds proximity to sweet spot: 0-25 points (11-13x = best)
        - Data quality: 0-20 points (injuries, lineups, real xG)
        - League quality: 0-15 points (Top 6 leagues = best)
        - Model agreement: 0-10 points (value score, quality)
        
        Returns dict with confidence score and breakdown
        """
        score = 0
        breakdown = {}
        
        try:
            # 1. SCORE PATTERN STRENGTH (0-30 points)
            predicted_score = prediction.get('prediction', '')
            pattern_score = self.SCORE_PATTERN_SCORES.get(predicted_score, 5)
            
            # 1b. XG ALIGNMENT ADJUSTMENT (-15 to +15 points)
            analysis = prediction.get('analysis', {})
            xg_adjustment = self._score_xg_alignment(predicted_score, analysis)
            pattern_score += xg_adjustment
            pattern_score = max(0, min(45, pattern_score))  # Cap at 0-45
            
            score += pattern_score
            breakdown['score_pattern'] = pattern_score
            breakdown['xg_alignment'] = xg_adjustment
            
            # 2. ODDS PROXIMITY TO SWEET SPOT (0-25 points)
            odds = prediction.get('odds', 0)
            odds_score = self._score_odds(odds)
            score += odds_score
            breakdown['odds_proximity'] = odds_score
            
            # 3. DATA QUALITY (0-20 points)
            analysis = prediction.get('analysis', {})
            data_score = self._score_data_quality(analysis)
            score += data_score
            breakdown['data_quality'] = data_score
            
            # 4. LEAGUE QUALITY (0-20 points) - BASED ON REAL DATA
            league = prediction.get('sport_key', '')
            if league in self.AVOID_LEAGUES:
                league_score = -30  # SKIP Serie A and Premier League (0% win rate)
            elif league in self.PREMIUM_LEAGUES:
                league_score = 20  # Ligue 1, Europa, Belgian (25-100% win rates)
            else:
                league_score = 5  # Unknown leagues
            score += league_score
            breakdown['league_quality'] = league_score
            
            # 5. MODEL AGREEMENT (0-10 points)
            value_score = prediction.get('value_score', 0)
            quality = prediction.get('quality', 0)
            model_score = min(10, (value_score / 20) * 5 + (quality / 20) * 5)
            score += model_score
            breakdown['model_agreement'] = round(model_score, 1)
            
            # 6. SIMILAR MATCHES PATTERN (AIstats Technology) (-30 to +30 points)
            similar_score = 0
            if self.similar_finder:
                try:
                    home_form = analysis.get('home_form', {})
                    away_form = analysis.get('away_form', {})
                    home_xg = analysis.get('xg_prediction', {}).get('home_xg', None)
                    away_xg = analysis.get('xg_prediction', {}).get('away_xg', None)
                    
                    similar_result = self.similar_finder.find_similar_matches(
                        league=league,
                        odds=odds,
                        home_form=home_form,
                        away_form=away_form,
                        predicted_score=predicted_score,
                        home_xg=home_xg,
                        away_xg=away_xg
                    )
                    
                    similar_score = similar_result.get('confidence_adjustment', 0)
                    breakdown['similar_matches'] = similar_score
                    breakdown['similar_matches_count'] = similar_result.get('similar_matches_count', 0)
                    breakdown['pattern_strength'] = similar_result.get('pattern_strength', 0)
                    
                except Exception as e:
                    logger.warning(f"Similar matches analysis failed: {e}")
                    similar_score = 0
            
            score += similar_score
            
            # Final confidence score (0-100)
            confidence = round(min(100, max(0, score)), 1)
            
            # Determine confidence tier
            if confidence >= 90:
                tier = "ELITE"
            elif confidence >= 85:
                tier = "PREMIUM"
            elif confidence >= 75:
                tier = "GOOD"
            elif confidence >= 65:
                tier = "MODERATE"
            else:
                tier = "LOW"
            
            # REAL DATA: wins happen at conf 70-94, odds 11-14x, scores 2-0/2-1
            odds = prediction.get('odds', 0)
            is_good_odds = 11.0 <= odds <= 14.0 or (odds <= 16.0 and predicted_score == '2-0')
            is_good_score = predicted_score in ['2-0', '2-1']
            
            # ======================================================================
            # EXPECTED VALUE CALCULATION (PROBABILITY-BASED FILTERING)
            # ======================================================================
            ev_data = None
            has_mathematical_edge = False
            
            if self.ev_calculator:
                try:
                    # Extract probability distributions from analysis
                    ensemble_probs = analysis.get('ensemble_probs', {})
                    poisson_probs = analysis.get('poisson_probs', ensemble_probs)  # Fallback to ensemble
                    neural_probs = analysis.get('neural_probs', None)
                    
                    # If no probabilities in analysis, calculate from xG using Poisson
                    if not poisson_probs and analysis.get('home_xg') and analysis.get('away_xg'):
                        home_xg = analysis.get('home_xg', 1.5)
                        away_xg = analysis.get('away_xg', 1.5)
                        
                        poisson_probs = {}
                        for h in range(7):
                            for a in range(7):
                                score = f"{h}-{a}"
                                prob = poisson.pmf(h, home_xg) * poisson.pmf(a, away_xg)
                                poisson_probs[score] = prob
                        
                        # Normalize
                        total = sum(poisson_probs.values())
                        if total > 0:
                            poisson_probs = {k: v/total for k, v in poisson_probs.items()}
                        
                        logger.debug(f"Generated Poisson probs from xG: {home_xg:.2f} vs {away_xg:.2f}")
                    
                    # If probabilities available, calculate EV
                    if poisson_probs:
                        ev_data = self.ev_calculator.calculate_ev(
                            predicted_score=predicted_score,
                            odds=odds,
                            poisson_probs=poisson_probs,
                            neural_probs=neural_probs,
                            similar_matches_probs=None  # TODO: Add SM probabilities
                        )
                        
                        has_mathematical_edge = ev_data.get('has_edge', False)
                        breakdown['expected_value'] = ev_data.get('ev_percentage', 0)
                        breakdown['ensemble_probability'] = ev_data.get('ensemble_probability', 0) * 100
                        breakdown['model_agreement'] = ev_data.get('model_agreement', False)
                        
                        # Track calibration
                        if self.calibration_tracker:
                            try:
                                match_info = f"{prediction.get('home_team', 'Team A')} vs {prediction.get('away_team', 'Team B')}"
                                suggestion_id = prediction.get('suggestion_id', f"{match_info}_{predicted_score}")
                                
                                self.calibration_tracker.track_prediction(
                                    suggestion_id=suggestion_id,
                                    match_info=match_info,
                                    predicted_score=predicted_score,
                                    ensemble_prob=ev_data['ensemble_probability'],
                                    individual_probs=ev_data['individual_probabilities'],
                                    odds=odds,
                                    ev_data=ev_data
                                )
                            except Exception as e:
                                logger.debug(f"Calibration tracking failed: {e}")
                        
                        logger.info(f"💰 EV: {ev_data['ev_percentage']:+.1f}% "
                                   f"(Prob: {ev_data['ensemble_probability']*100:.1f}%, Edge: {has_mathematical_edge})")
                    
                except Exception as e:
                    logger.warning(f"EV calculation failed: {e}")
            
            # Track Similar Matches impact for analysis
            if self.sm_tracker and similar_score != 0:
                try:
                    base_confidence = confidence - similar_score
                    match_info = f"{prediction.get('home_team', 'Team A')} vs {prediction.get('away_team', 'Team B')}"
                    
                    sm_data = {
                        'matches_found': breakdown.get('similar_matches_count', 0),
                        'pattern_strength': breakdown.get('pattern_strength', 0),
                        'predicted_score_frequency': 0.0
                    }
                    
                    suggestion_id = prediction.get('suggestion_id', f"{match_info}_{predicted_score}")
                    
                    self.sm_tracker.track_prediction(
                        suggestion_id=suggestion_id,
                        match_info=match_info,
                        predicted_score=predicted_score,
                        base_confidence=int(base_confidence),
                        sm_adjustment=int(similar_score),
                        final_confidence=int(confidence),
                        sm_data=sm_data
                    )
                except Exception as e:
                    logger.debug(f"SM tracking failed: {e}")
            
            # ======================================================================
            # FINAL DECISION: USE EV IF AVAILABLE, FALLBACK TO CONFIDENCE
            # ======================================================================
            if ev_data:
                # PROBABILITY-BASED FILTERING (preferred)
                should_bet = has_mathematical_edge and ev_data.get('model_agreement', True)
                decision_reason = "EV-based" if should_bet else "No mathematical edge"
            else:
                # CONFIDENCE-BASED FILTERING (fallback)
                should_bet = confidence >= 70 and is_good_score and is_good_odds
                decision_reason = "Confidence-based (no EV data)"
            
            result = {
                'confidence': confidence,
                'tier': tier,
                'breakdown': breakdown,
                'should_bet': should_bet,
                'ev_data': ev_data,
                'has_mathematical_edge': has_mathematical_edge,
                'decision_method': decision_reason
            }
            
            logger.info(f"📊 Confidence: {confidence} ({tier}) - {prediction.get('home_team')} vs {prediction.get('away_team')} → {predicted_score}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error calculating confidence: {e}")
            return {
                'confidence': 50,
                'tier': 'UNKNOWN',
                'breakdown': {},
                'should_bet': False
            }
    
    def _score_odds(self, odds: float) -> float:
        """
        Score odds based on REAL winning data
        12-14x = 4 wins (BEST), 10-12x = 2 wins
        9-11x = 1 win (4% WR - BAD), <10x = 2 wins
        """
        if odds < 7.0 or odds > 16.0:
            return 0  # Outside acceptable range
        
        # BEST RANGE: 12-14x (4 wins)
        if self.BEST_ODDS_MIN <= odds <= self.BEST_ODDS_MAX:
            return 30  # PERFECT - Most wins here
        
        # GOOD RANGE: 10-12x (2 wins)
        if 10.0 <= odds < 12.0:
            return 22  # Good
        
        # ACCEPTABLE: 14-16x (Union Saint-Gilloise 2-0 won at 15.92x)
        if 14.0 < odds <= 16.0:
            return 15  # OK for 2-0 only
        
        # WEAK: <10x (2 wins but lower sample)
        if 7.0 <= odds < 10.0:
            return 10  # Weak
        
        return 0
    
    def _score_xg_alignment(self, predicted_score: str, analysis: Dict) -> float:
        """
        Adjust score based on how well prediction aligns with xG data
        Returns -15 to +15 adjustment
        """
        home_xg = analysis.get('home_xg', 0)
        away_xg = analysis.get('away_xg', 0)
        
        # If no xG data, neutral adjustment
        if home_xg == 0 or away_xg == 0:
            return 0
        
        adjustment = 0
        
        # HIGH SCORING MATCH (both xG > 2.0)
        if home_xg > 2.0 and away_xg > 2.0:
            if predicted_score == '2-1':
                adjustment = 15  # BEST - High scoring but one wins
            elif predicted_score == '2-0':
                adjustment = 10  # One team dominates
            elif predicted_score == '1-1':
                adjustment = -10  # 1-1 has 10% win rate - AVOID
            elif predicted_score == '1-0' or predicted_score == '0-1':
                adjustment = -15  # Contradicts xG!
            else:
                adjustment = 0
        
        # LOW SCORING MATCH (both xG < 1.5)
        elif home_xg < 1.5 and away_xg < 1.5:
            if predicted_score == '1-0' or predicted_score == '0-1':
                adjustment = 10  # Tight defensive game
            elif predicted_score == '0-0':
                adjustment = 5   # Possible
            elif predicted_score == '1-1':
                adjustment = 5   # Still possible
            elif predicted_score in ['2-1', '2-2']:
                adjustment = -10  # Unlikely with low xG
            else:
                adjustment = 0
        
        # HOME DOMINANT (home xG > 2.0, away xG < 1.5)
        elif home_xg > 2.0 and away_xg < 1.5:
            if predicted_score == '2-0':
                adjustment = 20  # PERFECT - Home dominant, 66.7% WR
            elif predicted_score == '2-1':
                adjustment = 15  # Good - Home wins with goals
            elif predicted_score == '1-0':
                adjustment = -10  # 8.7% WR - AVOID
            elif predicted_score == '1-1':
                adjustment = -15  # Home should dominate
            else:
                adjustment = 0
        
        # AWAY DOMINANT (away xG > 2.0, home xG < 1.5)
        elif away_xg > 2.0 and home_xg < 1.5:
            if predicted_score == '1-2' or predicted_score == '0-2':
                adjustment = 15  # Away wins with goals
            elif predicted_score == '0-1':
                adjustment = 10  # Away wins tight
            elif predicted_score == '1-1':
                adjustment = -10  # Away should dominate
            else:
                adjustment = 0
        
        # BALANCED ATTACK (both xG between 1.5-2.5)
        elif 1.5 <= home_xg <= 2.5 and 1.5 <= away_xg <= 2.5:
            if predicted_score == '2-1':
                adjustment = 15  # Best for balanced - 15% WR
            elif predicted_score == '2-0':
                adjustment = 10  # One edges it - 66.7% WR
            elif predicted_score == '1-1':
                adjustment = -10  # Only 10% WR - AVOID
            else:
                adjustment = 0
        
        # REFEREE IMPACT BONUS (MONEY FEATURE!)
        referee_style = analysis.get('referee_style', 'balanced')
        if referee_style:
            # Low scoring predictions favor strict refs
            if predicted_score in ['1-0', '0-1', '0-0']:
                if referee_style == 'strict':
                    adjustment += 8  # Strict ref = fewer goals = good match
                elif referee_style == 'lenient':
                    adjustment -= 5  # Lenient ref = more goals = bad match
            
            # High scoring predictions favor lenient refs
            elif predicted_score in ['2-1', '3-1', '2-2', '3-2']:
                if referee_style == 'lenient':
                    adjustment += 8  # Lenient ref = more goals = good match
                elif referee_style == 'strict':
                    adjustment -= 5  # Strict ref = fewer goals = bad match
        
        # REST DAYS / FATIGUE PENALTY (MONEY FEATURE!)
        home_rest = analysis.get('home_rest_days', 4)
        away_rest = analysis.get('away_rest_days', 4)
        
        # Fatigue penalty (<3 days rest)
        if home_rest < 3 or away_rest < 3:
            adjustment -= 10  # Fatigued team = unpredictable
        
        # Major rest difference (unfair advantage)
        elif abs(home_rest - away_rest) > 5:
            adjustment -= 8  # Uneven rest = unpredictable outcome
        
        return adjustment
    
    def _score_data_quality(self, analysis: Dict) -> float:
        """
        Score data quality based on what real data we have
        Max 30 points for complete data (ENHANCED with referee + rest days)
        """
        score = 0
        
        # Real xG data (8 points)
        xg_source = analysis.get('xg_source', 'estimated')
        if xg_source == 'api_football':
            score += 8
        elif xg_source == 'calculated':
            score += 5
        else:
            score += 2
        
        # Injury data checked (5 points)
        if analysis.get('injuries_checked', False):
            score += 5
        
        # Lineup data available (7 points)
        if analysis.get('lineups_confirmed', False):
            score += 7
        elif analysis.get('lineups_checked', False):
            score += 3
        
        # REFEREE DATA (MONEY FEATURE!) - 5 points
        if analysis.get('referee_style'):
            score += 5
        
        # REST DAYS DATA (MONEY FEATURE!) - 5 points
        if analysis.get('has_rest_data', False):
            score += 5
        
        return score
    
    def get_confidence_stats(self, predictions: list) -> Dict:
        """
        Get statistics about confidence distribution
        """
        if not predictions:
            return {}
        
        confidences = [p.get('confidence', 0) for p in predictions]
        
        return {
            'total_predictions': len(predictions),
            'avg_confidence': round(sum(confidences) / len(confidences), 1),
            'max_confidence': max(confidences),
            'min_confidence': min(confidences),
            'elite_count': len([c for c in confidences if c >= 90]),
            'premium_count': len([c for c in confidences if 85 <= c < 90]),
            'good_count': len([c for c in confidences if 75 <= c < 85]),
            'moderate_count': len([c for c in confidences if 65 <= c < 75]),
            'low_count': len([c for c in confidences if c < 65])
        }

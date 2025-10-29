"""
Confidence Scoring System for Exact Score Predictions
Scores predictions 0-100 based on proven winning factors
"""

from typing import Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Calculate confidence scores for exact score predictions
    Target: Only bet on 85+ confidence predictions for 20-25% hit rate
    """
    
    def __init__(self):
        # REAL DATA from 153 settled predictions (Oct 2025)
        # FOCUS ON WINNERS: 2-0 (66.7%), 2-1 (15%), 11-13x odds (23.1%)
        self.SCORE_PATTERN_SCORES = {
            '2-0': 50,  # 66.7% WR (2/3) - ONLY WINNER! PRIORITIZE THIS
            '2-1': 25,  # 15% WR (3/20) - ACCEPTABLE
            '1-1': -10,  # 10% WR (1/10) - SKIP
            '1-0': -10,   # 8.7% WR (2/23) - SKIP
            '0-1': -20,   # 4.5% WR (1/22) - NEVER BET
            '0-0': -10,   # Low scoring risky
        }
        
        # Odds sweet spot: 11-13x = 23.1% WR (6/26) - PROVEN!
        self.OPTIMAL_ODDS_MIN = 11.0
        self.OPTIMAL_ODDS_MAX = 13.0
        
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
        
        logger.info("✅ Confidence scorer initialized with proven patterns")
    
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
            
            # Final confidence score (0-100)
            confidence = round(min(100, score), 1)
            
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
            
            result = {
                'confidence': confidence,
                'tier': tier,
                'breakdown': breakdown,
                'should_bet': confidence >= 85 and predicted_score in ['2-0', '2-1']  # ONLY bet on proven winners
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
        Score odds based on proximity to proven sweet spot (11-13x)
        Perfect score: 25 points for odds in 11-13 range
        """
        if odds < 7.0 or odds > 14.0:
            return 0  # Outside acceptable range
        
        if self.OPTIMAL_ODDS_MIN <= odds <= self.OPTIMAL_ODDS_MAX:
            return 25  # Perfect sweet spot
        
        # Gradual falloff outside sweet spot
        if 9.0 <= odds < 11.0 or 13.0 < odds <= 14.0:
            return 18  # Acceptable range
        
        if 7.0 <= odds < 9.0:
            return 12  # Lower confidence
        
        return 5  # Edge of acceptable range
    
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
            if predicted_score == '1-1':
                adjustment = 15  # Perfect! Both will score
            elif predicted_score == '2-1':
                adjustment = 10  # Good, high scoring
            elif predicted_score == '2-2':
                adjustment = 8   # Logical but unproven
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
            if predicted_score == '2-1' or predicted_score == '2-0':
                adjustment = 15  # Home wins with goals
            elif predicted_score == '1-0':
                adjustment = 10  # Home wins tight
            elif predicted_score == '1-1':
                adjustment = -10  # Home should dominate
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
            if predicted_score == '1-1':
                adjustment = 10  # Evenly matched
            elif predicted_score == '2-1':
                adjustment = 5   # Slight edge
            else:
                adjustment = 0
        
        return adjustment
    
    def _score_data_quality(self, analysis: Dict) -> float:
        """
        Score data quality based on what real data we have
        Max 20 points for complete data
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

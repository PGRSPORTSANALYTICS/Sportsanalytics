#!/usr/bin/env python3
"""
Similar Matches Technology - Like AIstats uses
Finds historical matches with similar characteristics and analyzes actual outcomes
"""
import sqlite3
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SimilarMatchesFinder:
    """
    Find similar historical matches and analyze their actual scores
    This is the pattern-matching approach that AIstats uses
    """
    
    def __init__(self, db_path: str = 'data/real_football.db'):
        self.db_path = db_path
        logger.info("✅ Similar Matches Finder initialized")
    
    def find_similar_matches(
        self,
        league: str,
        odds: float,
        home_form: Dict,
        away_form: Dict,
        predicted_score: str,
        home_xg: float = None,
        away_xg: float = None,
        min_matches: int = 20,
        max_matches: int = 100
    ) -> Dict:
        """
        Find historical matches with similar characteristics
        
        Returns:
            Dict with:
            - similar_matches: List of matches
            - score_distribution: How often each score occurred
            - confidence_adjustment: Boost/penalty for predicted score
            - pattern_strength: How reliable this pattern is (0-100)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Calculate similarity criteria
            odds_min = odds * 0.8  # ±20% odds range
            odds_max = odds * 1.2
            
            home_ppg = home_form.get('ppg', 1.5)
            away_ppg = away_form.get('ppg', 1.5)
            home_gpg = home_form.get('goals_per_game', 1.5)
            away_gpg = away_form.get('goals_per_game', 1.0)
            
            # Find settled matches with similar characteristics
            query = """
            SELECT 
                home_team,
                away_team,
                selection,
                odds,
                outcome,
                actual_score,
                analysis,
                match_date
            FROM football_opportunities
            WHERE (market = 'exact_score' OR selection LIKE 'Exact Score:%')
            AND selection NOT LIKE 'PARLAY%'
            AND outcome IS NOT NULL
            AND outcome != ''
            AND outcome NOT IN ('unknown', 'void')
            AND odds BETWEEN ? AND ?
            ORDER BY timestamp DESC
            LIMIT ?
            """
            
            cursor.execute(query, (odds_min, odds_max, max_matches * 2))
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                logger.warning(f"No similar matches found for odds {odds:.1f}x")
                return self._empty_result()
            
            # Filter by form similarity
            similar_matches = []
            for row in rows:
                analysis_json = row[6]
                if not analysis_json:
                    continue
                
                try:
                    analysis = json.loads(analysis_json)
                    hist_home_form = analysis.get('home_form', {})
                    hist_away_form = analysis.get('away_form', {})
                    
                    hist_home_ppg = hist_home_form.get('ppg', 0)
                    hist_away_ppg = hist_away_form.get('ppg', 0)
                    
                    # Check form similarity (±30%)
                    if hist_home_ppg and hist_away_ppg:
                        home_diff = abs(hist_home_ppg - home_ppg) / max(home_ppg, 0.1)
                        away_diff = abs(hist_away_ppg - away_ppg) / max(away_ppg, 0.1)
                        
                        if home_diff < 0.4 and away_diff < 0.4:
                            similar_matches.append({
                                'match': f"{row[0]} vs {row[1]}",
                                'predicted_score': row[2].split(':')[-1].strip(),
                                'actual_score': row[5] if row[5] else 'unknown',
                                'odds': row[3],
                                'outcome': row[4],
                                'date': row[7]
                            })
                except:
                    continue
            
            if len(similar_matches) < min_matches:
                logger.warning(f"Only {len(similar_matches)} similar matches found (min {min_matches})")
                return self._empty_result()
            
            # Analyze score distribution
            score_distribution = self._analyze_score_distribution(similar_matches)
            
            # Calculate confidence adjustment for our predicted score
            adjustment = self._calculate_confidence_adjustment(
                predicted_score,
                score_distribution,
                similar_matches
            )
            
            # Calculate pattern strength
            pattern_strength = min(100, (len(similar_matches) / min_matches) * 50)
            
            logger.info(f"✅ Found {len(similar_matches)} similar matches, "
                       f"adjustment: {adjustment:+.0f}, pattern strength: {pattern_strength:.0f}")
            
            return {
                'similar_matches_count': len(similar_matches),
                'score_distribution': score_distribution,
                'confidence_adjustment': adjustment,
                'pattern_strength': pattern_strength,
                'sample_matches': similar_matches[:5]  # Top 5 for reference
            }
            
        except Exception as e:
            logger.error(f"Error finding similar matches: {e}")
            return self._empty_result()
    
    def _analyze_score_distribution(self, matches: List[Dict]) -> Dict[str, Dict]:
        """Analyze what scores actually occurred in similar matches"""
        distribution = {}
        total = len(matches)
        
        for match in matches:
            actual = match['actual_score']
            if actual and actual != 'unknown':
                if actual not in distribution:
                    distribution[actual] = {'count': 0, 'percentage': 0.0, 'wins': 0}
                distribution[actual]['count'] += 1
                
                # Check if prediction was correct
                if match['predicted_score'] == actual and match['outcome'] in ('win', 'won'):
                    distribution[actual]['wins'] += 1
        
        # Calculate percentages
        for score in distribution:
            distribution[score]['percentage'] = (distribution[score]['count'] / total) * 100
        
        # Sort by frequency
        distribution = dict(sorted(
            distribution.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        ))
        
        return distribution
    
    def _calculate_confidence_adjustment(
        self,
        predicted_score: str,
        score_distribution: Dict,
        similar_matches: List[Dict]
    ) -> float:
        """
        Calculate confidence adjustment based on historical patterns
        
        Returns: -30 to +30 adjustment
        """
        if not score_distribution:
            return 0.0
        
        total_matches = len(similar_matches)
        
        # Check if our predicted score occurred in similar matches
        if predicted_score in score_distribution:
            data = score_distribution[predicted_score]
            frequency = data['percentage']
            actual_wins = data['wins']
            
            # Strong pattern: Score occurred 15%+ of the time
            if frequency >= 15.0:
                adjustment = +25  # Major boost
            elif frequency >= 10.0:
                adjustment = +15  # Good boost
            elif frequency >= 5.0:
                adjustment = +10  # Small boost
            else:
                adjustment = 0  # Rare but occurred
            
            # Extra boost if predictions for this score actually won
            if actual_wins > 0:
                win_rate = (actual_wins / data['count']) * 100
                if win_rate >= 30:
                    adjustment += 5
            
            logger.info(f"Score {predicted_score}: {frequency:.1f}% frequency, "
                       f"{actual_wins} wins → +{adjustment}")
            
        else:
            # Score NEVER occurred in similar matches
            # Check total similar matches count
            if total_matches >= 30:
                adjustment = -20  # Strong penalty (never seen in 30+ matches)
            elif total_matches >= 20:
                adjustment = -15  # Medium penalty
            else:
                adjustment = -5   # Light penalty (small sample)
            
            logger.warning(f"Score {predicted_score} NEVER occurred in {total_matches} similar matches → {adjustment}")
        
        # Cap adjustment
        return max(-30, min(30, adjustment))
    
    def _empty_result(self) -> Dict:
        """Return empty result when no similar matches found"""
        return {
            'similar_matches_count': 0,
            'score_distribution': {},
            'confidence_adjustment': 0.0,
            'pattern_strength': 0.0,
            'sample_matches': []
        }
    
    def get_pattern_insights(self, league: str, odds_range: Tuple[float, float]) -> Dict:
        """
        Get general insights about score patterns for a league/odds range
        Useful for understanding what typically happens
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = """
            SELECT 
                actual_score,
                COUNT(*) as occurrences,
                SUM(CASE WHEN outcome IN ('win','won') THEN 1 ELSE 0 END) as wins
            FROM football_opportunities
            WHERE (market = 'exact_score' OR selection LIKE 'Exact Score:%')
            AND selection NOT LIKE 'PARLAY%'
            AND outcome IS NOT NULL
            AND outcome != ''
            AND odds BETWEEN ? AND ?
            AND actual_score IS NOT NULL
            AND actual_score != ''
            GROUP BY actual_score
            ORDER BY occurrences DESC
            LIMIT 10
            """
            
            cursor.execute(query, (odds_range[0], odds_range[1]))
            rows = cursor.fetchall()
            conn.close()
            
            insights = {}
            total = sum(row[1] for row in rows)
            
            for score, count, wins in rows:
                insights[score] = {
                    'occurrences': count,
                    'percentage': (count / total * 100) if total > 0 else 0,
                    'wins': wins,
                    'win_rate': (wins / count * 100) if count > 0 else 0
                }
            
            return insights
            
        except Exception as e:
            logger.error(f"Error getting pattern insights: {e}")
            return {}

if __name__ == "__main__":
    # Test the finder
    logging.basicConfig(level=logging.INFO)
    
    finder = SimilarMatchesFinder()
    
    # Test with sample data
    result = finder.find_similar_matches(
        league='soccer_epl',
        odds=11.0,
        home_form={'ppg': 2.0, 'goals_per_game': 1.8},
        away_form={'ppg': 1.2, 'goals_per_game': 1.0},
        predicted_score='2-1'
    )
    
    print("\n📊 SIMILAR MATCHES ANALYSIS:")
    print(f"Found: {result['similar_matches_count']} matches")
    print(f"Confidence adjustment: {result['confidence_adjustment']:+.0f}")
    print(f"Pattern strength: {result['pattern_strength']:.0f}%")
    print(f"\nScore distribution:")
    for score, data in result['score_distribution'].items():
        print(f"  {score}: {data['percentage']:.1f}% ({data['count']} times, {data['wins']} wins)")

"""
🧠 H2H INTELLIGENCE SYSTEM
Adaptive head-to-head analysis that recognizes when historical patterns should override general predictions.

Example: Wolfsburg vs Leverkusen (Last 5: 0-4-1 for Wolfsburg)
- System detects strong dominance pattern
- Increases H2H weight from 20% → 55%
- Overrides optimistic xG predictions with historical reality
"""

from typing import Dict, List, Tuple
import statistics


class H2HIntelligence:
    """
    🧠 Analyzes head-to-head patterns and calculates adaptive prediction weights
    """
    
    def __init__(self):
        # Base weights for different dominance levels
        self.EXTREME_DOMINANCE_WEIGHT = 0.60  # 5-0 or 4-0-1 in last 5
        self.STRONG_DOMINANCE_WEIGHT = 0.50   # 4-1 in last 5
        self.MODERATE_DOMINANCE_WEIGHT = 0.35 # 3-1-1 or 3-2 in last 5
        self.SLIGHT_EDGE_WEIGHT = 0.25        # 3 wins in last 5
        self.BALANCED_WEIGHT = 0.15           # 2-2-1 or similar
        self.MINIMAL_WEIGHT = 0.10            # No clear pattern
    
    def analyze_h2h_pattern(self, h2h_matches: List[Dict]) -> Dict:
        """
        🔍 Deep analysis of head-to-head patterns
        
        Args:
            h2h_matches: List of H2H matches, most recent first
            Format: [{'home_team': str, 'away_team': str, 'home_score': int, 'away_score': int, 'date': str}]
        
        Returns:
            {
                'dominance_level': str,  # 'extreme', 'strong', 'moderate', 'slight', 'balanced', 'none'
                'recommended_weight': float,  # 0.10 to 0.60
                'dominant_team': str or None,
                'pattern_confidence': float,  # 0-100
                'key_insights': List[str],
                'score_patterns': Dict,
                'recent_trend': str  # 'continuing', 'reversing', 'neutral'
            }
        """
        if not h2h_matches or len(h2h_matches) < 3:
            return {
                'dominance_level': 'none',
                'recommended_weight': self.MINIMAL_WEIGHT,
                'dominant_team': None,
                'pattern_confidence': 0,
                'key_insights': ['Insufficient H2H history'],
                'score_patterns': {},
                'recent_trend': 'neutral'
            }
        
        # Analyze last 5-10 matches
        recent_matches = h2h_matches[:5]
        extended_matches = h2h_matches[:10] if len(h2h_matches) >= 10 else h2h_matches
        
        # Get team names from first match
        team_a = recent_matches[0]['home_team']
        team_b = recent_matches[0]['away_team']
        
        # Count wins/draws for each team
        team_a_wins = 0
        team_b_wins = 0
        draws = 0
        team_a_goals = []
        team_b_goals = []
        
        for match in recent_matches:
            # Determine which team is which in this match
            if match['home_team'] == team_a:
                a_score = match['home_score']
                b_score = match['away_score']
            else:
                a_score = match['away_score']
                b_score = match['home_score']
            
            team_a_goals.append(a_score)
            team_b_goals.append(b_score)
            
            if a_score > b_score:
                team_a_wins += 1
            elif b_score > a_score:
                team_b_wins += 1
            else:
                draws += 1
        
        # Calculate goal differentials
        avg_team_a_goals = statistics.mean(team_a_goals)
        avg_team_b_goals = statistics.mean(team_b_goals)
        goal_diff = avg_team_a_goals - avg_team_b_goals
        
        # Determine dominance level
        insights = []
        
        # EXTREME DOMINANCE: 5-0, 4-0-1, or 5+ goal average differential
        if (team_a_wins >= 5 or team_b_wins >= 5) or \
           (team_a_wins >= 4 and team_b_wins == 0) or \
           (team_b_wins >= 4 and team_a_wins == 0) or \
           abs(goal_diff) >= 1.5:
            
            if team_a_wins > team_b_wins:
                dominant_team = team_a
                dominance_level = 'extreme'
                recommended_weight = self.EXTREME_DOMINANCE_WEIGHT
                insights.append(f"{team_a} has EXTREME dominance: {team_a_wins}-{draws}-{team_b_wins} in last 5")
            else:
                dominant_team = team_b
                dominance_level = 'extreme'
                recommended_weight = self.EXTREME_DOMINANCE_WEIGHT
                insights.append(f"{team_b} has EXTREME dominance: {team_b_wins}-{draws}-{team_a_wins} in last 5")
            
            pattern_confidence = 95
        
        # STRONG DOMINANCE: 4-1 or 4+ goal differential
        elif (team_a_wins >= 4 or team_b_wins >= 4) or abs(goal_diff) >= 1.2:
            if team_a_wins > team_b_wins:
                dominant_team = team_a
                dominance_level = 'strong'
                recommended_weight = self.STRONG_DOMINANCE_WEIGHT
                insights.append(f"{team_a} has STRONG dominance: {team_a_wins}-{draws}-{team_b_wins} in last 5")
            else:
                dominant_team = team_b
                dominance_level = 'strong'
                recommended_weight = self.STRONG_DOMINANCE_WEIGHT
                insights.append(f"{team_b} has STRONG dominance: {team_b_wins}-{draws}-{team_a_wins} in last 5")
            
            pattern_confidence = 85
        
        # MODERATE DOMINANCE: 3-1-1 or 3-2
        elif team_a_wins >= 3 or team_b_wins >= 3:
            if team_a_wins > team_b_wins:
                dominant_team = team_a
                dominance_level = 'moderate'
                recommended_weight = self.MODERATE_DOMINANCE_WEIGHT
                insights.append(f"{team_a} has MODERATE edge: {team_a_wins}-{draws}-{team_b_wins} in last 5")
            else:
                dominant_team = team_b
                dominance_level = 'moderate'
                recommended_weight = self.MODERATE_DOMINANCE_WEIGHT
                insights.append(f"{team_b} has MODERATE edge: {team_b_wins}-{draws}-{team_a_wins} in last 5")
            
            pattern_confidence = 70
        
        # SLIGHT EDGE: Slight advantage
        elif abs(team_a_wins - team_b_wins) >= 2:
            if team_a_wins > team_b_wins:
                dominant_team = team_a
                dominance_level = 'slight'
                recommended_weight = self.SLIGHT_EDGE_WEIGHT
                insights.append(f"{team_a} has slight edge: {team_a_wins}-{draws}-{team_b_wins}")
            else:
                dominant_team = team_b
                dominance_level = 'slight'
                recommended_weight = self.SLIGHT_EDGE_WEIGHT
                insights.append(f"{team_b} has slight edge: {team_b_wins}-{draws}-{team_a_wins}")
            
            pattern_confidence = 55
        
        # BALANCED: No clear advantage
        else:
            dominant_team = None
            dominance_level = 'balanced'
            recommended_weight = self.BALANCED_WEIGHT
            insights.append(f"Balanced H2H: {team_a_wins}-{draws}-{team_b_wins}")
            pattern_confidence = 40
        
        # Analyze score patterns
        score_patterns = self._analyze_score_patterns(team_a_goals, team_b_goals, insights)
        
        # Detect trend changes
        recent_trend = self._detect_trend(recent_matches, extended_matches, team_a, team_b)
        if recent_trend == 'reversing':
            insights.append("⚠️ RECENT TREND REVERSAL detected - reducing H2H weight")
            recommended_weight *= 0.7  # Reduce weight if trend is changing
            pattern_confidence *= 0.8
        
        # Check for "bogey team" status (one team consistently loses)
        if dominance_level in ['extreme', 'strong']:
            loser = team_b if team_a_wins > team_b_wins else team_a
            winner = team_a if team_a_wins > team_b_wins else team_b
            insights.append(f"🎯 BOGEY TEAM STATUS: {loser} struggles against {winner}")
        
        return {
            'dominance_level': dominance_level,
            'recommended_weight': recommended_weight,
            'dominant_team': dominant_team,
            'pattern_confidence': pattern_confidence,
            'key_insights': insights,
            'score_patterns': score_patterns,
            'recent_trend': recent_trend,
            'team_a': team_a,
            'team_b': team_b,
            'team_a_record': f"{team_a_wins}-{draws}-{team_b_wins}",
            'avg_goals': {
                team_a: round(avg_team_a_goals, 2),
                team_b: round(avg_team_b_goals, 2)
            }
        }
    
    def _analyze_score_patterns(self, team_a_goals: List[int], team_b_goals: List[int], 
                                insights: List[str]) -> Dict:
        """Analyze scoring patterns in H2H matches"""
        patterns = {}
        
        # Total goals per match
        total_goals_per_match = [a + b for a, b in zip(team_a_goals, team_b_goals)]
        avg_total_goals = statistics.mean(total_goals_per_match)
        
        patterns['avg_total_goals'] = round(avg_total_goals, 2)
        patterns['high_scoring'] = avg_total_goals > 3.0
        patterns['low_scoring'] = avg_total_goals < 2.0
        
        if avg_total_goals > 3.5:
            insights.append(f"🔥 High-scoring H2H: {avg_total_goals:.1f} avg goals per match")
        elif avg_total_goals < 1.8:
            insights.append(f"🔒 Low-scoring H2H: {avg_total_goals:.1f} avg goals per match")
        
        # Clean sheets
        team_a_clean_sheets = sum(1 for g in team_b_goals if g == 0)
        team_b_clean_sheets = sum(1 for g in team_a_goals if g == 0)
        
        patterns['frequent_clean_sheets'] = (team_a_clean_sheets + team_b_clean_sheets) >= 3
        
        # BTTS (Both Teams To Score)
        btts_count = sum(1 for a, b in zip(team_a_goals, team_b_goals) if a > 0 and b > 0)
        btts_rate = btts_count / len(team_a_goals)
        
        patterns['btts_rate'] = round(btts_rate, 2)
        patterns['btts_common'] = btts_rate > 0.6
        
        if btts_rate > 0.7:
            insights.append(f"⚽ Both teams score in {btts_rate*100:.0f}% of H2H matches")
        elif btts_rate < 0.3:
            insights.append(f"🛡️ Clean sheets common - BTTS only {btts_rate*100:.0f}% of time")
        
        return patterns
    
    def _detect_trend(self, recent: List[Dict], extended: List[Dict], 
                     team_a: str, team_b: str) -> str:
        """Detect if H2H trend is continuing, reversing, or neutral"""
        if len(extended) < 6:
            return 'neutral'
        
        # Compare last 3 vs previous 3-7
        last_3 = recent[:3]
        previous = extended[3:7]
        
        # Count wins in each period
        def count_wins(matches, team):
            wins = 0
            for m in matches:
                if m['home_team'] == team and m['home_score'] > m['away_score']:
                    wins += 1
                elif m['away_team'] == team and m['away_score'] > m['home_score']:
                    wins += 1
            return wins
        
        team_a_recent_wins = count_wins(last_3, team_a)
        team_a_previous_wins = count_wins(previous, team_a)
        
        team_b_recent_wins = count_wins(last_3, team_b)
        team_b_previous_wins = count_wins(previous, team_b)
        
        # Detect reversal (team that was winning before is now losing)
        if team_a_previous_wins >= 3 and team_a_recent_wins == 0:
            return 'reversing'
        if team_b_previous_wins >= 3 and team_b_recent_wins == 0:
            return 'reversing'
        
        # Otherwise trend is continuing
        return 'continuing'
    
    def get_adaptive_weights(self, h2h_analysis: Dict) -> Tuple[float, float]:
        """
        Calculate adaptive ensemble weights based on H2H analysis
        
        Returns:
            (weight_for_xg_neural, weight_for_h2h)
        """
        h2h_weight = h2h_analysis['recommended_weight']
        ensemble_weight = 1.0 - h2h_weight
        
        return (ensemble_weight, h2h_weight)
    
    def should_override_prediction(self, h2h_analysis: Dict, 
                                  predicted_winner: str, 
                                  current_team: str) -> bool:
        """
        Determine if H2H pattern is strong enough to override xG/neural prediction
        
        Example: xG says Wolfsburg might win, but H2H shows Leverkusen dominance
        """
        if h2h_analysis['dominance_level'] not in ['extreme', 'strong']:
            return False
        
        dominant_team = h2h_analysis['dominant_team']
        
        # If prediction contradicts strong H2H pattern, recommend override
        if predicted_winner != dominant_team and h2h_analysis['pattern_confidence'] >= 80:
            return True
        
        return False


def format_h2h_insights(h2h_analysis: Dict) -> str:
    """Format H2H insights for logging/display"""
    lines = []
    lines.append(f"\n🧠 H2H INTELLIGENCE ANALYSIS:")
    lines.append(f"   Dominance Level: {h2h_analysis['dominance_level'].upper()}")
    lines.append(f"   Recommended H2H Weight: {h2h_analysis['recommended_weight']*100:.0f}%")
    lines.append(f"   Pattern Confidence: {h2h_analysis['pattern_confidence']}%")
    
    if h2h_analysis['dominant_team']:
        lines.append(f"   Dominant Team: {h2h_analysis['dominant_team']}")
    
    lines.append(f"   Recent Trend: {h2h_analysis['recent_trend']}")
    
    lines.append(f"\n   Key Insights:")
    for insight in h2h_analysis['key_insights']:
        lines.append(f"      • {insight}")
    
    return '\n'.join(lines)

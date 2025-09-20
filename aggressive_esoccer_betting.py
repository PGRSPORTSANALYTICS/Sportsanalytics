"""
🔥 SUPER AGGRESSIVE E-SOCCER BETTING
Continuous action system for 4+ games always running
"""

import time
import random
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class AggressiveBet:
    match_id: str
    home: str
    away: str
    market: str
    odds: float
    stake: float
    edge: float
    reason: str

class AggressiveEsoccerBetting:
    """Super aggressive betting for continuous e-soccer action"""
    
    def __init__(self, bankroll: float = 1000.0):
        self.bankroll = bankroll
        
    def find_aggressive_opportunities(self, matches: List) -> List[AggressiveBet]:
        """Find betting opportunities with VERY low thresholds for continuous action"""
        
        # 🛑 EMERGENCY KILL-SWITCH - PREVENT REAL MONEY BETTING
        import os
        enable_real_bets = os.getenv('ENABLE_REAL_BETS', '0')
        if enable_real_bets != '1':
            print("🛑 EMERGENCY KILL-SWITCH ACTIVE - AGGRESSIVE BETTING DISABLED")
            print("💡 Set ENABLE_REAL_BETS=1 environment variable to enable real betting")
            return []
        
        opportunities = []
        
        for match in matches:
            # Skip if no odds or too late in match
            if not hasattr(match, 'odds') or not match.odds:
                continue
            
            if not hasattr(match, 'elapsed'):
                match.elapsed = 0
            
            # Bet early in match (0-6 minutes of 8 minute games)
            if match.elapsed > 6:
                continue
                
            print(f"🔍 EVALUATING MATCH: {match.home} vs {match.away} (Score: {getattr(match, 'score', '0-0')}, Elapsed: {match.elapsed:.1f}min)")
            
            # OVER markets - very aggressive
            for line in [2.5, 3.5, 4.5, 5.5, 6.5]:
                over_key = f"over_{str(line).replace('.', '_')}"
                if over_key in match.odds:
                    odds = match.odds[over_key]
                    
                    # Simple aggressive probability (e-soccer tends to be higher scoring)
                    base_prob = 0.55 if line <= 3.5 else 0.45  # Favor lower lines
                    
                    # Adjust based on current score and time
                    current_goals = getattr(match, 'home_goals', 0) + getattr(match, 'away_goals', 0)
                    time_factor = (8 - match.elapsed) / 8  # More time = higher prob
                    prob = min(0.85, base_prob + (current_goals * 0.1) + (time_factor * 0.15))
                    
                    # Calculate edge
                    implied_prob = 1 / odds
                    edge = (prob - implied_prob) / implied_prob
                    
                    # VERY LOW threshold for continuous action
                    if edge >= 0.02:  # Just 2% edge!
                        stake = max(15, min(100, self.bankroll * 0.05))
                        
                        bet = AggressiveBet(
                            match_id=match.match_id,
                            home=match.home,
                            away=match.away,
                            market=f"Over {line}",
                            odds=odds,
                            stake=stake,
                            edge=edge,
                            reason=f"AGGRESSIVE OVER: {line} @ {odds}"
                        )
                        
                        opportunities.append(bet)
                        print(f"🔥 FOUND BET: Over {line} @ {odds} - Edge: {edge:.1%}, Stake: ${stake}")
            
            # UNDER markets - also aggressive
            for line in [4.5, 5.5, 6.5]:
                under_key = f"under_{str(line).replace('.', '_')}"
                if under_key in match.odds:
                    odds = match.odds[under_key]
                    
                    # Conservative under probability
                    base_prob = 0.50 if line >= 5.5 else 0.40
                    
                    current_goals = getattr(match, 'home_goals', 0) + getattr(match, 'away_goals', 0)
                    if current_goals >= line - 1:  # Close to the line
                        prob = max(0.20, base_prob - 0.20)
                    else:
                        prob = min(0.75, base_prob + (8 - match.elapsed) / 20)
                    
                    implied_prob = 1 / odds
                    edge = (prob - implied_prob) / implied_prob
                    
                    if edge >= 0.02:  # 2% edge
                        stake = max(20, min(120, self.bankroll * 0.06))
                        
                        bet = AggressiveBet(
                            match_id=match.match_id,
                            home=match.home,
                            away=match.away,
                            market=f"Under {line}",
                            odds=odds,
                            stake=stake,
                            edge=edge,
                            reason=f"AGGRESSIVE UNDER: {line} @ {odds}"
                        )
                        
                        opportunities.append(bet)
                        print(f"⚡ FOUND BET: Under {line} @ {odds} - Edge: {edge:.1%}, Stake: ${stake}")
            
            # BTTS - very aggressive for H2H leagues
            if "H2H" in getattr(match, 'league', '') or "GG" in getattr(match, 'league', ''):
                if "btts_yes" in match.odds:
                    odds = match.odds["btts_yes"]
                    
                    # BTTS probability
                    home_goals = getattr(match, 'home_goals', 0)
                    away_goals = getattr(match, 'away_goals', 0)
                    
                    if home_goals > 0 and away_goals > 0:
                        prob = 0.95  # Already both scored
                    else:
                        remaining_time = 8 - match.elapsed
                        prob = min(0.80, 0.45 + (remaining_time / 8) * 0.25)
                    
                    implied_prob = 1 / odds
                    edge = (prob - implied_prob) / implied_prob
                    
                    if edge >= 0.01:  # Just 1% edge for BTTS!
                        stake = max(25, min(80, self.bankroll * 0.04))
                        
                        bet = AggressiveBet(
                            match_id=match.match_id,
                            home=match.home,
                            away=match.away,
                            market="BTTS Yes",
                            odds=odds,
                            stake=stake,
                            edge=edge,
                            reason=f"AGGRESSIVE BTTS: Yes @ {odds}"
                        )
                        
                        opportunities.append(bet)
                        print(f"🎯 FOUND BET: BTTS Yes @ {odds} - Edge: {edge:.1%}, Stake: ${stake}")
        
        if not opportunities:
            print("❌ NO BETS FOUND - system too conservative? Lowering thresholds...")
        else:
            print(f"🔥 Found {len(opportunities)} AGGRESSIVE betting opportunities")
            
        return opportunities

def test_aggressive_betting():
    """Test the aggressive betting system"""
    
    # Mock match for testing
    class MockMatch:
        def __init__(self):
            self.match_id = "test_match_1"
            self.home = "Arsenal (BOLEC)"
            self.away = "Liverpool (MASFJA)"
            self.league = "Esoccer H2H GG League - 8 mins play"
            self.elapsed = 2.0
            self.score = "0-0"
            self.home_goals = 0
            self.away_goals = 0
            self.odds = {
                'over_2_5': 1.75,
                'under_2_5': 2.10,
                'over_3_5': 2.20,
                'under_3_5': 1.65,
                'over_4_5': 3.20,
                'under_4_5': 1.35,
                'btts_yes': 1.80,
                'btts_no': 1.95
            }
    
    betting_system = AggressiveEsoccerBetting(bankroll=1000.0)
    matches = [MockMatch()]
    
    opportunities = betting_system.find_aggressive_opportunities(matches)
    
    print(f"\n🎯 AGGRESSIVE BETTING TEST RESULTS:")
    print(f"Opportunities found: {len(opportunities)}")
    
    for bet in opportunities:
        print(f"  {bet.market} @ {bet.odds} - Stake: ${bet.stake} - Edge: {bet.edge:.1%}")

if __name__ == "__main__":
    test_aggressive_betting()
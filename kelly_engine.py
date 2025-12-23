"""
Kelly Criterion Engine for Bankroll Management
Calculates optimal bet sizing based on edge and odds.
Uses fractional Kelly (default 25%) for risk management.
"""

import os
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class KellyFraction(Enum):
    FULL = 1.0
    HALF = 0.5
    QUARTER = 0.25
    EIGHTH = 0.125


@dataclass
class KellyResult:
    full_kelly: float
    recommended_stake: float
    fraction_used: float
    edge_percent: float
    implied_prob: float
    true_prob: float
    max_loss_percent: float
    expected_growth: float
    risk_rating: str


class KellyEngine:
    """
    Kelly Criterion calculator for optimal bet sizing.
    
    Formula: f* = (bp - q) / b
    Where:
        f* = fraction of bankroll to bet
        b = decimal odds - 1 (net odds)
        p = probability of winning
        q = probability of losing (1 - p)
    """
    
    DEFAULT_FRACTION = KellyFraction.QUARTER
    MIN_EDGE_PERCENT = 2.0
    MAX_STAKE_PERCENT = 5.0
    MIN_STAKE_PERCENT = 0.5
    
    def __init__(
        self,
        bankroll: float = 1000.0,
        fraction: KellyFraction = None,
        min_edge: float = None,
        max_stake: float = None
    ):
        self.bankroll = bankroll
        self.fraction = fraction or self.DEFAULT_FRACTION
        self.min_edge = min_edge or self.MIN_EDGE_PERCENT
        self.max_stake = max_stake or self.MAX_STAKE_PERCENT
        
    def calculate_true_probability(self, odds: float, edge_percent: float) -> float:
        """
        Calculate true probability from odds and edge.
        
        Args:
            odds: Decimal odds (e.g., 2.50)
            edge_percent: Edge as percentage (e.g., 8.0 for 8%)
            
        Returns:
            True probability as decimal (0-1)
        """
        implied_prob = 1 / odds
        edge_decimal = edge_percent / 100
        true_prob = implied_prob + edge_decimal
        return min(max(true_prob, 0.01), 0.99)
    
    def calculate_kelly(
        self,
        odds: float,
        edge_percent: float,
        use_fraction: bool = True
    ) -> KellyResult:
        """
        Calculate Kelly stake for a bet.
        
        Args:
            odds: Decimal odds (e.g., 2.50)
            edge_percent: Edge as percentage (e.g., 8.0 for 8%)
            use_fraction: Whether to apply fractional Kelly
            
        Returns:
            KellyResult with stake recommendations
        """
        implied_prob = 1 / odds
        true_prob = self.calculate_true_probability(odds, edge_percent)
        
        b = odds - 1
        p = true_prob
        q = 1 - p
        
        full_kelly = (b * p - q) / b
        
        full_kelly = max(full_kelly, 0)
        
        fraction_value = self.fraction.value if use_fraction else 1.0
        recommended = full_kelly * fraction_value
        
        recommended = min(recommended, self.max_stake / 100)
        
        if edge_percent < self.min_edge:
            recommended = 0.0
            
        if recommended > 0 and recommended < (self.MIN_STAKE_PERCENT / 100):
            recommended = self.MIN_STAKE_PERCENT / 100
            
        expected_growth = p * recommended * b - q * recommended
        
        risk_rating = self._get_risk_rating(full_kelly * 100, edge_percent)
        
        return KellyResult(
            full_kelly=round(full_kelly * 100, 2),
            recommended_stake=round(recommended * 100, 2),
            fraction_used=fraction_value,
            edge_percent=edge_percent,
            implied_prob=round(implied_prob * 100, 2),
            true_prob=round(true_prob * 100, 2),
            max_loss_percent=round(recommended * 100, 2),
            expected_growth=round(expected_growth * 100, 4),
            risk_rating=risk_rating
        )
    
    def _get_risk_rating(self, full_kelly_percent: float, edge_percent: float) -> str:
        """Determine risk level of the bet."""
        if edge_percent >= 10 and full_kelly_percent <= 10:
            return "LOW"
        elif edge_percent >= 6 and full_kelly_percent <= 15:
            return "MEDIUM"
        elif edge_percent >= 4 and full_kelly_percent <= 20:
            return "ELEVATED"
        else:
            return "HIGH"
    
    def calculate_stake_amount(
        self,
        odds: float,
        edge_percent: float,
        bankroll: float = None
    ) -> Dict:
        """
        Calculate actual stake amount in currency.
        
        Args:
            odds: Decimal odds
            edge_percent: Edge percentage
            bankroll: Optional bankroll override
            
        Returns:
            Dict with stake amount and potential return
        """
        br = bankroll or self.bankroll
        result = self.calculate_kelly(odds, edge_percent)
        
        stake_amount = br * (result.recommended_stake / 100)
        potential_return = stake_amount * odds
        potential_profit = potential_return - stake_amount
        
        return {
            "stake_percent": result.recommended_stake,
            "stake_amount": round(stake_amount, 2),
            "potential_return": round(potential_return, 2),
            "potential_profit": round(potential_profit, 2),
            "risk_rating": result.risk_rating,
            "edge_percent": edge_percent,
            "full_kelly_percent": result.full_kelly
        }
    
    def batch_calculate(self, bets: list) -> list:
        """
        Calculate Kelly stakes for multiple bets.
        
        Args:
            bets: List of dicts with 'odds' and 'edge_percent' keys
            
        Returns:
            List of KellyResult objects
        """
        results = []
        for bet in bets:
            odds = bet.get('odds', 2.0)
            edge = bet.get('edge_percent', 0)
            result = self.calculate_kelly(odds, edge)
            results.append({
                **bet,
                "kelly": result
            })
        return results
    
    def get_portfolio_allocation(
        self,
        bets: list,
        max_total_exposure: float = 20.0
    ) -> Dict:
        """
        Calculate portfolio allocation for multiple concurrent bets.
        Scales down if total exposure exceeds maximum.
        
        Args:
            bets: List of bet dicts
            max_total_exposure: Max % of bankroll at risk
            
        Returns:
            Adjusted allocations and summary
        """
        results = self.batch_calculate(bets)
        
        total_stake = sum(r['kelly'].recommended_stake for r in results)
        
        scale_factor = 1.0
        if total_stake > max_total_exposure:
            scale_factor = max_total_exposure / total_stake
            
        allocations = []
        for r in results:
            adjusted_stake = r['kelly'].recommended_stake * scale_factor
            allocations.append({
                "match": r.get('match', 'Unknown'),
                "selection": r.get('selection', 'Unknown'),
                "odds": r.get('odds'),
                "edge_percent": r.get('edge_percent'),
                "original_stake_percent": r['kelly'].recommended_stake,
                "adjusted_stake_percent": round(adjusted_stake, 2),
                "risk_rating": r['kelly'].risk_rating
            })
            
        return {
            "allocations": allocations,
            "total_exposure_percent": round(min(total_stake, max_total_exposure), 2),
            "scale_factor": round(scale_factor, 2),
            "bet_count": len(bets)
        }


def get_kelly_recommendation(odds: float, edge_percent: float) -> Dict:
    """
    Quick helper to get Kelly recommendation for a single bet.
    Uses default 25% Kelly fraction.
    """
    engine = KellyEngine()
    result = engine.calculate_kelly(odds, edge_percent)
    
    return {
        "recommended_stake_percent": result.recommended_stake,
        "full_kelly_percent": result.full_kelly,
        "risk_rating": result.risk_rating,
        "edge_percent": edge_percent,
        "true_probability": result.true_prob,
        "should_bet": result.recommended_stake > 0
    }


if __name__ == "__main__":
    engine = KellyEngine(bankroll=1000)
    
    print("=== Kelly Engine Test ===\n")
    
    test_bets = [
        {"odds": 2.10, "edge_percent": 8.0, "match": "Liverpool vs Arsenal", "selection": "Over 2.5"},
        {"odds": 1.85, "edge_percent": 6.5, "match": "Man City vs Chelsea", "selection": "Home Win"},
        {"odds": 3.20, "edge_percent": 12.0, "match": "Barca vs Real", "selection": "BTTS Yes"},
    ]
    
    for bet in test_bets:
        result = engine.calculate_kelly(bet['odds'], bet['edge_percent'])
        stake = engine.calculate_stake_amount(bet['odds'], bet['edge_percent'])
        
        print(f"{bet['match']} - {bet['selection']}")
        print(f"  Odds: {bet['odds']} | Edge: {bet['edge_percent']}%")
        print(f"  Full Kelly: {result.full_kelly}% | Recommended (1/4): {result.recommended_stake}%")
        print(f"  Stake: ${stake['stake_amount']} | Potential Profit: ${stake['potential_profit']}")
        print(f"  Risk: {result.risk_rating}\n")
    
    print("=== Portfolio Allocation ===\n")
    portfolio = engine.get_portfolio_allocation(test_bets, max_total_exposure=15.0)
    print(f"Total Exposure: {portfolio['total_exposure_percent']}%")
    print(f"Scale Factor: {portfolio['scale_factor']}")
    for alloc in portfolio['allocations']:
        print(f"  {alloc['match']}: {alloc['adjusted_stake_percent']}% ({alloc['risk_rating']})")

"""
Kelly Criterion Engine for Bankroll Management
Calculates optimal bet sizing based on edge and odds.
Uses fractional Kelly (default 25%) for risk management.
Supports singles, parlays, and risk profiles.
"""

from __future__ import annotations

import math
import logging
from typing import Dict, Optional, Literal, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

RiskProfile = Literal["conservative", "balanced", "aggressive"]
MarketType = Literal["single", "parlay", "sgp"]


class KellyFraction(Enum):
    FULL = 1.0
    HALF = 0.5
    QUARTER = 0.25
    EIGHTH = 0.125


@dataclass
class StakeConfig:
    unit_value_sek: float = 100.0
    
    frac_kelly_map: Dict[RiskProfile, float] = None
    
    max_bankroll_fraction_per_bet: float = 0.02
    max_units_per_bet: float = 2.0
    min_edge: float = 0.0
    
    parlay_max_units: float = 0.50
    parlay_min_edge: float = 0.01
    parlay_unit_scale: float = 0.35
    
    min_odds: float = 1.01
    max_odds: float = 1000.0

    def __post_init__(self):
        if self.frac_kelly_map is None:
            self.frac_kelly_map = {
                "conservative": 0.10,
                "balanced": 0.25,
                "aggressive": 0.50,
            }


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


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def implied_prob_from_decimal_odds(odds: float) -> float:
    if odds <= 1.0:
        return 1.0
    return 1.0 / odds


def kelly_fraction_calc(decimal_odds: float, p_win: float) -> float:
    """
    Kelly fraction for a single bet with decimal odds.
    f* = (b*p - q)/b  where b = odds-1, q = 1-p
    """
    if decimal_odds <= 1.0:
        return 0.0
    b = decimal_odds - 1.0
    p = clamp(p_win, 0.0, 1.0)
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


def edge(decimal_odds: float, p_win: float) -> float:
    """
    Expected value per 1 unit staked:
      EV = p*(odds) - 1
    Example: odds=2.0, p=0.55 => EV = 0.10 (+10%)
    """
    p = clamp(p_win, 0.0, 1.0)
    return (p * decimal_odds) - 1.0


def money_to_units(amount: float, cfg: StakeConfig) -> float:
    return amount / cfg.unit_value_sek


def units_to_money(units: float, cfg: StakeConfig) -> float:
    return units * cfg.unit_value_sek


def parlay_stake_units(
    bankroll: float,
    decimal_odds: float,
    ev: float,
    cfg: StakeConfig,
) -> float:
    """
    Safe parlay/SGP sizing:
    - Require small positive edge
    - Scale by edge and tame by odds (higher odds => smaller)
    """
    if bankroll <= 0:
        return 0.0
    if ev < cfg.parlay_min_edge:
        return 0.0

    odds_tame = 1.0 / math.sqrt(max(decimal_odds, 1.01))
    raw_units = cfg.parlay_unit_scale * (ev * 100.0) * odds_tame / 10.0
    raw_units = max(0.0, raw_units)

    cap_by_bankroll = cfg.max_bankroll_fraction_per_bet * bankroll
    cap_by_bankroll_units = money_to_units(cap_by_bankroll, cfg)

    units = min(raw_units, cfg.parlay_max_units, cfg.max_units_per_bet, cap_by_bankroll_units)
    return round(units, 2)


def suggest_stake(
    bankroll: float,
    odds_decimal: float,
    model_prob: float,
    market_type: MarketType = "single",
    risk_profile: RiskProfile = "balanced",
    cfg: Optional[StakeConfig] = None,
) -> Dict[str, Any]:
    """
    Main staking function with risk profiles and market type support.
    
    Args:
        bankroll: Bankroll amount
        odds_decimal: Decimal odds
        model_prob: Model probability (0..1)
        market_type: 'single', 'parlay', or 'sgp'
        risk_profile: 'conservative', 'balanced', or 'aggressive'
        cfg: Optional StakeConfig
        
    Returns:
        Dict with stake_units, stake_amount, and metadata
    """
    cfg = cfg or StakeConfig()

    if bankroll <= 0:
        return {"ok": False, "reason": "bankroll_must_be_positive", "stake_units": 0.0, "stake_amount": 0.0}

    if not (cfg.min_odds <= odds_decimal <= cfg.max_odds):
        return {
            "ok": False,
            "reason": "odds_out_of_range",
            "stake_units": 0.0,
            "stake_amount": 0.0,
            "odds": odds_decimal,
        }

    p = clamp(model_prob, 0.0, 1.0)
    ev = edge(odds_decimal, p)
    imp = implied_prob_from_decimal_odds(odds_decimal)

    if ev <= cfg.min_edge:
        return {
            "ok": False,
            "reason": "no_positive_edge",
            "stake_units": 0.0,
            "stake_amount": 0.0,
            "ev": round(ev, 4),
            "model_prob": round(p, 4),
            "implied_prob": round(imp, 4),
        }

    if market_type in ("parlay", "sgp"):
        units = parlay_stake_units(bankroll, odds_decimal, ev, cfg)
        amount = round(units_to_money(units, cfg), 2)
        ok = units > 0
        return {
            "ok": ok,
            "reason": "parlay_sizing" if ok else "parlay_edge_too_low",
            "market_type": market_type,
            "risk_profile": risk_profile,
            "stake_units": units,
            "stake_amount": amount,
            "ev": round(ev, 4),
            "model_prob": round(p, 4),
            "implied_prob": round(imp, 4),
            "unit_value": cfg.unit_value_sek,
            "caps": {
                "max_units_per_bet": cfg.max_units_per_bet,
                "max_bankroll_fraction_per_bet": cfg.max_bankroll_fraction_per_bet,
                "parlay_max_units": cfg.parlay_max_units,
            },
        }

    base_kelly = kelly_fraction_calc(odds_decimal, p)
    frac = cfg.frac_kelly_map.get(risk_profile, cfg.frac_kelly_map["balanced"])
    f = base_kelly * frac

    raw_amount = bankroll * f
    raw_units = money_to_units(raw_amount, cfg)

    cap_by_bankroll = cfg.max_bankroll_fraction_per_bet * bankroll
    cap_by_bankroll_units = money_to_units(cap_by_bankroll, cfg)

    units = min(raw_units, cfg.max_units_per_bet, cap_by_bankroll_units)
    units = round(max(0.0, units), 2)
    amount = round(units_to_money(units, cfg), 2)

    ok = units > 0
    return {
        "ok": ok,
        "reason": "kelly_sizing" if ok else "kelly_zero",
        "market_type": market_type,
        "risk_profile": risk_profile,
        "stake_units": units,
        "stake_amount": amount,
        "kelly_full_fraction": round(base_kelly, 6),
        "kelly_fractional_fraction": round(f, 6),
        "ev": round(ev, 4),
        "model_prob": round(p, 4),
        "implied_prob": round(imp, 4),
        "unit_value": cfg.unit_value_sek,
        "caps": {
            "max_units_per_bet": cfg.max_units_per_bet,
            "max_bankroll_fraction_per_bet": cfg.max_bankroll_fraction_per_bet,
        },
    }


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
        max_stake: float = None,
        unit_value: float = 100.0
    ):
        self.bankroll = bankroll
        self.fraction = fraction or self.DEFAULT_FRACTION
        self.min_edge = min_edge or self.MIN_EDGE_PERCENT
        self.max_stake = max_stake or self.MAX_STAKE_PERCENT
        self.unit_value = unit_value
        self.config = StakeConfig(unit_value_sek=unit_value)
        
    def calculate_true_probability(self, odds: float, edge_percent: float) -> float:
        """
        Calculate true probability from odds and edge.
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
        """
        br = bankroll or self.bankroll
        result = self.calculate_kelly(odds, edge_percent)
        
        stake_amount = br * (result.recommended_stake / 100)
        potential_return = stake_amount * odds
        potential_profit = potential_return - stake_amount
        
        return {
            "stake_percent": result.recommended_stake,
            "stake_amount": round(stake_amount, 2),
            "stake_units": round(stake_amount / self.unit_value, 2),
            "potential_return": round(potential_return, 2),
            "potential_profit": round(potential_profit, 2),
            "risk_rating": result.risk_rating,
            "edge_percent": edge_percent,
            "full_kelly_percent": result.full_kelly
        }
    
    def suggest_stake(
        self,
        odds: float,
        model_prob: float,
        market_type: MarketType = "single",
        risk_profile: RiskProfile = "balanced"
    ) -> Dict[str, Any]:
        """
        Suggest stake using risk profiles and market types.
        """
        return suggest_stake(
            bankroll=self.bankroll,
            odds_decimal=odds,
            model_prob=model_prob,
            market_type=market_type,
            risk_profile=risk_profile,
            cfg=self.config
        )
    
    def batch_calculate(self, bets: list) -> list:
        """
        Calculate Kelly stakes for multiple bets.
        """
        results = []
        for bet in bets:
            odds = bet.get('odds', 2.0)
            edge_pct = bet.get('edge_percent', 0)
            result = self.calculate_kelly(odds, edge_pct)
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
                "adjusted_units": round((adjusted_stake / 100) * self.bankroll / self.unit_value, 2),
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
    engine = KellyEngine(bankroll=10000, unit_value=100)
    
    print("=== Kelly Engine Test ===\n")
    
    test_bets = [
        {"odds": 2.10, "edge_percent": 8.0, "match": "Liverpool vs Arsenal", "selection": "Over 2.5"},
        {"odds": 1.85, "edge_percent": 6.5, "match": "Man City vs Chelsea", "selection": "Home Win"},
        {"odds": 3.20, "edge_percent": 12.0, "match": "Barca vs Real", "selection": "BTTS Yes"},
    ]
    
    print("--- Single Bets (Edge-Based) ---\n")
    for bet in test_bets:
        result = engine.calculate_kelly(bet['odds'], bet['edge_percent'])
        stake = engine.calculate_stake_amount(bet['odds'], bet['edge_percent'])
        
        print(f"{bet['match']} - {bet['selection']}")
        print(f"  Odds: {bet['odds']} | Edge: {bet['edge_percent']}%")
        print(f"  Full Kelly: {result.full_kelly}% | Recommended (1/4): {result.recommended_stake}%")
        print(f"  Stake: {stake['stake_units']}u ({stake['stake_amount']} SEK)")
        print(f"  Risk: {result.risk_rating}\n")
    
    print("--- Risk Profiles (Prob-Based) ---\n")
    for profile in ["conservative", "balanced", "aggressive"]:
        result = engine.suggest_stake(
            odds=2.10,
            model_prob=0.55,
            market_type="single",
            risk_profile=profile
        )
        print(f"{profile.upper()}: {result['stake_units']}u | EV: {result['ev']*100:.1f}%")
    
    print("\n--- Parlay Sizing ---\n")
    parlay_result = engine.suggest_stake(
        odds=5.50,
        model_prob=0.22,
        market_type="parlay",
        risk_profile="balanced"
    )
    print(f"Parlay @ 5.50 odds: {parlay_result['stake_units']}u")
    print(f"EV: {parlay_result['ev']*100:.1f}%")
    
    print("\n=== Portfolio Allocation ===\n")
    portfolio = engine.get_portfolio_allocation(test_bets, max_total_exposure=15.0)
    print(f"Total Exposure: {portfolio['total_exposure_percent']}%")
    print(f"Scale Factor: {portfolio['scale_factor']}")
    for alloc in portfolio['allocations']:
        print(f"  {alloc['match']}: {alloc['adjusted_units']}u ({alloc['risk_rating']})")

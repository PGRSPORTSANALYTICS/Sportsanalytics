#!/usr/bin/env python3
"""
EV Controller - Stability & Verification Mode
==============================================
Central EV controls for Live Learning Mode.

ACTIVE CONTROLS (Dec 25, 2025):
- Hard EV cap: 25%
- EV deflator: 0.4x
- Blocked EV bands: 50-100%
- SGP: DISABLED
- CORNERS cap: 30% of daily portfolio
"""

import logging
from typing import Tuple, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

HARD_EV_CAP = 0.25
EV_DEFLATOR = 0.4
BLOCKED_EV_BANDS = [(0.50, 1.00)]

MARKET_EXPOSURE_CAPS = {
    "CORNERS": 0.30,
    "SGP": 0.00,
    "VALUE_SINGLE": 0.35,
    "CARDS": 0.20,
    "BASKET_SINGLE": 0.15,
    "TOTALS": 0.25,
    "BTTS": 0.20,
    "EXACT_SCORE": 0.00,
}

DISABLED_MARKETS = ["SGP", "EXACT_SCORE"]


@dataclass
class EVResult:
    """Result of EV control processing."""
    raw_ev: float
    deflated_ev: float
    capped_ev: float
    is_blocked: bool
    block_reason: Optional[str]
    is_approved: bool


def apply_ev_controls(raw_ev: float) -> EVResult:
    """
    Apply all EV controls from stability mode.
    
    Steps:
    1. Check if raw EV falls in blocked band (50-100%)
    2. Apply 0.4x deflator
    3. Cap at 25%
    
    Returns: EVResult with all processing details
    """
    for low, high in BLOCKED_EV_BANDS:
        if low <= raw_ev <= high:
            return EVResult(
                raw_ev=raw_ev,
                deflated_ev=0,
                capped_ev=0,
                is_blocked=True,
                block_reason=f"Raw EV {raw_ev:.1%} in blocked band {low:.0%}-{high:.0%}",
                is_approved=False
            )
    
    deflated = raw_ev * EV_DEFLATOR
    
    capped = min(deflated, HARD_EV_CAP)
    
    is_approved = capped >= 0.02
    
    return EVResult(
        raw_ev=raw_ev,
        deflated_ev=deflated,
        capped_ev=capped,
        is_blocked=False,
        block_reason=None,
        is_approved=is_approved
    )


def get_adjusted_ev(raw_ev: float) -> float:
    """
    Simple helper to get the final adjusted EV value.
    Returns 0 if blocked, otherwise deflated and capped value.
    """
    result = apply_ev_controls(raw_ev)
    if result.is_blocked:
        return 0
    return result.capped_ev


def is_ev_blocked(raw_ev: float) -> Tuple[bool, Optional[str]]:
    """
    Check if an EV value should be blocked.
    Returns: (is_blocked, reason)
    """
    for low, high in BLOCKED_EV_BANDS:
        if low <= raw_ev <= high:
            return True, f"EV {raw_ev:.1%} in blocked band {low:.0%}-{high:.0%}"
    return False, None


def is_market_disabled(market: str) -> bool:
    """Check if a market is disabled."""
    return market.upper() in DISABLED_MARKETS


def get_market_cap(market: str) -> float:
    """Get exposure cap for a market."""
    return MARKET_EXPOSURE_CAPS.get(market.upper(), 0.25)


def check_market_exposure(
    market: str, 
    current_counts: Dict[str, int]
) -> Tuple[bool, Optional[str]]:
    """
    Check if adding another bet to this market would exceed the cap.
    
    Args:
        market: The market to check
        current_counts: Dict of current bet counts by market
    
    Returns: (is_allowed, reason)
    """
    if is_market_disabled(market):
        return False, f"{market} is disabled in stability mode"
    
    total = sum(current_counts.values())
    if total == 0:
        return True, None
    
    market_upper = market.upper()
    current_market_count = current_counts.get(market_upper, 0)
    cap = get_market_cap(market_upper)
    
    current_pct = current_market_count / total if total > 0 else 0
    
    if current_pct >= cap:
        return False, f"{market} at cap ({current_pct:.0%} >= {cap:.0%})"
    
    return True, None


def enforce_market_caps(
    candidates: list,
    market_key: str = "product"
) -> list:
    """
    Filter candidates to enforce market exposure caps.
    
    Args:
        candidates: List of bet candidates (dicts or objects)
        market_key: Key/attr to get market type from candidate
    
    Returns: Filtered list respecting caps
    """
    market_counts: Dict[str, int] = {}
    approved = []
    
    for c in candidates:
        if isinstance(c, dict):
            market = c.get(market_key, "").upper()
        else:
            market = getattr(c, market_key, "").upper()
        
        if is_market_disabled(market):
            continue
        
        is_allowed, reason = check_market_exposure(market, market_counts)
        
        if is_allowed:
            approved.append(c)
            market_counts[market] = market_counts.get(market, 0) + 1
        else:
            logger.debug(f"Blocked by market cap: {reason}")
    
    return approved


def get_stability_status() -> Dict:
    """Get current stability mode status."""
    return {
        "mode": "STABILITY_VERIFICATION",
        "hard_ev_cap": f"{HARD_EV_CAP:.0%}",
        "ev_deflator": f"{EV_DEFLATOR:.0%}",
        "blocked_bands": [f"{l:.0%}-{h:.0%}" for l, h in BLOCKED_EV_BANDS],
        "disabled_markets": DISABLED_MARKETS,
        "market_caps": {k: f"{v:.0%}" for k, v in MARKET_EXPOSURE_CAPS.items()},
        "objective": "Verify edge via CLV, not P/L",
    }


if __name__ == "__main__":
    print("=" * 60)
    print("EV CONTROLLER - STABILITY & VERIFICATION MODE")
    print("=" * 60)
    
    status = get_stability_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 60)
    print("EV CONTROL TESTS")
    print("=" * 60)
    
    test_evs = [0.05, 0.15, 0.30, 0.55, 0.80, 1.20]
    for ev in test_evs:
        result = apply_ev_controls(ev)
        if result.is_blocked:
            print(f"  Raw EV {ev:.0%} → BLOCKED ({result.block_reason})")
        else:
            print(f"  Raw EV {ev:.0%} → Deflated {result.deflated_ev:.1%} → Capped {result.capped_ev:.1%} → Approved: {result.is_approved}")
    
    print("\n" + "=" * 60)
    print("MARKET CAP TESTS")
    print("=" * 60)
    
    current = {"CORNERS": 5, "VALUE_SINGLE": 3, "CARDS": 2}
    print(f"  Current counts: {current}")
    
    for market in ["CORNERS", "SGP", "CARDS", "BTTS"]:
        allowed, reason = check_market_exposure(market, current)
        status = "✅ ALLOWED" if allowed else f"❌ BLOCKED: {reason}"
        print(f"  {market}: {status}")

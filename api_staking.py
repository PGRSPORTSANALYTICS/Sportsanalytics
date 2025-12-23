from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Literal, Optional

from kelly_engine import suggest_stake, StakeConfig

router = APIRouter()

RiskProfile = Literal["conservative", "balanced", "aggressive"]
MarketType = Literal["single", "parlay", "sgp"]


class StakeRequest(BaseModel):
    bankroll: float = Field(..., gt=0)
    odds_decimal: float = Field(..., gt=1.0)
    model_prob: float = Field(..., ge=0.0, le=1.0)
    market_type: MarketType = "single"
    risk_profile: RiskProfile = "balanced"

    max_units_per_bet: Optional[float] = None
    max_bankroll_fraction_per_bet: Optional[float] = None


@router.post("/api/stake/suggest")
def stake_suggest(req: StakeRequest):
    cfg = StakeConfig()

    if req.max_units_per_bet is not None:
        cfg.max_units_per_bet = float(req.max_units_per_bet)

    if req.max_bankroll_fraction_per_bet is not None:
        cfg.max_bankroll_fraction_per_bet = float(req.max_bankroll_fraction_per_bet)

    return suggest_stake(
        bankroll=req.bankroll,
        odds_decimal=req.odds_decimal,
        model_prob=req.model_prob,
        market_type=req.market_type,
        risk_profile=req.risk_profile,
        cfg=cfg,
    )

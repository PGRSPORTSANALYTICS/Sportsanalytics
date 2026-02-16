"""
PGR Sports Analytics - Pydantic Data Contracts
================================================
Defines all module boundary contracts for the 6-module system.
Decimal odds only. Football first, scalable.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class MarketType(str, Enum):
    MONEYLINE = "moneyline"
    TOTALS = "totals"
    ASIAN_HANDICAP = "asian_handicap"
    BTTS = "btts"
    DOUBLE_CHANCE = "double_chance"
    CORNERS = "corners"
    CARDS = "cards"
    DRAW_NO_BET = "draw_no_bet"


class BetStatus(str, Enum):
    CANDIDATE = "candidate"
    PUBLISHED = "published"
    PLACED = "placed"
    SETTLED = "settled"
    VOIDED = "voided"


class GatingStatus(str, Enum):
    PRODUCTION = "PRODUCTION"
    LEARNING_ONLY = "LEARNING_ONLY"
    DISABLED = "DISABLED"


class ConfidenceBadge(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class OddsSnapshot(BaseModel):
    event_id: str
    sport: str = "football"
    league_id: str
    league_name: str = ""
    start_time_utc: datetime
    home_team: str
    away_team: str
    market_type: str
    selection: str
    line: Optional[float] = None
    bookmaker: str
    odds_decimal: float
    timestamp_utc: datetime
    fixture_id: Optional[int] = None


class MarketState(BaseModel):
    event_id: str
    market_type: str
    selection: str
    line: Optional[float] = None
    best_price: float
    best_bookmaker: str
    market_avg: float
    market_median: float
    dispersion: float
    book_count: int
    prices: Dict[str, float] = Field(default_factory=dict)
    timestamp_utc: datetime
    is_stale: bool = False
    stale_books: List[str] = Field(default_factory=list)


class FairOddsResult(BaseModel):
    event_id: str
    market_type: str
    selection: str
    line: Optional[float] = None
    model_prob: float
    fair_odds: float
    calibrated_prob: Optional[float] = None
    calibration_source: str = "global"
    confidence: float = 0.5
    confidence_badge: str = "MEDIUM"
    uncertainty: float = 0.0
    data_quality: float = 1.0
    league_sample_size: int = 0
    market_dispersion: float = 0.0
    volatility: float = 0.0


class EdgeResult(BaseModel):
    event_id: str
    home_team: str
    away_team: str
    league_id: str
    league_name: str = ""
    market_type: str
    selection: str
    line: Optional[float] = None
    book_odds: float
    bookmaker: str
    fair_odds: float
    model_prob: float
    edge_pct: float
    ev_pct: float
    expected_clv_pct: Optional[float] = None
    confidence: float = 0.5
    confidence_badge: str = "MEDIUM"
    sharpness_tags: List[str] = Field(default_factory=list)
    timing_bucket: str = ""
    start_time_utc: datetime = Field(default_factory=datetime.utcnow)
    volatility: float = 0.0
    gating_status: str = "LEARNING_ONLY"


class CLVRecord(BaseModel):
    bet_id: int
    event_id: str
    market_type: str
    selection: str
    bet_odds: float
    closing_odds: float
    clv_pct: float
    close_window_minutes: int = 5
    close_timestamp_utc: Optional[datetime] = None


class BetLifecycle(BaseModel):
    id: Optional[int] = None
    event_id: str
    home_team: str
    away_team: str
    league_id: str
    league_name: str = ""
    sport: str = "football"
    market_type: str
    selection: str
    line: Optional[float] = None
    odds_decimal: float
    bookmaker: str = ""
    fair_odds: float
    model_prob: float
    edge_pct: float
    ev_pct: float
    confidence: float = 0.5
    confidence_badge: str = "MEDIUM"
    status: str = "candidate"
    gating_status: str = "LEARNING_ONLY"
    stake_units: float = 1.0
    result: Optional[str] = None
    profit_loss: Optional[float] = None
    closing_odds: Optional[float] = None
    clv_pct: Optional[float] = None
    start_time_utc: Optional[datetime] = None
    published_at: Optional[datetime] = None
    placed_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    model_version: str = "pgr_v2"
    request_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: str = ""


class AuditEntry(BaseModel):
    bet_lifecycle_id: int
    action: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: datetime = Field(default_factory=datetime.utcnow)
    source: str = "system"


class EligibilityMap(BaseModel):
    sport: str = "football"
    league_id: str
    market_type: str
    status: str = "LEARNING_ONLY"
    total_bets: int = 0
    roi_pct: float = 0.0
    clv_avg: float = 0.0
    stability_score: float = 0.0
    drawdown_pct: float = 0.0
    recency_bonus: float = 0.0
    composite_score: float = 0.0
    can_publish: bool = False
    can_display_dashboard: bool = False


class BetCardDisplay(BaseModel):
    id: int
    event_id: str
    sport: str = "football"
    league: str
    home_team: str
    away_team: str
    market_type: str
    selection: str
    line: Optional[float] = None
    odds_decimal: float
    fair_odds: float
    edge_pct: float
    ev_pct: float
    expected_clv_pct: Optional[float] = None
    actual_clv_pct: Optional[float] = None
    confidence: float
    confidence_badge: str
    status: str
    gating_status: str
    result: Optional[str] = None
    profit_loss: Optional[float] = None
    bookmaker: str = ""
    start_time_utc: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    prices: Dict[str, float] = Field(default_factory=dict)


class WeeklyReport(BaseModel):
    week_start: str
    week_end: str
    total_bets: int = 0
    settled: int = 0
    wins: int = 0
    losses: int = 0
    hit_rate: float = 0.0
    roi_pct: float = 0.0
    profit_units: float = 0.0
    avg_clv: float = 0.0
    avg_ev: float = 0.0
    avg_odds: float = 0.0
    best_market: str = ""
    worst_market: str = ""
    top_league: str = ""
    promotions: int = 0
    demotions: int = 0
    by_market: Dict[str, Any] = Field(default_factory=dict)
    by_league: Dict[str, Any] = Field(default_factory=dict)

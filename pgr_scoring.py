"""
PGR Score — Weighted candidate ranking for three-layer signal routing.

Formula (weights must sum to 1.0):
  EV             40%
  Confidence     25%
  CLV Potential  15%
  Market Softness 10%
  League Tier    10%

Each component is normalised to 0–100 before weighting.
"""

from typing import Optional
from league_config import get_league_by_odds_key

EV_WEIGHT = 0.40
CONFIDENCE_WEIGHT = 0.25
CLV_WEIGHT = 0.15
MARKET_SOFTNESS_WEIGHT = 0.10
LEAGUE_TIER_WEIGHT = 0.10

MARKET_WEIGHTS: dict[str, float] = {
    "CORNERS": 1.20,
    "CARDS": 1.15,
    "FT_OVER_2_5": 1.10,
    "FT_OVER_1_5": 1.10,
    "FT_OVER_3_5": 1.05,
    "FT_OVER_4_5": 1.05,
    "BTTS_YES": 1.05,
    "BTTS_NO": 1.00,
    "HOME_WIN": 0.95,
    "AWAY_WIN": 0.95,
    "DRAW": 0.90,
    "DOUBLE_CHANCE_1X": 0.95,
    "DOUBLE_CHANCE_X2": 0.95,
    "DOUBLE_CHANCE_12": 0.95,
    "DNB_HOME": 0.95,
    "DNB_AWAY": 0.95,
}
MARKET_WEIGHT_DEFAULT = 1.00

LEAGUE_TIER_LETTER_MAP: dict[int, str] = {
    1: "A",
    2: "B",
    3: "C",
}
LEAGUE_TIER_SCORE_MAP: dict[str, float] = {
    "A": 100.0,
    "B": 65.0,
    "C": 30.0,
}


def _normalize_league_key(league_key: str) -> str:
    """Normalize a league key before lookup.

    Strips leading/trailing whitespace and lowercases so that variant
    forms of the same key (e.g. 'Soccer_epl' vs 'soccer_epl') resolve
    to the same lookup.  Returns empty string for None/falsy input so
    callers get a predictable B-tier fallback rather than a KeyError.
    """
    if not league_key:
        return ""
    return str(league_key).strip().lower()


def get_league_tier(league_key: str) -> str:
    """Return letter tier A/B/C for a league odds_api_key. Falls back to B."""
    normalized = _normalize_league_key(league_key)
    if not normalized:
        return "B"
    league = get_league_by_odds_key(normalized)
    if league is None:
        # Try stripping a common sport prefix ("soccer_") that some callers include
        for prefix in ("soccer_", "football_"):
            if normalized.startswith(prefix):
                league = get_league_by_odds_key(normalized[len(prefix):])
                if league is not None:
                    break
    if league is None:
        return "B"
    numeric = league.tier
    return LEAGUE_TIER_LETTER_MAP.get(numeric, "B")


def get_market_weight(market_key: str) -> float:
    """Return market weight multiplier (affects score, not hard exclusion)."""
    upper = market_key.upper()
    if "CORNER" in upper:
        return MARKET_WEIGHTS.get("CORNERS", MARKET_WEIGHT_DEFAULT)
    if "CARD" in upper:
        return MARKET_WEIGHTS.get("CARDS", MARKET_WEIGHT_DEFAULT)
    return MARKET_WEIGHTS.get(market_key.upper(), MARKET_WEIGHT_DEFAULT)


def compute_pgr_score(
    ev: float,
    confidence: float,
    market_key: str,
    league_key: str,
    clv_potential: Optional[float] = None,
    market_softness: Optional[float] = None,
) -> float:
    """
    Compute weighted PGR Score (0–100+).

    Args:
        ev: Expected value as a decimal (e.g. 0.15 = 15%).
        confidence: Model probability (0–1).
        market_key: Market identifier (e.g. 'FT_OVER_2_5').
        league_key: Odds API key (e.g. 'soccer_epl').
        clv_potential: Optional CLV estimate (decimal).  Falls back to EV proxy.
        market_softness: Optional market softness 0–1. Falls back to market weight proxy.

    Returns:
        Float PGR score.  Multiply by market weight before storing.
    """
    ev_score = min(max(ev * 200, 0.0), 100.0)

    conf_score = min(max(confidence * 100, 0.0), 100.0)

    if clv_potential is not None:
        clv_score = min(max(clv_potential * 200, 0.0), 100.0)
    else:
        clv_score = ev_score

    if market_softness is not None:
        soft_score = min(max(market_softness * 100, 0.0), 100.0)
    else:
        mw = get_market_weight(market_key)
        soft_score = min(max((mw - 0.85) / 0.40 * 100, 0.0), 100.0)

    tier = get_league_tier(league_key)
    tier_score = LEAGUE_TIER_SCORE_MAP.get(tier, 65.0)

    raw_score = (
        ev_score * EV_WEIGHT
        + conf_score * CONFIDENCE_WEIGHT
        + clv_score * CLV_WEIGHT
        + soft_score * MARKET_SOFTNESS_WEIGHT
        + tier_score * LEAGUE_TIER_WEIGHT
    )

    market_multiplier = get_market_weight(market_key)
    final_score = round(raw_score * market_multiplier, 4)
    return final_score


PRO_PICK_MIN_EV = 0.25
PRO_PICK_MIN_CONFIDENCE = 0.70
PRO_PICK_MIN_ODDS = 1.75
PRO_PICK_MAX_ODDS = 2.30
PRO_PICK_MAX_PER_DAY = 5
PRO_PICK_MIN_PGR_SCORE = 55.0   # Minimum weighted PGR score required for PRO PICK

VALUE_OPP_MIN_EV = 0.10  # Lowered from 12% Apr 2026 — more volume needed for data collection
VALUE_OPP_MIN_CONFIDENCE = 0.60
VALUE_OPP_MIN_ODDS = 1.60
VALUE_OPP_MAX_ODDS = 4.00
VALUE_OPP_MIN_PGR_SCORE = 35.0  # Minimum weighted PGR score required for VALUE OPP

WATCHLIST_MIN_EV = 0.03  # SIGNAL flatten Apr 17 2026: lowered from 7% to expose all 3%+ ACTIVE/DEGRADED signals (Developing Edge band)
WATCHLIST_MIN_CONFIDENCE = 0.50
WATCHLIST_MIN_PGR_SCORE = 20.0  # Minimum PGR score for WATCHLIST (below this → REJECTED)

CANDIDATE_MIN_EV = 0.07
CANDIDATE_MIN_ODDS = 1.60
CANDIDATE_MAX_ODDS = 4.00

REJECTION_REASONS = [
    "rejected_low_ev",
    "rejected_low_confidence",
    "rejected_low_odds",
    "rejected_high_odds",
    "rejected_market_type",
    "rejected_league_tier",        # Reserved: Tier C is downgraded (not rejected) by current policy
    "rejected_score_below_threshold",
    "routed_value_opp_from_pro_cap",  # PRO candidate downgraded due to daily cap / unique-match rule
]


def route_candidate(
    ev: float,
    confidence: float,
    odds: float,
    market_key: str,
    league_key: str,
    pgr_score: float,
    pro_picks_today: int = 0,
) -> tuple[str, str]:
    """
    Route a candidate into PRO_PICK, VALUE_OPP, WATCHLIST, or REJECTED.

    The weighted PGR score gates each tier — candidates that satisfy EV/confidence/odds
    hard limits but fall below the tier's minimum PGR score are downgraded to the next tier.

    Returns (routing, reason) where routing is one of:
        'PRO_PICK', 'VALUE_OPP', 'WATCHLIST', 'REJECTED'
    and reason is one of the REJECTION_REASONS or 'routed_<tier>'.
    """
    league_tier = get_league_tier(league_key)

    if odds < CANDIDATE_MIN_ODDS:
        return "REJECTED", "rejected_low_odds"
    if odds > CANDIDATE_MAX_ODDS:
        return "REJECTED", "rejected_high_odds"
    if ev < WATCHLIST_MIN_EV:
        return "REJECTED", "rejected_low_ev"
    if confidence < WATCHLIST_MIN_CONFIDENCE:
        return "REJECTED", "rejected_low_confidence"

    if pgr_score < WATCHLIST_MIN_PGR_SCORE:
        return "REJECTED", "rejected_score_below_threshold"

    # ── PRO PICK: all hard criteria + PGR score gate ─────────────────────────
    # Tier C leagues cannot qualify for PRO PICK — they are downgraded, not rejected.
    if (
        ev >= PRO_PICK_MIN_EV
        and confidence >= PRO_PICK_MIN_CONFIDENCE
        and PRO_PICK_MIN_ODDS <= odds <= PRO_PICK_MAX_ODDS
        and league_tier in ("A", "B")
        and pgr_score >= PRO_PICK_MIN_PGR_SCORE
        and pro_picks_today < PRO_PICK_MAX_PER_DAY
    ):
        return "PRO_PICK", "routed_pro_pick"

    # ── VALUE OPP: relaxed criteria + PGR score gate ─────────────────────────
    # Tier C candidates that meet PRO thresholds fall through to VALUE OPP here.
    if (
        ev >= VALUE_OPP_MIN_EV
        and confidence >= VALUE_OPP_MIN_CONFIDENCE
        and VALUE_OPP_MIN_ODDS <= odds <= VALUE_OPP_MAX_ODDS
        and pgr_score >= VALUE_OPP_MIN_PGR_SCORE
    ):
        return "VALUE_OPP", "routed_value_opp"

    # ── WATCHLIST: EV 7–12% band + confidence floor + PGR score gate ───────────
    # Upper bound ensures EV>12% candidates are never silently filed as WATCHLIST;
    # they are either routed VALUE_OPP (if confidence qualifies) or explicitly rejected.
    if WATCHLIST_MIN_EV <= ev < VALUE_OPP_MIN_EV and confidence >= WATCHLIST_MIN_CONFIDENCE:
        return "WATCHLIST", "routed_watchlist"

    return "REJECTED", "rejected_score_below_threshold"


def ensure_pgr_columns() -> None:
    """Add pgr_score, league_tier, routing_reason and decision-brain columns to football_opportunities if missing."""
    ddl_statements = [
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS pgr_score REAL",
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS league_tier TEXT",
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS routing_reason TEXT",
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS clv_score REAL",
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS clv_tier TEXT",
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS kickoff_epoch BIGINT",
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS tier TEXT",
    ]
    try:
        from db_helper import DatabaseConnection
        with DatabaseConnection.get_cursor() as cursor:
            for stmt in ddl_statements:
                try:
                    cursor.execute(stmt)
                except Exception as exc:
                    print(f"[pgr_scoring] DDL warning: {exc}")
    except Exception as e:
        print(f"[pgr_scoring] ensure_pgr_columns failed: {e}")

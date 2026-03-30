"""
PGR Scoring Module — Three-layer signal routing
Weighted PGR Score: EV(40%) + Confidence(25%) + CLV potential(15%) + Market softness(10%) + League tier(10%)
"""

from typing import Tuple

# ── Market softness weights ────────────────────────────────────────────────────
# Higher weight = softer market (more bookmaker margin, more model edge available)
MARKET_WEIGHTS: dict = {
    # Corners — very soft, low bookmaker competency
    "CORNERS_OVER_8_5": 1.45,
    "CORNERS_OVER_9_5": 1.45,
    "CORNERS_OVER_10_5": 1.40,
    "CORNERS_OVER_11_5": 1.35,
    # Cards — also soft, sharp books underweight these
    "CARDS_OVER_2_5": 1.40,
    "CARDS_OVER_3_5": 1.40,
    "CARDS_OVER_4_5": 1.35,
    "CARDS_OVER_5_5": 1.30,
    # Totals — moderate softness
    "FT_OVER_4_5": 1.25,
    "FT_OVER_3_5": 1.20,
    "FT_OVER_2_5": 1.10,
    "FT_OVER_1_5": 1.05,
    "FT_OVER_0_5": 1.00,
    # BTTS — moderate
    "BTTS_YES": 1.15,
    "BTTS_NO": 1.10,
    # Double Chance — slightly soft
    "DOUBLE_CHANCE_1X": 1.05,
    "DOUBLE_CHANCE_12": 1.05,
    "DOUBLE_CHANCE_X2": 1.05,
    "DC_HOME_DRAW": 1.05,
    "DC_HOME_AWAY": 1.05,
    "DC_DRAW_AWAY": 1.05,
    # 1X2 — sharpest market, bookmakers best here
    "HOME_WIN": 0.90,
    "AWAY_WIN": 0.85,
    "DRAW": 0.80,
    # Asian Handicap — fairly efficient
    "AH_HOME_-0.5": 0.90, "AH_HOME_+0.5": 0.90,
    "AH_HOME_-1.0": 0.88, "AH_HOME_+1.0": 0.88,
    "AH_HOME_-1.5": 0.85, "AH_HOME_+1.5": 0.85,
    "AH_AWAY_-0.5": 0.90, "AH_AWAY_+0.5": 0.90,
    "AH_AWAY_-1.0": 0.88, "AH_AWAY_+1.0": 0.88,
    "AH_AWAY_-1.5": 0.85, "AH_AWAY_+1.5": 0.85,
}

# ── League tier classification ─────────────────────────────────────────────────
# A = Strongest historical performance, high data quality, sharp markets (paradox: harder)
#     Our model has strong calibration here → PRO eligible
# B = Good performance, acceptable volatility → PRO + VALUE eligible
# C = Volatile / thin data / lower market quality → VALUE + WATCHLIST only, not PRO
LEAGUE_TIERS: dict = {
    # Tier A — Top 5 + UCL
    "soccer_epl": "A",
    "soccer_spain_la_liga": "A",
    "soccer_italy_serie_a": "A",
    "soccer_germany_bundesliga": "A",
    "soccer_france_ligue_one": "A",
    "soccer_uefa_champs_league": "A",
    # Tier B — Second-tier European + UEL/UECL
    "soccer_efl_champ": "B",
    "soccer_netherlands_eredivisie": "B",
    "soccer_portugal_primeira_liga": "B",
    "soccer_belgium_first_div": "B",
    "soccer_spl": "B",
    "soccer_uefa_europa_league": "B",
    "soccer_uefa_europa_conference_league": "B",
    "soccer_england_league1": "B",
    "soccer_england_league2": "B",
    "soccer_germany_bundesliga2": "B",
    "soccer_italy_serie_b": "B",
    "soccer_spain_segunda_division": "B",
    "soccer_france_ligue_two": "B",
    "soccer_turkey_super_league": "B",
    "soccer_greece_super_league": "B",
    "soccer_poland_ekstraklasa": "B",
    "soccer_austria_bundesliga": "B",
    "soccer_switzerland_superleague": "B",
    "soccer_sweden_allsvenskan": "B",
    "soccer_norway_eliteserien": "B",
    "soccer_denmark_superliga": "B",
    # Tier C — Americas / Asia / Lower data quality
    "soccer_brazil_campeonato": "C",
    "soccer_argentina_primera_division": "C",
    "soccer_usa_mls": "C",
    "soccer_mexico_ligamx": "C",
    "soccer_japan_j_league": "C",
    "soccer_korea_kleague1": "C",
    "soccer_australia_aleague": "C",
    "soccer_netherlands_eerste_divisie": "C",
    "soccer_portugal_segunda_liga": "C",
    "soccer_czech_liga": "C",
    "soccer_conmebol_copa_libertadores": "C",
    "soccer_conmebol_copa_sudamericana": "C",
    "soccer_brazil_serie_b": "C",
    "soccer_chile_campeonato": "C",
}

_TIER_SCORE = {"A": 1.0, "B": 0.70, "C": 0.35}


def get_league_tier(league_key: str) -> str:
    """Return league tier A, B, or C. Defaults to B for unknown leagues."""
    return LEAGUE_TIERS.get(str(league_key), "B")


def compute_pgr_score(
    ev: float,
    confidence: float,
    odds: float,
    market_key: str,
    league_key: str,
    clv_pct: float = 0.0,
) -> float:
    """
    Compute weighted PGR Score in [0.0, 1.0].

    Components:
        EV score       40%  — normalized 0%→0, 50%→1
        Confidence     25%  — model probability direct
        CLV potential  15%  — from clv_pct or odds-range proxy
        Market weight  10%  — softness of the market type
        League tier    10%  — historical data quality
    """
    # EV (40%)
    ev_score = min(1.0, max(0.0, float(ev) / 0.50))

    # Confidence (25%)
    conf_score = min(1.0, max(0.0, float(confidence)))

    # CLV potential (15%)
    if clv_pct != 0.0:
        clv_score = min(1.0, max(0.0, (float(clv_pct) + 5.0) / 25.0))
    else:
        # Proxy: sweet-spot odds have best CLV potential
        o = float(odds)
        if 1.75 <= o <= 2.10:
            clv_score = 0.75
        elif 1.60 <= o < 1.75 or 2.10 < o <= 2.50:
            clv_score = 0.55
        else:
            clv_score = 0.30

    # Market softness (10%)
    mw = MARKET_WEIGHTS.get(str(market_key), 1.0)
    market_score = min(1.0, max(0.0, (mw - 0.70) / 0.80))

    # League tier (10%)
    tier = get_league_tier(league_key)
    league_score = _TIER_SCORE.get(tier, 0.70)

    pgr = (
        0.40 * ev_score
        + 0.25 * conf_score
        + 0.15 * clv_score
        + 0.10 * market_score
        + 0.10 * league_score
    )
    return round(pgr, 4)


def route_candidate(
    ev: float,
    confidence: float,
    odds: float,
    market_key: str,
    league_key: str,
    is_learning_only: bool,
    pgr_score: float,
    # PRO thresholds
    pro_min_ev: float = 0.25,
    pro_min_conf: float = 0.70,
    pro_min_odds: float = 1.75,
    pro_max_odds: float = 2.30,
    # VALUE thresholds
    val_min_ev: float = 0.12,
    val_min_conf: float = 0.60,
    val_min_odds: float = 1.60,
    val_max_odds: float = 4.00,
    # WATCHLIST thresholds
    watch_min_ev: float = 0.07,
    watch_min_conf: float = 0.50,
) -> Tuple[str, str]:
    """
    Route a candidate into PRO_PICK, VALUE_OPP, WATCHLIST, or REJECTED.

    Returns (layer, routing_reason) where layer is one of:
        'PROD'       → PRO PICK  (bet_placed=True)
        'VALUE_OPP'  → VALUE OPPORTUNITY (bet_placed=False, public)
        'WATCHLIST'  → WATCHLIST (bet_placed=False, internal)
        'REJECTED'   → dropped  (do not save)
    """
    tier = get_league_tier(league_key)

    # ── Hard filters (apply to all layers) ────────────────────────────────────
    if odds < val_min_odds:
        return ("REJECTED", "rejected_low_odds")
    if odds > val_max_odds:
        return ("REJECTED", "rejected_high_odds")
    if ev < watch_min_ev:
        return ("REJECTED", "rejected_low_ev")
    if confidence < watch_min_conf:
        return ("REJECTED", "rejected_low_confidence")

    # ── PRO PICK ───────────────────────────────────────────────────────────────
    if (
        not is_learning_only
        and ev >= pro_min_ev
        and confidence >= pro_min_conf
        and pro_min_odds <= odds <= pro_max_odds
        and tier in ("A", "B")
    ):
        return ("PROD", "pro_pick")

    # ── VALUE OPPORTUNITY ──────────────────────────────────────────────────────
    if (
        not is_learning_only
        and ev >= val_min_ev
        and confidence >= val_min_conf
        and val_min_odds <= odds <= val_max_odds
    ):
        return ("VALUE_OPP", "value_opportunity")

    # ── WATCHLIST (internal only) ──────────────────────────────────────────────
    if ev >= watch_min_ev and confidence >= watch_min_conf:
        return ("WATCHLIST", "watchlist")

    # ── Rejection reason ──────────────────────────────────────────────────────
    if is_learning_only:
        return ("REJECTED", "rejected_market_type")
    if tier == "C" and ev < val_min_ev:
        return ("REJECTED", "rejected_league_tier")
    if ev < val_min_ev:
        return ("REJECTED", "rejected_low_ev")
    if confidence < val_min_conf:
        return ("REJECTED", "rejected_low_confidence")
    return ("REJECTED", "rejected_score_below_threshold")


def ensure_db_columns(conn) -> None:
    """Add pgr_score, league_tier, routing_reason columns if they don't exist."""
    ddl = [
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS pgr_score real",
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS league_tier text",
        "ALTER TABLE football_opportunities ADD COLUMN IF NOT EXISTS routing_reason text",
    ]
    with conn.cursor() as cur:
        for stmt in ddl:
            cur.execute(stmt)
    conn.commit()

"""
decision_brain.py — Market Decision Engine v2

Exact implementation of the specified scoring functions.
All public functions match the spec signatures precisely.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("decision_brain")

# ── Constants ─────────────────────────────────────────────────────────────────

SHARP_BOOKS = {"pinnacle", "betfair", "matchbook"}

LEAGUE_WEIGHTS: Dict[str, float] = {
    "Premier League": 1.00,
    "Serie A": 0.98,
    "La Liga": 0.98,
    "Bundesliga": 0.98,
    "Ligue 1": 0.96,
    "Championship": 0.93,
    "English Championship": 0.93,
    "League One": 0.88,
    "English League One": 0.88,
    "English League Two": 0.82,
    "Ekstraklasa": 0.87,
    "Polish Ekstraklasa": 0.87,
    "Swiss Super League": 0.89,
    "Austrian Bundesliga": 0.89,
    "Copa Libertadores": 0.85,
    # extended coverage
    "Champions League": 1.00,
    "Europa League": 0.95,
    "Conference League": 0.90,
    "Eredivisie": 0.92,
    "Primeira Liga": 0.90,
    "Brasileirao Serie A": 0.88,
    "Belgian Pro League": 0.88,
    "Turkish Super Lig": 0.85,
    "Scottish Premiership": 0.85,
    "Major League Soccer": 0.83,
    "Greek Super League": 0.82,
    "Czech First League": 0.80,
    "Danish Superliga": 0.80,
    "Allsvenskan": 0.82,
    "Eliteserien": 0.82,
    "Argentinian Primera Division": 0.84,
    "Liga MX": 0.84,
    "Japanese J1 League": 0.80,
    "Korean K League 1": 0.78,
    "Australian A-League": 0.78,
    "__default__": 0.90,
}


# ── Spec-exact scoring functions ─────────────────────────────────────────────

def score_edge(edge_pct: float) -> int:
    if edge_pct < 2:
        return 0
    if edge_pct < 5:
        return 8
    if edge_pct < 8:
        return 15
    if edge_pct < 12:
        return 24
    if edge_pct < 18:
        return 30
    return 35


def score_sharp(has_pinny: bool, has_betfair: bool, sharp_books_count: int) -> int:
    if sharp_books_count >= 3:
        return 20
    if has_pinny and has_betfair:
        return 16
    if has_pinny or has_betfair:
        return 12
    return 0


def score_movement(move_pct: float) -> int:
    """move_pct < 0 = market moved in our favor, > 0 = drifted away."""
    if move_pct <= -5:
        return 20
    if move_pct <= -2:
        return 14
    if move_pct < 1:
        return 6
    if move_pct < 4:
        return -4
    return -10


def score_books(aligned_books: int) -> int:
    if aligned_books >= 6:
        return 10
    if aligned_books >= 4:
        return 8
    if aligned_books == 3:
        return 6
    if aligned_books == 2:
        return 3
    return 0


def score_data_quality(confidence_label: str, soft_odds: bool, snapshots_count: int) -> int:
    score = 0
    if confidence_label == "SHARP_CONFIRMED":
        score += 10
    elif confidence_label == "UNVERIFIED":
        score -= 15
    elif confidence_label == "UNVERIFIED_LEGACY":
        score -= 10

    if soft_odds:
        score -= 5

    if snapshots_count > 0:
        score += 5

    return score


def compute_confidence_score(
    adjusted_edge_pct: float,
    has_pinny: bool,
    has_betfair: bool,
    sharp_books_count: int,
    move_pct: float,
    aligned_books: int,
    confidence_label: str,
    soft_odds: bool,
    snapshots_count: int,
) -> int:
    total = 0
    total += score_edge(adjusted_edge_pct)
    total += score_sharp(has_pinny, has_betfair, sharp_books_count)
    total += score_movement(move_pct)
    total += score_books(aligned_books)
    total += score_data_quality(confidence_label, soft_odds, snapshots_count)
    return max(0, min(100, total))


def adjusted_edge(raw_edge_pct: float, league_weight: float) -> float:
    return raw_edge_pct * league_weight


def confidence_band(score: int) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 55:
        return "MEDIUM"
    if score >= 35:
        return "LOW"
    return "VERY_LOW"


def compute_verdict(
    confidence_score: int,
    current_edge_pct: float,
    peak_edge_pct: float,
    confidence_label: str,
    soft_odds: bool,
    move_pct: float,
) -> Tuple[str, str]:
    decay = max(0.0, peak_edge_pct - current_edge_pct)

    if confidence_label in {"UNVERIFIED", "UNVERIFIED_LEGACY"} and confidence_score < 55:
        return "PASS", "unverified signal"

    if current_edge_pct < 2:
        return "PASS", "line gone"

    if move_pct > 5 and current_edge_pct < 5:
        return "PASS", "market drifted away"

    if confidence_score >= 70 and current_edge_pct >= 8 and decay <= 4 and not soft_odds:
        return "PLAY_NOW", "edge still live"

    if confidence_score >= 60 and current_edge_pct >= 5 and decay <= 10:
        return "LATE", "value reduced"

    if confidence_score >= 40 and current_edge_pct >= 3:
        return "WATCH", "needs confirmation"

    return "PASS", "weak setup"


def compute_market_state(
    move_pct: float, current_edge_pct: float, peak_edge_pct: float
) -> Tuple[str, str]:
    decay = max(0.0, peak_edge_pct - current_edge_pct)

    if current_edge_pct < 2:
        return "GONE", "market corrected too far"
    if move_pct <= -2 and decay < 4:
        return "LIVE_NOW", "edge active and confirmed"
    if move_pct < 1 and decay < 2:
        return "BUILDING", "market moving toward signal"
    if decay >= 4:
        return "FADING", "value reduced from peak"
    return "FLAT", "little movement since detection"


def movement_text(move_pct: float) -> str:
    if move_pct <= -1:
        return f"market moved in your favor, {move_pct:.1f}%"
    if move_pct >= 1:
        return f"market drifted away, +{move_pct:.1f}%"
    return f"flat since detection, {move_pct:.1f}%"


def stake_hint(verdict: str, band: str) -> str:
    if verdict == "PLAY_NOW" and band == "HIGH":
        return "1.0u"
    if verdict == "PLAY_NOW" and band == "MEDIUM":
        return "0.5u"
    if verdict == "LATE":
        return "0.25u"
    return "0u"


def market_rank_score(adjusted_edge_pct: float, confidence_score: int, verdict: str) -> float:
    verdict_bonus = {
        "PLAY_NOW": 15,
        "LATE": 8,
        "WATCH": 3,
        "PASS": 0,
    }.get(verdict, 0)
    return adjusted_edge_pct * 1.5 + confidence_score * 0.7 + verdict_bonus


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_league_weight(league: str) -> float:
    if not league:
        return LEAGUE_WEIGHTS["__default__"]
    for key, w in LEAGUE_WEIGHTS.items():
        if key == "__default__":
            continue
        if key.lower() in league.lower() or league.lower() in key.lower():
            return w
    return LEAGUE_WEIGHTS["__default__"]


def parse_bookmakers(raw) -> Dict[str, float]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {k: float(v) for k, v in raw.items() if v}
    try:
        d = json.loads(raw)
        return {k: float(v) for k, v in d.items() if v}
    except Exception:
        return {}


def derive_confidence_label(
    trust_level: Optional[str],
    clv_score: float,
    has_pinny: bool,
    has_betfair: bool,
    mode: Optional[str],
) -> str:
    if mode and mode.upper() == "LEARNING":
        return "UNVERIFIED_LEGACY"
    if has_pinny or has_betfair or clv_score >= 4:
        return "SHARP_CONFIRMED"
    if trust_level in ("PRO_PICK", "VALUE_OPP"):
        return "SHARP_CONFIRMED"
    if trust_level == "WATCHLIST":
        return "UNVERIFIED"
    return "UNVERIFIED"


def get_peak_edge_and_snapshots(
    event_id: Optional[str],
    pick_id: Optional[int],
    market: str,
    selection: str,
    fair_odds: Optional[float],
    open_odds: Optional[float],
    current_edge: float,
) -> Tuple[float, int]:
    """
    Returns (peak_edge_pct, snapshots_count).
    Queries pgr_odds_snapshots; falls back to open_odds proxy.
    """
    snap_count = 0
    peak_edge = current_edge

    try:
        from db_helper import db_helper
        eid = str(event_id or pick_id or "")
        if not eid:
            raise ValueError("no event id")

        row = db_helper.execute("""
            SELECT MAX(odds_decimal), COUNT(*)
            FROM pgr_odds_snapshots
            WHERE event_id = %s
              AND (market_type ILIKE %s OR %s ILIKE '%%' || market_type || '%%')
        """, (eid, f"%{market}%", market), fetch="one")

        if row and row[0]:
            best_snap_odds = float(row[0])
            snap_count = int(row[1] or 0)
            if fair_odds and fair_odds > 0:
                snap_peak = ((best_snap_odds / fair_odds) - 1.0) * 100.0
                peak_edge = max(current_edge, snap_peak)
    except Exception as exc:
        logger.debug(f"Snapshot query failed: {exc}")

    # Fallback: use open_odds as peak proxy
    if peak_edge <= current_edge and open_odds and fair_odds and fair_odds > 0:
        open_peak = ((open_odds / fair_odds) - 1.0) * 100.0
        peak_edge = max(current_edge, open_peak)

    return round(peak_edge, 2), snap_count


def build_why(
    confidence_label: str,
    has_pinny: bool,
    has_betfair: bool,
    sharp_book: Optional[str],
    sharp_price: Optional[float],
    move_pct: float,
    aligned_books: int,
    adj_edge: float,
    peak_edge: float,
    current_edge: float,
    soft_odds: bool,
    verdict: str,
) -> List[str]:
    why = []

    # Sharp status
    if confidence_label == "SHARP_CONFIRMED":
        book_label = sharp_book or ("Pinnacle" if has_pinny else "Betfair" if has_betfair else "sharp book")
        price_str = f" @ {sharp_price:.2f}" if sharp_price else ""
        why.append(f"sharp confirmed — {book_label}{price_str}")
    elif confidence_label == "UNVERIFIED_LEGACY":
        why.append("legacy signal — no sharp book anchor, use caution")
    else:
        why.append("unverified — no sharp book anchor")

    # Movement
    mv_abs = abs(move_pct)
    if move_pct <= -1:
        why.append(f"market moved {move_pct:.1f}% after detection")
    elif move_pct >= 1:
        why.append(f"market drifted +{move_pct:.1f}% away")
    else:
        why.append(f"flat since detection ({move_pct:+.1f}%)")

    # Books
    if aligned_books >= 2:
        why.append(f"{aligned_books} books aligned")
    else:
        why.append("single source — low confirmation")

    # Edge state
    decay = max(0.0, peak_edge - current_edge)
    if decay > 0.5:
        why.append(f"edge down from +{peak_edge:.1f}% to +{adj_edge:.1f}%")
    else:
        why.append(f"+{adj_edge:.1f}% — at peak")

    # Soft odds warning
    if soft_odds:
        why.append("soft books only — verify with sharp source before betting")

    return why


# ── Core entry point ──────────────────────────────────────────────────────────

def score_market(row: dict) -> dict:
    """
    Input: dict from football_opportunities (from the /api/v2/decision endpoint).
    Output: full decision object matching the spec.
    """
    league         = row.get("league", "")
    raw_edge       = float(row.get("ev_pct") or row.get("edge_percentage") or 0)
    current_odds   = float(row.get("odds") or 0) or None
    open_odds_raw  = float(row.get("open_odds") or 0) or None
    clv_score      = float(row.get("clv_score") or 0)
    trust_level    = row.get("trust_level") or ""
    mode           = row.get("mode") or ""
    market         = row.get("market", "")
    selection      = row.get("selection", "")
    pick_id        = row.get("id")
    event_id       = row.get("match_id") or row.get("event_id")

    # fair odds — derive from model_prob if missing
    fair_odds_raw  = row.get("fair_odds")
    fair_odds      = float(fair_odds_raw) if fair_odds_raw else None
    if not fair_odds:
        mp = float(row.get("model_prob") or row.get("calibrated_prob") or 0)
        if mp > 0:
            fair_odds = round(1.0 / mp, 3)

    # bookmakers
    bookmakers = parse_bookmakers(row.get("bookmakers") or row.get("odds_by_bookmaker"))

    # sharp book detection
    bm_lower = {k.lower(): (k, v) for k, v in bookmakers.items()}
    has_pinny   = any("pinnacle" in k for k in bm_lower)
    has_betfair = any("betfair" in k for k in bm_lower)
    sharp_books_in_bm = [k for k in bm_lower if any(s in k for s in SHARP_BOOKS)]
    sharp_books_count = len(sharp_books_in_bm)
    soft_odds = (sharp_books_count == 0)

    # sharp price / book
    sharp_book  = None
    sharp_price = None
    if has_pinny:
        for k, (orig, odds) in bm_lower.items():
            if "pinnacle" in k:
                sharp_book = orig
                sharp_price = odds
                break
    elif has_betfair:
        for k, (orig, odds) in bm_lower.items():
            if "betfair" in k:
                sharp_book = orig
                sharp_price = odds
                break
    elif sharp_books_in_bm:
        orig_k = bm_lower[sharp_books_in_bm[0]][0]
        sharp_book  = orig_k
        sharp_price = bookmakers[orig_k]

    # best price / book
    best_book  = None
    best_price = None
    if bookmakers:
        best_book_key = max(bookmakers, key=bookmakers.get)
        best_book  = best_book_key
        best_price = bookmakers[best_book_key]

    # league weight + adjusted edge
    lw       = get_league_weight(league)
    adj_edge = round(adjusted_edge(raw_edge, lw), 2)

    # move_pct: negative = moved in our favor (odds shortened), positive = drifted away
    move_pct = 0.0
    if open_odds_raw and current_odds and open_odds_raw > 0:
        move_pct = round((current_odds - open_odds_raw) / open_odds_raw * 100.0, 2)

    # peak edge + snapshot count
    peak_edge_pct, snapshots_count = get_peak_edge_and_snapshots(
        event_id, pick_id, market, selection, fair_odds, open_odds_raw, adj_edge
    )

    # aligned books (books offering >= fair value)
    aligned_books_count = 0
    if fair_odds:
        for _, bm_odds in bookmakers.items():
            if bm_odds >= fair_odds * 0.99:
                aligned_books_count += 1

    # confidence label
    conf_label = derive_confidence_label(trust_level, clv_score, has_pinny, has_betfair, mode)

    # confidence score
    conf_score = compute_confidence_score(
        adjusted_edge_pct=adj_edge,
        has_pinny=has_pinny,
        has_betfair=has_betfair,
        sharp_books_count=sharp_books_count,
        move_pct=move_pct,
        aligned_books=aligned_books_count,
        confidence_label=conf_label,
        soft_odds=soft_odds,
        snapshots_count=snapshots_count,
    )

    conf_band_label = confidence_band(conf_score)

    # edge decay
    edge_decay_pct = round(max(0.0, peak_edge_pct - adj_edge), 2)

    # verdict
    verdict_val, verdict_reason_val = compute_verdict(
        confidence_score=conf_score,
        current_edge_pct=adj_edge,
        peak_edge_pct=peak_edge_pct,
        confidence_label=conf_label,
        soft_odds=soft_odds,
        move_pct=move_pct,
    )

    # market state
    mstate_val, mstate_reason_val = compute_market_state(
        move_pct=move_pct,
        current_edge_pct=adj_edge,
        peak_edge_pct=peak_edge_pct,
    )

    # movement text
    mv_text = movement_text(move_pct)

    # stake hint
    stake = stake_hint(verdict_val, conf_band_label)

    # why panel
    why = build_why(
        confidence_label=conf_label,
        has_pinny=has_pinny,
        has_betfair=has_betfair,
        sharp_book=sharp_book,
        sharp_price=sharp_price,
        move_pct=move_pct,
        aligned_books=aligned_books_count,
        adj_edge=adj_edge,
        peak_edge=peak_edge_pct,
        current_edge=adj_edge,
        soft_odds=soft_odds,
        verdict=verdict_val,
    )

    # rank score for best-opportunity selection
    rank = market_rank_score(adj_edge, conf_score, verdict_val)

    # confidence breakdown (for debugging / UI tooltip)
    breakdown = {
        "edge_pts":         score_edge(adj_edge),
        "sharp_pts":        score_sharp(has_pinny, has_betfair, sharp_books_count),
        "movement_pts":     score_movement(move_pct),
        "book_pts":         score_books(aligned_books_count),
        "data_quality_pts": score_data_quality(conf_label, soft_odds, snapshots_count),
    }

    market_name = selection if selection else market

    return {
        "market_name":               market_name,
        "market":                    market,
        "selection":                 selection,
        "raw_edge_pct":              round(raw_edge, 2),
        "league_weight":             lw,
        "adjusted_edge_pct":         adj_edge,
        "peak_edge_pct":             peak_edge_pct,
        "edge_decay_pct":            edge_decay_pct,
        "confidence_score":          conf_score,
        "confidence_band":           conf_band_label,
        "confidence_breakdown":      breakdown,
        "verdict":                   verdict_val,
        "verdict_reason":            verdict_reason_val,
        "market_state":              mstate_val,
        "market_state_reason":       mstate_reason_val,
        "best_price":                round(best_price, 2) if best_price else None,
        "best_book":                 best_book,
        "sharp_price":               round(sharp_price, 2) if sharp_price else None,
        "sharp_book":                sharp_book,
        "fair_odds":                 round(fair_odds, 2) if fair_odds else None,
        "move_pct":                  move_pct,
        "movement_text":             mv_text,
        "aligned_books":             aligned_books_count,
        "soft_odds":                 soft_odds,
        "confidence_label":          conf_label,
        "stake_hint":                stake,
        "best_opportunity_in_match": False,
        "why":                       why,
        # internal
        "_rank_score":               rank,
        "_id":                       pick_id,
    }


def score_match(markets: List[dict]) -> List[dict]:
    """
    Score all markets for a match, rank by score, flag best opportunity.
    Returns sorted list (best first).
    """
    if not markets:
        return []

    scored = [score_market(m) for m in markets]
    scored.sort(key=lambda x: x["_rank_score"], reverse=True)

    # Flag best non-PASS opportunity
    best_set = False
    for m in scored:
        if not best_set and m["verdict"] != "PASS":
            m["best_opportunity_in_match"] = True
            best_set = True

    return scored

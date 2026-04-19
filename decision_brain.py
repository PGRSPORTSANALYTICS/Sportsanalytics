"""
decision_brain.py — Market Decision Engine v1

For each market in a match, produces a fully rendered decision object:
  - confidence_score (0-100) across 5 dimensions
  - league-weighted adjusted edge
  - peak vs now edge with decay
  - verdict: PLAY NOW / LATE / WATCH / PASS
  - market_state: BUILDING / LIVE NOW / FADING / GONE
  - ranked best opportunity per match

Reads from: football_opportunities + pgr_odds_snapshots
"""

import time
import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("decision_brain")

# ── League quality weights ───────────────────────────────────────────────────
# Weight 1.0 = maximum data quality + sharpest markets
LEAGUE_WEIGHTS: Dict[str, float] = {
    # Tier 1 — elite
    "Premier League": 1.00,
    "La Liga": 1.00,
    "Bundesliga": 1.00,
    "Serie A": 1.00,
    "Ligue 1": 1.00,
    "Champions League": 1.00,
    # Tier 1.5 — continental cups
    "Europa League": 0.95,
    "Conference League": 0.90,
    # Tier 2 — strong leagues
    "Eredivisie": 0.92,
    "Primeira Liga": 0.90,
    "Brasileirao Serie A": 0.88,
    "English Championship": 0.88,
    "Belgian Pro League": 0.88,
    "Turkish Super Lig": 0.85,
    "Scottish Premiership": 0.85,
    "Major League Soccer": 0.83,
    "Greek Super League": 0.82,
    "Czech First League": 0.80,
    "Danish Superliga": 0.80,
    # Tier 3 — emerging / lower quality
    "Austrian Bundesliga": 0.80,
    "Polish Ekstraklasa": 0.78,
    "Swiss Super League": 0.78,
    "Allsvenskan": 0.78,
    "Eliteserien": 0.78,
    "English League One": 0.78,
    "English League Two": 0.75,
    "Argentinian Primera Division": 0.80,
    "Liga MX": 0.80,
    "Japanese J1 League": 0.78,
    "Korean K League 1": 0.75,
    "Australian A-League": 0.75,
    "Copa Libertadores": 0.85,
    "__default__": 0.80,
}

SHARP_BOOKS = {"pinnacle", "betfair", "matchbook", "betsson", "nordicbet"}

VERDICT_BONUS = {"PLAY NOW": 20, "LATE": 10, "WATCH": 5, "PASS": 0}

CONFIDENCE_BANDS = [
    (80, "Elite"),
    (65, "Strong"),
    (50, "Moderate"),
    (35, "Weak"),
    (0,  "Noise"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _league_weight(league: str) -> float:
    if not league:
        return LEAGUE_WEIGHTS["__default__"]
    for key, w in LEAGUE_WEIGHTS.items():
        if key.lower() in league.lower() or league.lower() in key.lower():
            return w
    return LEAGUE_WEIGHTS["__default__"]


def _confidence_band(score: int) -> str:
    for threshold, label in CONFIDENCE_BANDS:
        if score >= threshold:
            return label
    return "Noise"


def _parse_analysis(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _parse_bookmakers(raw) -> Dict[str, float]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {k: float(v) for k, v in raw.items() if v}
    try:
        d = json.loads(raw)
        return {k: float(v) for k, v in d.items() if v}
    except Exception:
        return {}


# ── Confidence scoring ───────────────────────────────────────────────────────

def _score_edge(raw_edge: float, league_weight: float) -> Tuple[float, float]:
    """Returns (adj_edge_pct, edge_pts 0-30)."""
    adj = raw_edge * league_weight
    pts = min(30.0, max(0.0, adj * 2.2))   # 13.6% adj → 30 pts
    return round(adj, 2), round(pts, 1)


def _score_sharp(clv_score: float, clv_pct: Optional[float],
                 fair_odds: Optional[float], current_odds: Optional[float]) -> Tuple[float, str]:
    """Returns (sharp_pts 0-25, quality_label)."""
    if clv_score and clv_score > 0:
        pts = (clv_score / 6.0) * 25.0
        label = "sharp" if clv_score >= 4 else "standard"
    elif clv_pct is not None:
        pts = min(25.0, max(0.0, clv_pct * 2.0 + 12.0))
        label = "clv_proxy"
    elif fair_odds and current_odds and fair_odds > 0:
        ratio = current_odds / fair_odds
        pts = min(20.0, max(0.0, (ratio - 1.0) * 200.0))
        label = "fair_odds_proxy"
    else:
        pts = 8.0   # moderate assumed when no sharp data
        label = "no_anchor"
    return round(pts, 1), label


def _score_movement(open_odds: Optional[float], current_odds: Optional[float],
                    steam_flag: Optional[str]) -> Tuple[float, str]:
    """Returns (movement_pts 0-20, movement_text)."""
    pts = 0.0
    texts = []

    if steam_flag == "early":
        pts += 12.0
        texts.append("Early steam detected")
    elif steam_flag == "late":
        pts += 6.0
        texts.append("Late movement")

    if open_odds and current_odds and open_odds > 0:
        pct_change = (current_odds - open_odds) / open_odds * 100.0
        if pct_change < -3:
            # Odds shortened — sharp money confirming
            pts += min(8.0, abs(pct_change) * 0.8)
            texts.append(f"Odds shortened {abs(pct_change):.1f}% (sharp flow)")
        elif pct_change > 5:
            # Odds drifted — market fading the pick
            pts -= min(8.0, pct_change * 0.6)
            texts.append(f"Odds drifted +{pct_change:.1f}% (cooling)")
        else:
            texts.append("Line stable")

    if not texts:
        texts.append("No movement data")

    return round(max(0.0, min(20.0, pts)), 1), " · ".join(texts)


def _score_book_agreement(bookmakers: Dict[str, float],
                          fair_odds: Optional[float],
                          current_odds: Optional[float]) -> Tuple[float, List[str]]:
    """Returns (book_pts 0-15, aligned_book_names)."""
    if not bookmakers:
        return 5.0, []

    ref_odds = fair_odds or current_odds
    if not ref_odds:
        return 5.0, []

    aligned = []
    for bm, bm_odds in bookmakers.items():
        if bm_odds >= ref_odds * 0.99:   # bookmaker at or above fair
            aligned.append(bm)

    # Prioritise sharp books
    sharp_aligned = [b for b in aligned if b.lower() in SHARP_BOOKS]
    pts = len(sharp_aligned) * 8.0 + len([b for b in aligned if b not in sharp_aligned]) * 3.0
    return round(min(15.0, pts), 1), aligned


def _score_data_quality(row: dict) -> float:
    """Returns data_quality_pts 0-10."""
    pts = 0.0
    if row.get("calibrated_prob"):
        pts += 3.0
    if row.get("sim_prob") or row.get("sim_probability"):
        pts += 3.0
    if row.get("open_odds"):
        pts += 2.0
    if row.get("analysis_raw") or row.get("analysis"):
        pts += 2.0
    return pts


# ── Peak / decay ─────────────────────────────────────────────────────────────

def _peak_edge(pick_id: Optional[int], event_id: Optional[str],
               market: str, selection: str,
               fair_odds: Optional[float], current_edge: float) -> Tuple[float, float]:
    """
    Returns (peak_edge_pct, edge_decay_pct).
    Queries pgr_odds_snapshots for best historical odds; falls back to open_odds proxy.
    """
    if not (pick_id or event_id) or not fair_odds or fair_odds <= 0:
        return current_edge, 0.0

    try:
        from db_helper import db_helper
        eid = str(event_id or pick_id)
        row = db_helper.execute("""
            SELECT MAX(odds_decimal)
            FROM pgr_odds_snapshots
            WHERE event_id = %s
              AND (market_type ILIKE %s OR %s ILIKE '%%' || market_type || '%%')
              AND (selection ILIKE %s OR %s = '')
            LIMIT 1
        """, (eid, f"%{market}%", market, f"%{selection}%", selection), fetch="one")

        best_odds = float(row[0]) if row and row[0] else None

        if best_odds and best_odds > 0 and fair_odds > 0:
            peak_edge = ((best_odds / fair_odds) - 1.0) * 100.0
            peak_edge = max(peak_edge, current_edge)
            decay = (peak_edge - current_edge) / peak_edge * 100.0 if peak_edge > 0 else 0.0
            return round(peak_edge, 2), round(max(0.0, decay), 1)
    except Exception as e:
        logger.debug(f"Peak edge query failed: {e}")

    return current_edge, 0.0


# ── Market state ─────────────────────────────────────────────────────────────

def _market_state(kickoff_epoch: Optional[int], edge_decay_pct: float,
                  steam_flag: Optional[str], open_odds: Optional[float],
                  current_odds: Optional[float]) -> Tuple[str, str]:
    now = int(time.time())
    mins_to_ko = ((kickoff_epoch or (now + 7200)) - now) / 60.0

    if mins_to_ko < -35:
        return "GONE", "Match already in play"

    if -35 <= mins_to_ko <= 25:
        return "LIVE NOW", f"Kickoff in {int(mins_to_ko)}m" if mins_to_ko > 0 else "Kickoff passed"

    # Check if edge is fading
    drifting = False
    if open_odds and current_odds and current_odds > open_odds * 1.05:
        drifting = True

    if edge_decay_pct > 45 or drifting:
        reason = f"Edge decayed {edge_decay_pct:.0f}% from peak" if edge_decay_pct > 45 else "Odds drifting"
        return "FADING", reason

    if steam_flag == "early" or mins_to_ko > 240:
        return "BUILDING", "Early market phase, sharp book tracking active"

    return "BUILDING", f"~{int(mins_to_ko // 60)}h {int(mins_to_ko % 60)}m to kickoff"


# ── Verdict ──────────────────────────────────────────────────────────────────

def _verdict(adj_edge: float, conf_score: int,
             market_state: str, edge_decay_pct: float,
             clv_score: float) -> Tuple[str, str]:

    if market_state == "GONE":
        return "PASS", "Market closed — match in play"

    if market_state == "FADING" and edge_decay_pct > 60:
        return "PASS", f"Edge decayed {edge_decay_pct:.0f}% — too late"

    # PLAY NOW: elite signal, act immediately
    if (conf_score >= 68 and adj_edge >= 7.0 and
            market_state in ("BUILDING", "LIVE NOW") and
            edge_decay_pct < 35):
        reasons = []
        if adj_edge >= 10:
            reasons.append(f"{adj_edge:.1f}% adjusted edge")
        if clv_score >= 4:
            reasons.append("sharp anchor confirmed")
        if conf_score >= 80:
            reasons.append(f"{conf_score} confidence")
        return "PLAY NOW", " · ".join(reasons) if reasons else f"{adj_edge:.1f}% edge, {conf_score} conf"

    # LATE: confirmed but window narrowing
    if (conf_score >= 52 and adj_edge >= 5.0 and
            market_state == "LIVE NOW" and edge_decay_pct < 50):
        return "LATE", "Edge confirmed, closing window — act or skip"

    # WATCH: promising but wait for confirmation
    if (conf_score >= 42 and adj_edge >= 4.0 and
            market_state in ("BUILDING", "LIVE NOW", "FADING") and
            edge_decay_pct < 55):
        if market_state == "BUILDING":
            return "WATCH", "Market building — monitor for sharper entry"
        return "WATCH", "Below conviction threshold — hold for confirmation"

    return "PASS", "Insufficient edge or confidence"


# ── Stake hint ───────────────────────────────────────────────────────────────

def _stake_hint(verdict: str, conf_score: int, adj_edge: float) -> str:
    if verdict == "PLAY NOW":
        if conf_score >= 82 and adj_edge >= 10:
            return "2–3 units"
        if conf_score >= 68:
            return "1–2 units"
        return "1 unit"
    if verdict == "LATE":
        return "0.5–1 unit"
    return "—"


# ── Why panel ────────────────────────────────────────────────────────────────

def _build_why(adj_edge: float, conf_score: int, verdict: str,
               sharp_label: str, movement_text: str,
               aligned_books: List[str], edge_decay_pct: float,
               clv_score: float, tier: Optional[str],
               league_weight: float) -> List[str]:
    why = []

    # Edge line
    if adj_edge >= 8:
        why.append(f"Strong {adj_edge:.1f}% adjusted edge (league weight ×{league_weight:.2f})")
    elif adj_edge >= 5:
        why.append(f"Moderate {adj_edge:.1f}% adjusted edge")
    else:
        why.append(f"Thin {adj_edge:.1f}% adjusted edge — use caution")

    # Sharp anchor
    if sharp_label == "sharp" and clv_score >= 4:
        why.append(f"Sharp anchor confirmed (CLV score {clv_score:.0f}/6)")
    elif sharp_label == "clv_proxy":
        why.append("Closing-line value tracking active")
    elif sharp_label == "no_anchor":
        why.append("No sharp book anchor — model-only signal")

    # Movement
    if movement_text and movement_text != "No movement data":
        why.append(movement_text)

    # Book agreement
    sharp_aligned = [b for b in aligned_books if b.lower() in SHARP_BOOKS]
    if sharp_aligned:
        why.append(f"Sharp books onside: {', '.join(sharp_aligned)}")
    elif aligned_books:
        why.append(f"{len(aligned_books)} books at or above fair value")

    # Tier
    if tier in ("A", "B"):
        why.append(f"Tier {tier} model confidence")
    elif tier == "C":
        why.append("Tier C — lower model grade, size down")

    # Decay warning
    if edge_decay_pct > 30:
        why.append(f"⚠ Edge decayed {edge_decay_pct:.0f}% from peak")

    # Verdict reinforcement
    if verdict == "PASS" and adj_edge < 5:
        why.append("Raw edge below minimum threshold (5%)")

    return why


# ── Core entry point ─────────────────────────────────────────────────────────

def score_market(row: dict) -> dict:
    """
    Input: dict with fields from football_opportunities.
    Output: full decision object.
    """
    league        = row.get("league", "")
    raw_edge      = float(row.get("ev_pct") or row.get("edge_percentage") or 0)
    current_odds  = float(row.get("odds") or 0) or None
    open_odds     = float(row.get("open_odds") or 0) or None
    clv_score     = float(row.get("clv_score") or 0)
    clv_pct       = float(row.get("clv_pct") or 0) or None
    kickoff_epoch = row.get("kickoff_epoch")
    steam_flag    = row.get("steam_flag") or ""
    fair_odds_raw = row.get("fair_odds")
    fair_odds     = float(fair_odds_raw) if fair_odds_raw else None
    tier          = row.get("tier") or row.get("confidence_tier")
    pick_id       = row.get("id")
    event_id      = row.get("match_id") or row.get("event_id")
    market        = row.get("market", "")
    selection     = row.get("selection", "")
    bookmakers    = _parse_bookmakers(row.get("bookmakers") or row.get("odds_by_bookmaker"))

    # ── If fair_odds missing, derive from model_prob ─────────────────────────
    if not fair_odds:
        mp = float(row.get("model_prob") or row.get("calibrated_prob") or 0)
        if mp > 0:
            fair_odds = round(1.0 / mp, 3)

    # 1. League weight + adjusted edge
    lw = _league_weight(league)
    adj_edge, edge_pts = _score_edge(raw_edge, lw)

    # 2. Peak / decay
    peak_edge, edge_decay = _peak_edge(pick_id, event_id, market, selection, fair_odds, adj_edge)

    # 3. Confidence components
    sharp_pts, sharp_label   = _score_sharp(clv_score, clv_pct, fair_odds, current_odds)
    movement_pts, movement_text = _score_movement(open_odds, current_odds, steam_flag)
    book_pts, aligned_books  = _score_book_agreement(bookmakers, fair_odds, current_odds)
    dq_pts                   = _score_data_quality(row)

    conf_score = int(min(100, max(0,
        edge_pts + sharp_pts + movement_pts + book_pts + dq_pts
    )))
    conf_band = _confidence_band(conf_score)

    # 4. Market state
    market_state, state_reason = _market_state(
        kickoff_epoch, edge_decay, steam_flag, open_odds, current_odds
    )

    # 5. Verdict
    verdict, verdict_reason = _verdict(
        adj_edge, conf_score, market_state, edge_decay, clv_score
    )

    # 6. Stake hint
    stake = _stake_hint(verdict, conf_score, adj_edge)

    # 7. Why panel
    why = _build_why(
        adj_edge, conf_score, verdict, sharp_label, movement_text,
        aligned_books, edge_decay, clv_score, tier, lw
    )

    return {
        # Core metrics
        "market":               market,
        "selection":            selection,
        "odds":                 current_odds,
        "league":               league,
        "league_weight":        lw,
        # Edge
        "raw_edge_pct":         round(raw_edge, 2),
        "adjusted_edge_pct":    adj_edge,
        "peak_edge_pct":        round(peak_edge, 2),
        "edge_decay_pct":       edge_decay,
        # Confidence
        "confidence_score":     conf_score,
        "confidence_band":      conf_band,
        "confidence_breakdown": {
            "edge_pts":        edge_pts,
            "sharp_pts":       sharp_pts,
            "movement_pts":    movement_pts,
            "book_pts":        book_pts,
            "data_quality_pts": dq_pts,
        },
        # Decision
        "verdict":              verdict,
        "verdict_reason":       verdict_reason,
        "market_state":         market_state,
        "market_state_reason":  state_reason,
        # Context
        "movement_text":        movement_text,
        "aligned_books":        aligned_books,
        "why":                  why,
        "stake_hint":           stake,
        # Ranking key (used to find best opportunity)
        "_rank_score":          adj_edge * 0.5 + conf_score * 0.3 + VERDICT_BONUS[verdict],
    }


def score_match(markets: List[dict]) -> List[dict]:
    """
    Score all markets for a match and flag the best opportunity.
    Returns list of scored markets, sorted by rank (best first).
    """
    if not markets:
        return []

    scored = [score_market(m) for m in markets]
    scored.sort(key=lambda x: x["_rank_score"], reverse=True)

    # Tag best opportunity (only if verdict is not PASS)
    best_set = False
    for m in scored:
        m["is_best_opportunity"] = False
        if not best_set and m["verdict"] != "PASS":
            m["is_best_opportunity"] = True
            best_set = True

    return scored

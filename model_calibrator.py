"""
model_calibrator.py — Probability calibration layer.

Transforms raw model_prob into calibrated_prob before EV is displayed.

Three-phase approach:
  Phase 1 (N < 100): Global shrink derived from CLV ratio, fallback 0.25
  Phase 2 (N >= 100): Linear regression per segment (market_type × league_tier)
  Phase 3 (N >= 500): Per-bucket isotonic regression

Segments:
  market_type : MAIN (1X2, Over/Under, BTTS) vs CORNERS_CARDS
  league_tier : TIER1 (top leagues) vs TIER2 vs TIER3
  odds_bucket : 1.50-1.80 | 1.80-2.20 | 2.20-3.00 | 3.00+
"""

from __future__ import annotations
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Phase thresholds ─────────────────────────────────────────────────────────
PHASE1_MAX = 100
PHASE2_MAX = 500

# Fallback shrink factor until enough data exists
# displayed_ev = raw_ev * FALLBACK_SHRINK
FALLBACK_SHRINK = 0.25

# Safety bounds on any derived shrink factor
MIN_SHRINK = 0.10
MAX_SHRINK = 0.60

# ─── Classifiers ─────────────────────────────────────────────────────────────
TIER1_KEYWORDS = {
    "premier league", "la liga", "bundesliga", "serie a", "ligue 1",
    "champions league", "europa league", "eredivisie", "primeira liga",
}
TIER2_KEYWORDS = {
    "championship", "serie b", "ligue 2", "segunda", "bundesliga 2",
    "mls", "scottish", "allsvenskan",
}


def classify_market(market: str) -> str:
    m = (market or "").lower()
    if any(k in m for k in ("corner", "card", "prop", "player")):
        return "CORNERS_CARDS"
    return "MAIN"


def classify_league(league: str) -> str:
    lw = (league or "").lower()
    if any(k in lw for k in TIER1_KEYWORDS):
        return "TIER1"
    if any(k in lw for k in TIER2_KEYWORDS):
        return "TIER2"
    return "TIER3"


def classify_odds_bucket(odds: float) -> str:
    if odds < 1.8:
        return "1.50-1.80"
    if odds < 2.2:
        return "1.80-2.20"
    if odds < 3.0:
        return "2.20-3.00"
    return "3.00+"


# ─── DB helpers ───────────────────────────────────────────────────────────────
_CALIB_COLS = [
    "id", "model_prob", "calibrated_prob", "edge_percentage", "ev_sim",
    "odds", "close_odds", "clv_pct", "result", "outcome",
    "market", "market_type", "league", "league_tier", "odds_bucket",
]


def _load_calibration_data() -> list[dict]:
    """Load all PROD picks with CLV and outcome data."""
    try:
        from db_helper import db_helper
        rows = db_helper.execute(
            """
            SELECT
                id, model_prob, calibrated_prob, edge_percentage, ev_sim,
                odds, close_odds, clv_pct, result, outcome,
                market, market_type, league, league_tier, odds_bucket
            FROM football_opportunities
            WHERE mode IN ('PROD', 'LEARNING')
              AND odds > 1
              AND clv_pct IS NOT NULL
            ORDER BY timestamp DESC
            """,
            fetch="all",
        )
        if not rows:
            return []
        # cursor.fetchall() returns tuples — map to dicts
        return [dict(zip(_CALIB_COLS, r)) for r in rows]
    except Exception as e:
        logger.warning(f"[Calibrator] Failed to load data: {e}")
        return []


def _to_ev_pct(r: dict) -> float:
    """
    Normalize EV to percentage form.
    edge_percentage is stored as % (e.g. 24.1)
    ev_sim is stored as decimal (e.g. 0.241)
    """
    ep = r.get("edge_percentage")
    if ep is not None and ep > 0:
        return float(ep)
    es = r.get("ev_sim")
    if es is not None and es > 0:
        return float(es) * 100 if es < 2 else float(es)
    return 0.0


# ─── Stats computation ────────────────────────────────────────────────────────
_stats_cache: Optional[dict] = None
_stats_cache_ts: float = 0
STATS_TTL = 300  # re-compute every 5 minutes


def get_calibration_stats(force: bool = False) -> dict:
    """
    Compute (and cache) calibration statistics.
    Returns a dict with: n, phase, avg_raw_ev, avg_clv, shrink_factor, label,
    bucket_data, segment_data.
    """
    global _stats_cache, _stats_cache_ts
    now = time.time()
    if not force and _stats_cache and (now - _stats_cache_ts) < STATS_TTL:
        return _stats_cache

    rows = _load_calibration_data()
    n_total = len(rows)
    with_clv = [r for r in rows if r.get("clv_pct") is not None]
    with_outcome = [r for r in rows if r.get("outcome") in ("won", "win", "lost", "loss")]
    n_clv = len(with_clv)
    n_outcome = len(with_outcome)

    # ── Global averages ────────────────────────────────────────────────────
    avg_raw_ev = None
    avg_clv = None
    shrink = FALLBACK_SHRINK

    if with_clv:
        raw_evs = [_to_ev_pct(r) for r in with_clv if _to_ev_pct(r) > 0]
        clvs = [r["clv_pct"] for r in with_clv]
        if raw_evs:
            avg_raw_ev = round(sum(raw_evs) / len(raw_evs), 3)
        avg_clv = round(sum(clvs) / len(clvs), 3)

        if avg_raw_ev and avg_raw_ev > 0 and n_clv >= 20:
            derived = avg_clv / avg_raw_ev if avg_clv > 0 else FALLBACK_SHRINK
            shrink = round(max(MIN_SHRINK, min(MAX_SHRINK, derived)), 4)

    phase = 1 if n_clv < PHASE1_MAX else (2 if n_clv < PHASE2_MAX else 3)

    if n_clv == 0:
        label = "Early calibration (no data yet)"
    elif n_clv < PHASE1_MAX:
        label = f"Early calibration (N={n_clv})"
    elif n_clv < PHASE2_MAX:
        label = f"Calibrated (N={n_clv})"
    else:
        label = f"Full calibration (N={n_clv})"

    # ── Bucket analysis (raw EV buckets: 5-15%, 15-25%, 25%+) ─────────────
    bucket_data = _compute_ev_buckets(with_clv)

    # ── Segment breakdown ──────────────────────────────────────────────────
    segment_data = _compute_segments(with_clv)

    result = {
        "n_total": n_total,
        "n_clv": n_clv,
        "n_outcome": n_outcome,
        "avg_raw_ev": avg_raw_ev,
        "avg_clv": avg_clv,
        "shrink_factor": shrink,
        "phase": phase,
        "label": label,
        "bucket_data": bucket_data,
        "segment_data": segment_data,
    }
    _stats_cache = result
    _stats_cache_ts = now

    # Persist to DB asynchronously
    _persist_stats(result)
    return result


def _compute_ev_buckets(rows: list[dict]) -> dict:
    """Group by raw EV bucket and compute avg CLV per bucket."""
    buckets: dict[str, list] = {
        "0-10%": [], "10-20%": [], "20-30%": [], "30%+": [],
    }
    for r in rows:
        ev = _to_ev_pct(r)
        clv = r.get("clv_pct")
        if clv is None:
            continue
        if ev < 10:
            buckets["0-10%"].append(clv)
        elif ev < 20:
            buckets["10-20%"].append(clv)
        elif ev < 30:
            buckets["20-30%"].append(clv)
        else:
            buckets["30%+"].append(clv)

    out = {}
    for label, vals in buckets.items():
        if vals:
            out[label] = {
                "n": len(vals),
                "avg_clv": round(sum(vals) / len(vals), 3),
                "positive_rate": round(sum(1 for v in vals if v > 0) / len(vals), 3),
            }
    return out


def _compute_segments(rows: list[dict]) -> dict:
    """Group by market_type and league_tier."""
    segments: dict[str, list] = {}
    for r in rows:
        mt = r.get("market_type") or classify_market(r.get("market", ""))
        lt = r.get("league_tier") or classify_league(r.get("league", ""))
        key = f"{mt}_{lt}"
        clv = r.get("clv_pct")
        ev = r.get("ev_sim") or r.get("edge_percentage") or 0
        if clv is None:
            continue
        if key not in segments:
            segments[key] = []
        segments[key].append({"clv": clv, "ev": _to_ev_pct(r)})

    out = {}
    for seg, items in segments.items():
        if items:
            clvs = [x["clv"] for x in items]
            evs = [x["ev"] for x in items if x["ev"] > 0]
            avg_raw = sum(evs) / len(evs) if evs else None
            avg_clv = sum(clvs) / len(clvs)
            shrink = None
            if avg_raw and avg_raw > 0 and avg_clv > 0:
                shrink = round(
                    max(MIN_SHRINK, min(MAX_SHRINK, avg_clv / avg_raw)), 4
                )
            out[seg] = {
                "n": len(items),
                "avg_raw_ev": round(avg_raw, 3) if avg_raw else None,
                "avg_clv": round(avg_clv, 3),
                "shrink": shrink,
            }
    return out


def _persist_stats(stats: dict) -> None:
    """Save calibration snapshot to calibration_stats table."""
    import json as _json
    try:
        from db_helper import db_helper
        db_helper.execute(
            """
            INSERT INTO calibration_stats
                (n_total, n_with_clv, n_with_outcome, avg_raw_ev, avg_clv,
                 global_shrink_factor, phase, segment_data, bucket_data)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                stats["n_total"],
                stats["n_clv"],
                stats["n_outcome"],
                stats["avg_raw_ev"],
                stats["avg_clv"],
                stats["shrink_factor"],
                stats["phase"],
                _json.dumps(stats["segment_data"]),
                _json.dumps(stats["bucket_data"]),
            ),
            fetch="none",
        )
    except Exception:
        pass


# ─── Core calibration function ────────────────────────────────────────────────
def calibrate_ev(
    raw_ev: float,
    market: str = "",
    league: str = "",
    odds: float = 0.0,
) -> dict:
    """
    Apply calibration shrinkage to a raw EV figure.

    Args:
        raw_ev   : raw EV% from the engine (e.g. 24.5)
        market   : market label, used for segment lookup
        league   : league name, used for segment lookup
        odds     : decimal odds, used for odds_bucket lookup

    Returns dict:
        calibrated_ev    : shrunk EV for display (float)
        shrink_factor    : factor applied
        label            : UI string ("Early calibration (N=23)")
        phase            : 1 | 2 | 3
        n                : number of picks in calibration set
    """
    stats = get_calibration_stats()
    shrink = stats["shrink_factor"]

    # Phase 2+: use segment-specific shrink if available
    if stats["phase"] >= 2 and stats.get("segment_data"):
        mt = classify_market(market)
        lt = classify_league(league)
        seg_key = f"{mt}_{lt}"
        seg = stats["segment_data"].get(seg_key, {})
        seg_shrink = seg.get("shrink")
        if seg_shrink is not None and seg.get("n", 0) >= 20:
            shrink = seg_shrink

    calibrated = round(raw_ev * shrink, 2)

    return {
        "calibrated_ev": calibrated,
        "shrink_factor": shrink,
        "label": stats["label"],
        "phase": stats["phase"],
        "n": stats["n_clv"],
    }


def calibrate_prob(raw_prob: float, market: str = "", league: str = "") -> float:
    """
    Shrink raw model probability toward implied probability.
    This preserves ranking while reducing overconfidence.

    calibrated_prob ≈ implied_prob + shrink * (raw_prob - implied_prob)
    """
    stats = get_calibration_stats()
    shrink = stats["shrink_factor"]
    # We can't shrink toward implied without knowing odds, so use global shrink
    # as a blending factor: pull raw_prob toward 0.5 by (1 - shrink)
    blend = shrink
    calibrated = blend * raw_prob + (1 - blend) * 0.5
    return round(max(0.05, min(0.95, calibrated)), 6)


# ─── Backfill utility ────────────────────────────────────────────────────────
_BACKFILL_COLS = ["id", "edge_percentage", "ev_sim", "market", "league", "odds"]


def backfill_calibrated_ev(batch_size: int = 500) -> int:
    """
    Backfill calibrated_ev_pct for existing picks that don't have it yet.
    Returns number of rows updated.
    """
    try:
        from db_helper import db_helper
        rows = db_helper.execute(
            """
            SELECT id, edge_percentage, ev_sim, market, league, odds
            FROM football_opportunities
            WHERE calibrated_ev_pct IS NULL
              AND mode IN ('PROD', 'LEARNING')
              AND (edge_percentage IS NOT NULL OR ev_sim IS NOT NULL)
            LIMIT %s
            """,
            (batch_size,),
            fetch="all",
        )
        if not rows:
            return 0

        # fetchall() returns tuples — map to dicts
        records = [dict(zip(_BACKFILL_COLS, r)) for r in rows]

        updated = 0
        for r in records:
            raw_ev = _to_ev_pct(r)
            if raw_ev <= 0:
                continue
            result = calibrate_ev(
                raw_ev=raw_ev,
                market=r.get("market", ""),
                league=r.get("league", ""),
                odds=float(r.get("odds") or 0),
            )
            db_helper.execute(
                """
                UPDATE football_opportunities
                SET calibrated_ev_pct = %s,
                    calibration_version = %s
                WHERE id = %s
                """,
                (
                    result["calibrated_ev"],
                    f"phase{result['phase']}_shrink{result['shrink_factor']}",
                    r["id"],
                ),
                fetch="none",
            )
            updated += 1

        logger.info(f"[Calibrator] Backfilled {updated} rows")
        return updated
    except Exception as e:
        logger.error(f"[Calibrator] Backfill failed: {e}")
        return 0


# ─── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Model Calibrator — self-test ===\n")
    stats = get_calibration_stats()
    print(f"Phase      : {stats['phase']}")
    print(f"N (CLV)    : {stats['n_clv']}")
    print(f"Avg raw EV : {stats['avg_raw_ev']}%")
    print(f"Avg CLV    : {stats['avg_clv']}%")
    print(f"Shrink     : {stats['shrink_factor']}")
    print(f"Label      : {stats['label']}")
    print()
    print("Bucket breakdown:")
    for b, d in stats.get("bucket_data", {}).items():
        print(f"  {b:12s}  N={d['n']:3d}  avg_clv={d['avg_clv']:+.2f}%  pos_rate={d['positive_rate']:.0%}")
    print()
    print("Segment breakdown:")
    for s, d in stats.get("segment_data", {}).items():
        shrink_str = f"shrink={d['shrink']}" if d.get("shrink") else "shrink=pending"
        print(f"  {s:25s}  N={d['n']:3d}  raw={d['avg_raw_ev']}%  clv={d['avg_clv']:+.2f}%  {shrink_str}")
    print()
    print("Example calibrations:")
    for ev in [8.0, 12.0, 18.0, 24.5, 30.0]:
        r = calibrate_ev(ev, market="Over 2.5", league="Premier League", odds=2.0)
        print(f"  raw {ev:5.1f}% → calibrated {r['calibrated_ev']:5.2f}%  (shrink={r['shrink_factor']})")

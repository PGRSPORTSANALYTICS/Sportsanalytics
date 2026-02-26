"""
Smart Picks Engine — Daily Top 10

Generates exactly 10 curated Smart Picks per day based on SmartScore.
Posts to Discord smart-picks channel at 10:00 server time.

STRICT RULES:
- Odds range: 1.75 – 2.10
- No EV, no implied probability, no unit sizing, no odds shopping
- One pick per match, max 2 per league
- SmartScore-based ranking (NOT EV-based)
- Posted once per day, locked after posting
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("smart_picks_engine")

try:
    from db_helper import db_helper
except ImportError:
    logger.error("Could not import db_helper")
    raise


SMART_PICKS_WEBHOOK = os.getenv("DISCORD_WH_SMART_PICKS", "")

SMART_SCORE_WEIGHTS = {
    "model_prob": 0.40,
    "trust_score": 0.25,
    "line_stability": 0.15,
    "form_trend": 0.20,
}

CONFIDENCE_TIERS = {
    "Strong": 75,
    "Medium": 55,
    "Low": 0,
}

MODEL_GRADE_TIERS = {
    "A": 0.55,
    "B": 0.45,
    "C": 0.0,
}


def _get_server_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _already_posted_today() -> bool:
    """Returns True if picks were already successfully posted to Discord today."""
    today = _get_server_date()
    row = db_helper.execute("""
        SELECT COUNT(*) FROM smart_picks WHERE pick_date = %s AND discord_posted = TRUE
    """, (today,), fetch='one')
    return row is not None and row[0] > 0


def _picks_exist_today() -> bool:
    """Returns True if any picks (posted or not) were already generated today."""
    today = _get_server_date()
    row = db_helper.execute("""
        SELECT COUNT(*) FROM smart_picks WHERE pick_date = %s
    """, (today,), fetch='one')
    return row is not None and row[0] > 0


def _get_todays_picks_from_db() -> List[Dict]:
    """Fetch today's picks from DB (for re-posting if Discord post failed)."""
    today = _get_server_date()
    rows = db_helper.execute("""
        SELECT home_team, away_team, league, market, selection, odds, smart_score, confidence, model_grade
        FROM smart_picks WHERE pick_date = %s ORDER BY smart_score DESC
    """, (today,), fetch='all')
    if not rows:
        return []
    return [
        {
            "home_team": r[0], "away_team": r[1], "league": r[2],
            "market": r[3], "selection": r[4], "odds": r[5],
            "smart_score": r[6], "confidence": r[7], "model_grade": r[8]
        }
        for r in rows
    ]


def _mark_discord_posted_today():
    """Mark all today's picks as discord_posted = TRUE."""
    today = _get_server_date()
    db_helper.execute("""
        UPDATE smart_picks SET discord_posted = TRUE WHERE pick_date = %s
    """, (today,))


def _ensure_table():
    db_helper.execute("""
        CREATE TABLE IF NOT EXISTS smart_picks (
            id SERIAL PRIMARY KEY,
            pick_date TEXT NOT NULL,
            home_team TEXT,
            away_team TEXT,
            league TEXT,
            market TEXT,
            selection TEXT,
            odds REAL,
            smart_score REAL,
            confidence TEXT,
            model_grade TEXT,
            discord_posted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    db_helper.execute("""
        ALTER TABLE smart_picks ADD COLUMN IF NOT EXISTS discord_posted BOOLEAN DEFAULT FALSE
    """)


def _compute_trust_score(row: Dict) -> float:
    trust = row.get("trust_level", "L3")
    mapping = {"L1": 95, "L2": 70, "L3": 45}
    return mapping.get(trust, 45)


def _compute_line_stability(row: Dict) -> float:
    odds = float(row.get("odds", 0) or 0)
    open_odds = float(row.get("open_odds", 0) or 0)
    if open_odds <= 0 or odds <= 0:
        return 50.0
    drift = abs(odds - open_odds) / open_odds
    if drift < 0.02:
        return 95.0
    elif drift < 0.05:
        return 75.0
    elif drift < 0.10:
        return 55.0
    else:
        return 30.0


def _compute_form_trend(row: Dict) -> float:
    analysis = row.get("analysis", "{}")
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except:
            analysis = {}
    if not isinstance(analysis, dict):
        analysis = {}

    form_score = analysis.get("form_score", 0)
    if form_score:
        return min(max(float(form_score), 0), 100)

    confidence = float(row.get("confidence", 0) or 0)
    if confidence > 0:
        return min(confidence, 100)

    return 50.0


def _compute_smart_score(row: Dict) -> float:
    raw_prob = row.get("model_prob")
    model_prob = (float(raw_prob) if raw_prob is not None else 0.55) * 100
    trust = _compute_trust_score(row)
    stability = _compute_line_stability(row)
    form = _compute_form_trend(row)

    score = (
        model_prob * SMART_SCORE_WEIGHTS["model_prob"]
        + trust * SMART_SCORE_WEIGHTS["trust_score"]
        + stability * SMART_SCORE_WEIGHTS["line_stability"]
        + form * SMART_SCORE_WEIGHTS["form_trend"]
    )

    if row.get("bet_placed") and row.get("mode") == "PROD":
        score += 15

    return round(score, 2)


def _get_confidence(score: float) -> str:
    if score >= CONFIDENCE_TIERS["Strong"]:
        return "Strong"
    elif score >= CONFIDENCE_TIERS["Medium"]:
        return "Medium"
    return "Low"


def _get_model_grade(row: Dict) -> str:
    raw = row.get("model_prob")
    prob = float(raw) if raw is not None else 0.55
    if prob >= MODEL_GRADE_TIERS["A"]:
        return "A"
    elif prob >= MODEL_GRADE_TIERS["B"]:
        return "B"
    return "C"


def _fetch_candidates() -> List[Dict]:
    today = _get_server_date()
    columns = [
        "id", "home_team", "away_team", "league", "market", "selection", "odds",
        "model_prob", "trust_level", "open_odds", "confidence",
        "analysis", "mode", "bet_placed"
    ]

    rows = db_helper.execute("""
        SELECT id, home_team, away_team, league, market, selection, odds,
               model_prob, trust_level, open_odds, confidence,
               analysis, mode, bet_placed
        FROM football_opportunities
        WHERE match_date = %s
        AND odds >= 1.75 AND odds <= 2.10
        AND status = 'pending'
        ORDER BY id
    """, (today,), fetch='all')

    if rows and len(rows) >= 5:
        return [dict(zip(columns, r)) for r in rows]

    logger.info(f"Only {len(rows) if rows else 0} candidates in football_opportunities — using all_bets fallback")

    fallback_rows = db_helper.execute("""
        SELECT id, home_team, away_team,
               NULL as league, 'Value Single' as market,
               selection, odds,
               NULL as model_prob, NULL as trust_level, NULL as open_odds,
               NULL as confidence, NULL as analysis,
               mode, true as bet_placed
        FROM all_bets
        WHERE DATE(created_at AT TIME ZONE 'UTC') = %s::date
        AND odds >= 1.75 AND odds <= 2.10
        AND product = 'VALUE_SINGLE'
        AND mode = 'PROD'
        ORDER BY id ASC
    """, (today,), fetch='all')

    if not fallback_rows:
        return []

    return [dict(zip(columns, r)) for r in fallback_rows]


def _has_conflict(selection: str, existing_selection: str) -> bool:
    sel = selection.lower()
    existing = existing_selection.lower()
    if ("over" in sel and "under" in existing) or ("under" in sel and "over" in existing):
        return True
    if ("home" in sel and "away" in existing) or ("away" in sel and "home" in existing):
        return True
    return False


def _select_top_picks(candidates: List[Dict], target: int = 10) -> List[Dict]:
    seen_matches = {}
    league_count = {}
    selected = []

    for c in candidates:
        if len(selected) >= target:
            break

        match_key = f"{c['home_team']}_{c['away_team']}"
        league = c.get("league") or match_key
        sel = c.get("selection", "")

        if match_key in seen_matches:
            if _has_conflict(sel, seen_matches[match_key]):
                continue
            continue

        if league_count.get(league, 0) >= 2:
            continue

        selected.append(c)
        seen_matches[match_key] = sel
        league_count[league] = league_count.get(league, 0) + 1

    return selected


def generate_smart_picks() -> List[Dict]:
    _ensure_table()

    if _picks_exist_today():
        logger.info("Smart Picks already generated today — skipping to avoid duplicates")
        return []

    candidates = _fetch_candidates()
    if not candidates:
        logger.info("No candidates found for Smart Picks today")
        return []

    for c in candidates:
        c["smart_score"] = _compute_smart_score(c)

    candidates.sort(key=lambda x: x["smart_score"], reverse=True)

    picks = _select_top_picks(candidates, target=10)

    if not picks:
        logger.info("No qualifying Smart Picks after filtering")
        return []

    today = _get_server_date()
    for p in picks:
        p["confidence"] = _get_confidence(p["smart_score"])
        p["model_grade"] = _get_model_grade(p)
        db_helper.execute("""
            INSERT INTO smart_picks (pick_date, home_team, away_team, league, market, selection, odds, smart_score, confidence, model_grade)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            today,
            p.get("home_team", ""),
            p.get("away_team", ""),
            p.get("league", ""),
            p.get("market", ""),
            p.get("selection", ""),
            p.get("odds", 0),
            p.get("smart_score", 0),
            p["confidence"],
            p["model_grade"],
        ))

    logger.info(f"Generated {len(picks)} Smart Picks for {today}")
    return picks


def _format_discord_message(picks: List[Dict]) -> str:
    today = _get_server_date()
    lines = []
    lines.append(f"**PGR SMART PICKS – Daily Top 10**")
    lines.append(f"*{today}*")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    for i, p in enumerate(picks, 1):
        lines.append("")
        lines.append(f"**Smart Pick #{i}**")
        lines.append(f"League: {p.get('league') or 'Football'}")
        lines.append(f"Match: {p.get('home_team', '')} vs {p.get('away_team', '')}")
        lines.append(f"Selection: **{p.get('selection', 'N/A')}**")
        lines.append(f"Market: {p.get('market', 'N/A')}")
        lines.append(f"Odds: {float(p.get('odds', 0)):.2f}")
        lines.append(f"Confidence: {p.get('confidence', 'Low')}")
        lines.append(f"Model Grade: {p.get('model_grade', 'C')}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    lines.append("")
    lines.append("*Curated AI selections for recreational players. No staking advice.*")

    return "\n".join(lines)


def post_to_discord(picks: List[Dict]) -> bool:
    if not SMART_PICKS_WEBHOOK:
        logger.warning("DISCORD_WH_SMART_PICKS not set — cannot post Smart Picks")
        return False

    if not picks:
        logger.info("No picks to post")
        return False

    message = _format_discord_message(picks)

    try:
        resp = requests.post(
            SMART_PICKS_WEBHOOK,
            json={"content": message},
            timeout=15,
        )
        if resp.status_code in (200, 204):
            logger.info(f"Smart Picks posted to Discord ({len(picks)} picks)")
            _mark_discord_posted_today()
            return True
        else:
            logger.error(f"Discord post failed: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Discord post error: {e}")
        return False


def run_smart_picks():
    logger.info("========================================")
    logger.info("SMART PICKS ENGINE — Starting daily run")
    logger.info("========================================")

    picks = generate_smart_picks()

    if picks:
        posted = post_to_discord(picks)
        logger.info(f"Smart Picks complete: {len(picks)} picks, posted={posted}")
    elif not _already_posted_today():
        # Picks may be in DB but Discord post wasn't confirmed — retry
        db_picks = _get_todays_picks_from_db()
        if db_picks:
            logger.info(f"Smart Picks: {len(db_picks)} picks in DB but not confirmed posted — retrying Discord post")
            posted = post_to_discord(db_picks)
            logger.info(f"Smart Picks re-post complete: posted={posted}")
            picks = db_picks
        else:
            logger.info("Smart Picks complete: 0 picks generated")
    else:
        logger.info("Smart Picks already confirmed posted today — skipping")

    return picks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    run_smart_picks()

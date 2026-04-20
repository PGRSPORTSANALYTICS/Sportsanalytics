"""
Smart Value Engine — Daily Top 10

Generates exactly 10 curated Smart Value picks per day based on SmartScore.
Picks are stored in the DB and posted to the DISCORD_WH_SMART_PICKS channel.

STRICT RULES:
- Odds range: 1.75 – 2.30
- One pick per match, max 2 per league
- SmartScore-based ranking (NOT EV-based)
- Generated once per day, locked after generation
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


def _picks_exist_today() -> bool:
    """Returns True if any picks (posted or not) were already generated today."""
    today = _get_server_date()
    row = db_helper.execute("""
        SELECT COUNT(*) FROM smart_picks WHERE pick_date = %s
    """, (today,), fetch='one')
    return row is not None and row[0] > 0


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
            created_at TIMESTAMP DEFAULT NOW()
        )
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
        AND mode = 'PROD'
        AND odds >= 1.75 AND odds <= 2.30
        AND status = 'pending'
        AND selection NOT ILIKE '%%AH%%'
        AND selection NOT ILIKE '%%Asian%%'
        AND selection NOT ILIKE '%%Under 1.5%%'
        AND selection NOT ILIKE '%%Under 2.5%%'
        AND selection NOT ILIKE '%%Under 3.5%%'
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
        AND odds >= 1.75 AND odds <= 2.30
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


def _post_to_discord(picks: List[Dict], today: str) -> None:
    """Post Smart Value picks to the DISCORD_WH_SMART_PICKS channel."""
    webhook_url = os.environ.get("DISCORD_WH_SMART_PICKS")
    if not webhook_url:
        logger.warning("DISCORD_WH_SMART_PICKS not configured — skipping Discord post")
        return

    grade_emoji = {"A": "🟢", "B": "🟡", "C": "🔴"}
    conf_emoji  = {"Strong": "💪", "Medium": "👍", "Low": "🔵"}

    lines = []
    for i, p in enumerate(picks, 1):
        match = f"{p.get('home_team','')} vs {p.get('away_team','')}"
        league = p.get("league") or "–"
        sel    = p.get("selection", "–")
        odds   = p.get("odds", 0)
        score  = p.get("smart_score", 0)
        grade  = p.get("model_grade", "C")
        conf   = p.get("confidence", "Low")
        lines.append(
            f"{grade_emoji.get(grade,'⚪')} **{i}. {match}**\n"
            f"   {league} | {sel} @ `{odds:.2f}`\n"
            f"   SmartScore: **{score:.1f}** · {conf_emoji.get(conf,'')} {conf}"
        )

    header = f"📊 **Smart Value Picks — {today}** ({len(picks)} picks)\n" + "─" * 36
    chunk_size = 5
    for chunk_start in range(0, len(lines), chunk_size):
        chunk = lines[chunk_start:chunk_start + chunk_size]
        content = header + "\n\n" + "\n\n".join(chunk) if chunk_start == 0 else "\n\n".join(chunk)
        try:
            resp = requests.post(webhook_url, json={"content": content}, timeout=10)
            if resp.status_code not in (200, 204):
                logger.error(f"Discord webhook returned {resp.status_code}: {resp.text[:200]}")
            else:
                logger.info(f"Smart Picks posted to Discord (batch {chunk_start//chunk_size + 1})")
        except Exception as exc:
            logger.error(f"Discord post failed: {exc}")


def generate_smart_picks() -> List[Dict]:
    _ensure_table()

    if _picks_exist_today():
        logger.info("Smart Value already generated today — skipping to avoid duplicates")
        return []

    candidates = _fetch_candidates()
    if not candidates:
        logger.info("No candidates found for Smart Value today")
        return []

    for c in candidates:
        c["smart_score"] = _compute_smart_score(c)

    candidates.sort(key=lambda x: x["smart_score"], reverse=True)

    picks = _select_top_picks(candidates, target=10)

    if not picks:
        logger.info("No qualifying Smart Value after filtering")
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

    logger.info(f"Generated {len(picks)} Smart Value for {today}")
    return picks


def run_smart_picks() -> List[Dict]:
    """Generate, store, and post today's Smart Value picks to Discord."""
    if _picks_exist_today():
        logger.info("Smart Value: picks already generated today — skipping")
        return []

    logger.info("========================================")
    logger.info("SMART PICKS ENGINE — Starting daily run")
    logger.info("========================================")

    picks = generate_smart_picks()
    if picks:
        today = _get_server_date()
        _post_to_discord(picks, today)
    logger.info(f"Smart Value complete: {len(picks)} picks stored in DB")
    return picks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    run_smart_picks()

#!/usr/bin/env python3
"""
Smart Value Result Scanner
==========================
Settles Smart Value by joining to football_opportunities results.
Sends settled results to the DISCORD_WH_SMART_PICKS channel.

Runs every 30 minutes via combined_sports_runner.py.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict

from db_helper import DatabaseHelper

logger = logging.getLogger(__name__)


def _send_smart_pick_result(pick: dict) -> bool:
    """Post a settled Smart Pick result to Discord."""
    import requests

    webhook_url = os.environ.get("DISCORD_WH_SMART_PICKS")
    if not webhook_url:
        logger.warning("DISCORD_WH_SMART_PICKS not set — skipping Discord post")
        return False

    result = (pick.get("result") or "").upper()
    if result in ("WON", "WIN"):
        emoji, status, color = "✅", "WON", 0x2ECC71
        profit = round(float(pick.get("odds") or 2.0) - 1, 2)
    elif result in ("LOST", "LOSS"):
        emoji, status, color = "❌", "LOST", 0xE74C3C
        profit = -1.0
    elif result in ("VOID", "PUSH"):
        emoji, status, color = "↩️", "VOID", 0x95A5A6
        profit = 0.0
    else:
        return False

    grade    = pick.get("model_grade") or ""
    score_lbl = pick.get("actual_score") or "—"
    conf_lbl  = pick.get("confidence") or ""
    smart_scr = pick.get("smart_score") or 0

    fields = []
    if score_lbl and score_lbl != "—":
        fields.append({"name": "⚽ Score", "value": f"`{score_lbl}`", "inline": True})
    fields += [
        {"name": "📊 Odds",       "value": f"`{float(pick.get('odds') or 0):.2f}`", "inline": True},
        {"name": "💰 P/L",        "value": f"`{profit:+.2f}u`",                     "inline": True},
        {"name": "🎯 SmartScore", "value": f"`{float(smart_scr):.1f}`",              "inline": True},
        {"name": "Grade",         "value": f"`{grade}`",                             "inline": True},
        {"name": "Confidence",    "value": f"`{conf_lbl}`",                          "inline": True},
    ]

    embed = {
        "title": f"{emoji} Smart Pick {status} | {pick.get('selection','')}",
        "description": f"**{pick.get('home_team','')}** vs **{pick.get('away_team','')}**",
        "color": color,
        "fields": fields,
        "footer": {"text": f"{pick.get('league','')} • Smart Value"},
        "timestamp": datetime.utcnow().isoformat(),
    }

    results_webhook = os.environ.get("DISCORD_RESULTS_WEBHOOK")
    webhooks = [webhook_url]
    if results_webhook and results_webhook != webhook_url:
        webhooks.append(results_webhook)

    success = False
    for url in webhooks:
        try:
            resp = requests.post(url, json={"username": "PGR Smart Value", "embeds": [embed]}, timeout=8)
            if resp.status_code in (200, 204):
                success = True
            else:
                logger.warning(f"Discord HTTP {resp.status_code} for smart pick result")
        except Exception as e:
            logger.error(f"Discord post failed: {e}")

    return success


def run_smart_picks_settlement() -> Dict:
    """
    Main entry point called by combined_sports_runner.
    Joins unsettled smart_picks to football_opportunities results.
    Returns stats dict: {scanned, settled, discord_posted, errors}
    """
    stats = {"scanned": 0, "settled": 0, "discord_posted": 0, "errors": 0}
    db = DatabaseHelper()

    # Load unsettled smart_picks from the last 14 days
    try:
        rows = db.execute("""
            SELECT id, pick_date, home_team, away_team, league,
                   market, selection, odds, smart_score, confidence, model_grade
            FROM smart_picks
            WHERE result IS NULL
              AND pick_date::date >= CURRENT_DATE - INTERVAL '14 days'
            ORDER BY pick_date DESC
        """, fetch='all')
    except Exception as e:
        logger.error(f"smart_picks fetch error: {e}")
        stats["errors"] += 1
        return stats

    if not rows:
        logger.info("Smart Value settlement: nothing pending")
        return stats

    for row in rows:
        stats["scanned"] += 1
        sp_id       = row[0]
        pick_date   = str(row[1])        # YYYY-MM-DD text
        home_team   = row[2]
        away_team   = row[3]
        league      = row[4]
        market      = row[5]
        selection   = row[6]
        odds        = row[7]
        smart_score = row[8]
        confidence  = row[9]
        model_grade = row[10]

        # Look up settled result in football_opportunities.
        # STRICT: only trust PROD picks with bet_placed=true that have been properly
        # settled by the Results Engine. Avoids false positives from LEARNING / VALUE_OPP rows.
        try:
            opp = db.execute("""
                SELECT result, status
                FROM football_opportunities
                WHERE home_team ILIKE %s
                  AND away_team ILIKE %s
                  AND selection ILIKE %s
                  AND match_date::date BETWEEN %s::date - INTERVAL '1 day' AND %s::date + INTERVAL '1 day'
                  AND mode = 'PROD'
                  AND bet_placed = true
                  AND UPPER(status) IN ('SETTLED','WON','WIN','LOST','LOSS','VOID','PUSH')
                  AND UPPER(result) IN ('WON','WIN','LOST','LOSS','VOID','PUSH')
                  AND match_date::date <= CURRENT_DATE
                ORDER BY ABS(match_date::date - %s::date)
                LIMIT 1
            """, (home_team, away_team, selection, pick_date, pick_date, pick_date), fetch='one')
        except Exception as e:
            logger.error(f"Lookup error for smart_pick {sp_id}: {e}")
            stats["errors"] += 1
            continue

        if not opp:
            continue

        result_raw   = opp[0]
        result_upper = result_raw.upper() if result_raw else ""

        # Normalize result
        if result_upper in ("WON", "WIN"):
            settled_result = "WON"
        elif result_upper in ("LOST", "LOSS"):
            settled_result = "LOST"
        elif result_upper in ("VOID", "PUSH"):
            settled_result = "VOID"
        else:
            continue

        # Update smart_picks row
        try:
            db.execute("""
                UPDATE smart_picks
                SET result = %s, settled_at = NOW()
                WHERE id = %s
            """, (settled_result, sp_id))
            stats["settled"] += 1
            logger.info(f"✅ Smart Pick settled: {home_team} vs {away_team} | {selection} → {settled_result}")
        except Exception as e:
            logger.error(f"Update error for smart_pick {sp_id}: {e}")
            stats["errors"] += 1
            continue

        # Try to fetch actual score from analysis field
        try:
            score_row = db.execute("""
                SELECT analysis FROM football_opportunities
                WHERE home_team ILIKE %s AND away_team ILIKE %s
                  AND match_date::date BETWEEN %s::date - INTERVAL '1 day' AND %s::date + INTERVAL '1 day'
                  AND analysis IS NOT NULL
                LIMIT 1
            """, (home_team, away_team, pick_date, pick_date), fetch='one')
            import re as _re
            raw_analysis = score_row[0] if score_row else ""
            m = _re.search(r'(\d+)[:\-](\d+)', str(raw_analysis))
            actual_score = f"{m.group(1)}-{m.group(2)}" if m else "—"
        except Exception:
            actual_score = "—"

        # Send Discord result
        pick_dict = {
            "home_team": home_team,
            "away_team": away_team,
            "league": league,
            "market": market,
            "selection": selection,
            "odds": odds,
            "smart_score": smart_score,
            "confidence": confidence,
            "model_grade": model_grade,
            "result": settled_result,
            "actual_score": actual_score,
        }

        posted = _send_smart_pick_result(pick_dict)
        if posted:
            try:
                db.execute("""
                    UPDATE smart_picks SET discord_result_posted = TRUE WHERE id = %s
                """, (sp_id,))
                stats["discord_posted"] += 1
            except Exception:
                pass

    logger.info(
        f"Smart Value settlement: scanned={stats['scanned']} "
        f"settled={stats['settled']} discord={stats['discord_posted']} errors={stats['errors']}"
    )
    return stats

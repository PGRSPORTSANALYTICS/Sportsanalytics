"""
PROOF-OF-WORK POSTER
Posts CLV and edge evidence to WEBHOOK_PROOF Discord channel.

Format: pure market data — no wins/losses, no ROI.
  ✅ CLV example (odds when identified vs closing line)
  ✅ Edge identified (model vs market %)
  ❌ Never posts profit, ROI, or bet outcomes
"""

import os
import time
import logging
import requests
import db_helper

logger = logging.getLogger(__name__)

WEBHOOK_PROOF = os.getenv("WEBHOOK_PROOF", "")

MARKET_LABELS = {
    "BTTS_YES": "BTTS Yes", "BTTS_NO": "BTTS No",
    "HOME_WIN": "Home Win", "AWAY_WIN": "Away Win", "DRAW": "Draw",
    "FT_OVER_0_5": "Over 0.5", "FT_OVER_1_5": "Over 1.5",
    "FT_OVER_2_5": "Over 2.5", "FT_OVER_3_5": "Over 3.5",
    "FT_OVER_4_5": "Over 4.5", "FT_UNDER_2_5": "Under 2.5",
    "CORNERS_OVER_7_5": "Corners O7.5", "CORNERS_OVER_8_5": "Corners O8.5",
    "CORNERS_OVER_9_5": "Corners O9.5", "CORNERS_OVER_10_5": "Corners O10.5",
    "CARDS_OVER_2_5": "Cards O2.5", "CARDS_OVER_3_5": "Cards O3.5",
    "DC_HOME_DRAW": "DC Home/Draw", "DC_DRAW_AWAY": "DC Draw/Away",
    "Value Single": "1X2 / Market", "VALUE_OPP": "1X2 / Market",
    "Corners": "Corners", "Cards": "Cards",
}


def _label(market: str) -> str:
    return MARKET_LABELS.get(market, market.replace("_", " ").title())


def _fetch_model_data(bet_id: int) -> dict:
    """Fetch model_prob, ev, selection from DB."""
    try:
        row = db_helper.execute(
            "SELECT model_prob, ev, selection FROM football_opportunities WHERE id = %s",
            (bet_id,), fetch='one'
        )
        if row:
            return {
                "model_prob": float(row[0]) if row[0] else None,
                "ev":         float(row[1]) if row[1] else None,
                "selection":  row[2] or "",
            }
    except Exception as exc:
        logger.warning("proof_poster: DB fetch failed for bet %d: %s", bet_id, exc)
    return {}


def post_clv_proof(bet: dict, close_odds: float, clv: float, close_book: str,
                   mins_to_close: int | None = None) -> bool:
    """
    Post CLV proof embed to WEBHOOK_PROOF.

    Called by CLVService.save_clv() after a successful DB update.
    Only posts for positive CLV (confirmed edge) or significant CLV >= 3%.
    """
    if not WEBHOOK_PROOF:
        logger.debug("proof_poster: WEBHOOK_PROOF not set — skip")
        return False

    # Only post when market moved in our favour or significantly
    if clv < 2.5:
        logger.debug("proof_poster: CLV %.2f%% below threshold — skip bet %d", clv, bet['id'])
        return False

    model_data = _fetch_model_data(bet['id'])
    open_odds  = bet['open_odds']
    match_str  = f"{bet.get('home_team','?')} vs {bet.get('away_team','?')}"
    league     = (bet.get('league') or "").replace("soccer_", "").replace("_", " ").title()
    market_lbl = _label(bet.get('market', ''))
    selection  = model_data.get('selection') or bet.get('selection', '')

    model_prob = model_data.get('model_prob')
    ev         = model_data.get('ev')

    # Model & Market %
    market_pct = round(100 / open_odds, 1) if open_odds and open_odds > 1 else None
    model_pct  = None
    if model_prob:
        model_pct = round(model_prob if model_prob > 1 else model_prob * 100, 1)

    ev_str     = f"+{ev:.1f}%" if ev and ev >= 0 else (f"{ev:.1f}%" if ev else None)
    clv_str    = f"+{clv:.1f}%" if clv >= 0 else f"{clv:.1f}%"
    close_str  = f"{close_odds:.2f}"
    open_str   = f"{open_odds:.2f}"

    close_label = close_book.replace("Exchange", "").strip() if close_book else "sharp book"

    # Use selection as primary descriptor, fall back to market label
    # e.g. "Go Ahead Eagles -1.0 (AH)" is more useful than "Asian Handicap"
    market_display = selection if selection else market_lbl

    # Build description lines
    lines = [
        f"**{match_str}**",
        f"{league}  ·  *{market_display}*",
        "",
    ]

    # Block 1 — CLV (always shown)
    lines += [
        "```",
        f"CLV proof:",
        f"",
        f"Odds when identified : {open_str}",
        f"Closing odds         : {close_str}  [{close_label}]",
        f"CLV                  : {clv_str}",
        f"",
        f"Market moved → value confirmed ✅",
        "```",
    ]

    # Block 2 — Model vs Market (shown when data available)
    if model_pct and market_pct and ev_str:
        mins_txt = f"within {mins_to_close}min of kickoff" if mins_to_close and mins_to_close > 0 else "at close"
        lines += [
            "```",
            f"Edge identified:",
            f"",
            f"Model  : {model_pct}%",
            f"Market : {market_pct}%",
            f"Edge   : {ev_str}",
            f"",
            f"→ Market corrected {mins_txt}",
            "```",
        ]

    description = "\n".join(lines)

    embed = {
        "title": f"📊 CLV Proof  ·  {clv_str}",
        "description": description,
        "color": 0x22c55e,  # green
        "footer": {
            "text": "PGR Analytics · CLV = (open/close − 1) × 100  ·  Not financial advice"
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        resp = requests.post(
            WEBHOOK_PROOF,
            json={"embeds": [embed]},
            timeout=8,
        )
        if resp.status_code in (200, 204):
            logger.info("✅ proof_poster: posted CLV %s for bet %d (%s)", clv_str, bet['id'], match_str)
            return True
        else:
            logger.warning("proof_poster: webhook %d — %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.error("proof_poster: request failed: %s", exc)

    return False

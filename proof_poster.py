"""
PROOF-OF-WORK POSTER
Posts CLV and edge evidence to WEBHOOK_PROOF Discord channel.

Format: pure market data — no wins/losses, no ROI.
  ✅ CLV example (odds when identified vs closing line)
  ✅ Edge identified (model vs market %)
  ❌ Never posts profit, ROI, or bet outcomes

Two posting modes:
  1. Real-time: called by CLVService.save_clv() for CLV >= 2.0%
  2. Daily digest: called at 22:00 UTC — summarises all positive CLV from the day
"""

import os
import time
import logging
import requests
import db_helper as _db_module

logger = logging.getLogger(__name__)

WEBHOOK_PROOF = os.getenv("WEBHOOK_PROOF", "")

# Real-time post threshold — lower than before (was 2.5%)
REALTIME_CLV_THRESHOLD = 2.0

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
        row = _db_module.db_helper.execute(
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


def _mark_proof_sent(bet_id: int) -> None:
    """Mark pick as proof-posted to avoid duplicate Discord posts."""
    try:
        _db_module.db_helper.execute(
            "UPDATE football_opportunities SET proof_sent = TRUE WHERE id = %s",
            (bet_id,)
        )
    except Exception as exc:
        logger.debug("proof_poster: could not mark proof_sent for %d: %s", bet_id, exc)


def _send_embed(embed: dict, label: str = "") -> bool:
    """Send a single embed to WEBHOOK_PROOF. Returns True on success."""
    if not WEBHOOK_PROOF:
        logger.debug("proof_poster: WEBHOOK_PROOF not set — skip")
        return False
    try:
        resp = requests.post(
            WEBHOOK_PROOF,
            json={"embeds": [embed]},
            timeout=8,
        )
        if resp.status_code in (200, 204):
            logger.info("✅ proof_poster: posted %s", label)
            return True
        else:
            logger.warning("proof_poster: webhook %d — %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.error("proof_poster: request failed: %s", exc)
    return False


# ─────────────────────────────────────────────────────────
# 1. REAL-TIME: called by CLVService.save_clv()
# ─────────────────────────────────────────────────────────

def post_clv_proof(bet: dict, close_odds: float, clv: float, close_book: str,
                   mins_to_close: int | None = None) -> bool:
    """
    Post CLV proof embed to WEBHOOK_PROOF.
    Called by CLVService.save_clv() after a successful DB update.

    - Threshold: CLV >= 2.0% (was 2.5%)
    - Deduplication: proof_sent flag in DB prevents double-posting
    """
    if not WEBHOOK_PROOF:
        return False

    # Deduplication guard
    try:
        already = _db_module.db_helper.execute(
            "SELECT proof_sent FROM football_opportunities WHERE id = %s",
            (bet['id'],), fetch='one'
        )
        if already and already[0]:
            logger.debug("proof_poster: bet %d already posted — skip", bet['id'])
            return False
    except Exception:
        pass

    if clv < REALTIME_CLV_THRESHOLD:
        logger.debug("proof_poster: CLV %.2f%% below %.1f%% threshold — skip bet %d",
                     clv, REALTIME_CLV_THRESHOLD, bet['id'])
        return False

    model_data = _fetch_model_data(bet['id'])
    open_odds  = bet['open_odds']
    match_str  = f"{bet.get('home_team','?')} vs {bet.get('away_team','?')}"
    league     = (bet.get('league') or "").replace("soccer_", "").replace("_", " ").title()
    market_lbl = _label(bet.get('market', ''))
    selection  = model_data.get('selection') or bet.get('selection', '')

    model_prob = model_data.get('model_prob')
    ev         = model_data.get('ev')

    market_pct = round(100 / open_odds, 1) if open_odds and open_odds > 1 else None
    model_pct  = None
    if model_prob:
        model_pct = round(model_prob if model_prob > 1 else model_prob * 100, 1)

    ev_str    = f"+{ev:.1f}%" if ev and ev >= 0 else (f"{ev:.1f}%" if ev else None)
    clv_str   = f"+{clv:.1f}%"
    close_str = f"{close_odds:.2f}"
    open_str  = f"{open_odds:.2f}"
    close_lbl = close_book.replace("Exchange", "").strip() if close_book else "sharp book"
    market_display = selection if selection else market_lbl

    lines = [
        f"**{match_str}**",
        f"{league}  ·  *{market_display}*",
        "",
        "```",
        "CLV proof:",
        "",
        f"Odds when identified : {open_str}",
        f"Closing odds         : {close_str}  [{close_lbl}]",
        f"CLV                  : {clv_str}",
        "",
        "Market moved → value confirmed ✅",
        "```",
    ]

    if model_pct and market_pct and ev_str:
        mins_txt = f"within {mins_to_close}min of kickoff" if mins_to_close and mins_to_close > 0 else "at close"
        lines += [
            "```",
            "Edge identified:",
            "",
            f"Model  : {model_pct}%",
            f"Market : {market_pct}%",
            f"Edge   : {ev_str}",
            "",
            f"→ Market corrected {mins_txt}",
            "```",
        ]

    embed = {
        "title": f"📊 CLV Proof  ·  {clv_str}",
        "description": "\n".join(lines),
        "color": 0x22c55e,
        "footer": {"text": "PGR Analytics · CLV = (open/close − 1) × 100  ·  Not financial advice"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    ok = _send_embed(embed, label=f"CLV {clv_str} for bet {bet['id']} ({match_str})")
    if ok:
        _mark_proof_sent(bet['id'])
    return ok


# ─────────────────────────────────────────────────────────
# 2. DAILY DIGEST: called at 22:00 UTC
# ─────────────────────────────────────────────────────────

def post_daily_clv_digest() -> bool:
    """
    Daily CLV proof digest — posts a summary of all positive CLV captures
    from the last 24 hours. Runs at 22:00 UTC via combined_sports_runner.

    Includes ALL positive CLV (not just those above real-time threshold).
    Shows both confirmed beats and misses for transparency.
    """
    if not WEBHOOK_PROOF:
        logger.debug("proof_poster: WEBHOOK_PROOF not set — skip digest")
        return False

    try:
        day_start = int(time.time()) - 86400

        rows = _db_module.db_helper.execute("""
            SELECT
                home_team, away_team, league, market, selection,
                open_odds, close_odds, clv_pct, clv_source_book, steam_flag,
                close_ts, id
            FROM football_opportunities
            WHERE close_ts >= %s
              AND clv_pct IS NOT NULL
              AND clv_pct != 0
            ORDER BY clv_pct DESC
        """, (day_start,), fetch='all') or []

    except Exception as exc:
        logger.error("proof_poster digest: DB fetch failed: %s", exc)
        return False

    if not rows:
        logger.info("proof_poster digest: no CLV captures in last 24h — skip")
        return False

    positive = [r for r in rows if r[7] > 0]
    negative = [r for r in rows if r[7] < 0]

    pos_count  = len(positive)
    neg_count  = len(negative)
    total      = len(rows)
    beat_rate  = round(100 * pos_count / total, 1) if total else 0
    avg_pos    = round(sum(r[7] for r in positive) / pos_count, 2) if positive else 0
    avg_neg    = round(sum(r[7] for r in negative) / neg_count, 2) if negative else 0

    # Build pick lines (show top 8 positive + up to 3 notable negatives)
    pick_lines = []
    for r in positive[:8]:
        home, away, league, market, sel, open_o, close_o, clv, book, flag, close_ts, bid = r
        league_fmt = (league or "").replace("soccer_", "").replace("_", " ").title()
        mkt = sel or _label(market)
        pick_lines.append(
            f"✅  {clv:+.1f}%  {home} vs {away}  ·  {mkt}  [{league_fmt}]"
            f"  {open_o:.2f}→{close_o:.2f}"
        )

    if negative:
        pick_lines.append("")
        for r in negative[:3]:
            home, away, league, market, sel, open_o, close_o, clv, book, flag, close_ts, bid = r
            if abs(clv) < 2:
                continue
            mkt = sel or _label(market)
            pick_lines.append(
                f"❌  {clv:+.1f}%  {home} vs {away}  ·  {mkt}  {open_o:.2f}→{close_o:.2f}"
            )

    # Colour: green if majority positive, amber if mixed, red if majority negative
    color = 0x22c55e if beat_rate >= 55 else (0xf59e0b if beat_rate >= 40 else 0xef4444)

    summary_block = "\n".join([
        "```",
        f"CLV digest  ({total} captures today)",
        "",
        f"Beat closing line  : {pos_count}/{total}  ({beat_rate}%)",
        f"Avg positive CLV   : +{avg_pos}%",
        f"Avg negative CLV   :  {avg_neg}%",
        "```",
    ])

    picks_block = ("```\n" + "\n".join(pick_lines) + "\n```") if pick_lines else ""

    description = "\n".join(filter(None, [
        summary_block,
        picks_block,
    ]))

    embed = {
        "title": f"📈 Daily CLV Proof  ·  {beat_rate}% beat rate",
        "description": description,
        "color": color,
        "footer": {"text": "PGR Analytics · Closing Line Value = market beat rate  ·  Not financial advice"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    ok = _send_embed(embed, label=f"daily CLV digest ({pos_count}/{total} positive)")
    return ok

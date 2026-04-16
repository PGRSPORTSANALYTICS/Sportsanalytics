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

WEBHOOK_PROOF          = os.getenv("WEBHOOK_PROOF", "")
WEBHOOK_RESULTS        = os.getenv("DISCORD_RESULTS_WEBHOOK", "")

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

    # Block soft/bronze tier from WEBHOOK_PROOF — not sharp-book proof
    book_str = close_book or ''
    if '(soft)' in book_str:
        logger.info("proof_poster: skip WEBHOOK_PROOF — bronze source, not sharp proof (bet=%d, book=%s)",
                    bet['id'], book_str)
        return False

    # Block single-source captures from WEBHOOK_PROOF — unreliable as public proof
    # Exception: approx line from Pinnacle is allowed (sharp source, different line)
    import re as _re
    is_approx_sharp = '(line moved' in book_str and 'Pinnacle' in book_str
    n_sources = 1
    m = _re.search(r'n=(\d+)', book_str)
    if m:
        n_sources = int(m.group(1))
    if n_sources < 2 and not is_approx_sharp:
        logger.info("proof_poster: skip WEBHOOK_PROOF — n=%d source(s) only (book=%s, bet=%d)",
                    n_sources, book_str, bet['id'])
        return False

    # Block suspiciously high CLV — likely data noise from thin markets
    if clv > 30.0:
        logger.warning("proof_poster: CLV %.1f%% >30%% — likely data noise, skip WEBHOOK_PROOF (bet=%d)",
                       clv, bet['id'])
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


# ─────────────────────────────────────────────────────────
# 3. CLV BUCKET ANALYSIS — posts to DISCORD_RESULTS_WEBHOOK
# ─────────────────────────────────────────────────────────

def post_clv_buckets() -> bool:
    """
    Post CLV bucket win-rate analysis to the results Discord channel.

    Buckets: +5%+, +3-5%, +1-3%, +0-1%, Negative CLV
    Shows: n picks, win rate, avg CLV per bucket.
    Hypothesis: higher CLV = higher win rate.
    """
    if not WEBHOOK_RESULTS:
        logger.warning("proof_poster: DISCORD_RESULTS_WEBHOOK not set — skip CLV buckets")
        return False

    try:
        rows = _db_module.db_helper.execute("""
            SELECT
                CASE
                    WHEN clv_pct >= 5   THEN 4
                    WHEN clv_pct >= 3   THEN 3
                    WHEN clv_pct >= 1   THEN 2
                    WHEN clv_pct >= 0   THEN 1
                    ELSE                     0
                END                                              AS bucket_ord,
                COUNT(*)                                         AS total,
                SUM(CASE WHEN outcome = 'won'  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome = 'lost' THEN 1 ELSE 0 END) AS losses,
                ROUND(AVG(clv_pct)::numeric, 2)                 AS avg_clv
            FROM football_opportunities
            WHERE clv_pct IS NOT NULL
              AND outcome IN ('won', 'lost')
              AND match_id NOT LIKE 'seed_%%'
            GROUP BY bucket_ord
            ORDER BY bucket_ord DESC
        """, fetch='all') or []

    except Exception as exc:
        logger.error("proof_poster clv_buckets: DB fetch failed: %s", exc)
        return False

    if not rows:
        logger.info("proof_poster clv_buckets: no settled picks with CLV — skip")
        return False

    BUCKET_LABELS = {4: "+5%+", 3: "+3–5%", 2: "+1–3%", 1: "+0–1%", 0: "Negative"}
    BUCKET_ICONS  = {4: "🟢", 3: "🟡", 2: "🔵", 1: "⚪", 0: "🔴"}

    lines = []
    total_all = sum(r[1] for r in rows)
    wins_all  = sum(r[2] for r in rows)
    wr_all    = round(100 * wins_all / total_all, 1) if total_all else 0

    for r in rows:
        b_ord, total, wins, losses, avg_clv = r[0], r[1], r[2], r[3], r[4]
        wr = round(100 * wins / total, 1) if total > 0 else 0
        label = BUCKET_LABELS.get(b_ord, "?")
        icon  = BUCKET_ICONS.get(b_ord, "•")
        bar_n = round(wr / 10)   # 0–10 blocks
        bar   = "█" * bar_n + "░" * (10 - bar_n)
        lines.append(
            f"{icon}  {label:<10}  {bar}  {wr}%  ({wins}/{total}  avg CLV {avg_clv:+.1f}%)"
        )

    block = "\n".join(["```", *lines, "", f"Overall win rate  :  {wins_all}/{total_all}  ({wr_all}%)", "```"])

    # Color: green if top bucket beats overall, amber otherwise
    top_bucket = rows[0]
    top_wr = round(100 * top_bucket[2] / top_bucket[1], 1) if top_bucket[1] else 0
    color = 0x22c55e if top_wr > wr_all else 0xf59e0b

    embed = {
        "title": "📊 CLV Bucket Analysis — Win Rate by Closing Line Value",
        "description": (
            "Does beating the closing line predict wins?\n"
            f"Based on **{total_all} settled picks** with CLV tracking.\n\n"
            + block
            + "\n\n*Higher CLV = you got a better price than where the market settled.*"
        ),
        "color": color,
        "footer": {"text": "PGR Analytics · CLV Bucket Report · Not financial advice"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        resp = requests.post(
            WEBHOOK_RESULTS,
            json={"embeds": [embed]},
            timeout=8,
        )
        if resp.status_code in (200, 204):
            logger.info("✅ proof_poster: CLV bucket report posted")
            return True
        else:
            logger.warning("proof_poster clv_buckets: webhook %d — %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.error("proof_poster clv_buckets: request failed: %s", exc)
    return False


# ─────────────────────────────────────────────────────────────────
# 4. PER-PICK CLV CAPTURE — posts to DISCORD_RESULTS_WEBHOOK
# ─────────────────────────────────────────────────────────────────

def post_clv_capture(bet: dict, close_odds: float, clv: float,
                     close_book: str, mins_to_close: int | None = None) -> bool:
    """
    Post a one-line CLV result to DISCORD_RESULTS_WEBHOOK for EVERY pick
    when closing odds are captured — regardless of positive or negative CLV.

    Lets the user see pick-by-pick: open odds → close odds → CLV result.
    No threshold — all picks reported. Soft sources (api_football) are silently skipped.
    """
    if not WEBHOOK_RESULTS:
        return False

    # Soft/unreliable sources — save to DB only, never post to Discord
    _book_lower = (close_book or '').lower()
    if '(soft)' in _book_lower or 'api_football' in _book_lower or 'api-football' in _book_lower:
        return False

    try:
        open_odds = float(bet.get('open_odds') or 0)
        market    = _label(bet.get('market', ''))
        selection = bet.get('selection') or market
        home      = bet.get('home_team', '?')
        away      = bet.get('away_team', '?')
        league    = (bet.get('league') or '').replace('soccer_', '').replace('_', ' ').title()
        book_lbl  = (close_book or 'sharp').replace('Exchange', '').strip()

        beat    = clv >= 0
        icon    = '✅' if beat else '❌'
        clv_str = f'+{clv:.2f}%' if beat else f'{clv:.2f}%'

        open_str  = f'{open_odds:.2f}' if open_odds else '—'
        close_str = f'{close_odds:.2f}'

        # Data quality check — approx line, extreme CLV
        import re as _re
        quality_warn = ''
        is_approx = '(line moved' in book_lbl
        if is_approx:
            # Extract line info: "vs Pinnacle (line moved 2.5 → 2.25)"
            line_m = _re.search(r'line moved ([\d.]+)\s*→\s*([\d.]+)', book_lbl)
            if line_m:
                quality_warn = f'\n⚠️ *Approx CLV — linje rördes {line_m.group(1)} → {line_m.group(2)} hos Pinnacle*'
            else:
                quality_warn = '\n⚠️ *Approx CLV — Pinnacle erbjöd annan linje*'
        elif clv > 25.0:
            quality_warn = '\n⚠️ *Extremt hög CLV — kontrollera datakvalitet*'

        timing = ''
        if mins_to_close is not None:
            timing = f'  ·  {mins_to_close}min before KO'

        desc = (
            f"{icon} **{home} vs {away}**\n"
            f"{league}  ·  *{selection}*\n\n"
            f"```\n"
            f"{'Du tog':<20} {open_str}\n"
            f"{'Stängning ({})'.format(book_lbl):<20} {close_str}\n"
            f"{'CLV':<20} {clv_str}\n"
            f"```"
            f"{timing}"
            f"{quality_warn}"
        )

        color = 0x22c55e if (beat and not quality_warn) else (0xf59e0b if quality_warn else 0xef4444)

        embed = {
            "description": desc,
            "color": color,
            "footer": {"text": "PGR Analytics · CLV capture"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        resp = requests.post(
            WEBHOOK_RESULTS,
            json={"embeds": [embed]},
            timeout=8,
        )
        if resp.status_code in (200, 204):
            logger.debug("proof_poster: CLV capture posted for bet %s (CLV %s%%)",
                         bet.get('id'), clv_str)
            return True
        else:
            logger.warning("proof_poster clv_capture: webhook %d", resp.status_code)
    except Exception as exc:
        logger.error("proof_poster clv_capture: %s", exc)
    return False


# ─────────────────────────────────────────────────────────────────
# 5. DAILY CLV SUMMARY — posts to DISCORD_RESULTS_WEBHOOK
# ─────────────────────────────────────────────────────────────────

def _clv_stats_query(since_epoch=None):
    """Fetch CLV stats from a given epoch. If None, fetches all-time."""
    where_extra = f"AND timestamp >= {since_epoch}" if since_epoch else ""
    return _db_module.db_helper.execute(f"""
        SELECT
            COUNT(*)                                                             AS total,
            COUNT(*) FILTER (WHERE clv_pct IS NOT NULL)                          AS clv_tracked,
            COUNT(*) FILTER (WHERE clv_pct > 0)                                  AS clv_pos,
            ROUND(AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL)::numeric, 2)  AS avg_clv,
            ROUND(AVG(clv_pct) FILTER (WHERE clv_pct > 0)::numeric, 2)          AS avg_clv_pos,
            SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END)                       AS wins,
            ROUND(SUM(
                CASE WHEN outcome='won' THEN (odds - 1) ELSE -1.0 END
            )::numeric / NULLIF(COUNT(*), 0) * 100, 1)                           AS roi
        FROM football_opportunities
        WHERE outcome IN ('won', 'lost')
          AND mode IN ('PROD', 'VALUE_OPP')
          AND match_id NOT LIKE 'seed_%%'
          {where_extra}
    """, fetch='one')


def post_daily_clv_summary() -> bool:
    """
    Daily pulse check posted to DISCORD_RESULTS_WEBHOOK.
    Shows two panels: since CLV era start (today onward) + all-time reference.
    Tracks: bets, CLV beat rate, avg CLV, ROI.
    """
    if not WEBHOOK_RESULTS:
        logger.warning("proof_poster: DISCORD_RESULTS_WEBHOOK not set — skip daily CLV summary")
        return False

    # Fetch era start from system_kv
    era_epoch = None
    era_date  = "okänt datum"
    try:
        kv = _db_module.db_helper.execute(
            "SELECT value FROM system_kv WHERE key = 'clv_era_start'",
            fetch='one'
        )
        if kv and kv[0]:
            era_epoch = int(kv[0])
            era_date  = time.strftime("%d %b %Y", time.gmtime(era_epoch))
    except Exception as exc:
        logger.warning("proof_poster: could not read clv_era_start: %s", exc)

    try:
        era_row = _clv_stats_query(since_epoch=era_epoch)
        all_row = _clv_stats_query(since_epoch=None)
    except Exception as exc:
        logger.error("proof_poster daily_clv_summary: DB fetch failed: %s", exc)
        return False

    if not era_row or not all_row:
        return False

    def _fmt(row):
        total, clv_tracked, clv_pos, avg_clv, avg_clv_pos, wins, roi = row
        total       = total or 0
        clv_tracked = clv_tracked or 0
        clv_pos     = clv_pos or 0
        wins        = wins or 0
        beat_rate   = round(100 * clv_pos / clv_tracked, 1) if clv_tracked else 0
        wr          = round(100 * wins / total, 1) if total else 0
        avg_clv_s   = f"{avg_clv:+.2f}%" if avg_clv is not None else "n/a"
        roi_s       = f"{roi:+.1f}%" if roi is not None else "n/a"
        return total, clv_tracked, clv_pos, beat_rate, wr, avg_clv_s, roi_s

    e_total, e_clv, e_pos, e_beat, e_wr, e_avg, e_roi = _fmt(era_row)
    a_total, a_clv, a_pos, a_beat, a_wr, a_avg, a_roi = _fmt(all_row)

    # Color based on era beat rate
    if e_beat >= 55:
        color, trend = 0x22c55e, "🟢"
    elif e_beat >= 45:
        color, trend = 0xf59e0b, "🟡"
    else:
        color, trend = 0xef4444, "🔴"

    era_block = (
        f"```\n"
        f"{'Picks avgjorda':<24} {e_total:>5}\n"
        f"{'CLV-spårade':<24} {e_clv:>5}  ({round(100*e_clv/e_total,0) if e_total else 0:.0f}%)\n"
        f"{'Slog CLV (>0)':<24} {e_pos:>5}  ({e_beat}%)\n"
        f"{'Snitt CLV':<24} {e_avg:>8}\n"
        f"{'Win rate':<24} {e_wr:>6}%\n"
        f"{'ROI':<24} {e_roi:>8}\n"
        f"```"
    )

    all_block = (
        f"```\n"
        f"{'Picks avgjorda':<24} {a_total:>5}\n"
        f"{'Slog CLV (>0)':<24} {a_pos:>5}  ({a_beat}%)\n"
        f"{'Snitt CLV':<24} {a_avg:>8}\n"
        f"{'ROI':<24} {a_roi:>8}\n"
        f"```"
    )

    desc = (
        f"{trend} **Era-start: {era_date}** — clean baseline, nollställt idag\n\n"
        f"**📊 Sedan era-start**\n"
        + era_block
        + f"\n**📁 All-time (referens)**\n"
        + all_block
        + f"\n_{trend} CLV beat rate (era): **{e_beat}%** · mål >50%_"
    )

    embed = {
        "title": "📈 Daglig CLV-puls — Closing Line Value",
        "description": desc,
        "color": color,
        "footer": {"text": f"PGR Analytics · Era start {era_date} · Uppdateras 22:50 UTC"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        resp = requests.post(
            WEBHOOK_RESULTS,
            json={"embeds": [embed]},
            timeout=8,
        )
        if resp.status_code in (200, 204):
            logger.info("✅ proof_poster: daily CLV summary posted (%d picks era, beat_rate=%.1f%%)", e_total, e_beat)
            return True
        else:
            logger.warning("proof_poster daily_clv_summary: webhook %d — %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.error("proof_poster daily_clv_summary: request failed: %s", exc)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 7. RESULTS SNAPSHOT — posts to WEBHOOK_PROOF Wed + Sun
# ─────────────────────────────────────────────────────────────────────────────

def run_results_report(days: int = 3) -> bool:
    """
    Post a results snapshot to WEBHOOK_PROOF covering the last `days` days.
    Shows: bets, profit (units), beat closing line count.
    Called Wednesday (days=3) and Sunday (days=4).
    """
    if not WEBHOOK_PROOF:
        logger.debug("proof_poster results_report: WEBHOOK_PROOF not set — skip")
        return False

    now       = int(time.time())
    since_ts  = now - days * 86400
    from_date = time.strftime("%Y-%m-%d", time.gmtime(since_ts))

    try:
        rows = _db_module.db_helper.execute("""
            SELECT
                COUNT(*)                                                           AS total,
                SUM(CASE WHEN outcome = 'won' THEN (odds - 1) ELSE -1.0 END)     AS profit_u,

                -- Tier 1: Sharp CLV — exact Pinnacle/Betfair close
                SUM(CASE WHEN clv_pct > 0
                         AND clv_status != 'soft'
                         AND clv_source_book NOT ILIKE '%%api_football%%'
                         AND clv_source_book NOT ILIKE '~%%'
                         AND clv_source_book NOT ILIKE '%%(line moved%%'
                         THEN 1 ELSE 0 END)                                       AS sharp_beat,
                SUM(CASE WHEN clv_status != 'soft'
                         AND clv_pct IS NOT NULL
                         AND clv_source_book NOT ILIKE '%%api_football%%'
                         AND clv_source_book NOT ILIKE '~%%'
                         AND clv_source_book NOT ILIKE '%%(line moved%%'
                         THEN 1 ELSE 0 END)                                       AS sharp_total,

                -- Tier 2: Approx CLV — Pinnacle line moved
                SUM(CASE WHEN clv_pct > 0
                         AND clv_source_book ILIKE '%%(line moved%%'
                         THEN 1 ELSE 0 END)                                       AS approx_beat,
                SUM(CASE WHEN clv_source_book ILIKE '%%(line moved%%'
                         AND clv_pct IS NOT NULL
                         THEN 1 ELSE 0 END)                                       AS approx_total,

                -- Tier 3: Market confirmation — odds shortened (any source)
                SUM(CASE WHEN close_odds IS NOT NULL
                         AND open_odds  IS NOT NULL
                         AND close_odds < open_odds
                         THEN 1 ELSE 0 END)                                       AS market_moved,

                -- Total edge signals — union of all three (pick had at least one signal)
                SUM(CASE WHEN (
                    (clv_pct > 0 AND clv_status != 'soft'
                      AND clv_source_book NOT ILIKE '%%api_football%%'
                      AND clv_source_book NOT ILIKE '~%%')
                    OR (clv_pct > 0 AND clv_source_book ILIKE '%%(line moved%%')
                    OR (close_odds IS NOT NULL AND open_odds IS NOT NULL
                        AND close_odds < open_odds)
                ) THEN 1 ELSE 0 END)                                              AS edge_signals,

                -- Soft odds coverage (api_football / soft-flagged sources)
                SUM(CASE WHEN clv_pct IS NOT NULL
                         AND (clv_status = 'soft'
                              OR clv_source_book ILIKE '%%api_football%%'
                              OR clv_source_book ILIKE '~%%')
                         THEN 1 ELSE 0 END)                                       AS soft_coverage

            FROM football_opportunities
            WHERE outcome IN ('won', 'lost')
              AND (
                  mode IN ('PROD', 'VALUE_OPP')
                  OR (mode = 'LEARNING' AND (
                      market ILIKE '%%card%%' OR market ILIKE '%%corner%%'
                  ))
              )
              AND match_date >= %s
              AND match_id   NOT LIKE 'seed_%%'
        """, (from_date,), fetch='one')
    except Exception as exc:
        logger.error("proof_poster results_report: DB error: %s", exc)
        return False

    if not rows or not rows[0]:
        logger.info("proof_poster results_report: no settled picks — skip")
        return False

    total, profit_raw, sharp_beat, sharp_total, approx_beat, approx_total, market_moved, edge_signals, soft_coverage = rows
    total         = int(total or 0)
    profit_u      = float(profit_raw or 0)
    sharp_beat    = int(sharp_beat or 0)
    sharp_total   = int(sharp_total or 0)
    approx_beat   = int(approx_beat or 0)
    approx_total  = int(approx_total or 0)
    market_moved  = int(market_moved or 0)
    edge_signals  = int(edge_signals or 0)
    soft_coverage = int(soft_coverage or 0)

    if total == 0:
        logger.info("proof_poster results_report: 0 settled picks — skip")
        return False

    # Date range label
    from_day = time.strftime("%-d %b", time.gmtime(since_ts))
    to_day   = time.strftime("%-d %b", time.gmtime(now))
    period   = f"{from_day} – {to_day}"

    profit_str   = f"+{profit_u:.1f}u" if profit_u >= 0 else f"{profit_u:.1f}u"
    sharp_cov    = f"{sharp_total}/{total}"
    sharp_beat_s = f"{sharp_beat}/{sharp_total}" if sharp_total > 0 else "—"
    approx_str   = f"{approx_beat}/{approx_total}" if approx_total > 0 else "—"
    market_str   = f"{market_moved}/{total}"
    edge_str     = f"{edge_signals}/{total}"
    soft_str     = f"{soft_coverage}/{total}"
    edge_pct     = round(100 * edge_signals / total) if total > 0 else 0
    edge_icon    = "✅" if edge_pct >= 50 else "⚠️"

    color = 0x22c55e if profit_u >= 0 else 0xef4444

    # Dynamic market confirmation line
    if edge_pct >= 60:
        confirm_line = "Market is consistently confirming the edge."
    elif edge_pct >= 35:
        confirm_line = "Market is starting to confirm the edge."
    else:
        confirm_line = "Still gathering market confirmation."

    body_lines = [
        f"📊 **{total} bets · {profit_str} profit**",
        confirm_line,
        "",
        f"• **{sharp_total} bets with verified sharp closing line data**",
        f"→ **{sharp_beat_s} beat the market**",
        "",
        f"• **{edge_signals} confirmed value spots** *(market moved after entry)*",
        f"• **{soft_coverage} additional signals tracked** *(not used as proof)*",
        "",
        "*Still early — CLV is what I'm tracking long-term.*",
        "",
        "*Not every bet wins — but price is everything.*",
    ]

    embed = {
        "title":       f"📊 Results Snapshot  ·  {period}",
        "description": "\n".join(body_lines),
        "color":       color,
        "footer":      {"text": "Sharp = Pinnacle/Betfair exact close  ·  Soft = api_football signal only  ·  Not financial advice"},
        "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    ok = _send_embed(embed, label=f"results snapshot {period} ({total} picks, {profit_str})")
    if ok:
        logger.info("✅ proof_poster: results snapshot posted — %d picks, %s  sharp=%s approx=%s edge=%s/%d",
                    total, profit_str, sharp_str, approx_str, edge_signals, total)
    return ok

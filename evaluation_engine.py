"""
EVALUATION ENGINE
=================
Comprehensive system evaluation posted to Discord.

Triggered:
  - Manually: run_evaluation()
  - Automatically: every time PROD settled picks cross a 200-pick milestone
    (200, 400, 600...) via check_milestone_and_post()

Report covers:
  - Overall stats (WR, ROI, avg EV, avg CLV, CLV beat rate)
  - By league (n >= 10)
  - By EV tier (<10%, 10-20%, 20-30%, 30%+)
  - By CLV bucket (settled picks with CLV tracking)
  - By market type (Value Single, Corners, Cards)
  - By PGR Scale tier (Elite/Strong/Standard)
  - Progress indicator toward next milestone
"""

import os
import time
import logging
import requests
from decimal import Decimal

import db_helper as _db

logger = logging.getLogger(__name__)

WEBHOOK_RESULTS = os.getenv("DISCORD_RESULTS_WEBHOOK", "")

# System v2 launch — only evaluate picks created after this epoch
V2_LAUNCH_EPOCH = 1737763200   # Jan 25, 2026

# Milestones to auto-trigger evaluation
MILESTONE_STEP = 200

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _f(v, decimals=1):
    """Format Decimal or float safely."""
    if v is None:
        return "—"
    return f"{float(v):.{decimals}f}"


def _pct(wins, total):
    if not total:
        return 0.0
    return round(wins / total * 100, 1)


def _roi(rows_with_odds_and_outcome):
    """Calculate ROI% from list of (odds, outcome) tuples."""
    total = len(rows_with_odds_and_outcome)
    if not total:
        return None
    profit = sum((float(o) - 1) if oc == "won" else -1.0 for o, oc in rows_with_odds_and_outcome)
    return round(profit / total * 100, 2)


def _send(embed: dict, label: str = "") -> bool:
    if not WEBHOOK_RESULTS:
        logger.warning("evaluation_engine: DISCORD_RESULTS_WEBHOOK not set")
        return False
    try:
        resp = requests.post(WEBHOOK_RESULTS, json={"embeds": [embed]}, timeout=10)
        if resp.status_code in (200, 204):
            logger.info("✅ evaluation_engine: posted %s", label)
            return True
        logger.warning("evaluation_engine: webhook %d — %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.error("evaluation_engine: request error: %s", exc)
    return False


def _bar(pct, width=8):
    """Simple ASCII bar 0–100%."""
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ─────────────────────────────────────────────────────────────────
# Data fetchers
# ─────────────────────────────────────────────────────────────────

def _fetch_overall():
    return _db.db_helper.execute("""
        SELECT
            COUNT(*)                                                    AS n,
            SUM(CASE WHEN outcome='won'  THEN 1 ELSE 0 END)            AS wins,
            SUM(CASE WHEN outcome='lost' THEN 1 ELSE 0 END)            AS losses,
            COUNT(*) FILTER (WHERE clv_pct IS NOT NULL)                 AS with_clv,
            SUM(CASE WHEN clv_pct > 0   THEN 1 ELSE 0 END)             AS clv_pos,
            ROUND(AVG(edge_percentage)::numeric, 1)                    AS avg_ev,
            ROUND(AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL)::numeric, 2) AS avg_clv,
            ROUND(SUM(
                CASE WHEN outcome='won' THEN (odds - 1) ELSE -1.0 END
            )::numeric / NULLIF(COUNT(*), 0) * 100, 2)                 AS roi,
            ROUND(AVG(odds)::numeric, 3)                               AS avg_odds
        FROM football_opportunities
        WHERE outcome IN ('won', 'lost')
          AND mode IN ('PROD', 'VALUE_OPP')
          AND match_id NOT LIKE 'seed_%%'
          AND timestamp >= %s
    """, (V2_LAUNCH_EPOCH,), fetch='one')


def _fetch_by_league():
    return _db.db_helper.execute("""
        SELECT
            league,
            COUNT(*)                                                AS n,
            SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END)         AS wins,
            ROUND(AVG(edge_percentage)::numeric, 1)                AS avg_ev,
            ROUND(AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL)::numeric, 2) AS avg_clv,
            ROUND(SUM(
                CASE WHEN outcome='won' THEN (odds - 1) ELSE -1.0 END
            )::numeric / NULLIF(COUNT(*), 0) * 100, 1)             AS roi
        FROM football_opportunities
        WHERE outcome IN ('won', 'lost')
          AND mode IN ('PROD', 'VALUE_OPP')
          AND match_id NOT LIKE 'seed_%%'
          AND timestamp >= %s
        GROUP BY league
        HAVING COUNT(*) >= 10
        ORDER BY COUNT(*) DESC
        LIMIT 18
    """, (V2_LAUNCH_EPOCH,), fetch='all') or []


def _fetch_by_ev_tier():
    return _db.db_helper.execute("""
        SELECT tier, tier_ord,
            COUNT(*)                                                AS n,
            SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END)         AS wins,
            ROUND(AVG(odds)::numeric, 2)                           AS avg_odds,
            ROUND(SUM(
                CASE WHEN outcome='won' THEN (odds - 1) ELSE -1.0 END
            )::numeric / NULLIF(COUNT(*), 0) * 100, 1)             AS roi
        FROM (
            SELECT outcome, odds,
                CASE
                    WHEN edge_percentage >= 30 THEN '30%%+'
                    WHEN edge_percentage >= 20 THEN '20-30%%'
                    WHEN edge_percentage >= 10 THEN '10-20%%'
                    ELSE '<10%%'
                END AS tier,
                CASE
                    WHEN edge_percentage >= 30 THEN 3
                    WHEN edge_percentage >= 20 THEN 2
                    WHEN edge_percentage >= 10 THEN 1
                    ELSE 0
                END AS tier_ord
            FROM football_opportunities
            WHERE outcome IN ('won', 'lost')
              AND mode IN ('PROD', 'VALUE_OPP')
              AND match_id NOT LIKE 'seed_%%'
              AND timestamp >= %s
        ) sub
        GROUP BY tier, tier_ord
        ORDER BY tier_ord DESC
    """, (V2_LAUNCH_EPOCH,), fetch='all') or []


def _fetch_by_clv_bucket():
    return _db.db_helper.execute("""
        SELECT
            CASE
                WHEN clv_pct >= 5  THEN 4
                WHEN clv_pct >= 3  THEN 3
                WHEN clv_pct >= 1  THEN 2
                WHEN clv_pct >= 0  THEN 1
                ELSE               0
            END                                                     AS bucket_ord,
            COUNT(*)                                                AS n,
            SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END)         AS wins,
            ROUND(AVG(clv_pct)::numeric, 2)                        AS avg_clv,
            ROUND(SUM(
                CASE WHEN outcome='won' THEN (odds - 1) ELSE -1.0 END
            )::numeric / NULLIF(COUNT(*), 0) * 100, 1)             AS roi
        FROM football_opportunities
        WHERE outcome IN ('won', 'lost')
          AND clv_pct IS NOT NULL
          AND mode IN ('PROD', 'VALUE_OPP')
          AND match_id NOT LIKE 'seed_%%'
          AND timestamp >= %s
        GROUP BY bucket_ord
        ORDER BY bucket_ord DESC
    """, (V2_LAUNCH_EPOCH,), fetch='all') or []


def _fetch_by_market():
    return _db.db_helper.execute("""
        SELECT mkt,
            COUNT(*)                                                AS n,
            SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END)         AS wins,
            ROUND(AVG(edge_percentage)::numeric, 1)                AS avg_ev,
            ROUND(SUM(
                CASE WHEN outcome='won' THEN (odds - 1) ELSE -1.0 END
            )::numeric / NULLIF(COUNT(*), 0) * 100, 1)             AS roi
        FROM (
            SELECT outcome, odds, edge_percentage,
                CASE
                    WHEN market = 'Corners' OR market ILIKE '%%corner%%' THEN 'Corners'
                    WHEN market = 'Cards'   OR market ILIKE '%%card%%'   THEN 'Cards'
                    ELSE 'Value Singles'
                END AS mkt
            FROM football_opportunities
            WHERE outcome IN ('won', 'lost')
              AND mode IN ('PROD', 'VALUE_OPP')
              AND match_id NOT LIKE 'seed_%%'
              AND timestamp >= %s
        ) sub
        GROUP BY mkt
        ORDER BY COUNT(*) DESC
    """, (V2_LAUNCH_EPOCH,), fetch='all') or []


def _fetch_by_pgr_tier():
    return _db.db_helper.execute("""
        SELECT tier, tier_ord,
            COUNT(*)                                                AS n,
            SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END)         AS wins,
            ROUND(AVG(edge_percentage)::numeric, 1)                AS avg_ev,
            ROUND(SUM(
                CASE WHEN outcome='won' THEN (odds - 1) ELSE -1.0 END
            )::numeric / NULLIF(COUNT(*), 0) * 100, 1)             AS roi
        FROM (
            SELECT outcome, odds, edge_percentage,
                CASE
                    WHEN confidence >= 0.70 THEN '🟢 Elite Value'
                    WHEN confidence >= 0.50 THEN '🟡 Strong Value'
                    ELSE                         '🔵 Standard Value'
                END AS tier,
                CASE
                    WHEN confidence >= 0.70 THEN 2
                    WHEN confidence >= 0.50 THEN 1
                    ELSE 0
                END AS tier_ord
            FROM football_opportunities
            WHERE outcome IN ('won', 'lost')
              AND mode IN ('PROD', 'VALUE_OPP')
              AND match_id NOT LIKE 'seed_%%'
              AND timestamp >= %s
        ) sub
        GROUP BY tier, tier_ord
        ORDER BY tier_ord DESC
    """, (V2_LAUNCH_EPOCH,), fetch='all') or []


def _fetch_pending_count():
    row = _db.db_helper.execute("""
        SELECT COUNT(*) FROM football_opportunities
        WHERE (outcome IS NULL OR outcome = '' OR outcome = 'pending')
          AND mode IN ('PROD', 'VALUE_OPP')
          AND match_id NOT LIKE 'seed_%%'
          AND timestamp >= %s
    """, (V2_LAUNCH_EPOCH,), fetch='one')
    return row[0] if row else 0


# ─────────────────────────────────────────────────────────────────
# Report builder
# ─────────────────────────────────────────────────────────────────

def _build_report(milestone_n=None):
    """
    Fetch all data and build a list of Discord embeds.
    Returns (list_of_embeds, settled_count).
    """
    overall = _fetch_overall()
    if not overall or not overall[0]:
        return [], 0

    n, wins, losses, with_clv, clv_pos, avg_ev, avg_clv, roi, avg_odds = overall
    n = int(n); wins = int(wins); losses = int(losses)
    with_clv = int(with_clv or 0); clv_pos = int(clv_pos or 0)
    wr = _pct(wins, n)
    clv_beat = _pct(clv_pos, with_clv) if with_clv else None
    roi_f = float(roi) if roi else 0.0
    roi_sign = "+" if roi_f >= 0 else ""

    pending = _fetch_pending_count()
    next_milestone = ((n // MILESTONE_STEP) + 1) * MILESTONE_STEP
    progress_to_next = n % MILESTONE_STEP
    progress_bar = _bar(progress_to_next / MILESTONE_STEP * 100, width=10)

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    color_main = 0x22c55e if roi_f >= 0 else 0xef4444

    # ── EMBED 1: Overall summary ──────────────────────────────────
    title_suffix = f"  ·  Milestone #{n // MILESTONE_STEP}" if milestone_n else ""
    clv_line = (
        f"CLV Beat Rate      : {clv_pos}/{with_clv} ({clv_beat:.1f}%)  avg {_f(avg_clv, 2)}%"
        if with_clv else "CLV Beat Rate      : tracking in progress..."
    )
    summary_block = "\n".join([
        "```",
        f"Settled picks      : {n}  (W:{wins}  L:{losses})",
        f"Win rate           : {wr}%",
        f"ROI (flat stake)   : {roi_sign}{_f(roi, 2)}%",
        f"Avg EV (model)     : {_f(avg_ev, 1)}%",
        f"Avg odds           : {_f(avg_odds, 2)}",
        clv_line,
        "",
        f"Progress to {next_milestone}  : [{progress_bar}] {progress_to_next}/{MILESTONE_STEP}",
        f"Pending picks      : {pending}",
        "```",
    ])

    embed1 = {
        "title": f"📊 PGR Evaluation Report{title_suffix}",
        "description": (
            f"**System v2 — since Jan 25, 2026**\n"
            f"Full breakdown by league, EV, CLV, market, and PGR Scale tier.\n\n"
            + summary_block
        ),
        "color": color_main,
        "timestamp": ts,
        "footer": {"text": "PGR Analytics · Evaluation Engine · Not financial advice"},
    }

    # ── EMBED 2: By league ────────────────────────────────────────
    by_league = _fetch_by_league()
    league_lines = ["```"]
    league_lines.append(f"{'League':<28} {'n':>4} {'WR':>6} {'EV':>6} {'CLV':>6} {'ROI':>7}")
    league_lines.append("─" * 58)
    for row in by_league:
        lg = (row[0] or "Unknown").replace("soccer_", "").replace("_", " ")
        lg = lg[:26]
        ln = int(row[1]); lw = int(row[2])
        lwr = _pct(lw, ln)
        lev = _f(row[3], 1)
        lclv = f"{float(row[4]):+.1f}%" if row[4] is not None else "  —  "
        lroi_v = float(row[5]) if row[5] is not None else 0.0
        lroi = f"{'+' if lroi_v >= 0 else ''}{lroi_v:.1f}%"
        league_lines.append(f"{lg:<28} {ln:>4} {lwr:>5.1f}% {lev:>5}% {lclv:>6} {lroi:>7}")
    league_lines.append("```")

    embed2 = {
        "title": "🌍 League Breakdown",
        "description": "\n".join(league_lines),
        "color": 0x3b82f6,
        "timestamp": ts,
    }

    # ── EMBED 3: EV tier + CLV bucket ────────────────────────────
    ev_tiers = _fetch_by_ev_tier()
    ev_lines = ["**EV Tier Analysis**", "```"]
    ev_lines.append(f"{'EV Tier':<10} {'n':>4} {'WR':>6} {'Odds':>5} {'ROI':>7}")
    ev_lines.append("─" * 36)
    for row in ev_tiers:
        tw = int(row[3]); tn = int(row[2])
        twr = _pct(tw, tn)
        troi_v = float(row[5]) if row[5] is not None else 0.0
        troi = f"{'+' if troi_v >= 0 else ''}{troi_v:.1f}%"
        ev_lines.append(f"{row[0]:<10} {tn:>4} {twr:>5.1f}% {_f(row[4],2):>5} {troi:>7}")
    ev_lines.append("```")

    BUCKET_LABELS = {4: "+5%+", 3: "+3–5%", 2: "+1–3%", 1: "+0–1%", 0: "Negative"}
    BUCKET_ICONS  = {4: "🟢", 3: "🟡", 2: "🔵", 1: "⚪", 0: "🔴"}
    clv_buckets = _fetch_by_clv_bucket()
    clv_lines = ["\n**CLV Bucket → Win Rate**", "```"]
    for row in clv_buckets:
        bk = int(row[0]); bn = int(row[1]); bw = int(row[2])
        bwr = _pct(bw, bn)
        bar = _bar(bwr, width=8)
        bclv = float(row[3]) if row[3] else 0
        broi_v = float(row[4]) if row[4] is not None else 0.0
        broi = f"{'+' if broi_v >= 0 else ''}{broi_v:.1f}%"
        icon = BUCKET_ICONS.get(bk, "•")
        label = BUCKET_LABELS.get(bk, "?")
        clv_lines.append(f"{icon} {label:<9} {bar} {bwr:5.1f}% ({bw}/{bn}) roi{broi}")
    if not clv_buckets:
        clv_lines.append("CLV tracking building sample — not enough data yet")
    clv_lines.append("```")

    embed3 = {
        "title": "📈 EV Tiers & CLV Buckets",
        "description": "\n".join(ev_lines + clv_lines),
        "color": 0x8b5cf6,
        "timestamp": ts,
    }

    # ── EMBED 4: Market + PGR Scale ──────────────────────────────
    by_market = _fetch_by_market()
    mkt_lines = ["**Market Breakdown**", "```"]
    mkt_lines.append(f"{'Market':<16} {'n':>4} {'WR':>6} {'EV':>6} {'ROI':>7}")
    mkt_lines.append("─" * 42)
    for row in by_market:
        mw = int(row[2]); mn = int(row[1])
        mwr = _pct(mw, mn)
        mroi_v = float(row[4]) if row[4] is not None else 0.0
        mroi = f"{'+' if mroi_v >= 0 else ''}{mroi_v:.1f}%"
        mkt_lines.append(f"{(row[0] or ''):<16} {mn:>4} {mwr:>5.1f}% {_f(row[3],1):>5}% {mroi:>7}")
    mkt_lines.append("```")

    by_tier = _fetch_by_pgr_tier()
    tier_lines = ["\n**PGR Scale Tier**", "```"]
    tier_lines.append(f"{'Tier':<22} {'n':>4} {'WR':>6} {'EV':>6} {'ROI':>7}")
    tier_lines.append("─" * 44)
    for row in by_tier:
        tw = int(row[3]); tn = int(row[2])
        twr = _pct(tw, tn)
        troi_v = float(row[4]) if row[4] is not None else 0.0
        troi = f"{'+' if troi_v >= 0 else ''}{troi_v:.1f}%"
        tier_lines.append(f"{(row[0] or ''):<22} {tn:>4} {twr:>5.1f}% {_f(row[5] if len(row) > 5 else None,1):>5}% {troi:>7}")
    tier_lines.append("```")

    verdict = ("✅ **System performing above expectation** — positive ROI with CLV beat rate confirming edge."
               if roi_f >= 0 and (clv_beat or 0) >= 50
               else "⚠️ **Variance window** — EV is positive, allowing sample to grow before conclusions."
               if roi_f < 0
               else "📊 **On track** — monitoring CLV coverage and long-run EV realisation.")

    embed4 = {
        "title": "🎯 Market & PGR Scale Breakdown",
        "description": "\n".join(mkt_lines + tier_lines) + f"\n\n{verdict}",
        "color": 0xf59e0b,
        "timestamp": ts,
        "footer": {"text": f"PGR Analytics · Evaluation Engine · {n} settled picks since v2 launch"},
    }

    return [embed1, embed2, embed3, embed4], n


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def run_evaluation(milestone_n=None) -> bool:
    """
    Build and post full evaluation to Discord results channel.
    Returns True if all embeds posted successfully.
    """
    try:
        embeds, settled = _build_report(milestone_n=milestone_n)
        if not embeds:
            logger.info("evaluation_engine: no data to post")
            return False

        ok = True
        for i, embed in enumerate(embeds):
            success = _send(embed, label=f"evaluation embed {i+1}/{len(embeds)}")
            if not success:
                ok = False
            if i < len(embeds) - 1:
                time.sleep(0.5)   # slight delay between embeds to maintain order
        logger.info("evaluation_engine: report done — settled=%d ok=%s", settled, ok)
        return ok
    except Exception as exc:
        logger.error("evaluation_engine: run_evaluation error: %s", exc)
        import traceback
        traceback.print_exc()
        return False


def check_milestone_and_post() -> bool:
    """
    Check if settled PROD pick count just crossed a MILESTONE_STEP boundary.
    Called by combined_sports_runner after each result update cycle.
    Returns True if milestone was reached and evaluation was posted.
    """
    try:
        row = _db.db_helper.execute("""
            SELECT COUNT(*) FROM football_opportunities
            WHERE outcome IN ('won', 'lost')
              AND mode IN ('PROD', 'VALUE_OPP')
              AND match_id NOT LIKE 'seed_%%'
              AND timestamp >= %s
        """, (V2_LAUNCH_EPOCH,), fetch='one')

        if not row:
            return False

        n = int(row[0])

        # Check if we previously logged this milestone
        prev_row = _db.db_helper.execute("""
            SELECT value FROM system_kv WHERE key = 'last_evaluation_milestone'
        """, fetch='one')
        prev_milestone = int(prev_row[0]) if prev_row and prev_row[0] else 0

        current_milestone = (n // MILESTONE_STEP) * MILESTONE_STEP
        if current_milestone > 0 and current_milestone > prev_milestone:
            logger.info(
                "🎯 evaluation_engine: milestone %d reached (prev=%d) — posting evaluation",
                current_milestone, prev_milestone
            )
            ok = run_evaluation(milestone_n=current_milestone)
            if ok:
                _db.db_helper.execute("""
                    INSERT INTO system_kv (key, value)
                    VALUES ('last_evaluation_milestone', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, (str(current_milestone),))
            return ok
        return False

    except Exception as exc:
        logger.error("evaluation_engine: check_milestone_and_post error: %s", exc)
        return False


def get_progress() -> dict:
    """Return current progress stats (for API endpoints / status checks)."""
    try:
        row = _db.db_helper.execute("""
            SELECT
                COUNT(*) as n,
                SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END) as wins,
                ROUND(AVG(edge_percentage)::numeric, 1) as avg_ev,
                ROUND(AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL)::numeric, 2) as avg_clv,
                COUNT(*) FILTER (WHERE clv_pct IS NOT NULL) as with_clv
            FROM football_opportunities
            WHERE outcome IN ('won', 'lost')
              AND mode IN ('PROD', 'VALUE_OPP')
              AND match_id NOT LIKE 'seed_%%'
              AND timestamp >= %s
        """, (V2_LAUNCH_EPOCH,), fetch='one')

        if not row or not row[0]:
            return {"settled": 0, "next_milestone": MILESTONE_STEP, "progress_pct": 0}

        n = int(row[0])
        wins = int(row[1] or 0)
        next_milestone = ((n // MILESTONE_STEP) + 1) * MILESTONE_STEP
        return {
            "settled": n,
            "wins": wins,
            "win_rate": _pct(wins, n),
            "avg_ev": float(row[2]) if row[2] else None,
            "avg_clv": float(row[3]) if row[3] else None,
            "clv_coverage": int(row[4] or 0),
            "next_milestone": next_milestone,
            "progress_pct": round((n % MILESTONE_STEP) / MILESTONE_STEP * 100, 1),
        }
    except Exception as exc:
        logger.error("evaluation_engine: get_progress error: %s", exc)
        return {}

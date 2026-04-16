#!/usr/bin/env python3
"""
Daily & Weekly Scanner Recap — Discord Notifications
Daily:  Every night at 22:30 — what the scanner found today
Weekly: Every Sunday at 22:30 — scanner summary for Mon-Sun

Frame: value scanner, not tipster. We show where the market is wrong.
"""

import os
import logging
import requests
from datetime import datetime, date, timedelta
from db_connection import DatabaseConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_RESULTS_WEBHOOK')
DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━━"


def send_discord_message(content: str) -> bool:
    """Send a plain-text message to Discord."""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("No DISCORD_RESULTS_WEBHOOK set")
        return False
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
        logger.info("✅ Discord message sent")
        return True
    except Exception as e:
        logger.error(f"❌ Discord send error: {e}")
        return False


# ─────────────────────────────────────────────
# DATA HELPERS
# ─────────────────────────────────────────────

def _fetch_scanner_stats(start_date: date, end_date: date) -> dict:
    """Pull edge / EV stats for the date range from football_opportunities."""
    db = DatabaseConnection()
    stats = {
        "edges_total": 0,
        "edges_prod": 0,
        "avg_ev": None,
        "top_markets": [],
        "settled": {"won": 0, "lost": 0, "profit": 0.0},
        "smart_picks": {"won": 0, "lost": 0, "profit": 0.0},
        "clv_avg": None,
        "clv_positive_pct": None,
        "best_odds_range": None,
        "top_leagues": [],
    }
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:

                # 1. Edges found (all non-learning, positive EV)
                cur.execute("""
                    SELECT COUNT(*), AVG(ev_pct), mode
                    FROM football_opportunities
                    WHERE match_date::date BETWEEN %s AND %s
                      AND ev_pct > 0
                      AND mode NOT IN ('LEARNING', 'LEARNING_ONLY', 'DISABLED')
                    GROUP BY mode
                """, (start_date, end_date))
                for row in cur.fetchall():
                    cnt, avg_ev, mode = row
                    stats["edges_total"] += (cnt or 0)
                    if mode == 'PROD':
                        stats["edges_prod"] += (cnt or 0)
                        stats["avg_ev"] = round(avg_ev * 100, 1) if avg_ev else None

                # 2. Top markets by edge count
                cur.execute("""
                    SELECT market, COUNT(*) as n
                    FROM football_opportunities
                    WHERE match_date::date BETWEEN %s AND %s
                      AND ev_pct > 0
                      AND mode NOT IN ('LEARNING', 'LEARNING_ONLY', 'DISABLED')
                    GROUP BY market
                    ORDER BY n DESC
                    LIMIT 5
                """, (start_date, end_date))
                stats["top_markets"] = [(r[0], r[1]) for r in cur.fetchall()]

                # 3. Settled outcomes (PROD only)
                cur.execute("""
                    SELECT outcome, odds
                    FROM football_opportunities
                    WHERE match_date::date BETWEEN %s AND %s
                      AND outcome IN ('won', 'lost', 'WON', 'LOST')
                      AND mode = 'PROD'
                """, (start_date, end_date))
                for outcome, odds in cur.fetchall():
                    is_win = outcome.lower() == 'won'
                    profit = (float(odds) - 1) if is_win else -1.0
                    stats["settled"]["won" if is_win else "lost"] += 1
                    stats["settled"]["profit"] += profit

                # 4. Smart Value tracker
                cur.execute("""
                    SELECT outcome, odds
                    FROM football_opportunities
                    WHERE match_date::date BETWEEN %s AND %s
                      AND outcome IN ('won', 'lost', 'WON', 'LOST')
                      AND (smart_pick = TRUE OR tier = 'SMART_PICK')
                      AND mode = 'PROD'
                """, (start_date, end_date))
                for outcome, odds in cur.fetchall():
                    is_win = outcome.lower() == 'won'
                    profit = (float(odds) - 1) if is_win else -1.0
                    stats["smart_picks"]["won" if is_win else "lost"] += 1
                    stats["smart_picks"]["profit"] += profit

                # 5. CLV — only sharp captures (exclude api_football, soft, line-moved)
                cur.execute("""
                    SELECT AVG(clv_pct),
                           100.0 * SUM(CASE WHEN clv_pct > 0 THEN 1 ELSE 0 END)
                               / NULLIF(COUNT(*), 0)
                    FROM football_opportunities
                    WHERE match_date::date BETWEEN %s AND %s
                      AND clv_pct IS NOT NULL
                      AND mode = 'PROD'
                      AND clv_source_book NOT ILIKE %s
                      AND clv_source_book NOT ILIKE %s
                      AND clv_source_book NOT ILIKE %s
                """, (start_date, end_date, '%api_football%', '~%', '%(line moved%'))
                row = cur.fetchone()
                if row and row[0] is not None:
                    stats["clv_avg"] = round(row[0], 2)
                    stats["clv_positive_pct"] = round(row[1] or 0, 1)

                # 6. Best odds range (min 3 settled picks)
                cur.execute("""
                    SELECT
                        CASE
                            WHEN odds < 1.70 THEN '< 1.70'
                            WHEN odds < 1.90 THEN '1.70–1.89'
                            WHEN odds < 2.10 THEN '1.90–2.09'
                            WHEN odds < 2.50 THEN '2.10–2.49'
                            ELSE '2.50+'
                        END as range,
                        COUNT(*) as n,
                        SUM(CASE WHEN outcome IN ('won','WON') THEN odds-1 ELSE -1 END) as profit
                    FROM football_opportunities
                    WHERE match_date::date BETWEEN %s AND %s
                      AND outcome IN ('won','lost','WON','LOST')
                      AND mode = 'PROD'
                    GROUP BY range
                    HAVING COUNT(*) >= 3
                    ORDER BY profit DESC
                    LIMIT 1
                """, (start_date, end_date))
                row = cur.fetchone()
                if row:
                    stats["best_odds_range"] = {
                        "range": row[0], "n": row[1], "profit": round(row[2], 2)
                    }

                # 7. Top leagues (min 5 settled picks)
                cur.execute("""
                    SELECT league, COUNT(*) as n,
                           SUM(CASE WHEN outcome IN ('won','WON') THEN odds-1 ELSE -1 END) as profit
                    FROM football_opportunities
                    WHERE match_date::date BETWEEN %s AND %s
                      AND outcome IN ('won','lost','WON','LOST')
                      AND mode = 'PROD'
                    GROUP BY league
                    HAVING COUNT(*) >= 5
                    ORDER BY profit DESC
                    LIMIT 3
                """, (start_date, end_date))
                stats["top_leagues"] = [
                    (r[0], r[1], round(r[2], 2)) for r in cur.fetchall()
                ]

    except Exception as e:
        logger.error(f"❌ Error fetching scanner stats: {e}")

    return stats


# ─────────────────────────────────────────────
# MESSAGE BUILDERS
# ─────────────────────────────────────────────

def _build_daily_message(s: dict, date_str: str) -> str:
    avg_ev_str = f"+{s['avg_ev']:.1f}%" if s["avg_ev"] is not None else "n/a"

    lines = [
        f"📡 Scanner Recap — {date_str}",
        "",
        f"Edges found: {s['edges_total']} ({s['edges_prod']} PROD)",
        f"Avg Edge (PROD): {avg_ev_str}",
        "",
        DIVIDER,
    ]

    # Top markets
    if s["top_markets"]:
        lines += ["", "📊 Top Markets"]
        for market, n in s["top_markets"]:
            lines.append(f"{market}: {n}")
        lines += ["", DIVIDER]

    # Best odds range
    if s["best_odds_range"]:
        r = s["best_odds_range"]
        lines += [
            "",
            "🎯 Best Odds Range Identified",
            f"{r['range']} · {r['n']} picks · strongest signal concentration",
            "",
            DIVIDER,
        ]

    # CLV
    if s["clv_avg"] is not None:
        lines += [
            "",
            "📈 CLV (Closing Line Value)",
            f"Avg CLV: +{s['clv_avg']:.1f}%",
            f"Positive rate: {s['clv_positive_pct']:.0f}%",
            "",
            DIVIDER,
        ]

    # Top leagues
    if s["top_leagues"]:
        lines += ["", "🏆 Most Active Value Leagues (sample)"]
        lines.append(" · ".join(lg for lg, _, _ in s["top_leagues"]))
        lines += ["", DIVIDER]

    # Model signals (Smart Value — low emphasis)
    sp = s["smart_picks"]
    sp_total = sp["won"] + sp["lost"]
    clv_str = f"+{s['clv_avg']:.1f}%" if s["clv_avg"] is not None else "n/a"
    lines += [
        "",
        "🧠 Model Signals (Tracked Subset)",
        f"{s['edges_prod']} signals tracked",
        f"Avg CLV: {clv_str}",
        "",
        "This is a sample of tracked signals — not full scanner output.",
        "",
        DIVIDER,
        "",
        "⚙️ Scanner runs continuously across multiple leagues & markets.",
        "Not all opportunities are included in tracking.",
    ]

    return "\n".join(lines)


def _build_weekly_message(s: dict, week_str: str) -> str:
    avg_ev_str = f"+{s['avg_ev']:.1f}%" if s["avg_ev"] is not None else "n/a"

    lines = [
        f"📡 Weekly Scanner Report — {week_str}",
        "",
        f"Edges found: {s['edges_total']} ({s['edges_prod']} PROD)",
        f"Avg Edge (PROD): {avg_ev_str}",
        "",
        DIVIDER,
    ]

    # Top markets
    if s["top_markets"]:
        lines += ["", "📊 Top Markets"]
        for market, n in s["top_markets"]:
            lines.append(f"{market}: {n}")
        lines += ["", DIVIDER]

    # Best odds range
    if s["best_odds_range"]:
        r = s["best_odds_range"]
        lines += [
            "",
            "🎯 Best Odds Range Identified",
            f"{r['range']} · {r['n']} picks · strongest signal concentration",
            "",
            DIVIDER,
        ]

    # CLV
    if s["clv_avg"] is not None:
        lines += [
            "",
            "📈 CLV (Closing Line Value)",
            f"Avg CLV: +{s['clv_avg']:.1f}%",
            f"Positive rate: {s['clv_positive_pct']:.0f}%",
            "",
            DIVIDER,
        ]

    # Top leagues
    if s["top_leagues"]:
        lines += ["", "🏆 Most Active Value Leagues (sample)"]
        lines.append(" · ".join(lg for lg, _, _ in s["top_leagues"]))
        lines += ["", DIVIDER]

    # Model signals
    clv_str = f"+{s['clv_avg']:.1f}%" if s["clv_avg"] is not None else "n/a"
    lines += [
        "",
        "🧠 Model Signals (Tracked Subset)",
        f"{s['edges_prod']} signals tracked",
        f"Avg CLV: {clv_str}",
        "",
        "This is a sample of tracked signals — not full scanner output.",
        "",
        DIVIDER,
        "",
        "⚙️ Scanner runs continuously across multiple leagues & markets.",
        "Not all opportunities are included in tracking.",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────
# SEND FUNCTIONS
# ─────────────────────────────────────────────

def send_daily_discord_recap():
    """Daily scanner recap — sent at 22:30."""
    logger.info("📊 Generating daily scanner recap...")

    today = date.today()
    s = _fetch_scanner_stats(today, today)

    if s["edges_total"] == 0:
        logger.info("No edges found today — skipping daily recap")
        return

    date_str = today.strftime("%B %d, %Y")
    message = _build_daily_message(s, date_str)
    send_discord_message(message)

    avg_ev_str = f"+{s['avg_ev']:.1f}%" if s["avg_ev"] else "n/a"
    logger.info(f"📊 Daily recap sent: {s['edges_total']} edges, avg EV {avg_ev_str}")


def send_weekly_discord_recap():
    """Weekly scanner recap — sent Sunday at 22:30 (Mon–Sun)."""
    logger.info("📊 Generating weekly scanner recap...")

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    s = _fetch_scanner_stats(monday, today)

    if s["edges_total"] == 0:
        logger.info("No edges this week — skipping weekly recap")
        return

    week_str = f"{monday.strftime('%b %d')} – {today.strftime('%b %d, %Y')}"
    message = _build_weekly_message(s, week_str)
    send_discord_message(message)

    avg_ev_str = f"+{s['avg_ev']:.1f}%" if s["avg_ev"] else "n/a"
    logger.info(f"📊 Weekly recap sent: {s['edges_total']} edges, avg EV {avg_ev_str}")


# ─────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────

def send_daily_recap():
    """Legacy alias."""
    send_daily_discord_recap()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'weekly':
        send_weekly_discord_recap()
    else:
        send_daily_discord_recap()

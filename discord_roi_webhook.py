"""
Discord ROI/Stats Webhook - Sends performance updates to Discord
Single canonical source: football_opportunities WHERE mode='PROD'
"""

import os
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def get_db_url() -> str:
    return os.environ.get("DATABASE_URL", "")


def get_roi_stats() -> Dict[str, Any]:
    """Aggregate ROI and performance stats from football_opportunities (PROD only)."""
    try:
        db_url = get_db_url()
        if not db_url:
            return {"error": "No database URL configured"}

        engine = create_engine(db_url)

        with engine.connect() as conn:

            # All-time settled (WON + LOST only, normalise case)
            all_time = conn.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))           AS wins,
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('LOST','LOSS'))         AS losses,
                    COALESCE(SUM(CASE
                        WHEN UPPER(result) IN ('WON','WIN')  THEN (odds - 1.0)
                        WHEN UPPER(result) IN ('LOST','LOSS') THEN -1.0
                        ELSE 0 END), 0)                                              AS units
                FROM football_opportunities
                WHERE mode = 'PROD'
                  AND UPPER(result) IN ('WON','WIN','LOST','LOSS')
            """)).fetchone()

            # Picks created today (by kickoff / match_date)
            today_placed = conn.execute(text("""
                SELECT
                    COUNT(*)                                                          AS total,
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))           AS wins,
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('LOST','LOSS'))         AS losses,
                    COALESCE(SUM(CASE
                        WHEN UPPER(result) IN ('WON','WIN')  THEN (odds - 1.0)
                        WHEN UPPER(result) IN ('LOST','LOSS') THEN -1.0
                        ELSE 0 END), 0)                                              AS units,
                    COUNT(*) FILTER (WHERE UPPER(status) IN ('PENDING','IN_PROGRESS')) AS pending
                FROM football_opportunities
                WHERE mode = 'PROD'
                  AND match_date = TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
            """)).fetchone()

            # Settled today (match_date = today AND result known)
            settled_today = conn.execute(text("""
                SELECT
                    COUNT(*)                                                          AS total,
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))           AS wins,
                    COALESCE(SUM(CASE
                        WHEN UPPER(result) IN ('WON','WIN')  THEN (odds - 1.0)
                        WHEN UPPER(result) IN ('LOST','LOSS') THEN -1.0
                        ELSE 0 END), 0)                                              AS units
                FROM football_opportunities
                WHERE mode = 'PROD'
                  AND match_date = TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
                  AND UPPER(result) IN ('WON','WIN','LOST','LOSS')
            """)).fetchone()

            # Last 7 days
            week_stats = conn.execute(text("""
                SELECT
                    COUNT(*)                                                          AS total,
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))           AS wins,
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('LOST','LOSS'))         AS losses,
                    COALESCE(SUM(CASE
                        WHEN UPPER(result) IN ('WON','WIN')  THEN (odds - 1.0)
                        WHEN UPPER(result) IN ('LOST','LOSS') THEN -1.0
                        ELSE 0 END), 0)                                              AS units
                FROM football_opportunities
                WHERE mode = 'PROD'
                  AND UPPER(result) IN ('WON','WIN','LOST','LOSS')
                  AND kickoff_epoch >= EXTRACT(EPOCH FROM (CURRENT_DATE - INTERVAL '7 days'))
            """)).fetchone()

            # This calendar month
            month_stats = conn.execute(text("""
                SELECT
                    COUNT(*)                                                          AS total,
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))           AS wins,
                    COUNT(*) FILTER (WHERE UPPER(result) IN ('LOST','LOSS'))         AS losses,
                    COALESCE(SUM(CASE
                        WHEN UPPER(result) IN ('WON','WIN')  THEN (odds - 1.0)
                        WHEN UPPER(result) IN ('LOST','LOSS') THEN -1.0
                        ELSE 0 END), 0)                                              AS units
                FROM football_opportunities
                WHERE mode = 'PROD'
                  AND UPPER(result) IN ('WON','WIN','LOST','LOSS')
                  AND kickoff_epoch >= EXTRACT(EPOCH FROM DATE_TRUNC('month', CURRENT_DATE))
            """)).fetchone()

            # Last 10 settled picks for emoji row
            recent = conn.execute(text("""
                SELECT home_team, away_team, selection, odds, result, market
                FROM football_opportunities
                WHERE mode = 'PROD'
                  AND UPPER(result) IN ('WON','WIN','LOST','LOSS')
                ORDER BY kickoff_epoch DESC, id DESC
                LIMIT 10
            """)).fetchall()

        def roi_pct(units, total):
            return (units / total * 100) if total > 0 else 0.0

        def hit_pct(wins, total):
            return (wins / total * 100) if total > 0 else 0.0

        all_wins   = int(all_time[0] or 0)
        all_losses = int(all_time[1] or 0)
        all_units  = float(all_time[2] or 0)
        all_total  = all_wins + all_losses

        tp_total   = int(today_placed[0] or 0)
        tp_wins    = int(today_placed[1] or 0)
        tp_losses  = int(today_placed[2] or 0)
        tp_units   = float(today_placed[3] or 0)
        tp_pending = int(today_placed[4] or 0)

        st_total   = int(settled_today[0] or 0)
        st_wins    = int(settled_today[1] or 0)
        st_units   = float(settled_today[2] or 0)

        wk_total   = int(week_stats[0] or 0)
        wk_wins    = int(week_stats[1] or 0)
        wk_losses  = int(week_stats[2] or 0)
        wk_units   = float(week_stats[3] or 0)

        mo_total   = int(month_stats[0] or 0)
        mo_wins    = int(month_stats[1] or 0)
        mo_losses  = int(month_stats[2] or 0)
        mo_units   = float(month_stats[3] or 0)

        return {
            "all_time": {
                "total":    all_total,
                "wins":     all_wins,
                "losses":   all_losses,
                "hit_rate": hit_pct(all_wins, all_total),
                "units":    all_units,
                "roi":      roi_pct(all_units, all_total),
            },
            "today": {
                "total":    tp_total,
                "wins":     tp_wins,
                "losses":   tp_losses,
                "pending":  tp_pending,
                "units":    tp_units,
                "hit_rate": hit_pct(tp_wins, tp_total - tp_pending) if (tp_total - tp_pending) > 0 else 0,
            },
            "settled_today": {
                "total": st_total,
                "wins":  st_wins,
                "units": st_units,
            },
            "week": {
                "total":    wk_total,
                "wins":     wk_wins,
                "losses":   wk_losses,
                "hit_rate": hit_pct(wk_wins, wk_total),
                "units":    wk_units,
                "roi":      roi_pct(wk_units, wk_total),
            },
            "month": {
                "total":    mo_total,
                "wins":     mo_wins,
                "losses":   mo_losses,
                "hit_rate": hit_pct(mo_wins, mo_total),
                "units":    mo_units,
                "roi":      roi_pct(mo_units, mo_total),
            },
            "recent": [
                {
                    "match":   f"{r[0]} vs {r[1]}",
                    "pick":    r[2],
                    "odds":    float(r[3]) if r[3] else 0,
                    "result":  r[4],
                    "product": r[5] if r[5] else "BET",
                }
                for r in recent
            ],
        }

    except Exception as e:
        logger.error(f"Error getting ROI stats: {e}")
        return {"error": str(e)}


def build_discord_embed(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Build Discord embed payload from stats."""
    if "error" in stats:
        return {
            "embeds": [{
                "title": "⚠️ Stats Error",
                "description": f"Could not fetch stats: {stats['error']}",
                "color": 0xFF5555,
                "timestamp": datetime.utcnow().isoformat(),
            }]
        }

    all_time     = stats.get("all_time", {})
    settled_today = stats.get("settled_today", {})
    week         = stats.get("week", {})
    month        = stats.get("month", {})
    recent       = stats.get("recent", [])

    roi   = all_time.get("roi", 0)
    color = 0x00FFA6 if roi >= 10 else 0x22C55E if roi >= 0 else 0xFFA500 if roi >= -10 else 0xFF5555

    recent_row = ""
    if recent:
        recent_row = " ".join(
            "✅" if r["result"] and r["result"].upper() in ("WON", "WIN") else "❌"
            for r in recent[:10]
        )

    date_str = datetime.utcnow().strftime("%d %b")

    desc = (
        f"**All-time** — {roi:+.1f}% ROI  |  {all_time.get('units', 0):+.1f}u  |  "
        f"{all_time.get('wins', 0)}W-{all_time.get('losses', 0)}L  ({all_time.get('hit_rate', 0):.1f}%)\n"
        f"**This month** — {month.get('roi', 0):+.1f}% ROI  |  {month.get('units', 0):+.1f}u  |  {month.get('total', 0)} bets\n"
        f"**Last 7 days** — {week.get('roi', 0):+.1f}% ROI  |  {week.get('units', 0):+.1f}u  |  {week.get('total', 0)} bets\n"
        f"**Today** — {settled_today.get('wins', 0)}W-{settled_today.get('total', 0) - settled_today.get('wins', 0)}L  |  {settled_today.get('units', 0):+.1f}u settled"
    )

    if recent_row:
        desc += f"\n\n**Last {len(recent[:10])} results:** {recent_row}"

    return {
        "embeds": [{
            "title": f"📊 PGR Daily ROI — {date_str}",
            "description": desc,
            "color": color,
            "footer": {"text": f"PGR Sports Analytics  •  {all_time.get('total', 0)} bets tracked"},
            "timestamp": datetime.utcnow().isoformat(),
        }]
    }


def send_discord_stats(custom_message: Optional[str] = None) -> bool:
    """Send ROI stats to Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("⚠️ DISCORD_WEBHOOK_URL not set")
        return False

    try:
        stats   = get_roi_stats()
        payload = build_discord_embed(stats)

        if custom_message:
            payload["content"] = custom_message

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code in [200, 204]:
            logger.info("✅ Discord stats sent successfully")
            return True
        else:
            logger.error(f"❌ Discord webhook failed: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"❌ Discord webhook error: {e}")
        return False


def send_result_notification(match: str, pick: str, odds: float, result: str, profit: float) -> bool:
    """Send individual result notification to Discord."""
    if not DISCORD_WEBHOOK_URL:
        return False

    try:
        emoji      = "✅" if result.upper() in ("WON", "WIN") else "❌"
        color      = 0x00FF00 if result.upper() in ("WON", "WIN") else 0xFF5555
        profit_str = f"+{profit:.1f}u" if profit > 0 else f"{profit:.1f}u"

        payload = {
            "embeds": [{
                "title":       f"{emoji} Result: {result}",
                "description": f"**{match}**",
                "color":       color,
                "fields": [
                    {"name": "Pick",   "value": pick,                "inline": True},
                    {"name": "Odds",   "value": f"{odds:.2f}",       "inline": True},
                    {"name": "P/L",    "value": profit_str,          "inline": True},
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }]
        }

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        return response.status_code in [200, 204]

    except Exception as e:
        logger.error(f"❌ Discord result notification error: {e}")
        return False


if __name__ == "__main__":
    print("🔍 Testing Discord ROI webhook...")
    stats = get_roi_stats()
    print(f"📊 All-time: {stats.get('all_time', {})}")
    print(f"📊 This month: {stats.get('month', {})}")
    print(f"📊 Last 7d: {stats.get('week', {})}")
    print(f"📊 Settled today: {stats.get('settled_today', {})}")

    if DISCORD_WEBHOOK_URL:
        success = send_discord_stats("📊 Manual stats update requested")
        print(f"{'✅' if success else '❌'} Discord send: {'success' if success else 'failed'}")
    else:
        print("⚠️ No DISCORD_WEBHOOK_URL configured")

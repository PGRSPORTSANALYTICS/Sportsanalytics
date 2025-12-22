"""
Discord ROI/Stats Webhook - Sends performance updates to Discord
"""

import os
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def get_db_url() -> str:
    """Get database URL from environment."""
    return os.environ.get("DATABASE_URL", "")


def get_roi_stats() -> Dict[str, Any]:
    """Aggregate ROI and performance stats from database."""
    try:
        db_url = get_db_url()
        if not db_url:
            return {"error": "No database URL configured"}
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            today = datetime.utcnow().date()
            week_ago = today - timedelta(days=7)
            month_start = today.replace(day=1)
            
            all_time_query = text("""
                SELECT 
                    COUNT(*) as total_bets,
                    COUNT(CASE WHEN result IN ('WON', 'WIN') THEN 1 END) as wins,
                    COUNT(CASE WHEN result IN ('LOST', 'LOSS') THEN 1 END) as losses,
                    COALESCE(SUM(CASE 
                        WHEN result IN ('WON', 'WIN') THEN (odds - 1) 
                        WHEN result IN ('LOST', 'LOSS') THEN -1 
                        ELSE 0 
                    END), 0) as units_profit
                FROM all_bets
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
            """)
            all_time = conn.execute(all_time_query).fetchone()
            
            today_placed_query = text("""
                SELECT 
                    COUNT(*) as total_bets,
                    COUNT(CASE WHEN result IN ('WON', 'WIN') THEN 1 END) as wins,
                    COUNT(CASE WHEN result IN ('LOST', 'LOSS') THEN 1 END) as losses,
                    COALESCE(SUM(CASE 
                        WHEN result IN ('WON', 'WIN') THEN (odds - 1) 
                        WHEN result IN ('LOST', 'LOSS') THEN -1 
                        ELSE 0 
                    END), 0) as units_profit,
                    COUNT(CASE WHEN result IS NULL OR result = '' THEN 1 END) as pending
                FROM all_bets
                WHERE DATE(created_at) = CURRENT_DATE
            """)
            today_stats = conn.execute(today_placed_query).fetchone()
            
            today_settled_query = text("""
                SELECT 
                    COUNT(*) as total_bets,
                    COUNT(CASE WHEN result IN ('WON', 'WIN') THEN 1 END) as wins,
                    COALESCE(SUM(CASE 
                        WHEN result IN ('WON', 'WIN') THEN (odds - 1) 
                        WHEN result IN ('LOST', 'LOSS') THEN -1 
                        ELSE 0 
                    END), 0) as units_profit
                FROM all_bets
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                AND DATE(settled_at) = CURRENT_DATE
            """)
            today_settled = conn.execute(today_settled_query).fetchone()
            
            week_query = text("""
                SELECT 
                    COUNT(*) as total_bets,
                    COUNT(CASE WHEN result IN ('WON', 'WIN') THEN 1 END) as wins,
                    COUNT(CASE WHEN result IN ('LOST', 'LOSS') THEN 1 END) as losses,
                    COALESCE(SUM(CASE 
                        WHEN result IN ('WON', 'WIN') THEN (odds - 1) 
                        WHEN result IN ('LOST', 'LOSS') THEN -1 
                        ELSE 0 
                    END), 0) as units_profit
                FROM all_bets
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                AND DATE(settled_at) >= CURRENT_DATE - INTERVAL '7 days'
            """)
            week_stats = conn.execute(week_query).fetchone()
            
            month_query = text("""
                SELECT 
                    COUNT(*) as total_bets,
                    COUNT(CASE WHEN result IN ('WON', 'WIN') THEN 1 END) as wins,
                    COUNT(CASE WHEN result IN ('LOST', 'LOSS') THEN 1 END) as losses,
                    COALESCE(SUM(CASE 
                        WHEN result IN ('WON', 'WIN') THEN (odds - 1) 
                        WHEN result IN ('LOST', 'LOSS') THEN -1 
                        ELSE 0 
                    END), 0) as units_profit
                FROM all_bets
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                AND DATE(settled_at) >= DATE_TRUNC('month', CURRENT_DATE)
            """)
            month_stats = conn.execute(month_query).fetchone()
            
            pending_query = text("""
                SELECT 
                    (SELECT COUNT(*) FROM all_bets WHERE result IS NULL OR result = '') +
                    (SELECT COUNT(*) FROM football_opportunities WHERE UPPER(status) IN ('PENDING', 'IN_PROGRESS') AND mode != 'TEST')
                as pending
            """)
            pending = conn.execute(pending_query).fetchone()
            
            recent_query = text("""
                SELECT home_team, away_team, selection, odds, result, product, settled_at
                FROM all_bets
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                ORDER BY settled_at DESC NULLS LAST, id DESC
                LIMIT 10
            """)
            recent = conn.execute(recent_query).fetchall()
        
        def calc_roi(wins, total):
            if total == 0:
                return 0.0
            return (wins / total) * 100
        
        def calc_units_roi(units, total):
            if total == 0:
                return 0.0
            return (units / total) * 100
        
        all_total = all_time[0] or 0
        all_wins = all_time[1] or 0
        all_losses = all_time[2] or 0
        all_units = float(all_time[3] or 0)
        
        today_total = today_stats[0] or 0
        today_wins = today_stats[1] or 0
        today_losses = today_stats[2] or 0
        today_units = float(today_stats[3] or 0)
        today_pending = today_stats[4] or 0 if len(today_stats) > 4 else 0
        
        settled_today_total = today_settled[0] or 0 if today_settled else 0
        settled_today_wins = today_settled[1] or 0 if today_settled else 0
        settled_today_units = float(today_settled[2] or 0) if today_settled else 0
        
        week_total = week_stats[0] or 0
        week_wins = week_stats[1] or 0
        week_units = float(week_stats[3] or 0)
        
        month_total = month_stats[0] or 0
        month_wins = month_stats[1] or 0
        month_units = float(month_stats[3] or 0)
        
        return {
            "all_time": {
                "total": all_total,
                "wins": all_wins,
                "losses": all_losses,
                "hit_rate": calc_roi(all_wins, all_total),
                "units": all_units,
                "roi": calc_units_roi(all_units, all_total)
            },
            "today": {
                "total": today_total,
                "wins": today_wins,
                "losses": today_losses,
                "pending": today_pending,
                "hit_rate": calc_roi(today_wins, today_total - today_pending) if (today_total - today_pending) > 0 else 0,
                "units": today_units
            },
            "settled_today": {
                "total": settled_today_total,
                "wins": settled_today_wins,
                "units": settled_today_units
            },
            "week": {
                "total": week_total,
                "wins": week_wins,
                "hit_rate": calc_roi(week_wins, week_total),
                "units": week_units,
                "roi": calc_units_roi(week_units, week_total)
            },
            "month": {
                "total": month_total,
                "wins": month_wins,
                "hit_rate": calc_roi(month_wins, month_total),
                "units": month_units,
                "roi": calc_units_roi(month_units, month_total)
            },
            "pending": pending[0] if pending else 0,
            "recent": [
                {
                    "match": f"{r[0]} vs {r[1]}" if r[1] and not str(r[0]).startswith('PARLAY') else str(r[0]),
                    "pick": r[2],
                    "odds": float(r[3]) if r[3] else 0,
                    "result": r[4],
                    "product": r[5] if len(r) > 5 else "BET"
                } for r in recent
            ]
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
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
    
    all_time = stats.get("all_time", {})
    today = stats.get("today", {})
    settled_today = stats.get("settled_today", {})
    week = stats.get("week", {})
    month = stats.get("month", {})
    pending = stats.get("pending", 0)
    recent = stats.get("recent", [])
    
    roi = all_time.get("roi", 0)
    if roi >= 10:
        color = 0x00FF00  # Green
        status_emoji = "🚀"
    elif roi >= 0:
        color = 0x22C55E  # Light green
        status_emoji = "✅"
    elif roi >= -10:
        color = 0xFFA500  # Orange
        status_emoji = "⚠️"
    else:
        color = 0xFF5555  # Red
        status_emoji = "📉"
    
    units_display = f"+{all_time.get('units', 0):.1f}" if all_time.get('units', 0) >= 0 else f"{all_time.get('units', 0):.1f}"
    
    fields = [
        {
            "name": "📊 All-Time Performance",
            "value": f"**ROI:** {roi:+.1f}%\n**Units:** {units_display}u\n**Record:** {all_time.get('wins', 0)}W-{all_time.get('losses', 0)}L ({all_time.get('hit_rate', 0):.1f}%)",
            "inline": True
        },
        {
            "name": "📅 This Month",
            "value": f"**ROI:** {month.get('roi', 0):+.1f}%\n**Units:** {month.get('units', 0):+.1f}u\n**Bets:** {month.get('total', 0)} ({month.get('hit_rate', 0):.1f}%)",
            "inline": True
        },
        {
            "name": "📆 Last 7 Days",
            "value": f"**ROI:** {week.get('roi', 0):+.1f}%\n**Units:** {week.get('units', 0):+.1f}u\n**Bets:** {week.get('total', 0)} ({week.get('hit_rate', 0):.1f}%)",
            "inline": True
        },
        {
            "name": "🎯 Picks Today",
            "value": f"**Placed:** {today.get('total', 0)} bets\n**Settled:** {today.get('wins', 0)}W-{today.get('losses', 0)}L\n**Pending:** {today.get('pending', 0)}",
            "inline": True
        },
        {
            "name": "✅ Settled Today",
            "value": f"**Bets:** {settled_today.get('total', 0)}\n**Units:** {settled_today.get('units', 0):+.1f}u\n**Wins:** {settled_today.get('wins', 0)}",
            "inline": True
        }
    ]
    
    if recent:
        recent_lines = []
        for r in recent[:10]:
            emoji = "✅" if r["result"] in ["WON", "WIN"] else "❌"
            product = r.get("product", "BET")
            product_emoji = {"CORNERS": "🔢", "CARDS": "🟨", "VALUE_SINGLE": "⚽", "BASKET_SINGLE": "🏀", "BASKET_PARLAY": "🏀", "SGP": "🎲", "EXACT_SCORE": "🎯"}.get(product, "📊")
            match_short = r['match'][:20] + "..." if len(r['match']) > 20 else r['match']
            pick_short = r['pick'][:15] + "..." if len(r['pick']) > 15 else r['pick']
            recent_lines.append(f"{emoji}{product_emoji} {match_short} - {pick_short} @ {r['odds']:.2f}")
        fields.append({
            "name": "🔄 Last 10 Results",
            "value": "\n".join(recent_lines),
            "inline": False
        })
    
    embed = {
        "embeds": [{
            "title": f"{status_emoji} PGR Performance Report",
            "description": f"**{all_time.get('total', 0)}** total bets tracked | Updated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
            "color": color,
            "fields": fields,
            "footer": {
                "text": "PGR Sports Analytics • Value Betting System"
            },
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    
    return embed


def send_discord_stats(custom_message: Optional[str] = None) -> bool:
    """Send ROI stats to Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("⚠️ DISCORD_WEBHOOK_URL not set")
        return False
    
    try:
        stats = get_roi_stats()
        payload = build_discord_embed(stats)
        
        if custom_message:
            payload["content"] = custom_message
        
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
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
        emoji = "✅" if result in ["WON", "WIN"] else "❌"
        color = 0x00FF00 if result in ["WON", "WIN"] else 0xFF5555
        profit_str = f"+{profit:.1f}u" if profit > 0 else f"{profit:.1f}u"
        
        payload = {
            "embeds": [{
                "title": f"{emoji} Result: {result}",
                "description": f"**{match}**",
                "color": color,
                "fields": [
                    {"name": "Pick", "value": pick, "inline": True},
                    {"name": "Odds", "value": f"{odds:.2f}", "inline": True},
                    {"name": "P/L", "value": profit_str, "inline": True}
                ],
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        return response.status_code in [200, 204]
        
    except Exception as e:
        logger.error(f"❌ Discord result notification error: {e}")
        return False


if __name__ == "__main__":
    print("🔍 Testing Discord ROI webhook...")
    stats = get_roi_stats()
    print(f"📊 Stats: {stats}")
    
    if DISCORD_WEBHOOK_URL:
        success = send_discord_stats("📊 Manual stats update requested")
        print(f"{'✅' if success else '❌'} Discord send: {'success' if success else 'failed'}")
    else:
        print("⚠️ No DISCORD_WEBHOOK_URL configured")

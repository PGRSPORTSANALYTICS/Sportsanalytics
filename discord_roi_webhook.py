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
                FROM football_opportunities
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                AND mode != 'TEST'
            """)
            all_time = conn.execute(all_time_query).fetchone()
            
            today_query = text("""
                SELECT 
                    COUNT(*) as total_bets,
                    COUNT(CASE WHEN result IN ('WON', 'WIN') THEN 1 END) as wins,
                    COUNT(CASE WHEN result IN ('LOST', 'LOSS') THEN 1 END) as losses,
                    COALESCE(SUM(CASE 
                        WHEN result IN ('WON', 'WIN') THEN (odds - 1) 
                        WHEN result IN ('LOST', 'LOSS') THEN -1 
                        ELSE 0 
                    END), 0) as units_profit
                FROM football_opportunities
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                AND DATE(match_date) = :today
                AND mode != 'TEST'
            """)
            today_stats = conn.execute(today_query, {"today": str(today)}).fetchone()
            
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
                FROM football_opportunities
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                AND DATE(match_date) >= :week_ago
                AND mode != 'TEST'
            """)
            week_stats = conn.execute(week_query, {"week_ago": str(week_ago)}).fetchone()
            
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
                FROM football_opportunities
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                AND DATE(match_date) >= :month_start
                AND mode != 'TEST'
            """)
            month_stats = conn.execute(month_query, {"month_start": str(month_start)}).fetchone()
            
            pending_query = text("""
                SELECT COUNT(*) as pending
                FROM football_opportunities
                WHERE status = 'pending'
                AND mode != 'TEST'
            """)
            pending = conn.execute(pending_query).fetchone()
            
            recent_query = text("""
                SELECT home_team, away_team, selection, odds, result
                FROM football_opportunities
                WHERE result IN ('WON', 'WIN', 'LOST', 'LOSS')
                AND mode != 'TEST'
                ORDER BY match_date DESC, id DESC
                LIMIT 5
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
        today_units = float(today_stats[3] or 0)
        
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
                "hit_rate": calc_roi(today_wins, today_total),
                "units": today_units
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
                    "match": f"{r[0]} vs {r[1]}",
                    "pick": r[2],
                    "odds": float(r[3]) if r[3] else 0,
                    "result": r[4]
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
            "name": "🎯 Today",
            "value": f"**Units:** {today.get('units', 0):+.1f}u\n**Record:** {today.get('wins', 0)}W / {today.get('total', 0)} bets",
            "inline": True
        },
        {
            "name": "⏳ Pending",
            "value": f"**{pending}** bets awaiting results",
            "inline": True
        }
    ]
    
    if recent:
        recent_lines = []
        for r in recent[:5]:
            emoji = "✅" if r["result"] in ["WON", "WIN"] else "❌"
            recent_lines.append(f"{emoji} {r['pick']} @ {r['odds']:.2f}")
        fields.append({
            "name": "🔄 Recent Results",
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

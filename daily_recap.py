#!/usr/bin/env python3
"""
Daily & Weekly Recap - Discord ROI Notifications
Daily: Every night at 22:30 - summarizes the day
Weekly: Every Sunday at 22:30 - summarizes Monday to Sunday
"""

import os
import logging
import requests
from datetime import datetime, date, timedelta
from db_connection import DatabaseConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '-1003269011722')


def send_discord_embed(title: str, description: str, color: int, fields: list = None):
    """Send a rich embed to Discord"""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("No DISCORD_WEBHOOK_URL set")
        return False
    
    try:
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "PGR Sports Analytics"}
        }
        
        if fields:
            embed["fields"] = fields
        
        payload = {"embeds": [embed]}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("✅ Discord embed sent successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Discord send error: {e}")
        return False


def send_telegram_message(message: str):
    """Send message to Telegram channel via HTTP API"""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("No TELEGRAM_BOT_TOKEN set")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("✅ Recap sent to Telegram")
        return True
    except Exception as e:
        logger.error(f"❌ Telegram send error: {e}")
        return False


def get_results_for_date_range(start_date: date, end_date: date):
    """Get all results for a date range from all products"""
    
    db = DatabaseConnection()
    results = {
        'value_singles': {'won': 0, 'lost': 0, 'profit': 0},
        'corners_cards': {'won': 0, 'lost': 0, 'profit': 0},
        'parlays': {'won': 0, 'lost': 0, 'profit': 0},
        'basketball': {'won': 0, 'lost': 0, 'profit': 0}
    }
    
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT selection, odds, outcome, market
                FROM football_opportunities
                WHERE match_date::date BETWEEN %s AND %s
                AND outcome IN ('won', 'lost', 'WON', 'LOST')
            """, (start_date, end_date))
            rows = cur.fetchall()
            
            for row in rows:
                selection, odds, outcome, market = row
                is_win = outcome.lower() == 'won'
                profit_units = (float(odds) - 1) if is_win else -1
                
                is_corners_cards = any(x in str(selection).lower() for x in ['corner', 'card'])
                cat = 'corners_cards' if is_corners_cards else 'value_singles'
                
                if is_win:
                    results[cat]['won'] += 1
                else:
                    results[cat]['lost'] += 1
                results[cat]['profit'] += profit_units
            
            cur.execute("""
                SELECT total_odds, result
                FROM ml_parlay_predictions
                WHERE match_date::date BETWEEN %s AND %s
                AND result IN ('WON', 'LOST')
            """, (start_date, end_date))
            rows = cur.fetchall()
            
            for row in rows:
                odds, result = row
                is_win = result == 'WON'
                profit_units = (float(odds) - 1) if is_win else -1
                
                if is_win:
                    results['parlays']['won'] += 1
                else:
                    results['parlays']['lost'] += 1
                results['parlays']['profit'] += profit_units
            
            cur.execute("""
                SELECT odds, status
                FROM basketball_predictions
                WHERE commence_time::date BETWEEN %s AND %s
                AND status IN ('won', 'lost', 'WON', 'LOST')
            """, (start_date, end_date))
            rows = cur.fetchall()
            
            for row in rows:
                odds, status = row
                is_win = status.lower() == 'won'
                profit_units = (float(odds) - 1) if is_win else -1
                
                if is_win:
                    results['basketball']['won'] += 1
                else:
                    results['basketball']['lost'] += 1
                results['basketball']['profit'] += profit_units
    
    return results


def send_daily_discord_recap():
    """Send daily recap to Discord at 22:30"""
    logger.info("📊 Generating daily Discord recap...")
    
    today = date.today()
    results = get_results_for_date_range(today, today)
    
    total_won = sum(r['won'] for r in results.values())
    total_lost = sum(r['lost'] for r in results.values())
    total_profit = sum(r['profit'] for r in results.values())
    total_bets = total_won + total_lost
    
    if total_bets == 0:
        logger.info("No settled bets today, skipping daily recap")
        return
    
    hit_rate = (total_won / total_bets * 100) if total_bets > 0 else 0
    
    if total_profit >= 5:
        color = 0x10B981  # Green
    elif total_profit >= 0:
        color = 0xF59E0B  # Orange
    else:
        color = 0xEF4444  # Red
    
    profit_emoji = "🟢" if total_profit >= 0 else "🔴"
    today_str = today.strftime("%A, %B %d")
    
    description = f"""
**Record:** {total_won}-{total_lost} ({hit_rate:.1f}%)
**Net Profit:** {profit_emoji} {total_profit:+.2f} units
"""
    
    fields = []
    
    if results['value_singles']['won'] + results['value_singles']['lost'] > 0:
        vs = results['value_singles']
        fields.append({
            "name": "⚽ Value Singles",
            "value": f"{vs['won']}-{vs['lost']} | {vs['profit']:+.2f}u",
            "inline": True
        })
    
    if results['corners_cards']['won'] + results['corners_cards']['lost'] > 0:
        cc = results['corners_cards']
        fields.append({
            "name": "🔢 Corners & Cards",
            "value": f"{cc['won']}-{cc['lost']} | {cc['profit']:+.2f}u",
            "inline": True
        })
    
    if results['parlays']['won'] + results['parlays']['lost'] > 0:
        p = results['parlays']
        fields.append({
            "name": "🎲 Parlays",
            "value": f"{p['won']}-{p['lost']} | {p['profit']:+.2f}u",
            "inline": True
        })
    
    if results['basketball']['won'] + results['basketball']['lost'] > 0:
        bb = results['basketball']
        fields.append({
            "name": "🏀 Basketball",
            "value": f"{bb['won']}-{bb['lost']} | {bb['profit']:+.2f}u",
            "inline": True
        })
    
    send_discord_embed(
        title=f"📊 Daily Recap - {today_str}",
        description=description,
        color=color,
        fields=fields
    )
    
    logger.info(f"📊 Daily recap sent: {total_bets} bets, {total_profit:+.2f} units")


def send_weekly_discord_recap():
    """Send weekly recap to Discord on Sunday at 22:30 (Mon-Sun)"""
    logger.info("📊 Generating weekly Discord recap...")
    
    today = date.today()
    
    days_since_monday = today.weekday()
    monday = today - timedelta(days=days_since_monday)
    sunday = today
    
    results = get_results_for_date_range(monday, sunday)
    
    total_won = sum(r['won'] for r in results.values())
    total_lost = sum(r['lost'] for r in results.values())
    total_profit = sum(r['profit'] for r in results.values())
    total_bets = total_won + total_lost
    
    if total_bets == 0:
        logger.info("No settled bets this week, skipping weekly recap")
        return
    
    hit_rate = (total_won / total_bets * 100) if total_bets > 0 else 0
    roi = (total_profit / total_bets * 100) if total_bets > 0 else 0
    
    if total_profit >= 10:
        color = 0x10B981  # Green
    elif total_profit >= 0:
        color = 0xF59E0B  # Orange
    else:
        color = 0xEF4444  # Red
    
    profit_emoji = "🟢" if total_profit >= 0 else "🔴"
    week_str = f"{monday.strftime('%b %d')} - {sunday.strftime('%b %d, %Y')}"
    
    description = f"""
**Total Bets:** {total_bets}
**Record:** {total_won}-{total_lost} ({hit_rate:.1f}%)
**ROI:** {roi:+.1f}%
**Net Profit:** {profit_emoji} **{total_profit:+.2f} units**
"""
    
    fields = []
    
    if results['value_singles']['won'] + results['value_singles']['lost'] > 0:
        vs = results['value_singles']
        vs_bets = vs['won'] + vs['lost']
        vs_roi = (vs['profit'] / vs_bets * 100) if vs_bets > 0 else 0
        fields.append({
            "name": "⚽ Value Singles",
            "value": f"{vs['won']}-{vs['lost']} | {vs['profit']:+.2f}u ({vs_roi:+.1f}%)",
            "inline": True
        })
    
    if results['corners_cards']['won'] + results['corners_cards']['lost'] > 0:
        cc = results['corners_cards']
        cc_bets = cc['won'] + cc['lost']
        cc_roi = (cc['profit'] / cc_bets * 100) if cc_bets > 0 else 0
        fields.append({
            "name": "🔢 Corners & Cards",
            "value": f"{cc['won']}-{cc['lost']} | {cc['profit']:+.2f}u ({cc_roi:+.1f}%)",
            "inline": True
        })
    
    if results['parlays']['won'] + results['parlays']['lost'] > 0:
        p = results['parlays']
        p_bets = p['won'] + p['lost']
        p_roi = (p['profit'] / p_bets * 100) if p_bets > 0 else 0
        fields.append({
            "name": "🎲 Parlays",
            "value": f"{p['won']}-{p['lost']} | {p['profit']:+.2f}u ({p_roi:+.1f}%)",
            "inline": True
        })
    
    if results['basketball']['won'] + results['basketball']['lost'] > 0:
        bb = results['basketball']
        bb_bets = bb['won'] + bb['lost']
        bb_roi = (bb['profit'] / bb_bets * 100) if bb_bets > 0 else 0
        fields.append({
            "name": "🏀 Basketball",
            "value": f"{bb['won']}-{bb['lost']} | {bb['profit']:+.2f}u ({bb_roi:+.1f}%)",
            "inline": True
        })
    
    send_discord_embed(
        title=f"📈 Weekly Recap - {week_str}",
        description=description,
        color=color,
        fields=fields
    )
    
    logger.info(f"📊 Weekly recap sent: {total_bets} bets, {total_profit:+.2f} units, {roi:+.1f}% ROI")


def send_daily_recap():
    """Legacy function - now sends to Discord"""
    send_daily_discord_recap()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'weekly':
        send_weekly_discord_recap()
    else:
        send_daily_discord_recap()

#!/usr/bin/env python3
"""
Daily Recap - Sends a summary of all day's results at 22:30
Covers: Exact Score, Value Singles, SGP, and College Basketball
"""

import os
import logging
import requests
from datetime import datetime, date
from db_connection import DatabaseConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '-1003269011722')


def send_telegram_message(message: str):
    """Send message to Telegram channel via HTTP API"""
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


def get_todays_results():
    """Get all results for today from all products"""
    today = date.today().isoformat()
    
    db = DatabaseConnection()
    results = {
        'exact_score': {'won': 0, 'lost': 0, 'profit': 0, 'details': []},
        'value_singles': {'won': 0, 'lost': 0, 'profit': 0, 'details': []},
        'sgp': {'won': 0, 'lost': 0, 'profit': 0, 'details': []},
        'basketball': {'won': 0, 'lost': 0, 'profit': 0, 'details': []}
    }
    
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT home_team, away_team, selection, odds, stake, outcome, actual_score, market
                FROM football_opportunities
                WHERE match_date::date = %s
                AND status = 'settled'
                ORDER BY updated_at DESC
            """, (today,))
            rows = cur.fetchall()
            
            for row in rows:
                home, away, selection, odds, stake, outcome, score, market = row
                is_win = outcome in ('won', 'win', 'WON', 'WIN')
                profit = (odds - 1) * stake if is_win else -stake
                
                is_exact = selection and 'Exact Score' in str(selection)
                if is_exact or (market and 'exact' in str(market).lower()):
                    cat = 'exact_score'
                else:
                    cat = 'value_singles'
                
                if is_win:
                    results[cat]['won'] += 1
                else:
                    results[cat]['lost'] += 1
                results[cat]['profit'] += profit
                
                if is_win:
                    results[cat]['details'].append(
                        f"✅ {home} vs {away} | {selection} @ {odds:.2f} | +{profit:.0f} kr"
                    )
            
            cur.execute("""
                SELECT home_team, away_team, LEFT(parlay_description, 30), bookmaker_odds, stake, result
                FROM sgp_predictions
                WHERE match_date::date = %s
                AND result IS NOT NULL
                ORDER BY settled_timestamp DESC
            """, (today,))
            rows = cur.fetchall()
            
            for row in rows:
                home, away, parlay, odds, stake, result = row
                is_win = result in ('WON', 'WIN')
                profit = (odds - 1) * stake if is_win else -stake
                
                if is_win:
                    results['sgp']['won'] += 1
                else:
                    results['sgp']['lost'] += 1
                results['sgp']['profit'] += profit
                
                if is_win:
                    results['sgp']['details'].append(
                        f"✅ {home} vs {away} | {parlay}... @ {odds:.2f} | +{profit:.0f} kr"
                    )
            
            cur.execute("""
                SELECT match, selection, odds, status
                FROM basketball_predictions
                WHERE commence_time::date = %s
                AND status IN ('won', 'lost', 'WON', 'LOST')
                ORDER BY verified_at DESC
            """, (today,))
            rows = cur.fetchall()
            
            stake = 160
            for row in rows:
                match, selection, odds, status = row
                is_win = status in ('won', 'WON')
                profit = (odds - 1) * stake if is_win else -stake
                
                if is_win:
                    results['basketball']['won'] += 1
                else:
                    results['basketball']['lost'] += 1
                results['basketball']['profit'] += profit
                
                if is_win:
                    results['basketball']['details'].append(
                        f"✅ {match} | {selection} @ {odds:.2f} | +{profit:.0f} kr"
                    )
    
    return results


def format_recap_message(results: dict) -> str:
    """Format the daily recap message"""
    today = datetime.now().strftime("%A, %B %d")
    
    total_won = sum(r['won'] for r in results.values())
    total_lost = sum(r['lost'] for r in results.values())
    total_profit = sum(r['profit'] for r in results.values())
    
    msg = f"""
<b>📊 DAILY RECAP - {today}</b>

━━━━━━━━━━━━━━━━━━━━━━

<b>⚽ EXACT SCORE</b>
Won: {results['exact_score']['won']} | Lost: {results['exact_score']['lost']}
Profit: <b>{results['exact_score']['profit']:+,.0f} kr</b>
"""
    
    if results['exact_score']['details']:
        msg += "\n" + "\n".join(results['exact_score']['details'][:3])
    
    msg += f"""

<b>📈 VALUE SINGLES</b>
Won: {results['value_singles']['won']} | Lost: {results['value_singles']['lost']}
Profit: <b>{results['value_singles']['profit']:+,.0f} kr</b>
"""
    
    if results['value_singles']['details']:
        msg += "\n" + "\n".join(results['value_singles']['details'][:3])
    
    msg += f"""

<b>🎲 SGP PARLAYS</b>
Won: {results['sgp']['won']} | Lost: {results['sgp']['lost']}
Profit: <b>{results['sgp']['profit']:+,.0f} kr</b>
"""
    
    if results['sgp']['details']:
        msg += "\n" + "\n".join(results['sgp']['details'][:5])
    
    msg += f"""

<b>🏀 COLLEGE BASKETBALL</b>
Won: {results['basketball']['won']} | Lost: {results['basketball']['lost']}
Profit: <b>{results['basketball']['profit']:+,.0f} kr</b>
"""
    
    if results['basketball']['details']:
        msg += "\n" + "\n".join(results['basketball']['details'][:3])
    
    profit_color = "🟢" if total_profit >= 0 else "🔴"
    
    msg += f"""

━━━━━━━━━━━━━━━━━━━━━━

<b>{profit_color} DAILY TOTAL</b>
Won: {total_won} | Lost: {total_lost}
Hit Rate: {(total_won/(total_won+total_lost)*100) if (total_won+total_lost) > 0 else 0:.1f}%
<b>Net Profit: {total_profit:+,.0f} kr</b>

━━━━━━━━━━━━━━━━━━━━━━
🤖 PGR AI Predictions
"""
    
    return msg


def send_daily_recap():
    """Main function to send daily recap"""
    logger.info("📊 Generating daily recap...")
    
    results = get_todays_results()
    
    total_bets = sum(r['won'] + r['lost'] for r in results.values())
    
    if total_bets == 0:
        logger.info("No settled bets today, skipping recap")
        return
    
    message = format_recap_message(results)
    
    send_telegram_message(message)
    
    logger.info(f"📊 Recap sent: {total_bets} bets, {sum(r['profit'] for r in results.values()):+,.0f} kr profit")


if __name__ == "__main__":
    send_daily_recap()

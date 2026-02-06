"""
Free Picks Engine - Sends selected free picks to Discord
Selects 1-2 high-value picks daily for free distribution.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor

DISCORD_FREE_PICKS_WEBHOOK_URL = os.getenv("DISCORD_FREE_PICKS_WEBHOOK_URL")

HIGH_VISIBILITY_LEAGUES = [
    'Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1',
    'English Championship', 'Primeira Liga', 'Eredivisie',
    'Champions League', 'Europa League'
]

ALLOWED_SELECTIONS = ['Home Win', 'Away Win', 'Over 2.5 Goals', 'Under 2.5 Goals']
ODDS_MIN = 1.70
ODDS_MAX = 2.20
MIN_CONFIDENCE = 0.60


def get_db_connection():
    """Get database connection."""
    import time
    for attempt in range(3):
        try:
            conn = psycopg2.connect(
                os.getenv('DATABASE_URL'),
                connect_timeout=10,
                options='-c statement_timeout=30000'
            )
            return conn
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise e


def get_free_pick_candidates(hours_ahead: int = 24, limit: int = 5) -> List[Dict]:
    """Get best pick candidates for free distribution."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                id, home_team, away_team, league, match_date,
                selection, odds, model_prob, edge_percentage,
                confidence, trust_level, analysis
            FROM football_opportunities
            WHERE match_date::timestamp > NOW()
              AND match_date::timestamp < NOW() + INTERVAL '%s hours'
              AND market = 'Value Single'
              AND odds BETWEEN %s AND %s
              AND confidence >= %s
              AND outcome IS NULL
              AND league IN %s
              AND selection IN %s
            ORDER BY 
                CASE WHEN trust_level = 'L1' THEN 1 
                     WHEN trust_level = 'L2' THEN 2 
                     ELSE 3 END,
                edge_percentage DESC NULLS LAST,
                confidence DESC
            LIMIT %s
        """, (hours_ahead, ODDS_MIN, ODDS_MAX, MIN_CONFIDENCE, 
              tuple(HIGH_VISIBILITY_LEAGUES), tuple(ALLOWED_SELECTIONS), limit))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return [dict(r) for r in results]
    except Exception as e:
        print(f"Error getting free pick candidates: {e}")
        return []


def format_free_pick(pick: Dict) -> str:
    """Format a pick for Discord display."""
    from discord_notifier import build_analysis_reason
    
    home = pick.get('home_team', 'TBD')
    away = pick.get('away_team', 'TBD')
    league = pick.get('league', 'Unknown')
    selection = pick.get('selection', 'N/A')
    odds = pick.get('odds', 0)
    
    reason = build_analysis_reason(pick)
    
    content = "🎯 **VALUE SINGLES — Today's Picks**\n\n"
    content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += f"**{league}**\n"
    content += f"• {home} vs {away} — **{selection}** @ {odds:.2f} (TBD) 🔘\n"
    if reason:
        content += f"{reason}\n"
    content += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += "*1 pick(s) | Flat 1u | PGR Analytics*"
    
    return content


def send_free_pick_to_discord(content: str, title: str = "") -> bool:
    """Send free pick to Discord webhook."""
    if not DISCORD_FREE_PICKS_WEBHOOK_URL:
        print("No Free Picks Discord webhook configured")
        return False
    
    try:
        embed = {
            "description": content[:4000],
            "color": 3066993,
            "footer": {"text": "PGR Sports Analytics — Value Singles"}
        }
        
        payload = {"embeds": [embed]}
        
        response = requests.post(
            DISCORD_FREE_PICKS_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        
        if response.status_code in [200, 204]:
            print(f"Sent free pick to Discord: {title}")
            return True
        else:
            print(f"Discord error: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error sending to Discord: {e}")
        return False


def mark_pick_as_free_sent(pick_id: int) -> bool:
    """Mark a pick as sent to free channel."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE football_opportunities 
            SET discord_sent = TRUE 
            WHERE id = %s
        """, (pick_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error marking pick as sent: {e}")
        return False


def run_free_picks(picks_to_send: int = 1):
    """Run free picks distribution."""
    print(f"\n{'='*50}")
    print(f"FREE PICKS ENGINE - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*50}\n")
    
    candidates = get_free_pick_candidates(hours_ahead=48, limit=picks_to_send + 2)
    
    if not candidates:
        print("No suitable picks found for free distribution")
        return 0
    
    sent = 0
    for pick in candidates[:picks_to_send]:
        content = format_free_pick(pick)
        title = f"🎁 FREE PICK: {pick['home_team']} vs {pick['away_team']}"
        
        print(f"\n--- FREE PICK ---")
        print(content)
        
        if send_free_pick_to_discord(content, title):
            mark_pick_as_free_sent(pick['id'])
            sent += 1
    
    print(f"\nFree Picks Complete: {sent}/{picks_to_send} picks sent")
    return sent


def send_specific_pick(home_team: str, away_team: str) -> bool:
    """Send a specific match as a free pick."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                id, home_team, away_team, league, match_date,
                selection, odds, model_prob, edge_percentage,
                confidence, trust_level, analysis
            FROM football_opportunities
            WHERE (home_team ILIKE %s AND away_team ILIKE %s)
              AND market = 'Value Single'
              AND outcome IS NULL
            ORDER BY match_date DESC
            LIMIT 1
        """, (f"%{home_team}%", f"%{away_team}%"))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            pick = dict(result)
            content = format_free_pick(pick)
            title = f"🎁 FREE PICK: {pick['home_team']} vs {pick['away_team']}"
            return send_free_pick_to_discord(content, title)
        else:
            print(f"No pick found for {home_team} vs {away_team}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    run_free_picks(1)

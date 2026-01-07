"""
Bet Distribution Controller - Central control for all Discord bet distribution.
Ensures ONLY valid, non-duplicate, same-day bets are sent.
"""

import os
import json
import hashlib
import requests
from datetime import datetime, date
from typing import Optional, Dict, List, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_FREE_PICKS_WEBHOOK_URL = os.getenv("DISCORD_FREE_PICKS_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


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


def ensure_distribution_log_table():
    """Ensure the bet distribution log table exists."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bet_distribution_log (
                id SERIAL PRIMARY KEY,
                bet_id VARCHAR(255) UNIQUE NOT NULL,
                opportunity_id INTEGER,
                sport VARCHAR(50),
                league VARCHAR(255),
                home_team VARCHAR(255),
                away_team VARCHAR(255),
                market VARCHAR(100),
                selection VARCHAR(255),
                line VARCHAR(100),
                odds DECIMAL(5,2),
                units DECIMAL(5,2),
                event_date DATE,
                discord_channel VARCHAR(100),
                sent_at TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error creating distribution log table: {e}")
        return False


def generate_bet_id(sport: str, league: str, event_id: str, market: str, 
                    selection: str, line: str, event_date: str) -> str:
    """Generate unique bet ID using hash of key fields."""
    raw = f"{sport}|{league}|{event_id}|{market}|{selection}|{line}|{event_date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def is_duplicate_bet(bet_id: str) -> bool:
    """Check if bet has already been sent."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM bet_distribution_log WHERE bet_id = %s LIMIT 1
        """, (bet_id,))
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}")
        return True


def is_same_day_event(event_date) -> bool:
    """Check if event is happening today (server date)."""
    try:
        today = date.today()
        
        if isinstance(event_date, str):
            if 'T' in event_date:
                event_date = event_date.split('T')[0]
            parsed = datetime.strptime(event_date, '%Y-%m-%d').date()
        elif isinstance(event_date, datetime):
            parsed = event_date.date()
        elif isinstance(event_date, date):
            parsed = event_date
        else:
            return False
        
        return parsed == today
    except Exception as e:
        logger.error(f"Error parsing event date: {e}")
        return False


def log_sent_bet(bet_id: str, opportunity_id: int, sport: str, league: str,
                 home_team: str, away_team: str, market: str, selection: str,
                 line: str, odds: float, units: float, event_date, 
                 discord_channel: str) -> bool:
    """Log a sent bet to prevent duplicates."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if isinstance(event_date, datetime):
            event_date = event_date.date()
        elif isinstance(event_date, str):
            if 'T' in event_date:
                event_date = event_date.split('T')[0]
        
        cur.execute("""
            INSERT INTO bet_distribution_log 
            (bet_id, opportunity_id, sport, league, home_team, away_team,
             market, selection, line, odds, units, event_date, discord_channel)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (bet_id) DO NOTHING
        """, (bet_id, opportunity_id, sport, league, home_team, away_team,
              market, selection, line, odds, units, event_date, discord_channel))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"📝 Logged bet: {bet_id[:8]}... | {home_team} vs {away_team} | {selection} @ {odds}")
        return True
    except Exception as e:
        logger.error(f"Error logging bet: {e}")
        return False


def get_todays_sent_count(discord_channel: str = None) -> int:
    """Get count of bets sent today."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if discord_channel:
            cur.execute("""
                SELECT COUNT(*) FROM bet_distribution_log 
                WHERE DATE(sent_at) = CURRENT_DATE AND discord_channel = %s
            """, (discord_channel,))
        else:
            cur.execute("""
                SELECT COUNT(*) FROM bet_distribution_log 
                WHERE DATE(sent_at) = CURRENT_DATE
            """)
        
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error getting sent count: {e}")
        return 0


def validate_and_send_bet(
    opportunity_id: int,
    sport: str,
    league: str,
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    line: str,
    odds: float,
    units: float,
    event_date,
    confidence: float,
    trust_level: str,
    discord_channel: str,
    webhook_url: str
) -> Tuple[bool, str]:
    """
    Validate and send a bet to Discord.
    Returns (success, reason).
    """
    ensure_distribution_log_table()
    
    if not is_same_day_event(event_date):
        return False, "EVENT_NOT_TODAY"
    
    event_id = f"{home_team}_{away_team}"
    event_date_str = str(event_date)[:10] if event_date else ""
    
    bet_id = generate_bet_id(sport, league, event_id, market, selection, line, event_date_str)
    
    if is_duplicate_bet(bet_id):
        return False, "DUPLICATE_BET"
    
    if not webhook_url:
        return False, "NO_WEBHOOK"
    
    if isinstance(event_date, datetime):
        date_display = event_date.strftime('%H:%M UTC')
    elif isinstance(event_date, str):
        date_display = event_date
    else:
        date_display = "Today"
    
    trust_emoji = "🟢" if trust_level in ['L1', 'L1_HIGH_TRUST'] else "🟡" if trust_level == 'L2' else "⚪"
    
    content = f"""**{home_team} vs {away_team}**
*{league}*
📅 {date_display}

━━━━━━━━━━━━━━━━━━━━

**🎯 Selection:** {selection}
**💰 Odds:** {odds:.2f}
**📊 Confidence:** {confidence:.0f}%
**{trust_emoji} Trust Level:** {trust_level}
**📏 Stake:** {units:.1f} units

━━━━━━━━━━━━━━━━━━━━

*PGR Sports Analytics*
*Flat stake | Bet responsibly*
"""
    
    try:
        embed = {
            "description": content[:4000],
            "color": 3066993,
            "footer": {"text": f"Bet ID: {bet_id[:8]}"}
        }
        
        title = f"🎯 {home_team} vs {away_team}"
        embed["title"] = title
        
        payload = {"embeds": [embed]}
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        
        if response.status_code in [200, 204]:
            log_sent_bet(
                bet_id=bet_id,
                opportunity_id=opportunity_id,
                sport=sport,
                league=league,
                home_team=home_team,
                away_team=away_team,
                market=market,
                selection=selection,
                line=line,
                odds=odds,
                units=units,
                event_date=event_date,
                discord_channel=discord_channel
            )
            logger.info(f"✅ SENT: {home_team} vs {away_team} | {selection} @ {odds} → {discord_channel}")
            return True, "SUCCESS"
        else:
            logger.error(f"Discord error: {response.status_code}")
            return False, f"DISCORD_ERROR_{response.status_code}"
    except Exception as e:
        logger.error(f"Send error: {e}")
        return False, f"SEND_ERROR"


def distribute_free_picks(max_picks: int = 2) -> int:
    """Distribute today's free picks with full validation."""
    ensure_distribution_log_table()
    
    logger.info(f"\n{'='*50}")
    logger.info(f"BET DISTRIBUTION CONTROLLER - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    logger.info(f"{'='*50}")
    
    already_sent = get_todays_sent_count('free_picks')
    if already_sent >= max_picks:
        logger.info(f"⏸️ Daily limit reached: {already_sent}/{max_picks} picks already sent today")
        return 0
    
    remaining = max_picks - already_sent
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                id, home_team, away_team, league, match_date,
                selection, odds, model_prob, edge_percentage,
                confidence, trust_level, market
            FROM football_opportunities
            WHERE DATE(match_date::timestamp) = CURRENT_DATE
              AND market = 'Value Single'
              AND odds BETWEEN 1.70 AND 2.20
              AND confidence >= 60
              AND outcome IS NULL
              AND selection IN ('Home Win', 'Away Win', 'Over 2.5 Goals', 'Under 2.5 Goals')
            ORDER BY 
                CASE WHEN trust_level IN ('L1', 'L1_HIGH_TRUST') THEN 1 
                     WHEN trust_level = 'L2' THEN 2 
                     ELSE 3 END,
                edge_percentage DESC NULLS LAST,
                confidence DESC
            LIMIT %s
        """, (remaining + 5,))
        
        candidates = cur.fetchall()
        cur.close()
        conn.close()
        
        if not candidates:
            logger.info("❌ No valid same-day picks found")
            return 0
        
        sent = 0
        for pick in candidates:
            if sent >= remaining:
                break
            
            success, reason = validate_and_send_bet(
                opportunity_id=pick['id'],
                sport='football',
                league=pick['league'] or 'Unknown',
                home_team=pick['home_team'],
                away_team=pick['away_team'],
                market=pick['market'],
                selection=pick['selection'],
                line=pick['selection'],
                odds=float(pick['odds'] or 0),
                units=1.0,
                event_date=pick['match_date'],
                confidence=float(pick['confidence'] or 0),
                trust_level=pick['trust_level'] or 'L3',
                discord_channel='free_picks',
                webhook_url=DISCORD_FREE_PICKS_WEBHOOK_URL
            )
            
            if success:
                sent += 1
            else:
                logger.debug(f"⏭️ Skipped: {pick['home_team']} vs {pick['away_team']} - {reason}")
        
        logger.info(f"\n📊 Distribution Summary: {sent}/{remaining} picks sent (Total today: {already_sent + sent})")
        return sent
        
    except Exception as e:
        logger.error(f"Distribution error: {e}")
        return 0


def get_distribution_stats() -> Dict:
    """Get distribution statistics."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                discord_channel,
                COUNT(*) as total_sent,
                COUNT(DISTINCT DATE(sent_at)) as days_active,
                MAX(sent_at) as last_sent
            FROM bet_distribution_log
            GROUP BY discord_channel
        """)
        
        stats = cur.fetchall()
        cur.close()
        conn.close()
        
        return {row['discord_channel']: dict(row) for row in stats}
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {}


if __name__ == "__main__":
    ensure_distribution_log_table()
    sent = distribute_free_picks(2)
    print(f"\nDistributed {sent} picks")
    
    stats = get_distribution_stats()
    print(f"\nDistribution Stats: {json.dumps(stats, default=str, indent=2)}")

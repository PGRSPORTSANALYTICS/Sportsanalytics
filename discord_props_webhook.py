"""
Discord Props Webhook - Sends Corners, Cards, and Shots picks to Discord
"""

import os
import requests
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_PROPS_WEBHOOK_URL = os.environ.get("DISCORD_PROPS_WEBHOOK_URL", "")


def get_db_url() -> str:
    return os.environ.get("DATABASE_URL", "")


def send_props_picks_to_discord(picks: List[Dict], market_type: str = "PROPS") -> bool:
    """Send Corners/Cards/Shots picks to Discord props channel."""
    if not DISCORD_PROPS_WEBHOOK_URL:
        logger.warning("No DISCORD_PROPS_WEBHOOK_URL configured")
        return False
    
    if not picks:
        logger.info("No picks to send")
        return True
    
    try:
        embeds = []
        
        for pick in picks[:10]:
            market = pick.get('market', 'Props')
            home_team = pick.get('home_team', 'TBD')
            away_team = pick.get('away_team', 'TBD')
            selection = pick.get('selection', '')
            odds = pick.get('odds', 0)
            ev = pick.get('ev', 0) or pick.get('edge_percentage', 0)
            confidence = pick.get('confidence', 0)
            kickoff = pick.get('match_date', '')
            league = pick.get('league', '')
            
            if market == 'Corners':
                emoji = "🔷"
                color = 0x3498db
            elif market == 'Cards':
                emoji = "🟨"
                color = 0xf1c40f
            elif market == 'Shots':
                emoji = "🎯"
                color = 0xe74c3c
            else:
                emoji = "📊"
                color = 0x9b59b6
            
            ev_bullets = "🔥🔥🔥" if ev >= 8 else "🔥🔥" if ev >= 5 else "🔥" if ev >= 3 else ""
            
            embed = {
                "title": f"{emoji} {market.upper()} | {selection}",
                "description": f"**{home_team}** vs **{away_team}**",
                "color": color,
                "fields": [
                    {"name": "📊 Odds", "value": f"`{odds:.2f}`", "inline": True},
                    {"name": "💎 EV", "value": f"`+{ev:.1f}%` {ev_bullets}", "inline": True},
                    {"name": "🎯 Confidence", "value": f"`{confidence:.0f}%`", "inline": True},
                ],
                "footer": {"text": f"{league} • {kickoff[:16] if kickoff else 'TBD'}"},
                "timestamp": datetime.utcnow().isoformat()
            }
            
            embeds.append(embed)
        
        chunk_size = 10
        for i in range(0, len(embeds), chunk_size):
            chunk = embeds[i:i + chunk_size]
            payload = {
                "username": "PGR Props Bot",
                "embeds": chunk
            }
            
            response = requests.post(DISCORD_PROPS_WEBHOOK_URL, json=payload, timeout=10)
            
            if response.status_code not in [200, 204]:
                logger.error(f"Discord props webhook failed: {response.status_code} - {response.text}")
                return False
        
        logger.info(f"✅ Sent {len(picks)} props picks to Discord")
        return True
        
    except Exception as e:
        logger.error(f"Discord props webhook error: {e}")
        return False


def send_new_props_picks() -> Dict[str, int]:
    """Query new unsent Corners/Cards/Shots picks and send to Discord."""
    try:
        db_url = get_db_url()
        if not db_url:
            return {"sent": 0, "error": "No database URL"}
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            query = text("""
                SELECT id, home_team, away_team, match_date, market, selection, 
                       odds, edge_percentage, confidence, league, trust_level
                FROM football_opportunities 
                WHERE market IN ('Corners', 'Cards', 'Shots')
                  AND mode = 'PROD'
                  AND DATE(match_date) >= CURRENT_DATE
                  AND (discord_sent IS NULL OR discord_sent = false)
                  AND edge_percentage >= 3
                ORDER BY match_date ASC, edge_percentage DESC
                LIMIT 20
            """)
            
            results = conn.execute(query).fetchall()
            
            if not results:
                return {"sent": 0, "message": "No new props picks"}
            
            picks = []
            ids_to_update = []
            
            for row in results:
                picks.append({
                    'id': row[0],
                    'home_team': row[1],
                    'away_team': row[2],
                    'match_date': str(row[3]) if row[3] else '',
                    'market': row[4],
                    'selection': row[5],
                    'odds': float(row[6]) if row[6] else 0,
                    'ev': float(row[7]) if row[7] else 0,
                    'confidence': float(row[8]) if row[8] else 0,
                    'league': row[9] or '',
                    'trust_level': row[10] or ''
                })
                ids_to_update.append(row[0])
            
            success = send_props_picks_to_discord(picks)
            
            if success and ids_to_update:
                update_query = text("""
                    UPDATE football_opportunities 
                    SET discord_sent = true 
                    WHERE id = ANY(:ids)
                """)
                conn.execute(update_query, {"ids": ids_to_update})
                conn.commit()
            
            return {"sent": len(picks) if success else 0}
        
    except Exception as e:
        logger.error(f"Error sending new props picks: {e}")
        return {"sent": 0, "error": str(e)}


def send_manual_props_summary() -> bool:
    """Send a summary of today's props picks to Discord."""
    try:
        db_url = get_db_url()
        if not db_url:
            return False
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            query = text("""
                SELECT market, 
                       COUNT(*) as picks,
                       COUNT(CASE WHEN outcome = 'won' THEN 1 END) as wins,
                       COUNT(CASE WHEN outcome = 'lost' THEN 1 END) as losses,
                       COALESCE(SUM(CASE 
                           WHEN outcome = 'won' THEN (odds - 1)
                           WHEN outcome = 'lost' THEN -1
                           ELSE 0
                       END), 0) as units
                FROM football_opportunities 
                WHERE market IN ('Corners', 'Cards', 'Shots')
                  AND mode = 'PROD'
                  AND DATE(match_date) = CURRENT_DATE
                GROUP BY market
            """)
            
            results = conn.execute(query).fetchall()
            
            if not results:
                logger.info("No props picks today")
                return True
            
            fields = []
            total_picks = 0
            total_wins = 0
            total_losses = 0
            total_units = 0
            
            for row in results:
                market, picks, wins, losses, units = row
                total_picks += picks
                total_wins += wins
                total_losses += losses
                total_units += float(units)
                
                emoji = "🔷" if market == 'Corners' else "🟨" if market == 'Cards' else "🎯"
                pending = picks - wins - losses
                
                fields.append({
                    "name": f"{emoji} {market}",
                    "value": f"`{wins}W-{losses}L` ({pending} pending)\n`{float(units):+.2f}u`",
                    "inline": True
                })
            
            pending_total = total_picks - total_wins - total_losses
            roi = (total_units / total_picks * 100) if total_picks > 0 else 0
            
            color = 0x2ecc71 if total_units > 0 else 0xe74c3c if total_units < 0 else 0x95a5a6
            
            embed = {
                "title": "📊 Today's Props Summary",
                "color": color,
                "fields": fields + [
                    {"name": "📈 Total", "value": f"`{total_wins}W-{total_losses}L` ({pending_total} pending)", "inline": True},
                    {"name": "💰 Units", "value": f"`{total_units:+.2f}u`", "inline": True},
                    {"name": "📊 ROI", "value": f"`{roi:+.1f}%`", "inline": True}
                ],
                "footer": {"text": f"Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"}
            }
            
            payload = {
                "username": "PGR Props Bot",
                "embeds": [embed]
            }
            
            response = requests.post(DISCORD_PROPS_WEBHOOK_URL, json=payload, timeout=10)
            
            return response.status_code in [200, 204]
        
    except Exception as e:
        logger.error(f"Error sending props summary: {e}")
        return False


if __name__ == "__main__":
    print("🔍 Testing Discord Props webhook...")
    result = send_new_props_picks()
    print(f"📊 Result: {result}")

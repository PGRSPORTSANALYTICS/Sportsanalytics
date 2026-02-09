"""
Bet Distribution Controller - Central control for all Discord bet distribution.
Ensures ONLY valid, non-duplicate, same-day bets are sent.
Includes League Routing for grouped, league-specific distribution.
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
from collections import defaultdict

from discord_notifier import build_analysis_reason, format_kickoff, format_bookmaker_odds, format_odds_comparison

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCORD_FREE_PICKS_WEBHOOK_URL = os.getenv("DISCORD_FREE_PICKS_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
WEBHOOK_VALUE_SINGLES = os.getenv("WEBHOOK_Value_singles")
WEBHOOK_RESULTS = os.getenv("DISCORD_RESULTS_WEBHOOK")

LEAGUE_NORMALIZATION = {
    'premier league': 'Premier League',
    'english premier league': 'Premier League',
    'epl': 'Premier League',
    'serie a': 'Serie A',
    'italian serie a': 'Serie A',
    'la liga': 'La Liga',
    'spanish la liga': 'La Liga',
    'bundesliga': 'Bundesliga',
    'german bundesliga': 'Bundesliga',
    'ligue 1': 'Ligue 1',
    'french ligue 1': 'Ligue 1',
    'championship': 'Championship',
    'english championship': 'Championship',
    'eredivisie': 'Eredivisie',
    'dutch eredivisie': 'Eredivisie',
    'primeira liga': 'Primeira Liga',
    'portuguese primeira liga': 'Primeira Liga',
    'mls': 'MLS',
    'major league soccer': 'MLS',
    'champions league': 'Champions League',
    'uefa champions league': 'Champions League',
    'europa league': 'Europa League',
    'uefa europa league': 'Europa League',
    'scottish premiership': 'Scottish Premiership',
    'belgian pro league': 'Belgian Pro League',
    'english league one': 'League One',
    'league one': 'League One',
    'english league two': 'League Two',
    'league two': 'League Two',
    'fa cup': 'FA Cup',
    'copa del rey': 'Copa del Rey',
    'coppa italia': 'Coppa Italia',
    'dfb pokal': 'DFB Pokal',
}

LEAGUE_CHANNEL_MAP = {
    'Premier League': {'channel': 'premier-league', 'env_var': 'DISCORD_PREMIER_LEAGUE_WEBHOOK'},
    'Serie A': {'channel': 'serie-a', 'env_var': 'DISCORD_SERIE_A_WEBHOOK'},
    'La Liga': {'channel': 'la-liga', 'env_var': 'DISCORD_LA_LIGA_WEBHOOK'},
    'Bundesliga': {'channel': 'bundesliga', 'env_var': 'DISCORD_BUNDESLIGA_WEBHOOK'},
    'Ligue 1': {'channel': 'ligue-1', 'env_var': 'DISCORD_LIGUE_1_WEBHOOK'},
    'Championship': {'channel': 'championship', 'env_var': 'DISCORD_CHAMPIONSHIP_WEBHOOK'},
    'Eredivisie': {'channel': 'eredivisie', 'env_var': 'DISCORD_EREDIVISIE_WEBHOOK'},
    'Champions League': {'channel': 'champions-league', 'env_var': 'DISCORD_CHAMPIONS_LEAGUE_WEBHOOK'},
    'Europa League': {'channel': 'europa-league', 'env_var': 'DISCORD_EUROPA_LEAGUE_WEBHOOK'},
}

FALLBACK_CHANNEL = {'channel': 'other-leagues', 'env_var': 'DISCORD_FREE_PICKS_WEBHOOK_URL'}


def normalize_league(league_name: str) -> Optional[str]:
    """Normalize league name to standard format."""
    if not league_name:
        return None
    
    lower = league_name.lower().strip()
    
    if lower in LEAGUE_NORMALIZATION:
        return LEAGUE_NORMALIZATION[lower]
    
    for key, value in LEAGUE_NORMALIZATION.items():
        if key in lower or lower in key:
            return value
    
    return league_name.title()


def get_league_webhook(league: str) -> Tuple[Optional[str], str]:
    """Get webhook URL and channel name for a league."""
    normalized = normalize_league(league)
    
    if normalized in LEAGUE_CHANNEL_MAP:
        config = LEAGUE_CHANNEL_MAP[normalized]
        webhook = os.getenv(config['env_var'])
        if webhook:
            return webhook, config['channel']
    
    fallback_webhook = os.getenv(FALLBACK_CHANNEL['env_var'])
    return fallback_webhook, FALLBACK_CHANNEL['channel']


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


LEAGUE_TO_SPORT_KEY = {
    'Premier League': 'soccer_epl',
    'Championship': 'soccer_efl_champ',
    'La Liga': 'soccer_spain_la_liga',
    'Serie A': 'soccer_italy_serie_a',
    'Bundesliga': 'soccer_germany_bundesliga',
    'Ligue 1': 'soccer_france_ligue_one',
    'Eredivisie': 'soccer_netherlands_eredivisie',
    'Primeira Liga': 'soccer_portugal_primeira_liga',
    'Scottish Premiership': 'soccer_scotland_premiership',
    'Belgian Pro League': 'soccer_belgium_first_div',
    'League One': 'soccer_england_league1',
    'League Two': 'soccer_england_league2',
    'Champions League': 'soccer_uefa_champs_league',
    'Europa League': 'soccer_uefa_europa_league',
    'Copa del Rey': 'soccer_spain_la_liga',
    'Coppa Italia': 'soccer_italy_serie_a',
    'FA Cup': 'soccer_epl',
}


def refresh_odds_for_picks(picks: list) -> list:
    """Refresh bookmaker odds for picks just before distribution.
    Uses The Odds API to get current odds and adds live comparison.
    Returns picks with updated odds_comparison field."""
    from discord_notifier import fetch_live_odds_for_match, format_odds_comparison
    
    api_key = os.getenv('THE_ODDS_API_KEY')
    if not api_key:
        logger.info("⏭️ No THE_ODDS_API_KEY — skipping live odds refresh")
        return picks
    
    leagues_needed = set()
    for p in picks:
        league = normalize_league(p.get('league', '')) or 'Other'
        sport_key = LEAGUE_TO_SPORT_KEY.get(league)
        if sport_key:
            leagues_needed.add(sport_key)
    
    if len(leagues_needed) > 3:
        logger.info(f"⏭️ Too many leagues ({len(leagues_needed)}) — skipping live refresh to save API quota")
        return picks
    
    for pick in picks:
        try:
            league = normalize_league(pick.get('league', '')) or 'Other'
            sport_key = LEAGUE_TO_SPORT_KEY.get(league)
            if not sport_key:
                continue
            
            selection = pick.get('selection', '')
            home_team = pick.get('home_team', '')
            away_team = pick.get('away_team', '')
            model_odds = float(pick.get('odds', 0))
            
            live_data = fetch_live_odds_for_match(home_team, away_team, selection, sport_key)
            
            if live_data:
                pick['live_odds_data'] = live_data
                pick['odds_comparison'] = format_odds_comparison(model_odds, live_data)
                
                if live_data.get('odds_by_bookmaker'):
                    pick['odds_by_bookmaker'] = live_data['odds_by_bookmaker']
                    pick['best_odds_value'] = live_data.get('best_odds_value')
                    pick['best_odds_bookmaker'] = live_data.get('best_odds_bookmaker')
                    pick['avg_odds'] = live_data.get('avg_odds')
                    logger.info(f"🔄 Fresh odds: {home_team} vs {away_team} | Best: {live_data.get('best_odds_value', '?')} @ {live_data.get('best_odds_bookmaker', '?')}")
        except Exception as e:
            logger.debug(f"Live odds refresh failed for {pick.get('home_team', '?')}: {e}")
    
    return picks


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
    webhook_url: str,
    analysis=None,
    edge_percentage=None,
    model_prob=None
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
    
    product_label = market.upper() if market else "VALUE SINGLES"
    if 'CORNER' in product_label.upper():
        product_emoji = "🔷"
        product_label = "CORNERS"
    elif 'CARD' in product_label.upper():
        product_emoji = "🟨"
        product_label = "CARDS"
    elif 'BASKET' in product_label.upper():
        product_emoji = "🏀"
        product_label = "BASKETBALL"
    else:
        product_emoji = "🎯"
        product_label = "VALUE SINGLES"
    
    reason = build_analysis_reason({
        'analysis': analysis, 'odds': odds,
        'edge_percentage': edge_percentage, 'model_prob': model_prob
    })
    
    ko = format_kickoff({'match_date': event_date})
    ko_str = f" | {ko}" if ko else ""
    
    content = f"{product_emoji} **{product_label} — Today's Picks**\n\n"
    content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += f"**{league}**\n"
    content += f"• {home_team} vs {away_team} — **{selection}** @ {odds:.2f}{ko_str} (TBD) 🔘\n"
    if reason:
        content += f"{reason}\n"
    content += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += f"*1 pick(s) | Flat {units:.0f}u | PGR Analytics*"
    
    try:
        embed = {
            "description": content[:4000],
            "color": 3066993,
            "footer": {"text": f"PGR Sports Analytics — {product_label}"}
        }
        
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
                confidence, trust_level, market, analysis
            FROM football_opportunities
            WHERE DATE(match_date::timestamp) = CURRENT_DATE
              AND market = 'Value Single'
              AND odds BETWEEN 1.70 AND 2.20
              AND confidence >= 60
              AND outcome IS NULL
              AND selection IN ('Over 2.5 Goals', 'Under 2.5 Goals', 'Over 1.5 Goals', 'Under 3.5 Goals', 'BTTS Yes', 'BTTS No')
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
                webhook_url=DISCORD_FREE_PICKS_WEBHOOK_URL,
                analysis=pick.get('analysis'),
                edge_percentage=pick.get('edge_percentage'),
                model_prob=pick.get('model_prob')
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


def format_league_message(league: str, bets: List[Dict]) -> str:
    """Format a grouped message for a single league."""
    bets_sorted = sorted(bets, key=lambda x: x.get('match_date') or datetime.max)
    
    content = "🎯 **VALUE SINGLES — Today's Picks**\n\n"
    content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += f"**{league}**\n"
    
    for bet in bets_sorted:
        ko = format_kickoff(bet)
        ko_str = f" | {ko}" if ko else ""
        content += f"• {bet['home_team']} vs {bet['away_team']} — **{bet['selection']}** @ {float(bet.get('odds', 0)):.2f}{ko_str} (TBD) 🔘\n"
        reason = build_analysis_reason(bet)
        if reason:
            content += f"{reason}\n"
    
    content += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += f"*{len(bets)} pick(s) | Flat 1u | PGR Analytics*"
    
    return content


def send_league_grouped_message(league: str, bets: List[Dict], webhook_url: str, channel: str) -> Tuple[bool, List[int]]:
    """Send a grouped league message and return success + list of sent bet IDs."""
    if not webhook_url:
        logger.warning(f"⚠️ No webhook for {league}, skipping")
        return False, []
    
    content = format_league_message(league, bets)
    
    try:
        embed = {
            "description": content[:4000],
            "color": 3066993,
            "footer": {"text": f"PGR Sports Analytics — {league}"}
        }
        
        payload = {"embeds": [embed]}
        response = requests.post(webhook_url, json=payload, timeout=10)
        
        if response.status_code in [200, 204]:
            sent_ids = []
            for bet in bets:
                event_id = f"{bet['home_team']}_{bet['away_team']}"
                event_date_str = str(bet.get('match_date', ''))[:10]
                bet_id = generate_bet_id(
                    'football', league, event_id, 
                    bet.get('market', 'Value Single'),
                    bet['selection'], bet['selection'], event_date_str
                )
                
                log_sent_bet(
                    bet_id=bet_id,
                    opportunity_id=bet['id'],
                    sport='football',
                    league=league,
                    home_team=bet['home_team'],
                    away_team=bet['away_team'],
                    market=bet.get('market', 'Value Single'),
                    selection=bet['selection'],
                    line=bet['selection'],
                    odds=float(bet.get('odds', 0)),
                    units=1.0,
                    event_date=bet.get('match_date'),
                    discord_channel=channel
                )
                sent_ids.append(bet['id'])
            
            logger.info(f"✅ SENT {league}: {len(bets)} picks → #{channel}")
            return True, sent_ids
        else:
            logger.error(f"Discord error for {league}: {response.status_code}")
            return False, []
    except Exception as e:
        logger.error(f"Send error for {league}: {e}")
        return False, []


def distribute_by_league(max_per_league: int = 3) -> Dict[str, int]:
    """Distribute today's picks grouped by league."""
    ensure_distribution_log_table()
    
    logger.info(f"\n{'='*60}")
    logger.info(f"LEAGUE ROUTING DISTRIBUTION - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    logger.info(f"{'='*60}")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                id, home_team, away_team, league, match_date,
                selection, odds, model_prob, edge_percentage,
                confidence, trust_level, market, analysis
            FROM football_opportunities
            WHERE DATE(match_date::timestamp) = CURRENT_DATE
              AND market = 'Value Single'
              AND odds BETWEEN 1.50 AND 2.50
              AND confidence >= 55
              AND outcome IS NULL
              AND selection IN ('Over 2.5 Goals', 'Under 2.5 Goals',
                               'Over 1.5 Goals', 'Under 3.5 Goals',
                               'BTTS Yes', 'BTTS No')
            ORDER BY match_date ASC
        """)
        
        all_picks = cur.fetchall()
        cur.close()
        conn.close()
        
        if not all_picks:
            logger.info("❌ No valid same-day picks found")
            return {}
        
        league_groups = defaultdict(list)
        for pick in all_picks:
            league = normalize_league(pick['league']) or 'Other'
            
            event_id = f"{pick['home_team']}_{pick['away_team']}"
            event_date_str = str(pick.get('match_date', ''))[:10]
            bet_id = generate_bet_id(
                'football', league, event_id,
                pick.get('market', 'Value Single'),
                pick['selection'], pick['selection'], event_date_str
            )
            
            if is_duplicate_bet(bet_id):
                continue
            
            league_groups[league].append(dict(pick))
        
        league_order = sorted(
            league_groups.keys(),
            key=lambda lg: min(
                (p.get('match_date') or datetime.max for p in league_groups[lg]),
                default=datetime.max
            )
        )
        
        results = {}
        for league in league_order:
            bets = league_groups[league][:max_per_league]
            
            if not bets:
                continue
            
            webhook, channel = get_league_webhook(league)
            
            success, sent_ids = send_league_grouped_message(league, bets, webhook, channel)
            
            if success:
                results[league] = len(sent_ids)
        
        logger.info(f"\n📊 League Distribution Summary:")
        for league, count in results.items():
            logger.info(f"   • {league}: {count} picks")
        logger.info(f"   Total: {sum(results.values())} picks across {len(results)} leagues")
        
        return results
        
    except Exception as e:
        logger.error(f"League distribution error: {e}")
        return {}


def send_results_to_discord(results: List[Dict]) -> int:
    """Send settled bet results to Discord."""
    if not results:
        return 0
    
    webhook = WEBHOOK_RESULTS or DISCORD_WEBHOOK_URL
    if not webhook:
        logger.warning("⚠️ No results webhook configured")
        return 0
    
    wins = [r for r in results if str(r.get('outcome', '')).upper() == 'WON']
    losses = [r for r in results if str(r.get('outcome', '')).upper() == 'LOST']
    pushes = [r for r in results if str(r.get('outcome', '')).upper() == 'PUSH']
    
    total_units = sum(r.get('units', 1.0) for r in results)
    profit = sum(
        (float(r.get('odds', 1.0)) - 1) * float(r.get('units', 1.0)) if str(r.get('outcome', '')).upper() == 'WON'
        else -float(r.get('units', 1.0)) if str(r.get('outcome', '')).upper() == 'LOST'
        else 0
        for r in results
    )
    
    content = "**📊 RESULTS UPDATE**\n"
    content += "━" * 30 + "\n\n"
    
    for r in results:
        outcome = str(r.get('outcome', 'PENDING')).upper()
        emoji = "✅" if outcome == 'WON' else "❌" if outcome == 'LOST' else "🔄"
        
        content += f"{emoji} **{r.get('home_team', '')} vs {r.get('away_team', '')}**\n"
        market = r.get('market', '')
        selection = r.get('selection', '')
        if market and market.lower() not in selection.lower():
            selection = f"{selection} {market}"
        content += f"• {selection} @ {float(r.get('odds', 0)):.2f}\n"
        if r.get('final_score'):
            content += f"• Score: {r['final_score']}\n"
        content += "\n"
    
    content += "━" * 30 + "\n"
    content += f"**Summary:** {len(wins)}W - {len(losses)}L - {len(pushes)}P\n"
    content += f"**P/L:** {profit:+.2f} units\n"
    
    try:
        embed = {
            "description": content[:4000],
            "color": 3066993 if profit >= 0 else 15158332,
            "footer": {"text": f"PGR Sports Analytics — Results"}
        }
        
        payload = {"embeds": [embed]}
        response = requests.post(webhook, json=payload, timeout=10)
        
        if response.status_code in [200, 204]:
            logger.info(f"✅ Results sent: {len(wins)}W-{len(losses)}L-{len(pushes)}P ({profit:+.2f}u)")
            return len(results)
        else:
            logger.error(f"Discord error: {response.status_code}")
            return 0
    except Exception as e:
        logger.error(f"Results send error: {e}")
        return 0


def get_todays_settled_bets() -> List[Dict]:
    """Get today's settled bets for results notification."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                fo.id, fo.home_team, fo.away_team, fo.league,
                fo.selection, fo.odds, fo.outcome,
                fo.actual_score as final_score,
                COALESCE(bdl.units, 1.0) as units
            FROM football_opportunities fo
            LEFT JOIN bet_distribution_log bdl ON bdl.opportunity_id = fo.id
            WHERE DATE(fo.match_date::timestamp) = CURRENT_DATE
              AND fo.outcome IS NOT NULL
              AND fo.outcome != 'PENDING'
              AND fo.outcome != ''
            ORDER BY fo.match_date ASC
        """)
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return [dict(r) for r in results]
    except Exception as e:
        logger.error(f"Get settled bets error: {e}")
        return []


def distribute_value_singles(max_picks: int = 5) -> int:
    """Distribute value singles to dedicated channel."""
    ensure_distribution_log_table()
    
    webhook = WEBHOOK_VALUE_SINGLES or DISCORD_FREE_PICKS_WEBHOOK_URL
    if not webhook:
        logger.error("❌ No value singles webhook configured")
        return 0
    
    logger.info(f"\n{'='*50}")
    logger.info(f"VALUE SINGLES DISTRIBUTION - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    logger.info(f"{'='*50}")
    
    already_sent = get_todays_sent_count('value_singles')
    if already_sent >= max_picks:
        logger.info(f"⏸️ Daily limit reached: {already_sent}/{max_picks}")
        return 0
    
    remaining = max_picks - already_sent
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                id, home_team, away_team, league, match_date,
                selection, odds, model_prob, edge_percentage,
                confidence, trust_level, market, analysis,
                odds_by_bookmaker, best_odds_value, best_odds_bookmaker, avg_odds
            FROM football_opportunities
            WHERE DATE(match_date::timestamp) = CURRENT_DATE
              AND market = 'Value Single'
              AND odds BETWEEN 1.50 AND 2.50
              AND confidence >= 55
              AND outcome IS NULL
            ORDER BY 
                CASE WHEN trust_level IN ('L1', 'L1_HIGH_TRUST') THEN 1 
                     WHEN trust_level = 'L2' THEN 2 
                     ELSE 3 END,
                edge_percentage DESC NULLS LAST,
                match_date ASC
            LIMIT %s
        """, (remaining + 10,))
        
        candidates = cur.fetchall()
        cur.close()
        conn.close()
        
        if not candidates:
            logger.info("❌ No valid value singles found")
            return 0
        
        valid_picks = []
        for pick in candidates:
            if len(valid_picks) >= remaining:
                break
            
            event_id = f"{pick['home_team']}_{pick['away_team']}"
            event_date_str = str(pick.get('match_date', ''))[:10]
            bet_id = generate_bet_id(
                'football', pick['league'] or 'Unknown', event_id,
                'Value Single', pick['selection'], pick['selection'], event_date_str
            )
            
            if not is_duplicate_bet(bet_id):
                valid_picks.append(dict(pick))
        
        if not valid_picks:
            logger.info("❌ All candidates already sent")
            return 0
        
        valid_picks = refresh_odds_for_picks(valid_picks)
        
        league_groups = defaultdict(list)
        for pick in valid_picks:
            league = normalize_league(pick['league']) or 'Other'
            league_groups[league].append(pick)
        
        content = "🎯 **VALUE SINGLES — Today's Picks**\n\n"
        content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for league in sorted(league_groups.keys()):
            bets = sorted(league_groups[league], key=lambda x: x.get('match_date') or datetime.max)
            content += f"**{league}**\n"
            
            for bet in bets:
                content += f"• {bet['home_team']} vs {bet['away_team']} — **{bet['selection']}** @ {float(bet['odds']):.2f} (TBD) 🔘\n"
                reason = build_analysis_reason(bet)
                if reason:
                    content += f"{reason}\n"
                bookmaker_line = format_bookmaker_odds(bet)
                if bookmaker_line:
                    content += f"{bookmaker_line}\n"
                odds_comp = bet.get('odds_comparison', '')
                if odds_comp:
                    content += f"{odds_comp}\n"
            
            content += "\n"
        
        content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        content += f"*{len(valid_picks)} pick(s) | Flat 1u | PGR Analytics*"
        
        try:
            embed = {
                "description": content[:4000],
                "color": 3066993,
                "footer": {"text": f"PGR Sports Analytics — Value Singles"}
            }
            
            payload = {"embeds": [embed]}
            response = requests.post(webhook, json=payload, timeout=10)
            
            if response.status_code in [200, 204]:
                for pick in valid_picks:
                    event_id = f"{pick['home_team']}_{pick['away_team']}"
                    event_date_str = str(pick.get('match_date', ''))[:10]
                    bet_id = generate_bet_id(
                        'football', pick['league'] or 'Unknown', event_id,
                        'Value Single', pick['selection'], pick['selection'], event_date_str
                    )
                    
                    log_sent_bet(
                        bet_id=bet_id,
                        opportunity_id=pick['id'],
                        sport='football',
                        league=normalize_league(pick['league']) or 'Other',
                        home_team=pick['home_team'],
                        away_team=pick['away_team'],
                        market='Value Single',
                        selection=pick['selection'],
                        line=pick['selection'],
                        odds=float(pick['odds']),
                        units=1.0,
                        event_date=pick['match_date'],
                        discord_channel='value_singles'
                    )
                
                logger.info(f"✅ Sent {len(valid_picks)} value singles to Discord")
                return len(valid_picks)
            else:
                logger.error(f"Discord error: {response.status_code}")
                return 0
        except Exception as e:
            logger.error(f"Send error: {e}")
            return 0
        
    except Exception as e:
        logger.error(f"Distribution error: {e}")
        return 0


def send_daily_results() -> int:
    """Send daily results summary to Discord."""
    settled = get_todays_settled_bets()
    if settled:
        return send_results_to_discord(settled)
    logger.info("📊 No settled bets to report today")
    return 0


def send_instant_pick(pick: Dict) -> bool:
    """Send a single pick to Discord immediately when created."""
    ensure_distribution_log_table()
    
    webhook = WEBHOOK_VALUE_SINGLES or DISCORD_FREE_PICKS_WEBHOOK_URL
    if not webhook:
        logger.warning("⚠️ No value singles webhook for instant send")
        return False
    
    home_team = pick.get('home_team', '')
    away_team = pick.get('away_team', '')
    league = normalize_league(pick.get('league')) or 'Other'
    selection = pick.get('selection', '')
    odds = float(pick.get('odds', 0))
    confidence = float(pick.get('confidence', 0))
    trust_level = pick.get('trust_level', 'L3')
    match_date = pick.get('match_date')
    opportunity_id = pick.get('id')
    
    event_id = f"{home_team}_{away_team}"
    event_date_str = str(match_date)[:10] if match_date else date.today().isoformat()
    bet_id = generate_bet_id('football', league, event_id, 'Value Single', selection, selection, event_date_str)
    
    if is_duplicate_bet(bet_id):
        logger.debug(f"⏭️ Already sent: {home_team} vs {away_team}")
        return False
    
    if not is_same_day_event(match_date):
        logger.debug(f"⏭️ Not today's event: {home_team} vs {away_team}")
        return False
    
    bookmaker_line = format_bookmaker_odds(pick)
    
    content = "🎯 **VALUE SINGLES — Today's Picks**\n\n"
    content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += f"**{league}**\n"
    content += f"• {home_team} vs {away_team} — **{selection}** @ {odds:.2f} (TBD) 🔘\n"
    if bookmaker_line:
        content += f"{bookmaker_line}\n"
    content += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += "*1 pick(s) | Flat 1u | PGR Analytics*"
    
    try:
        embed = {
            "description": content[:4000],
            "color": 3066993,
            "footer": {"text": "PGR Sports Analytics — Value Singles"}
        }
        
        payload = {"embeds": [embed]}
        response = requests.post(webhook, json=payload, timeout=10)
        
        if response.status_code in [200, 204]:
            log_sent_bet(
                bet_id=bet_id,
                opportunity_id=opportunity_id,
                sport='football',
                league=league,
                home_team=home_team,
                away_team=away_team,
                market='Value Single',
                selection=selection,
                line=selection,
                odds=odds,
                units=1.0,
                event_date=match_date,
                discord_channel='value_singles'
            )
            logger.info(f"⚡ INSTANT: {home_team} vs {away_team} | {selection} @ {odds:.2f}")
            return True
        else:
            logger.error(f"Discord error: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Instant send error: {e}")
        return False


if __name__ == "__main__":
    ensure_distribution_log_table()
    
    print("Testing value singles distribution...")
    sent = distribute_value_singles(5)
    print(f"\nSent {sent} value singles")
    
    print("\nChecking for results to send...")
    results_sent = send_daily_results()
    print(f"Sent {results_sent} results")
    
    stats = get_distribution_stats()
    print(f"\nDistribution Stats: {json.dumps(stats, default=str, indent=2)}")

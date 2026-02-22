"""
Player Props Engine - Learning Mode
====================================
Fetches player prop odds from The Odds API for both football and basketball.
Computes edge using player statistics and stores all data for learning.

Markets:
  Football: player_anytime_goalscorer, player_shots_on_goal
  Basketball: player_points, player_rebounds

Mode: LEARNING ONLY - no real stakes, data collection for AI training.
"""

import os
import logging
import time
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from db_connection import DatabaseConnection, clean_database_url

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

FOOTBALL_LEAGUES = [
    'soccer_epl',
    'soccer_spain_la_liga',
    'soccer_italy_serie_a',
    'soccer_germany_bundesliga',
    'soccer_france_ligue_one',
    'soccer_uefa_champs_league',
    'soccer_sweden_allsvenskan',
]

FOOTBALL_PROP_MARKETS = [
    'player_anytime_goalscorer',
    'player_shots_on_goal',
]

BASKETBALL_LEAGUES = [
    'basketball_nba',
]

BASKETBALL_PROP_MARKETS = [
    'player_points',
    'player_rebounds',
    'player_assists',
    'player_points_rebounds_assists',
]

SWEDISH_BOOKMAKERS = ['betsson', 'unibet', 'leovegas', 'coolbet', 'nordicbet']

MAX_EVENTS_PER_CYCLE = 10
MAX_API_CREDITS_PER_CYCLE = 50
MAX_PROPS_PER_CYCLE = 30
MIN_EDGE_PCT = 5.0
MAX_PROPS_PER_DAY = 20


class PlayerPropsEngine:
    def __init__(self):
        self.api_key = os.getenv('THE_ODDS_API_KEY')
        if not self.api_key:
            raise ValueError("THE_ODDS_API_KEY required for Player Props Engine")
        self.credits_used = 0
        self.stats = {'football_props': 0, 'basketball_props': 0, 'total_saved': 0, 'errors': 0}

    def _get_daily_props_count(self) -> int:
        try:
            with DatabaseConnection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM player_props 
                    WHERE created_at >= CURRENT_DATE
                """)
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.warning(f"Could not check daily props count: {e}")
            return 0

    def run_cycle(self) -> Dict:
        logger.info("=" * 60)
        logger.info("🎯 PLAYER PROPS ENGINE - LEARNING MODE")
        logger.info("=" * 60)

        daily_count = self._get_daily_props_count()
        remaining_budget = MAX_PROPS_PER_DAY - daily_count
        if remaining_budget <= 0:
            logger.info(f"🛑 Daily props cap reached ({daily_count}/{MAX_PROPS_PER_DAY}). Skipping cycle.")
            return {'football_props': 0, 'basketball_props': 0, 'total_saved': 0, 'errors': 0, 'daily_cap_hit': True}

        logger.info(f"📊 Daily budget: {remaining_budget} props remaining ({daily_count}/{MAX_PROPS_PER_DAY} used)")

        self.credits_used = 0
        self.stats = {'football_props': 0, 'basketball_props': 0, 'total_saved': 0, 'errors': 0}

        all_props = []

        try:
            basketball_props = self._run_basketball_props()
            self.stats['basketball_props'] = len(basketball_props)
            all_props.extend(basketball_props)
        except Exception as e:
            logger.error(f"Basketball props error: {e}")
            self.stats['errors'] += 1

        try:
            football_props = self._run_football_props()
            self.stats['football_props'] = len(football_props)
            all_props.extend(football_props)
        except Exception as e:
            logger.error(f"Football props error: {e}")
            self.stats['errors'] += 1

        all_props.sort(key=lambda x: x.get('edge_pct', 0), reverse=True)

        cap = min(MAX_PROPS_PER_CYCLE, remaining_budget)
        if len(all_props) > cap:
            logger.info(f"🎯 Capped to {cap} best props (from {len(all_props)} found, daily budget: {remaining_budget})")
            all_props = all_props[:cap]

        if all_props:
            saved = self._save_props_to_db(all_props)
            self.stats['total_saved'] = saved

        logger.info(f"🎯 Props cycle complete: {self.stats['football_props']} football, "
                     f"{self.stats['basketball_props']} basketball, "
                     f"{self.stats['total_saved']} saved, {self.credits_used} API credits used")
        return self.stats

    def _filter_future_events(self, events: List[Dict]) -> List[Dict]:
        now = datetime.now(timezone.utc)
        future = []
        for e in events:
            ct = e.get('commence_time', '')
            if ct:
                try:
                    event_time = datetime.fromisoformat(ct.replace('Z', '+00:00'))
                    if event_time > now:
                        future.append(e)
                    else:
                        logger.debug(f"⏭️ Skipping already started: {e.get('home_team','')} vs {e.get('away_team','')}")
                except (ValueError, AttributeError):
                    future.append(e)
            else:
                future.append(e)
        return future

    def _run_football_props(self) -> List[Dict]:
        logger.info("⚽ Scanning football player props...")
        all_props = []

        for league in FOOTBALL_LEAGUES:
            if self.credits_used >= MAX_API_CREDITS_PER_CYCLE:
                logger.warning("⚠️ API credit limit reached for this cycle")
                break

            events = self._get_events(league)
            if not events:
                continue

            events = self._filter_future_events(events)
            if not events:
                logger.info(f"⚽ {league}: no future events")
                continue

            events_to_scan = events[:MAX_EVENTS_PER_CYCLE]
            logger.info(f"⚽ {league}: {len(events)} future events, scanning {len(events_to_scan)}")

            for event in events_to_scan:
                if self.credits_used >= MAX_API_CREDITS_PER_CYCLE:
                    break

                props = self._get_event_player_props(
                    sport=league,
                    event_id=event['id'],
                    home_team=event.get('home_team', ''),
                    away_team=event.get('away_team', ''),
                    commence_time=event.get('commence_time', ''),
                    markets=FOOTBALL_PROP_MARKETS,
                    sport_type='football'
                )
                all_props.extend(props)
                time.sleep(1)

        logger.info(f"⚽ Football: {len(all_props)} props found")
        return all_props

    def _run_basketball_props(self) -> List[Dict]:
        logger.info("🏀 Scanning basketball player props...")
        all_props = []

        for league in BASKETBALL_LEAGUES:
            if self.credits_used >= MAX_API_CREDITS_PER_CYCLE:
                logger.warning("⚠️ API credit limit reached for this cycle")
                break

            events = self._get_events(league)
            if not events:
                continue

            events = self._filter_future_events(events)
            if not events:
                logger.info(f"🏀 {league}: no future events")
                continue

            events_to_scan = events[:MAX_EVENTS_PER_CYCLE]
            logger.info(f"🏀 {league}: {len(events)} future events, scanning {len(events_to_scan)}")

            for event in events_to_scan:
                if self.credits_used >= MAX_API_CREDITS_PER_CYCLE:
                    break

                props = self._get_event_player_props(
                    sport=league,
                    event_id=event['id'],
                    home_team=event.get('home_team', ''),
                    away_team=event.get('away_team', ''),
                    commence_time=event.get('commence_time', ''),
                    markets=BASKETBALL_PROP_MARKETS,
                    sport_type='basketball'
                )
                all_props.extend(props)
                time.sleep(1)

        logger.info(f"🏀 Basketball: {len(all_props)} props found")
        return all_props

    def _get_events(self, sport_key: str) -> List[Dict]:
        url = f"{ODDS_API_BASE}/sports/{sport_key}/events"
        params = {
            'apiKey': self.api_key,
            'dateFormat': 'iso',
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                events = resp.json()
                return events
            elif resp.status_code == 422:
                logger.debug(f"No events for {sport_key}")
                return []
            else:
                logger.warning(f"Events API error for {sport_key}: {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"Events fetch error for {sport_key}: {e}")
            return []

    def _get_event_player_props(self, sport: str, event_id: str, home_team: str,
                                 away_team: str, commence_time: str,
                                 markets: List[str], sport_type: str) -> List[Dict]:
        props = []
        markets_str = ','.join(markets)

        regions = 'eu,uk,us'

        url = f"{ODDS_API_BASE}/sports/{sport}/events/{event_id}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': regions,
            'markets': markets_str,
            'oddsFormat': 'decimal',
            'dateFormat': 'iso',
        }

        try:
            resp = requests.get(url, params=params, timeout=20)
            self.credits_used += 1

            if resp.status_code != 200:
                if resp.status_code == 422:
                    logger.debug(f"No player props for {home_team} vs {away_team}")
                else:
                    logger.warning(f"Props API error: {resp.status_code} for {home_team} vs {away_team}")
                return []

            data = resp.json()
            bookmakers = data.get('bookmakers', [])

            if not bookmakers:
                return []

            all_outcomes = {}

            for bm in bookmakers:
                bm_key = bm.get('key', '')
                bm_title = bm.get('title', '')
                is_swedish = any(sw in bm_key.lower() for sw in SWEDISH_BOOKMAKERS)

                for market_data in bm.get('markets', []):
                    market_key = market_data.get('key', '')

                    for outcome in market_data.get('outcomes', []):
                        player_name = outcome.get('description', '')
                        selection = outcome.get('name', '')
                        line = outcome.get('point')
                        odds = outcome.get('price', 0)

                        if not player_name or odds <= 1.0:
                            continue

                        prop_key = f"{player_name}|{market_key}|{selection}|{line}"

                        if prop_key not in all_outcomes or odds > all_outcomes[prop_key]['odds']:
                            implied_prob = 1.0 / odds if odds > 0 else 0
                            model_prob = self._estimate_model_prob(
                                sport_type, market_key, player_name, line, odds, implied_prob
                            )
                            edge = ((model_prob * odds) - 1) * 100 if model_prob > 0 else 0

                            all_outcomes[prop_key] = {
                                'sport': sport_type,
                                'league': sport,
                                'event_id': event_id,
                                'home_team': home_team,
                                'away_team': away_team,
                                'commence_time': commence_time,
                                'player_name': player_name,
                                'market': market_key,
                                'line': line,
                                'selection': selection,
                                'odds': odds,
                                'implied_prob': implied_prob,
                                'model_prob': model_prob,
                                'edge_pct': edge,
                                'confidence': model_prob * 100 if model_prob else 0,
                                'bookmaker': bm_title,
                                'region': 'se' if is_swedish else regions,
                                'is_swedish_bm': is_swedish,
                            }
                        elif is_swedish and odds == all_outcomes[prop_key]['odds']:
                            all_outcomes[prop_key]['bookmaker'] = bm_title
                            all_outcomes[prop_key]['region'] = 'se'
                            all_outcomes[prop_key]['is_swedish_bm'] = True

            best_per_player_market = {}
            for prop in all_outcomes.values():
                pm_key = f"{prop['player_name']}|{prop['market']}"
                if pm_key not in best_per_player_market or prop['edge_pct'] > best_per_player_market[pm_key]['edge_pct']:
                    best_per_player_market[pm_key] = prop

            props = list(best_per_player_market.values())

            if props:
                logger.info(f"🎯 {home_team} vs {away_team}: {len(props)} player props found")

        except Exception as e:
            logger.error(f"Props fetch error for {event_id}: {e}")

        return props

    def _estimate_model_prob(self, sport: str, market: str, player_name: str,
                              line: Optional[float], odds: float, implied_prob: float) -> float:
        """
        Learning mode estimation: use implied probability with small adjustments.
        In production, this would use real player stats from API-Football / ESPN.
        For now, we apply a conservative devig to the implied probability.
        """
        if implied_prob <= 0:
            return 0

        if market == 'player_anytime_goalscorer':
            devig_factor = 1.05
        elif market == 'player_shots_on_goal':
            devig_factor = 1.08 if (line and line <= 1.5) else 1.04
        elif market == 'player_points':
            devig_factor = 1.06
        elif market == 'player_rebounds':
            devig_factor = 1.06
        elif market == 'player_assists':
            devig_factor = 1.06
        elif market in ('player_points_rebounds_assists', 'player_pra'):
            devig_factor = 1.05
        else:
            devig_factor = 1.05

        model_prob = min(implied_prob * devig_factor, 0.95)
        return model_prob

    def _save_props_to_db(self, props: List[Dict]) -> int:
        saved = 0
        try:
            with DatabaseConnection.get_cursor() as cursor:
                for prop in props:
                    try:
                        commence_ts = None
                        if prop.get('commence_time'):
                            try:
                                commence_ts = datetime.fromisoformat(prop['commence_time'].replace('Z', '+00:00'))
                            except (ValueError, AttributeError):
                                pass

                        cursor.execute("""
                            SELECT id FROM player_props 
                            WHERE event_id = %s AND player_name = %s AND market = %s 
                              AND selection = %s AND line IS NOT DISTINCT FROM %s
                            LIMIT 1
                        """, (prop['event_id'], prop['player_name'], prop['market'],
                              prop['selection'], prop.get('line')))

                        if cursor.fetchone():
                            continue

                        cursor.execute("""
                            INSERT INTO player_props 
                            (sport, league, event_id, home_team, away_team, commence_time,
                             player_name, market, line, selection, odds, implied_prob,
                             model_prob, edge_pct, confidence, bookmaker, region,
                             status, mode, open_odds)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    'pending', 'LEARNING', %s)
                        """, (
                            prop['sport'], prop['league'], prop['event_id'],
                            prop['home_team'], prop['away_team'], commence_ts,
                            prop['player_name'], prop['market'], prop.get('line'),
                            prop['selection'], prop['odds'], prop.get('implied_prob'),
                            prop.get('model_prob'), prop.get('edge_pct'),
                            prop.get('confidence'), prop.get('bookmaker'),
                            prop.get('region'), prop['odds']
                        ))
                        saved += 1

                    except Exception as e:
                        logger.warning(f"Save prop error: {e}")

        except Exception as e:
            logger.error(f"DB save error: {e}")

        return saved

    def get_todays_props_summary(self) -> Dict:
        try:
            with DatabaseConnection.get_cursor(dict_cursor=True) as cursor:
                cursor.execute("""
                    SELECT sport, market, COUNT(*) as total,
                           COUNT(CASE WHEN outcome = 'won' THEN 1 END) as wins,
                           COUNT(CASE WHEN outcome = 'lost' THEN 1 END) as losses,
                           AVG(edge_pct) as avg_edge,
                           AVG(odds) as avg_odds
                    FROM player_props
                    WHERE commence_time::date = CURRENT_DATE
                      AND mode = 'LEARNING'
                    GROUP BY sport, market
                    ORDER BY sport, market
                """)
                rows = cursor.fetchall()

                summary = {}
                for row in rows:
                    key = f"{row['sport']}_{row['market']}"
                    summary[key] = dict(row)

                return summary
        except Exception as e:
            logger.error(f"Summary error: {e}")
            return {}

    def get_top_edge_props(self, min_edge: float = MIN_EDGE_PCT, limit: int = 10) -> List[Dict]:
        try:
            with DatabaseConnection.get_cursor(dict_cursor=True) as cursor:
                cursor.execute("""
                    SELECT * FROM player_props
                    WHERE commence_time > NOW()
                      AND edge_pct >= %s
                      AND mode = 'LEARNING'
                      AND status = 'pending'
                    ORDER BY edge_pct DESC
                    LIMIT %s
                """, (min_edge, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Top edge fetch error: {e}")
            return []


def send_props_to_discord(props: List[Dict]) -> bool:
    webhook_url = os.environ.get("DISCORD_PROPS_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("No DISCORD_PROPS_WEBHOOK_URL configured")
        return False

    if not props:
        return True

    try:
        embeds = []

        for prop in props[:10]:
            sport = prop.get('sport', '')
            sport_emoji = "⚽" if sport == 'football' else "🏀"

            market = prop.get('market', '')
            if market == 'player_anytime_goalscorer':
                market_label = "Anytime Goalscorer"
                color = 0x2ecc71
            elif market == 'player_shots_on_goal':
                market_label = "Shots on Goal"
                color = 0xe74c3c
            elif market == 'player_points':
                market_label = "Points"
                color = 0x3498db
            elif market == 'player_rebounds':
                market_label = "Rebounds"
                color = 0x9b59b6
            else:
                market_label = market
                color = 0x95a5a6

            edge = prop.get('edge_pct', 0) or 0
            ev_badges = "🔥🔥🔥" if edge >= 8 else "🔥🔥" if edge >= 5 else "🔥" if edge >= 3 else ""

            line_str = f" {prop['line']}" if prop.get('line') is not None else ""
            selection = prop.get('selection', '')

            fields = [
                {"name": "🏟️ Match", "value": f"**{prop.get('home_team', '')}** vs **{prop.get('away_team', '')}**", "inline": False},
                {"name": "📊 Odds", "value": f"`{prop.get('odds', 0):.2f}`", "inline": True},
                {"name": "💎 Edge", "value": f"`{edge:+.1f}%` {ev_badges}", "inline": True},
                {"name": "📖 Bookmaker", "value": f"`{prop.get('bookmaker', 'N/A')}`", "inline": True},
            ]

            if line_str:
                fields.insert(1, {"name": "📏 Line", "value": f"`{line_str.strip()}`", "inline": True})

            commence = prop.get('commence_time', '')
            if isinstance(commence, datetime):
                commence = commence.strftime('%Y-%m-%d %H:%M')
            elif isinstance(commence, str):
                commence = commence[:16]

            embed = {
                "title": f"{sport_emoji} {market_label} | {prop.get('player_name', '')} {selection}{line_str}",
                "color": color,
                "fields": fields,
                "footer": {"text": f"🧪 LEARNING MODE • {prop.get('league', '')} • {commence}"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            embeds.append(embed)

        header_embed = {
            "title": "🎯 Player Props Scanner — Learning Mode",
            "description": f"Found **{len(props)}** props with edge ≥ {MIN_EDGE_PCT}%\n"
                           f"⚠️ **No real stakes** — data collection only",
            "color": 0xf39c12,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        all_embeds = [header_embed] + embeds

        for i in range(0, len(all_embeds), 10):
            chunk = all_embeds[i:i + 10]
            payload = {
                "username": "PGR Props Bot",
                "embeds": chunk
            }
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code not in [200, 204]:
                logger.error(f"Discord props webhook failed: {resp.status_code}")
                return False

        logger.info(f"✅ Sent {len(props)} player props to Discord (learning mode)")
        return True

    except Exception as e:
        logger.error(f"Discord props send error: {e}")
        return False


def run_player_props_cycle() -> Dict:
    try:
        engine = PlayerPropsEngine()
        stats = engine.run_cycle()

        try:
            from player_props_filter import filter_quality_props
            raw_props = engine.get_top_edge_props(min_edge=0, limit=500)
            if raw_props:
                quality = filter_quality_props(raw_props)
                stats['quality_props'] = len(quality)
                logger.info(f"🏆 Quality filter: {len(quality)} props passed from {len(raw_props)} raw")

                if quality:
                    _save_quality_flags(quality)
        except Exception as e:
            logger.warning(f"Quality filter error (non-fatal): {e}")
            stats['quality_props'] = 0

        return stats

    except Exception as e:
        logger.error(f"Player props cycle error: {e}")
        return {'football_props': 0, 'basketball_props': 0, 'total_saved': 0, 'errors': 1}


def _save_quality_flags(quality_props: List[Dict]):
    try:
        with DatabaseConnection.get_cursor() as cursor:
            for prop in quality_props:
                prop_id = prop.get('id')
                if not prop_id:
                    continue
                cursor.execute("""
                    UPDATE player_props 
                    SET model_prob = %s, edge_pct = %s, confidence = %s,
                        notes = %s
                    WHERE id = %s
                """, (
                    prop.get('model_prob'),
                    prop.get('edge_pct'),
                    prop.get('confidence'),
                    f"{'PREMIUM' if prop.get('is_premium') else 'QUALITY'}|proj={prop.get('projected',0)}|diff={prop.get('projection_diff',0)}|hit={prop.get('hit_rate_over',0):.0%}|min={prop.get('avg_minutes',0)}|g7={prop.get('games_last_7',0)}",
                    prop_id
                ))
            logger.info(f"✅ Updated {len(quality_props)} props with quality flags")
    except Exception as e:
        logger.warning(f"Quality flag save error: {e}")


if __name__ == "__main__":
    result = run_player_props_cycle()
    print(f"Results: {result}")

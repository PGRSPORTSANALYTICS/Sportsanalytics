"""
Player Props Settlement Engine
================================
Automatically settles player prop bets by fetching actual game stats
from nba_api and comparing against the prop line.

Supports: player_points, player_rebounds, player_assists, player_points_rebounds_assists
Sports: Basketball (NBA + NCAAB via nba_api for NBA only; NCAAB auto-voids after 24h)
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from db_connection import DatabaseConnection

logger = logging.getLogger(__name__)

SETTLE_GRACE_HOURS = 3
NCAAB_VOID_HOURS = 24
NBA_VOID_HOURS = 48

MARKET_STAT_MAP = {
    'player_points': 'PTS',
    'player_rebounds': 'REB',
    'player_assists': 'AST',
    'player_points_rebounds_assists': 'PRA',
}

_boxscore_cache = {}
_cache_ttl = 1800


def run_player_props_settlement() -> Dict:
    stats = {
        'settled': 0,
        'won': 0,
        'lost': 0,
        'push': 0,
        'void': 0,
        'skipped': 0,
        'errors': 0,
    }

    try:
        pending = _get_pending_props()
        if not pending:
            logger.info("No pending player props to settle")
            return stats

        logger.info(f"Found {len(pending)} pending player props to check")

        games_by_date = {}
        for prop in pending:
            ct = prop['commence_time']
            if ct:
                game_date = ct.strftime('%Y-%m-%d') if hasattr(ct, 'strftime') else str(ct)[:10]
                key = f"{prop['player_name']}|{game_date}"
                if key not in games_by_date:
                    games_by_date[key] = []
                games_by_date[key].append(prop)

        player_stats_cache = {}
        settled_count = 0

        for key, props in games_by_date.items():
            player_name = props[0]['player_name']
            league = props[0].get('league', '')
            commence_time = props[0]['commence_time']

            if 'ncaab' in str(league).lower():
                hours_since = _hours_since(commence_time)
                if hours_since > NCAAB_VOID_HOURS:
                    for prop in props:
                        _settle_prop(prop['id'], 'void', None, 'NCAAB - no stats API available')
                        stats['void'] += 1
                        stats['settled'] += 1
                continue

            if not _game_likely_finished(commence_time):
                stats['skipped'] += len(props)
                continue

            actual_stats = _get_player_game_stats(player_name, commence_time)

            if actual_stats is None:
                hours_since = _hours_since(commence_time)
                if hours_since > NBA_VOID_HOURS:
                    for prop in props:
                        _settle_prop(prop['id'], 'void', None, f'No stats found after {NBA_VOID_HOURS}h')
                        stats['void'] += 1
                        stats['settled'] += 1
                else:
                    stats['skipped'] += len(props)
                continue

            if actual_stats.get('dnp'):
                for prop in props:
                    _settle_prop(prop['id'], 'void', None, 'DNP - Did not play')
                    stats['void'] += 1
                    stats['settled'] += 1
                continue

            for prop in props:
                try:
                    result = _evaluate_prop(prop, actual_stats)
                    if result:
                        outcome, actual_val, note = result
                        _settle_prop(prop['id'], outcome, actual_val, note)
                        stats[outcome] += 1
                        stats['settled'] += 1
                        settled_count += 1
                except Exception as e:
                    logger.warning(f"Error settling prop {prop['id']}: {e}")
                    stats['errors'] += 1

            if settled_count % 10 == 0 and settled_count > 0:
                time.sleep(0.5)

        logger.info(f"Settlement complete: {stats['settled']} settled "
                     f"({stats['won']}W/{stats['lost']}L/{stats['push']}P/{stats['void']}V), "
                     f"{stats['skipped']} skipped, {stats['errors']} errors")

    except Exception as e:
        logger.error(f"Player props settlement error: {e}")
        stats['errors'] += 1

    return stats


def _get_pending_props() -> List[Dict]:
    try:
        with DatabaseConnection.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, player_name, sport, league, market, line, selection,
                       odds, commence_time, home_team, away_team, status, notes
                FROM player_props
                WHERE status = 'pending'
                  AND sport = 'basketball'
                  AND commence_time < NOW() - INTERVAL '%s hours'
                  AND commence_time > NOW() - INTERVAL '5 days'
                ORDER BY commence_time ASC
                LIMIT 200
            """ % SETTLE_GRACE_HOURS)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching pending props: {e}")
        return []


def _get_player_game_stats(player_name: str, commence_time) -> Optional[Dict]:
    game_date = commence_time.strftime('%Y-%m-%d') if hasattr(commence_time, 'strftime') else str(commence_time)[:10]
    cache_key = f"{player_name}|{game_date}"

    now = time.time()
    if cache_key in _boxscore_cache:
        cached, ts = _boxscore_cache[cache_key]
        if now - ts < _cache_ttl:
            return cached

    try:
        from nba_stats_provider import _get_player_id
        pid = _get_player_id(player_name)
        if not pid:
            logger.debug(f"Player not found: {player_name}")
            return None

        from nba_api.stats.endpoints import playergamelog
        time.sleep(0.7)

        log = playergamelog.PlayerGameLog(
            player_id=pid, season='2025-26', timeout=15
        )
        df = log.get_data_frames()[0]

        if df.empty:
            return None

        target_date = datetime.strptime(game_date, '%Y-%m-%d').date()

        for _, row in df.iterrows():
            game_date_str = str(row.get('GAME_DATE', ''))
            try:
                if 'T' in game_date_str:
                    gd = datetime.fromisoformat(game_date_str).date()
                else:
                    for fmt in ['%b %d, %Y', '%Y-%m-%d', '%m/%d/%Y']:
                        try:
                            gd = datetime.strptime(game_date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        continue
            except Exception:
                continue

            if abs((gd - target_date).days) <= 1:
                min_str = str(row.get('MIN', '0'))
                try:
                    if ':' in min_str:
                        parts = min_str.split(':')
                        minutes = int(parts[0]) + int(parts[1]) / 60
                    else:
                        minutes = float(min_str) if min_str else 0
                except (ValueError, IndexError):
                    minutes = 0

                if minutes < 1:
                    result = {'dnp': True, 'minutes': 0}
                else:
                    pts = float(row.get('PTS', 0) or 0)
                    reb = float(row.get('REB', 0) or 0)
                    ast = float(row.get('AST', 0) or 0)
                    result = {
                        'dnp': False,
                        'minutes': round(minutes, 1),
                        'PTS': pts,
                        'REB': reb,
                        'AST': ast,
                        'PRA': pts + reb + ast,
                    }

                _boxscore_cache[cache_key] = (result, now)
                return result

        return None

    except Exception as e:
        logger.warning(f"Stats fetch error for {player_name} on {game_date}: {e}")
        return None


def _evaluate_prop(prop: Dict, actual_stats: Dict) -> Optional[Tuple[str, float, str]]:
    market = prop['market']
    line = prop.get('line')
    selection = prop.get('selection', '').strip()

    if line is None:
        return None

    stat_key = MARKET_STAT_MAP.get(market)
    if not stat_key:
        return None

    actual_val = actual_stats.get(stat_key)
    if actual_val is None:
        return None

    line = float(line)
    sel_lower = selection.lower()

    if 'over' in sel_lower:
        if actual_val > line:
            outcome = 'won'
        elif actual_val == line:
            outcome = 'push'
        else:
            outcome = 'lost'
    elif 'under' in sel_lower:
        if actual_val < line:
            outcome = 'won'
        elif actual_val == line:
            outcome = 'push'
        else:
            outcome = 'lost'
    else:
        return None

    note = f"Actual: {actual_val:.0f} vs Line: {line:.1f} ({selection})"
    return outcome, actual_val, note


def _settle_prop(prop_id: int, outcome: str, actual_val: Optional[float], note: str):
    try:
        status = 'settled'
        result_str = outcome.upper()
        if outcome == 'push':
            result_str = 'PUSH'

        profit = 0
        if outcome == 'won':
            profit = 1.0
        elif outcome == 'lost':
            profit = -1.0

        with DatabaseConnection.get_cursor() as cursor:
            cursor.execute("""
                UPDATE player_props
                SET status = %s,
                    outcome = %s,
                    result = %s,
                    profit_loss = %s,
                    settled_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (status, outcome, result_str, profit, prop_id))

    except Exception as e:
        logger.warning(f"Error settling prop {prop_id}: {e}")


def _game_likely_finished(commence_time) -> bool:
    if commence_time is None:
        return False
    now = datetime.now(timezone.utc)
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    hours_since = (now - commence_time).total_seconds() / 3600
    return hours_since >= SETTLE_GRACE_HOURS


def _hours_since(commence_time) -> float:
    if commence_time is None:
        return 0
    now = datetime.now(timezone.utc)
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    return (now - commence_time).total_seconds() / 3600


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    result = run_player_props_settlement()
    print(f"Settlement results: {result}")

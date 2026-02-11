"""
NBA Stats Provider
==================
Fetches player game logs from nba_api for quality filtering.
Caches stats in PostgreSQL to avoid repeated API calls.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
from db_connection import DatabaseConnection

logger = logging.getLogger(__name__)

CURRENT_SEASON = '2025-26'

_stats_cache = {}
_cache_ttl = 3600


def _get_player_id(player_name: str) -> Optional[int]:
    try:
        from nba_api.stats.static import players
        name_lower = player_name.lower().strip()

        found = players.find_players_by_full_name(player_name)
        if found:
            return found[0]['id']

        parts = name_lower.split()
        if len(parts) >= 2:
            last = parts[-1]
            by_last = [p for p in players.get_players() if p['last_name'].lower() == last and p['is_active']]
            if len(by_last) == 1:
                return by_last[0]['id']
            for p in by_last:
                if p['first_name'].lower().startswith(parts[0][:3]):
                    return p['id']

        return None
    except Exception as e:
        logger.debug(f"Player ID lookup failed for {player_name}: {e}")
        return None


def get_player_stats(player_name: str, num_games: int = 15) -> Optional[Dict]:
    cache_key = f"{player_name}_{CURRENT_SEASON}"
    now = time.time()
    if cache_key in _stats_cache:
        cached, ts = _stats_cache[cache_key]
        if now - ts < _cache_ttl:
            return cached

    pid = _get_player_id(player_name)
    if not pid:
        logger.debug(f"Player not found in NBA: {player_name}")
        return None

    try:
        from nba_api.stats.endpoints import playergamelog
        time.sleep(0.6)
        log = playergamelog.PlayerGameLog(
            player_id=pid, season=CURRENT_SEASON, timeout=15
        )
        df = log.get_data_frames()[0]

        if df.empty:
            return None

        total_games = len(df)
        recent = df.head(num_games)

        avg_min_str = recent['MIN'].astype(str)
        minutes = []
        for m in avg_min_str:
            try:
                if ':' in str(m):
                    parts = str(m).split(':')
                    minutes.append(int(parts[0]) + int(parts[1]) / 60)
                else:
                    minutes.append(float(m))
            except (ValueError, IndexError):
                minutes.append(0)

        last_10 = minutes[:10] if len(minutes) >= 10 else minutes
        last_7_games = df.head(7)
        games_played_last_7 = len(last_7_games)

        last_game_min = minutes[0] if minutes else 0

        avg_min_10 = sum(last_10) / len(last_10) if last_10 else 0

        pts_recent = recent['PTS'].astype(float).tolist()
        reb_recent = recent['REB'].astype(float).tolist()
        ast_recent = recent['AST'].astype(float).tolist()

        avg_pts = sum(pts_recent) / len(pts_recent) if pts_recent else 0
        avg_reb = sum(reb_recent) / len(reb_recent) if reb_recent else 0
        avg_ast = sum(ast_recent) / len(ast_recent) if ast_recent else 0
        avg_pra = avg_pts + avg_reb + avg_ast

        is_starter = avg_min_10 >= 25
        is_rotation = avg_min_10 >= 15
        returning_from_injury = (
            games_played_last_7 <= 2 and total_games >= 10
        )
        limited_last_game = last_game_min < 15 and avg_min_10 >= 22

        stats = {
            'player_id': pid,
            'player_name': player_name,
            'total_games': total_games,
            'avg_min_last_10': round(avg_min_10, 1),
            'games_played_last_7': games_played_last_7,
            'last_game_min': round(last_game_min, 1),
            'avg_pts': round(avg_pts, 1),
            'avg_reb': round(avg_reb, 1),
            'avg_ast': round(avg_ast, 1),
            'avg_pra': round(avg_pra, 1),
            'is_starter': is_starter,
            'is_rotation': is_rotation,
            'returning_from_injury': returning_from_injury,
            'limited_last_game': limited_last_game,
            'pts_last_10': pts_recent[:10],
            'reb_last_10': reb_recent[:10],
            'ast_last_10': ast_recent[:10],
        }

        _stats_cache[cache_key] = (stats, now)
        return stats

    except Exception as e:
        logger.warning(f"Stats fetch error for {player_name}: {e}")
        return None


def get_projection(stats: Dict, market: str, line: float) -> Optional[Dict]:
    if not stats:
        return None

    if market == 'player_points':
        projected = stats['avg_pts']
        recent_vals = stats.get('pts_last_10', [])
    elif market == 'player_rebounds':
        projected = stats['avg_reb']
        recent_vals = stats.get('reb_last_10', [])
    elif market == 'player_assists':
        projected = stats['avg_ast']
        recent_vals = stats.get('ast_last_10', [])
    elif market in ('player_points_rebounds_assists', 'player_pra'):
        projected = stats['avg_pra']
        pts = stats.get('pts_last_10', [])
        reb = stats.get('reb_last_10', [])
        ast = stats.get('ast_last_10', [])
        min_len = min(len(pts), len(reb), len(ast))
        recent_vals = [pts[i] + reb[i] + ast[i] for i in range(min_len)]
    else:
        return None

    if not recent_vals or len(recent_vals) < 10:
        return None

    diff = projected - line
    games_over = sum(1 for v in recent_vals if v > line)
    hit_rate = games_over / len(recent_vals) if recent_vals else 0

    consistency = 1.0 - (max(recent_vals) - min(recent_vals)) / (projected + 0.1) if projected > 0 else 0

    return {
        'projected': round(projected, 1),
        'line': line,
        'diff': round(diff, 1),
        'hit_rate_over': round(hit_rate, 3),
        'games_over': games_over,
        'games_total': len(recent_vals),
        'consistency': round(max(0, min(1, consistency)), 2),
    }


def batch_get_stats(player_names: List[str]) -> Dict[str, Optional[Dict]]:
    results = {}
    for name in player_names:
        results[name] = get_player_stats(name)
    return results

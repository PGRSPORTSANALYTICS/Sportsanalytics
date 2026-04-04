#!/usr/bin/env python3
"""
Referee Stats Service
---------------------
Fetches real referee card statistics from API-Football,
caches results in PostgreSQL (7-day TTL), and returns a
stats dict compatible with the CardsEngine.

Usage:
    from referee_stats_service import get_referee_stats
    stats = get_referee_stats(referee_name, league, api_client)
"""

import logging
import json
import time
from typing import Optional, Dict

from db_helper import DatabaseHelper as _db

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 7
MIN_FIXTURES_FOR_STATS = 5   # Need at least 5 matches for meaningful stats


def _ensure_table():
    """Create referee_stats_cache table if it doesn't exist."""
    try:
        _db.execute("""
            CREATE TABLE IF NOT EXISTS referee_stats_cache (
                referee_name TEXT PRIMARY KEY,
                cards_pm REAL,
                yellows_pm REAL,
                reds_pm REAL,
                fouls_pm REAL,
                total_matches INTEGER,
                style TEXT,
                league_sample TEXT,
                updated_at BIGINT
            )
        """, fetch=None)
    except Exception as e:
        logger.warning(f"referee_stats_cache table creation: {e}")


def _get_cached(referee_name: str) -> Optional[Dict]:
    """Return cached stats if fresh enough, else None."""
    try:
        row = _db.execute("""
            SELECT cards_pm, yellows_pm, reds_pm, fouls_pm,
                   total_matches, style, updated_at
            FROM referee_stats_cache
            WHERE referee_name = %s
        """, (referee_name,), fetch='one')
        if not row:
            return None
        age_days = (time.time() - (row[6] or 0)) / 86400
        if age_days > CACHE_TTL_DAYS:
            return None
        return {
            'referee_name': referee_name,
            'cards_per_match': float(row[0] or 4.2),
            'yellows_per_match': float(row[1] or 3.9),
            'reds_per_match': float(row[2] or 0.08),
            'fouls_per_match': float(row[3] or 23.0),
            'total_matches': int(row[4] or 0),
            'style': row[5] or 'balanced',
            'foul_to_card_conversion': _foul_to_card(row[0], row[3]),
            'early_card_rate': 0.25,
            'big_match_intensity': 1.0,
            'source': 'db_cache',
        }
    except Exception as e:
        logger.warning(f"referee cache read error: {e}")
        return None


def _save_cache(referee_name: str, stats: Dict):
    """Upsert referee stats into cache table."""
    try:
        _db.execute("""
            INSERT INTO referee_stats_cache
                (referee_name, cards_pm, yellows_pm, reds_pm, fouls_pm,
                 total_matches, style, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (referee_name) DO UPDATE SET
                cards_pm = EXCLUDED.cards_pm,
                yellows_pm = EXCLUDED.yellows_pm,
                reds_pm = EXCLUDED.reds_pm,
                fouls_pm = EXCLUDED.fouls_pm,
                total_matches = EXCLUDED.total_matches,
                style = EXCLUDED.style,
                updated_at = EXCLUDED.updated_at
        """, (
            referee_name,
            stats.get('cards_per_match', 4.2),
            stats.get('yellows_per_match', 3.9),
            stats.get('reds_per_match', 0.08),
            stats.get('fouls_per_match', 23.0),
            stats.get('total_matches', 0),
            stats.get('style', 'balanced'),
            int(time.time()),
        ), fetch=None)
    except Exception as e:
        logger.warning(f"referee cache save error: {e}")


def _foul_to_card(cards_pm, fouls_pm):
    """Calculate foul-to-card conversion ratio."""
    try:
        c = float(cards_pm or 4.2)
        f = float(fouls_pm or 23.0)
        return round(c / f, 3) if f > 0 else 0.18
    except Exception:
        return 0.18


def _classify_style(cards_pm: float) -> str:
    """Classify referee style based on cards per match."""
    if cards_pm >= 5.5:
        return 'very_strict'
    elif cards_pm >= 4.8:
        return 'strict'
    elif cards_pm <= 3.2:
        return 'lenient'
    elif cards_pm <= 3.8:
        return 'fairly_lenient'
    return 'balanced'


def _fetch_from_api(referee_name: str, api_client) -> Optional[Dict]:
    """
    Query API-Football for recent fixtures by this referee.
    Returns stats dict or None on failure.
    """
    try:
        import requests, os
        api_key = os.environ.get('API_FOOTBALL_KEY', '')
        if not api_key:
            return None

        headers = {'x-apisports-key': api_key}

        # Query last 2 seasons of fixtures for this referee
        total_yellows = total_reds = total_fouls = n = 0

        for season in [2024, 2023]:
            url = 'https://v3.football.api-sports.io/fixtures'
            params = {'referee': referee_name, 'season': season}
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=8)
                if resp.status_code != 200:
                    continue
                data = resp.json().get('response', [])
                for fx in data:
                    stats_list = fx.get('statistics', [])
                    for team_stats in stats_list:
                        for stat in team_stats.get('statistics', []):
                            stype = stat.get('type', '').lower()
                            val = stat.get('value')
                            if val is None:
                                continue
                            try:
                                val = float(val)
                            except Exception:
                                continue
                            if 'yellow' in stype and 'red' not in stype:
                                total_yellows += val
                            elif 'red' in stype:
                                total_reds += val
                            elif 'foul' in stype:
                                total_fouls += val
                    n += 1
            except Exception as e:
                logger.warning(f"API-Football referee fetch season {season}: {e}")

        if n < MIN_FIXTURES_FOR_STATS:
            logger.info(f"🎴 Referee {referee_name}: only {n} fixtures found, using defaults")
            return None

        yellows_pm = round(total_yellows / n, 2)
        reds_pm    = round(total_reds / n, 3)
        fouls_pm   = round(total_fouls / n, 1) if total_fouls > 0 else 23.0
        cards_pm   = round(yellows_pm + reds_pm, 2)
        style      = _classify_style(cards_pm)

        logger.info(
            f"✅ Referee {referee_name}: {n} matches, "
            f"{cards_pm:.1f} cards/match, style={style}"
        )
        return {
            'referee_name': referee_name,
            'cards_per_match': cards_pm,
            'yellows_per_match': yellows_pm,
            'reds_per_match': reds_pm,
            'fouls_per_match': fouls_pm,
            'total_matches': n,
            'style': style,
            'foul_to_card_conversion': _foul_to_card(cards_pm, fouls_pm),
            'early_card_rate': 0.25,
            'big_match_intensity': 1.0,
            'source': 'api_football',
        }
    except Exception as e:
        logger.error(f"referee API fetch failed for {referee_name}: {e}")
        return None


def get_referee_stats(
    referee_name: Optional[str],
    league: str = '',
    api_client=None,
) -> Dict:
    """
    Main entry point. Returns referee stats dict for use in CardsEngine.
    Priority: DB cache → API-Football live → default profile.
    """
    _ensure_table()

    if not referee_name or referee_name.strip().lower() in ('', 'unknown', 'tbd', 'tba'):
        logger.info("⚠️ No referee assigned yet — using league defaults")
        return _default_profile(league)

    referee_name = referee_name.strip()

    # 1. Try DB cache
    cached = _get_cached(referee_name)
    if cached:
        logger.info(f"📦 Referee cache hit: {referee_name} ({cached['style']}, {cached['cards_per_match']:.1f} cards/match)")
        return cached

    # 2. Try API-Football
    logger.info(f"🔍 Fetching referee stats for: {referee_name}")
    api_stats = _fetch_from_api(referee_name, api_client)
    if api_stats:
        _save_cache(referee_name, api_stats)
        return api_stats

    # 3. Fallback to league-calibrated default
    logger.info(f"⚠️ No stats found for {referee_name}, using league default")
    return _default_profile(league, referee_name)


def _default_profile(league: str = '', referee_name: str = 'Unknown') -> Dict:
    """
    League-calibrated default referee profile.
    Based on real average cards/match per top league.
    """
    league_lower = (league or '').lower()

    # League-specific averages (real data)
    if any(k in league_lower for k in ['serie a', 'italy', 'italian']):
        cards_pm = 5.1   # Serie A is strict
    elif any(k in league_lower for k in ['la liga', 'spain', 'spanish', 'primera']):
        cards_pm = 5.3   # La Liga most cards in Europe
    elif any(k in league_lower for k in ['ligue 1', 'france', 'french']):
        cards_pm = 4.8
    elif any(k in league_lower for k in ['bundesliga', 'german', 'germany']):
        cards_pm = 4.0   # Bundesliga fewer cards
    elif any(k in league_lower for k in ['premier league', 'england', 'english']):
        cards_pm = 3.9
    elif any(k in league_lower for k in ['eredivisie', 'dutch', 'netherlands']):
        cards_pm = 4.2
    elif any(k in league_lower for k in ['champions league', 'europa', 'conference']):
        cards_pm = 3.8   # European competitions slightly cleaner
    elif any(k in league_lower for k in ['turkish', 'turkey']):
        cards_pm = 5.6
    elif any(k in league_lower for k in ['greek', 'greece']):
        cards_pm = 5.4
    elif any(k in league_lower for k in ['portuguese', 'primeira']):
        cards_pm = 4.6
    else:
        cards_pm = 4.4   # Global average

    style = _classify_style(cards_pm)
    yellows_pm = round(cards_pm * 0.93, 2)  # ~7% reds

    return {
        'referee_name': referee_name,
        'cards_per_match': cards_pm,
        'yellows_per_match': yellows_pm,
        'reds_per_match': round(cards_pm * 0.07, 3),
        'fouls_per_match': round(cards_pm * 5.3, 1),
        'total_matches': 0,
        'style': style,
        'foul_to_card_conversion': round(1 / 5.3, 3),
        'early_card_rate': 0.25,
        'big_match_intensity': 1.0,
        'source': 'league_default',
    }

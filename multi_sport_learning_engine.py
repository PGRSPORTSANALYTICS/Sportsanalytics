"""
Multi-Sport Learning Engine
============================
Scans odds from The Odds API for Tennis, NHL/SHL Hockey, and MMA.
Learning mode only - no real stakes, simulated 1u flat bets.
Collects data to find edges for potential future production markets.
"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import requests
from db_connection import DatabaseConnection

logger = logging.getLogger(__name__)

SPORT_CONFIG = {
    'TENNIS': {
        'sport_keys': [
            'tennis_atp_australian_open', 'tennis_atp_french_open',
            'tennis_atp_us_open', 'tennis_atp_wimbledon',
            'tennis_wta_australian_open', 'tennis_wta_french_open',
            'tennis_wta_us_open', 'tennis_wta_wimbledon',
            'tennis_atp_indian_wells', 'tennis_wta_indian_wells',
            'tennis_atp_miami_open', 'tennis_wta_miami_open',
            'tennis_atp_rome', 'tennis_wta_rome',
            'tennis_atp_madrid_open', 'tennis_wta_madrid_open',
            'tennis_atp_canadian_open', 'tennis_wta_canadian_open',
            'tennis_atp_cincinnati_open', 'tennis_wta_cincinnati_open',
            'tennis_atp_shanghai', 'tennis_wta_beijing',
            'tennis_atp_qatar_open', 'tennis_wta_qatar_open',
            'tennis_atp_dubai', 'tennis_wta_dubai',
        ],
        'markets': 'h2h,totals',
        'label': 'Tennis',
        'emoji': '🎾',
    },
    'HOCKEY': {
        'sport_keys': [
            'icehockey_nhl',
            'icehockey_sweden_hockey_league',
            'icehockey_sweden_allsvenskan',
        ],
        'markets': 'h2h,totals',
        'label': 'Hockey',
        'emoji': '🏒',
    },
    'MMA': {
        'sport_keys': [
            'mma_mixed_martial_arts',
        ],
        'markets': 'h2h',
        'label': 'MMA',
        'emoji': '🥊',
    },
}

ODDS_RANGE = (1.40, 3.50)
MAX_PICKS_PER_SPORT = 15
API_BUDGET_PER_CYCLE = 12


def run_multi_sport_learning() -> Dict:
    stats = {
        'TENNIS': {'scanned': 0, 'saved': 0},
        'HOCKEY': {'scanned': 0, 'saved': 0},
        'MMA': {'scanned': 0, 'saved': 0},
        'api_calls': 0,
        'errors': 0,
    }

    api_key = os.environ.get('THE_ODDS_API_KEY', '')
    if not api_key:
        try:
            from real_odds_api import RealOddsAPI
            api = RealOddsAPI()
            api_key = api.api_key
        except Exception:
            logger.error("No Odds API key available")
            return stats

    active_sports = _get_active_sports(api_key)
    if not active_sports:
        logger.warning("Could not fetch active sports list")
        return stats

    active_keys = {s['key'] for s in active_sports}

    for category, config in SPORT_CONFIG.items():
        if stats['api_calls'] >= API_BUDGET_PER_CYCLE:
            logger.info(f"API budget reached ({API_BUDGET_PER_CYCLE} calls), stopping")
            break

        matching_keys = [k for k in config['sport_keys'] if k in active_keys]
        if not matching_keys:
            logger.info(f"{config['emoji']} {config['label']}: No active events")
            continue

        logger.info(f"{config['emoji']} {config['label']}: {len(matching_keys)} active leagues")

        existing = _get_existing_events(category)

        for sport_key in matching_keys:
            if stats['api_calls'] >= API_BUDGET_PER_CYCLE:
                break

            try:
                events = _fetch_odds(api_key, sport_key, config['markets'])
                stats['api_calls'] += 1

                if not events:
                    continue

                league_label = sport_key.replace('_', ' ').title()
                stats[category]['scanned'] += len(events)

                saved = _process_events(events, category, sport_key, league_label, existing, config)
                stats[category]['saved'] += saved

                time.sleep(0.3)

            except Exception as e:
                logger.warning(f"Error processing {sport_key}: {e}")
                stats['errors'] += 1

        logger.info(f"{config['emoji']} {config['label']}: "
                     f"{stats[category]['scanned']} events scanned, "
                     f"{stats[category]['saved']} picks saved")

    total_saved = sum(s['saved'] for s in [stats['TENNIS'], stats['HOCKEY'], stats['MMA']])
    logger.info(f"Multi-sport learning complete: {total_saved} total picks saved, "
                f"{stats['api_calls']} API calls used")

    return stats


def _get_active_sports(api_key: str) -> List[Dict]:
    try:
        resp = requests.get(
            'https://api.the-odds-api.com/v4/sports',
            params={'apiKey': api_key},
            timeout=10
        )
        if resp.status_code == 200:
            return [s for s in resp.json() if s.get('active')]
        return []
    except Exception as e:
        logger.warning(f"Error fetching sports list: {e}")
        return []


def _fetch_odds(api_key: str, sport_key: str, markets: str) -> List[Dict]:
    try:
        resp = requests.get(
            f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds',
            params={
                'apiKey': api_key,
                'regions': 'eu',
                'markets': markets,
                'oddsFormat': 'decimal',
            },
            timeout=15
        )
        if resp.status_code == 200:
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.debug(f"Odds API: {sport_key} -> {len(resp.json())} events (remaining: {remaining})")
            return resp.json()
        elif resp.status_code == 404:
            return []
        else:
            logger.warning(f"Odds API {resp.status_code} for {sport_key}")
            return []
    except Exception as e:
        logger.warning(f"Error fetching odds for {sport_key}: {e}")
        return []


def _get_existing_events(category: str) -> set:
    try:
        with DatabaseConnection.get_cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT event_id || '|' || market || '|' || selection
                FROM learning_bets
                WHERE sport_category = %s
                  AND status = 'pending'
            """, (category,))
            return {row[0] for row in cursor.fetchall()}
    except Exception:
        return set()


def _process_events(events: List[Dict], category: str, sport_key: str,
                    league: str, existing: set, config: Dict) -> int:
    saved = 0
    picks = []

    for event in events:
        event_id = event.get('id', '')
        home = event.get('home_team', '')
        away = event.get('away_team', '')
        commence = event.get('commence_time', '')

        if not commence:
            continue

        try:
            ct = datetime.fromisoformat(commence.replace('Z', '+00:00'))
        except Exception:
            continue

        if ct < datetime.now(timezone.utc):
            continue

        bookmakers = event.get('bookmakers', [])
        if not bookmakers:
            continue

        best_odds = _extract_best_odds(bookmakers)

        for market_key, outcomes in best_odds.items():
            for selection, odds_val in outcomes.items():
                if odds_val < ODDS_RANGE[0] or odds_val > ODDS_RANGE[1]:
                    continue

                dedup_key = f"{event_id}|{market_key}|{selection}"
                if dedup_key in existing:
                    continue

                implied = 1.0 / odds_val
                edge = 0.0

                line = None
                if 'Over' in selection or 'Under' in selection:
                    parts = selection.split(' ')
                    try:
                        line = float(parts[-1])
                        selection_clean = parts[0]
                    except ValueError:
                        selection_clean = selection
                else:
                    selection_clean = selection

                picks.append({
                    'event_id': event_id,
                    'sport_key': sport_key,
                    'league': league,
                    'home_team': home,
                    'away_team': away,
                    'market': market_key,
                    'selection': selection_clean if line else selection,
                    'line': line,
                    'odds': odds_val,
                    'implied_prob': round(implied * 100, 1),
                    'edge_pct': edge,
                    'commence_time': ct,
                    'dedup_key': dedup_key,
                })
                existing.add(dedup_key)

    picks.sort(key=lambda x: x['odds'], reverse=False)
    picks = picks[:MAX_PICKS_PER_SPORT]

    for pick in picks:
        try:
            _save_pick(category, pick)
            saved += 1
        except Exception as e:
            logger.warning(f"Error saving pick: {e}")

    return saved


def _extract_best_odds(bookmakers: List[Dict]) -> Dict[str, Dict[str, float]]:
    best = {}

    for bm in bookmakers:
        for market in bm.get('markets', []):
            market_key = market.get('key', '')
            if market_key not in best:
                best[market_key] = {}

            for outcome in market.get('outcomes', []):
                name = outcome.get('name', '')
                price = outcome.get('price', 0)
                point = outcome.get('point')

                if point is not None:
                    sel = f"Over {point}" if name == 'Over' else f"Under {point}"
                else:
                    sel = name

                if sel not in best[market_key] or price > best[market_key][sel]:
                    best[market_key][sel] = price

    return best


def _save_pick(category: str, pick: Dict):
    with DatabaseConnection.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO learning_bets (
                sport_category, sport_key, league, event_id,
                home_team, away_team, market, selection, line,
                odds, implied_prob, model_prob, edge_pct,
                status, commence_time, mode
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            category, pick['sport_key'], pick['league'], pick['event_id'],
            pick['home_team'], pick['away_team'], pick['market'],
            pick['selection'], pick.get('line'),
            pick['odds'], pick['implied_prob'], None, pick['edge_pct'],
            'pending', pick['commence_time'], 'LEARNING'
        ))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    result = run_multi_sport_learning()
    print(f"Results: {result}")

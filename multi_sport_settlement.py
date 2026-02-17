"""
Multi-Sport Settlement Engine
==============================
Settles learning bets for Tennis, Hockey, and MMA using The Odds API scores endpoint.
"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import requests
from db_connection import DatabaseConnection

logger = logging.getLogger(__name__)

SETTLE_GRACE_HOURS = 2
VOID_AFTER_HOURS = 72

SPORT_GRACE_HOURS = {
    'TENNIS': 2,
    'HOCKEY': 3,
    'MMA': 4,
}


def run_multi_sport_settlement() -> Dict:
    stats = {
        'settled': 0,
        'won': 0,
        'lost': 0,
        'push': 0,
        'void': 0,
        'skipped': 0,
        'errors': 0,
    }

    api_key = os.environ.get('THE_ODDS_API_KEY', '')
    if not api_key:
        try:
            from real_odds_api import RealOddsAPI
            api = RealOddsAPI()
            api_key = api.api_key
        except Exception:
            logger.error("No Odds API key for settlement")
            return stats

    pending = _get_pending_bets()
    if not pending:
        logger.info("No pending learning bets to settle")
        return stats

    logger.info(f"Found {len(pending)} pending learning bets to check")

    events_by_id = {}
    for bet in pending:
        eid = bet['event_id']
        if eid not in events_by_id:
            events_by_id[eid] = []
        events_by_id[eid].append(bet)

    sport_keys_needed = set()
    for bet in pending:
        sport_keys_needed.add(bet['sport_key'])

    scores_cache = {}
    for sport_key in sport_keys_needed:
        try:
            scores = _fetch_scores(api_key, sport_key)
            for score in scores:
                scores_cache[score.get('id', '')] = score
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"Error fetching scores for {sport_key}: {e}")
            stats['errors'] += 1

    for event_id, bets in events_by_id.items():
        score_data = scores_cache.get(event_id)
        sample_bet = bets[0]

        if score_data is None:
            hours_since = _hours_since(sample_bet['commence_time'])
            if hours_since > VOID_AFTER_HOURS:
                for bet in bets:
                    _settle_bet(bet['id'], 'void', f'No scores found after {VOID_AFTER_HOURS}h')
                    stats['void'] += 1
                    stats['settled'] += 1
            else:
                stats['skipped'] += len(bets)
            continue

        if not score_data.get('completed'):
            stats['skipped'] += len(bets)
            continue

        home_score, away_score = _extract_scores(score_data, sample_bet['sport_category'])
        if home_score is None or away_score is None:
            stats['skipped'] += len(bets)
            continue

        home_team_api = score_data.get('home_team', '')
        away_team_api = score_data.get('away_team', '')

        for bet in bets:
            try:
                result = _evaluate_bet(bet, home_score, away_score, home_team_api, away_team_api)
                if result:
                    outcome, note = result
                    profit = 0.0
                    if outcome == 'won':
                        profit = 1.0
                    elif outcome == 'lost':
                        profit = -1.0

                    _settle_bet(bet['id'], outcome, note, profit)
                    if outcome in stats:
                        stats[outcome] += 1
                    stats['settled'] += 1
                else:
                    stats['skipped'] += 1
            except Exception as e:
                logger.warning(f"Error settling bet {bet['id']}: {e}")
                stats['errors'] += 1

    logger.info(f"Settlement complete: {stats['settled']} settled "
                f"({stats['won']}W/{stats['lost']}L/{stats['push']}P/{stats['void']}V), "
                f"{stats['skipped']} skipped")

    return stats


def _get_pending_bets() -> List[Dict]:
    try:
        with DatabaseConnection.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, sport_category, sport_key, event_id,
                       home_team, away_team, market, selection, line,
                       odds, commence_time
                FROM learning_bets
                WHERE status = 'pending'
                  AND commence_time < NOW() - INTERVAL '2 hours'
                  AND commence_time > NOW() - INTERVAL '10 days'
                ORDER BY commence_time ASC
                LIMIT 300
            """)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching pending bets: {e}")
        return []


def _fetch_scores(api_key: str, sport_key: str) -> List[Dict]:
    try:
        resp = requests.get(
            f'https://api.the-odds-api.com/v4/sports/{sport_key}/scores',
            params={
                'apiKey': api_key,
                'daysFrom': 3,
            },
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        logger.warning(f"Scores fetch error for {sport_key}: {e}")
        return []


def _extract_scores(score_data: Dict, sport_category: str) -> Tuple[Optional[float], Optional[float]]:
    scores = score_data.get('scores', [])
    if not scores or len(scores) < 2:
        return None, None

    home_team = score_data.get('home_team', '')
    away_team = score_data.get('away_team', '')

    home_score = None
    away_score = None

    for s in scores:
        name = s.get('name', '')
        score_val = s.get('score')
        if score_val is None:
            continue
        try:
            score_float = float(score_val)
        except (ValueError, TypeError):
            continue

        if name == home_team:
            home_score = score_float
        elif name == away_team:
            away_score = score_float

    return home_score, away_score


def _evaluate_bet(bet: Dict, home_score: float, away_score: float,
                  home_team_api: str, away_team_api: str) -> Optional[Tuple[str, str]]:
    market = bet['market']
    selection = bet['selection']
    line = bet.get('line')
    bet_home = bet['home_team']
    bet_away = bet['away_team']
    sport_cat = bet.get('sport_category', '')

    total = home_score + away_score
    score_str = f"{home_score:.0f}-{away_score:.0f}"

    if market in ('h2h', 'h2h_lay'):
        is_lay = market == 'h2h_lay'
        if selection == bet_home or selection == home_team_api:
            if home_score > away_score:
                raw = 'won'
            elif home_score == away_score:
                if sport_cat == 'TENNIS':
                    return 'void', f"Tennis draw (walkover?) {score_str}"
                return 'push', f"Draw {score_str}"
            else:
                raw = 'lost'
            result = 'lost' if (is_lay and raw == 'won') else ('won' if (is_lay and raw == 'lost') else raw)
            return result, f"{'Lay ' if is_lay else ''}Home {'win' if raw == 'won' else 'lost'} {score_str}"
        elif selection == bet_away or selection == away_team_api:
            if away_score > home_score:
                raw = 'won'
            elif home_score == away_score:
                if sport_cat == 'TENNIS':
                    return 'void', f"Tennis draw (walkover?) {score_str}"
                return 'push', f"Draw {score_str}"
            else:
                raw = 'lost'
            result = 'lost' if (is_lay and raw == 'won') else ('won' if (is_lay and raw == 'lost') else raw)
            return result, f"{'Lay ' if is_lay else ''}Away {'win' if raw == 'won' else 'lost'} {score_str}"
        elif selection.lower() == 'draw':
            if home_score == away_score:
                raw = 'won'
            else:
                raw = 'lost'
            result = 'lost' if (is_lay and raw == 'won') else ('won' if (is_lay and raw == 'lost') else raw)
            return result, f"{'Lay ' if is_lay else ''}Draw {score_str}"

    elif market == 'totals':
        if line is None:
            return None

        if 'Over' in selection or selection == 'Over':
            if total > line:
                return 'won', f"Over {line}: total={total:.0f}"
            elif total == line:
                return 'push', f"Push: total={total:.0f} = line {line}"
            else:
                return 'lost', f"Under {line}: total={total:.0f}"
        elif 'Under' in selection or selection == 'Under':
            if total < line:
                return 'won', f"Under {line}: total={total:.0f}"
            elif total == line:
                return 'push', f"Push: total={total:.0f} = line {line}"
            else:
                return 'lost', f"Over {line}: total={total:.0f}"

    return None


def _settle_bet(bet_id: int, outcome: str, note: str, profit: float = 0.0):
    try:
        result_str = outcome.upper()
        with DatabaseConnection.get_cursor() as cursor:
            cursor.execute("""
                UPDATE learning_bets
                SET status = 'settled',
                    outcome = %s,
                    result = %s,
                    profit_loss = %s,
                    result_notes = %s,
                    settled_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (outcome, result_str, profit, note, bet_id))
    except Exception as e:
        logger.warning(f"Error settling bet {bet_id}: {e}")


def _hours_since(commence_time) -> float:
    if commence_time is None:
        return 0
    now = datetime.now(timezone.utc)
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    return (now - commence_time).total_seconds() / 3600


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    result = run_multi_sport_settlement()
    print(f"Settlement results: {result}")

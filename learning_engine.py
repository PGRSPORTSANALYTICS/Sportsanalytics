"""
Self-Learning Engine v1.0
=========================
Computes performance statistics across ALL leagues and markets using
rolling windows (last 50, last 100, all-time).

Tracks:
- Per league: ROI, hit rate, avg CLV, profit units, league_score
- Per market: ROI, hit rate, avg CLV, profit units, market_score
- Per league+market combo: combined stats and score

Scores use weighted formula:
  score = ROI_weight * ROI + CLV_weight * avg_CLV + volume_weight * log(total_bets)

Low-volume dimensions are penalized via log(volume) to prevent overfitting.
"""

import math
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from db_helper import db_helper

logger = logging.getLogger(__name__)

ROI_WEIGHT = 0.45
CLV_WEIGHT = 0.35
VOLUME_WEIGHT = 0.20

ROLLING_WINDOWS = {
    'last_50': 50,
    'last_100': 100,
    'all_time': None,
}

EXCLUDED_MARKETS = {'exact_score', 'correct_score', 'first_half_exact', 'halftime_score'}

SPORTS_TABLE_MAP = {
    'football': {
        'table': 'football_opportunities',
        'league_col': 'league',
        'market_col': 'market',
        'odds_col': 'odds',
        'result_col': 'result',
        'status_col': 'status',
        'clv_col': 'clv_pct',
        'mode_col': 'mode',
        'open_odds_col': 'open_odds',
        'close_odds_col': 'close_odds',
        'settled_statuses': ("settled",),
        'win_results': ("won", "win"),
        'loss_results': ("lost", "loss"),
    },
    'basketball': {
        'table': 'basketball_predictions',
        'league_col': 'league',
        'market_col': 'market',
        'odds_col': 'odds',
        'result_col': 'status',
        'status_col': 'status',
        'clv_col': None,
        'mode_col': None,
        'open_odds_col': 'odds',
        'close_odds_col': None,
        'settled_statuses': ("won", "lost"),
        'win_results': ("won",),
        'loss_results': ("lost",),
    },
}


def _compute_stats(bets: List[Dict]) -> Dict[str, Any]:
    if not bets:
        return {
            'total_bets': 0, 'wins': 0, 'losses': 0,
            'roi_pct': 0.0, 'hit_rate': 0.0, 'avg_clv': 0.0,
            'profit_units': 0.0, 'avg_odds': 0.0, 'score': 0.0,
        }

    wins = sum(1 for b in bets if b['is_win'])
    losses = sum(1 for b in bets if b['is_loss'])
    total = wins + losses
    if total == 0:
        return {
            'total_bets': 0, 'wins': 0, 'losses': 0,
            'roi_pct': 0.0, 'hit_rate': 0.0, 'avg_clv': 0.0,
            'profit_units': 0.0, 'avg_odds': 0.0, 'score': 0.0,
        }

    profit = sum((b['odds'] - 1) for b in bets if b['is_win']) + sum(-1 for b in bets if b['is_loss'])
    roi = (profit / total) * 100 if total > 0 else 0.0
    hit_rate = (wins / total) * 100 if total > 0 else 0.0
    clv_values = [b['clv'] for b in bets if b['clv'] is not None]
    avg_clv = sum(clv_values) / len(clv_values) if clv_values else 0.0
    avg_odds = sum(b['odds'] for b in bets) / len(bets) if bets else 0.0

    score = (
        ROI_WEIGHT * roi +
        CLV_WEIGHT * avg_clv +
        VOLUME_WEIGHT * math.log(max(total, 1)) * 10
    )

    return {
        'total_bets': total,
        'wins': wins,
        'losses': losses,
        'roi_pct': round(roi, 2),
        'hit_rate': round(hit_rate, 2),
        'avg_clv': round(avg_clv, 4),
        'profit_units': round(profit, 2),
        'avg_odds': round(avg_odds, 3),
        'score': round(score, 3),
    }


def _fetch_settled_bets(sport: str) -> List[Dict]:
    cfg = SPORTS_TABLE_MAP.get(sport)
    if not cfg:
        return []

    status_placeholders = ','.join(['%s'] * len(cfg['settled_statuses']))
    clv_expr = cfg['clv_col'] if cfg['clv_col'] else 'NULL'
    mode_filter = f"AND ({cfg['mode_col']} IS NULL OR {cfg['mode_col']} != 'TEST')" if cfg['mode_col'] else ''

    query = f"""
        SELECT {cfg['league_col']} as league,
               {cfg['market_col']} as market,
               {cfg['odds_col']}::real as odds,
               {cfg['result_col']} as result,
               {clv_expr} as clv
        FROM {cfg['table']}
        WHERE {cfg['status_col']} IN ({status_placeholders})
        {mode_filter}
        ORDER BY id DESC
    """

    try:
        rows = db_helper.execute(query, cfg['settled_statuses'], fetch='all') or []
    except Exception as e:
        logger.error(f"Error fetching {sport} bets: {e}")
        return []

    bets = []
    for row in rows:
        try:
            r = dict(row) if hasattr(row, '_mapping') else {
                'league': row[0], 'market': row[1], 'odds': row[2],
                'result': row[3], 'clv': row[4],
            }
            result_str = str(r.get('result', '')).lower().strip()
            odds_val = float(r.get('odds', 0) or 0)
            clv_val = float(r.get('clv') or 0) if r.get('clv') is not None else None
            league = str(r.get('league', '') or '').strip()
            market = str(r.get('market', '') or '').strip()

            if not league or not market or odds_val <= 1.0:
                continue
            if market.lower() in EXCLUDED_MARKETS:
                continue

            bets.append({
                'league': league,
                'market': market,
                'odds': odds_val,
                'clv': clv_val,
                'is_win': result_str in cfg['win_results'],
                'is_loss': result_str in cfg['loss_results'],
            })
        except Exception:
            continue

    return bets


def _group_bets(bets: List[Dict], key_func) -> Dict[str, List[Dict]]:
    groups = {}
    for b in bets:
        key = key_func(b)
        if key not in groups:
            groups[key] = []
        groups[key].append(b)
    return groups


def compute_all_stats(sport: str = 'football') -> Dict[str, Any]:
    logger.info(f"Computing learning stats for {sport}...")
    bets = _fetch_settled_bets(sport)
    logger.info(f"  Fetched {len(bets)} settled bets")

    if not bets:
        return {'league': {}, 'market': {}, 'league_market': {}, 'global': {}}

    results = {'league': {}, 'market': {}, 'league_market': {}, 'global': {}}

    for window_name, window_size in ROLLING_WINDOWS.items():
        window_bets = bets[:window_size] if window_size else bets

        results['global'][window_name] = _compute_stats(window_bets)

        league_groups = _group_bets(window_bets, lambda b: b['league'])
        for league, lbets in league_groups.items():
            if league not in results['league']:
                results['league'][league] = {}
            results['league'][league][window_name] = _compute_stats(lbets)

        market_groups = _group_bets(window_bets, lambda b: b['market'])
        for market, mbets in market_groups.items():
            if market not in results['market']:
                results['market'][market] = {}
            results['market'][market][window_name] = _compute_stats(mbets)

        lm_groups = _group_bets(window_bets, lambda b: f"{b['league']}|{b['market']}")
        for lm_key, lmbets in lm_groups.items():
            if lm_key not in results['league_market']:
                results['league_market'][lm_key] = {}
            results['league_market'][lm_key][window_name] = _compute_stats(lmbets)

    return results


def save_stats_to_db(sport: str = 'football') -> int:
    stats = compute_all_stats(sport)
    saved = 0
    now = datetime.utcnow()

    for dimension in ['league', 'market', 'league_market', 'global']:
        if dimension == 'global':
            items = {'global': stats['global']}
        else:
            items = stats[dimension]

        for dim_key, windows in items.items():
            for window_name, s in windows.items():
                if s['total_bets'] == 0:
                    continue

                if dimension == 'league_market' and '|' in dim_key:
                    parts = dim_key.split('|', 1)
                    label = f"{parts[0]} / {parts[1]}"
                elif dimension == 'global':
                    label = f"Global {sport}"
                else:
                    label = dim_key

                try:
                    db_helper.execute("""
                        INSERT INTO learning_stats
                            (sport, dimension, dimension_key, dimension_label, window_type,
                             total_bets, wins, losses, roi_pct, hit_rate, avg_clv,
                             profit_units, avg_odds, score, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sport, dimension, dimension_key, window_type)
                        DO UPDATE SET
                            dimension_label = EXCLUDED.dimension_label,
                            total_bets = EXCLUDED.total_bets,
                            wins = EXCLUDED.wins,
                            losses = EXCLUDED.losses,
                            roi_pct = EXCLUDED.roi_pct,
                            hit_rate = EXCLUDED.hit_rate,
                            avg_clv = EXCLUDED.avg_clv,
                            profit_units = EXCLUDED.profit_units,
                            avg_odds = EXCLUDED.avg_odds,
                            score = EXCLUDED.score,
                            updated_at = EXCLUDED.updated_at
                    """, (
                        sport, dimension, dim_key, label, window_name,
                        s['total_bets'], s['wins'], s['losses'],
                        s['roi_pct'], s['hit_rate'], s['avg_clv'],
                        s['profit_units'], s['avg_odds'], s['score'], now
                    ))
                    saved += 1
                except Exception as e:
                    logger.error(f"Error saving stats {dimension}/{dim_key}/{window_name}: {e}")

    logger.info(f"Saved {saved} learning_stats rows for {sport}")
    return saved


def get_league_scores(sport: str = 'football', window: str = 'all_time') -> Dict[str, float]:
    try:
        rows = db_helper.execute("""
            SELECT dimension_key, score
            FROM learning_stats
            WHERE sport = %s AND dimension = 'league' AND window_type = %s
            ORDER BY score DESC
        """, (sport, window), fetch='all') or []
        return {str(row[0]): float(row[1]) for row in rows}
    except Exception as e:
        logger.error(f"Error getting league scores: {e}")
        return {}


def get_market_scores(sport: str = 'football', window: str = 'all_time') -> Dict[str, float]:
    try:
        rows = db_helper.execute("""
            SELECT dimension_key, score
            FROM learning_stats
            WHERE sport = %s AND dimension = 'market' AND window_type = %s
            ORDER BY score DESC
        """, (sport, window), fetch='all') or []
        return {str(row[0]): float(row[1]) for row in rows}
    except Exception as e:
        logger.error(f"Error getting market scores: {e}")
        return {}


def get_league_market_score(sport: str, league: str, market: str, window: str = 'all_time') -> float:
    key = f"{league}|{market}"
    try:
        row = db_helper.execute("""
            SELECT score FROM learning_stats
            WHERE sport = %s AND dimension = 'league_market'
              AND dimension_key = %s AND window_type = %s
        """, (sport, key, window), fetch='one')
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0


def compute_bet_confidence(
    model_ev: float,
    league: str,
    market: str,
    sport: str = 'football',
    league_scores: Optional[Dict[str, float]] = None,
    market_scores: Optional[Dict[str, float]] = None,
) -> float:
    if league_scores is None:
        league_scores = get_league_scores(sport)
    if market_scores is None:
        market_scores = get_market_scores(sport)

    league_score = league_scores.get(league, 0.0)
    market_score = market_scores.get(market, 0.0)

    league_norm = max(0.1, min(2.0, 1.0 + league_score / 100.0))
    market_norm = max(0.1, min(2.0, 1.0 + market_score / 100.0))

    clv_score = get_league_market_score(sport, league, market)
    clv_norm = max(0.1, min(2.0, 1.0 + clv_score / 100.0))

    confidence = model_ev * league_norm * market_norm * clv_norm
    return round(confidence, 6)


def run_learning_update():
    total_saved = 0
    for sport in SPORTS_TABLE_MAP:
        try:
            saved = save_stats_to_db(sport)
            total_saved += saved
        except Exception as e:
            logger.error(f"Error computing stats for {sport}: {e}")
    logger.info(f"Learning update complete: {total_saved} total stats saved")
    return total_saved


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_learning_update()

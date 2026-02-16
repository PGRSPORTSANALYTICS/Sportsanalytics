"""
PGR Module 4 — League/Market Discovery + Gating (Self-Learning)
================================================================
Extends existing auto_promoter with richer scoring:
  score = ROI + CLV + stability - drawdown + sample_bonus + recency_bonus

Tracks by: league, market, odds band, confidence band, time-to-kickoff band.
Controls what gets published to dashboard and Discord.
"""

import math
import logging
import statistics
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from db_helper import db_helper
from pgr_models import EligibilityMap

logger = logging.getLogger(__name__)

PROMO_MIN_BETS = 80
PROMO_MIN_ROI = 3.0
PROMO_MIN_CLV = 0.0
PROMO_MIN_STABILITY = 0.3
DEMOTE_ROI_THRESHOLD = -2.0
DISABLE_ROI_THRESHOLD = -8.0
DISABLE_MIN_BETS = 150

SCORE_WEIGHTS = {
    'roi': 0.25,
    'clv': 0.20,
    'stability': 0.15,
    'drawdown': 0.10,
    'sample': 0.15,
    'recency': 0.15,
}


def _compute_stability(profit_series: List[float]) -> float:
    if len(profit_series) < 5:
        return 0.5
    cumulative = []
    s = 0
    for p in profit_series:
        s += p
        cumulative.append(s)
    if not cumulative or max(cumulative) == 0:
        return 0.5
    peak = cumulative[0]
    max_dd = 0
    for c in cumulative:
        if c > peak:
            peak = c
        dd = (peak - c) / max(peak, 1)
        if dd > max_dd:
            max_dd = dd
    stability = 1.0 - min(max_dd, 1.0)
    return round(stability, 3)


def _compute_drawdown_pct(profit_series: List[float]) -> float:
    if len(profit_series) < 5:
        return 0.0
    cumulative = []
    s = 0
    for p in profit_series:
        s += p
        cumulative.append(s)
    peak = cumulative[0]
    max_dd = 0
    for c in cumulative:
        if c > peak:
            peak = c
        dd_pct = ((peak - c) / max(peak, 1)) * 100
        if dd_pct > max_dd:
            max_dd = dd_pct
    return round(max_dd, 1)


def _compute_recency_bonus(profit_series: List[float], window: int = 20) -> float:
    if len(profit_series) < window:
        return 0.0
    recent = profit_series[-window:]
    recent_profit = sum(recent)
    total_profit = sum(profit_series)
    if total_profit == 0:
        return 0.0
    ratio = recent_profit / max(abs(total_profit), 1)
    return round(min(max(ratio, -1), 1) * 10, 2)


def compute_composite_score(roi: float, clv: float, stability: float,
                            drawdown: float, n_bets: int,
                            recency_bonus: float) -> float:
    roi_norm = min(max(roi, -20), 50)
    clv_norm = min(max(clv * 10, -10), 20)
    stability_norm = stability * 20
    drawdown_penalty = min(drawdown, 30)
    sample_bonus = math.log(max(n_bets, 1)) * 3

    score = (
        SCORE_WEIGHTS['roi'] * roi_norm +
        SCORE_WEIGHTS['clv'] * clv_norm +
        SCORE_WEIGHTS['stability'] * stability_norm -
        SCORE_WEIGHTS['drawdown'] * drawdown_penalty +
        SCORE_WEIGHTS['sample'] * sample_bonus +
        SCORE_WEIGHTS['recency'] * recency_bonus
    )
    return round(score, 2)


def get_eligibility_map(sport: str = 'football') -> List[EligibilityMap]:
    rows = db_helper.execute("""
        SELECT b.league_id, b.market_type,
               COUNT(*) as n,
               SUM(CASE WHEN b.result = 'won' THEN 1 ELSE 0 END) as wins,
               AVG(b.clv_pct) as avg_clv,
               AVG(b.ev_pct) as avg_ev,
               SUM(b.profit_loss) as total_profit
        FROM pgr_bet_lifecycle b
        WHERE b.sport = %s AND b.status = 'settled'
        GROUP BY b.league_id, b.market_type
        HAVING COUNT(*) >= 5
        ORDER BY COUNT(*) DESC
    """, (sport,), fetch='all') or []

    status_map = {}
    status_rows = db_helper.execute("""
        SELECT league_id, market_type, status, manual_override
        FROM league_market_status
        WHERE sport = %s
    """, (sport,), fetch='all') or []
    for sr in status_rows:
        status_map[f"{sr[0]}|{sr[1]}"] = {'status': sr[2], 'manual': sr[3]}

    results = []
    for r in rows:
        league_id = r[0]
        market_type = r[1]
        n = r[2]
        wins = r[3]
        avg_clv = float(r[4]) if r[4] else 0
        total_profit = float(r[6]) if r[6] else 0
        roi = (total_profit / n * 100) if n > 0 else 0

        profit_rows = db_helper.execute("""
            SELECT profit_loss FROM pgr_bet_lifecycle
            WHERE sport = %s AND league_id = %s AND market_type = %s
            AND status = 'settled' AND profit_loss IS NOT NULL
            ORDER BY settled_at ASC
        """, (sport, league_id, market_type), fetch='all') or []
        profit_series = [float(pr[0]) for pr in profit_rows]

        stability = _compute_stability(profit_series)
        drawdown = _compute_drawdown_pct(profit_series)
        recency = _compute_recency_bonus(profit_series)
        score = compute_composite_score(roi, avg_clv, stability, drawdown, n, recency)

        key = f"{league_id}|{market_type}"
        existing = status_map.get(key, {})
        current_status = existing.get('status', 'LEARNING_ONLY')

        can_publish = current_status == 'PRODUCTION'
        can_display = current_status in ('PRODUCTION', 'LEARNING_ONLY')

        results.append(EligibilityMap(
            sport=sport,
            league_id=league_id,
            market_type=market_type,
            status=current_status,
            total_bets=n,
            roi_pct=round(roi, 2),
            clv_avg=round(avg_clv, 3),
            stability_score=stability,
            drawdown_pct=drawdown,
            recency_bonus=recency,
            composite_score=score,
            can_publish=can_publish,
            can_display_dashboard=can_display,
        ))

    results.sort(key=lambda x: x.composite_score, reverse=True)
    return results


def run_enhanced_promotion(sport: str = 'football') -> Dict:
    eligibility = get_eligibility_map(sport)
    changes = {'promoted': [], 'demoted': [], 'disabled': [], 'unchanged': []}

    for e in eligibility:
        current = e.status
        new_status = current

        if current == 'LEARNING_ONLY':
            if (e.total_bets >= PROMO_MIN_BETS and
                    e.roi_pct > PROMO_MIN_ROI and
                    e.clv_avg >= PROMO_MIN_CLV and
                    e.stability_score >= PROMO_MIN_STABILITY):
                new_status = 'PRODUCTION'
                changes['promoted'].append({
                    'league': e.league_id, 'market': e.market_type,
                    'reason': f'Promoted: {e.total_bets} bets, ROI {e.roi_pct:.1f}%, CLV {e.clv_avg:.3f}, stability {e.stability_score:.2f}',
                    'score': e.composite_score,
                })
            elif e.total_bets >= DISABLE_MIN_BETS and e.roi_pct < DISABLE_ROI_THRESHOLD:
                new_status = 'DISABLED'
                changes['disabled'].append({
                    'league': e.league_id, 'market': e.market_type,
                    'reason': f'Disabled: ROI {e.roi_pct:.1f}% after {e.total_bets} bets',
                    'score': e.composite_score,
                })
            else:
                changes['unchanged'].append({
                    'league': e.league_id, 'market': e.market_type,
                    'score': e.composite_score,
                })

        elif current == 'PRODUCTION':
            if e.total_bets >= PROMO_MIN_BETS and (e.roi_pct < DEMOTE_ROI_THRESHOLD or
                    (e.clv_avg < -0.5 and e.total_bets >= 100)):
                new_status = 'LEARNING_ONLY'
                changes['demoted'].append({
                    'league': e.league_id, 'market': e.market_type,
                    'reason': f'Demoted: ROI {e.roi_pct:.1f}%, CLV {e.clv_avg:.3f}',
                    'score': e.composite_score,
                })
            else:
                changes['unchanged'].append({
                    'league': e.league_id, 'market': e.market_type,
                    'score': e.composite_score,
                })
        else:
            changes['unchanged'].append({
                'league': e.league_id, 'market': e.market_type,
                'score': e.composite_score,
            })

    return changes


def get_discovery_view(sport: str = 'football', min_bets: int = 10) -> Dict:
    eligibility = get_eligibility_map(sport)

    top_leagues = {}
    top_markets = {}
    promotion_candidates = []

    for e in eligibility:
        if e.total_bets < min_bets:
            continue

        if e.league_id not in top_leagues:
            top_leagues[e.league_id] = {'bets': 0, 'roi': 0, 'clv': 0, 'score': 0, 'count': 0}
        tl = top_leagues[e.league_id]
        tl['bets'] += e.total_bets
        tl['roi'] += e.roi_pct * e.total_bets
        tl['clv'] += e.clv_avg * e.total_bets
        tl['score'] = max(tl['score'], e.composite_score)
        tl['count'] += 1

        if e.market_type not in top_markets:
            top_markets[e.market_type] = {'bets': 0, 'roi': 0, 'clv': 0, 'score': 0, 'count': 0}
        tm = top_markets[e.market_type]
        tm['bets'] += e.total_bets
        tm['roi'] += e.roi_pct * e.total_bets
        tm['clv'] += e.clv_avg * e.total_bets
        tm['score'] = max(tm['score'], e.composite_score)
        tm['count'] += 1

        if (e.status == 'LEARNING_ONLY' and
                e.total_bets >= PROMO_MIN_BETS * 0.6 and
                e.roi_pct > 0):
            promotion_candidates.append({
                'league': e.league_id, 'market': e.market_type,
                'bets': e.total_bets, 'roi': e.roi_pct,
                'clv': e.clv_avg, 'stability': e.stability_score,
                'score': e.composite_score,
                'bets_needed': max(0, PROMO_MIN_BETS - e.total_bets),
            })

    for k in top_leagues:
        tl = top_leagues[k]
        tl['roi'] = round(tl['roi'] / tl['bets'], 2) if tl['bets'] > 0 else 0
        tl['clv'] = round(tl['clv'] / tl['bets'], 3) if tl['bets'] > 0 else 0

    for k in top_markets:
        tm = top_markets[k]
        tm['roi'] = round(tm['roi'] / tm['bets'], 2) if tm['bets'] > 0 else 0
        tm['clv'] = round(tm['clv'] / tm['bets'], 3) if tm['bets'] > 0 else 0

    sorted_leagues = sorted(top_leagues.items(), key=lambda x: x[1]['score'], reverse=True)
    sorted_markets = sorted(top_markets.items(), key=lambda x: x[1]['score'], reverse=True)
    promotion_candidates.sort(key=lambda x: x['score'], reverse=True)

    return {
        'top_leagues': [{'league': k, **v} for k, v in sorted_leagues[:20]],
        'top_markets': [{'market': k, **v} for k, v in sorted_markets[:20]],
        'promotion_candidates': promotion_candidates[:15],
        'total_combos': len(eligibility),
        'production_count': sum(1 for e in eligibility if e.status == 'PRODUCTION'),
        'learning_count': sum(1 for e in eligibility if e.status == 'LEARNING_ONLY'),
        'disabled_count': sum(1 for e in eligibility if e.status == 'DISABLED'),
    }


def is_publishable(sport: str, league_id: str, market_type: str) -> bool:
    row = db_helper.execute("""
        SELECT status, manual_override FROM league_market_status
        WHERE sport = %s AND league_id = %s AND market_type = %s
    """, (sport, league_id, market_type), fetch='one')
    if row:
        return row[0] == 'PRODUCTION'
    return False

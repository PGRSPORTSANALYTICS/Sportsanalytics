"""
PGR Module 3 — Edge/EV + CLV Intelligence
============================================
Core value computation: Edge%, EV%, CLV from closing snapshots.
Timing learning, sharpness signals, ranked bet candidates.

Edge% = (book_odds / fair_odds) - 1
EV% = (p * (book_odds - 1)) - (1 - p)
CLV% = (closing_odds / bet_odds) - 1
"""

import logging
import statistics
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from db_helper import db_helper
from pgr_models import EdgeResult, CLVRecord

logger = logging.getLogger(__name__)

DEFAULT_CLOSE_WINDOW_MINUTES = 5

TIME_BUCKETS = [
    ('0-1h', 0, 60),
    ('1-3h', 60, 180),
    ('3-6h', 180, 360),
    ('6-12h', 360, 720),
    ('12-24h', 720, 1440),
    ('24h+', 1440, 99999),
]


def compute_edge(book_odds: float, fair_odds: float) -> float:
    if fair_odds <= 1.0:
        return 0.0
    return round(((book_odds / fair_odds) - 1) * 100, 3)


def compute_ev(model_prob: float, book_odds: float) -> float:
    if model_prob <= 0 or book_odds <= 1.0:
        return 0.0
    ev = (model_prob * (book_odds - 1)) - (1 - model_prob)
    return round(ev * 100, 3)


def compute_clv(bet_odds: float, closing_odds: float) -> float:
    if bet_odds <= 1.0 or closing_odds <= 1.0:
        return 0.0
    return round(((closing_odds / bet_odds) - 1) * 100, 3)


def get_closing_odds(event_id: str, market_type: str, selection: str,
                     start_time_utc: datetime,
                     close_window_minutes: int = DEFAULT_CLOSE_WINDOW_MINUTES,
                     line: float = None) -> Optional[Tuple[float, datetime]]:
    close_start = start_time_utc - timedelta(minutes=close_window_minutes)
    close_end = start_time_utc + timedelta(minutes=2)

    query = """
        SELECT odds_decimal, timestamp_utc
        FROM pgr_odds_snapshots
        WHERE event_id = %s
        AND market_type = %s
        AND selection = %s
        AND timestamp_utc BETWEEN %s AND %s
    """
    params = [event_id, market_type, selection, close_start, close_end]

    if line is not None:
        query += " AND line = %s"
        params.append(line)

    query += " ORDER BY timestamp_utc DESC LIMIT 1"

    row = db_helper.execute(query, tuple(params), fetch='one')
    if row:
        return float(row[0]), row[1]
    return None


def get_closing_best_price(event_id: str, market_type: str, selection: str,
                           start_time_utc: datetime,
                           close_window_minutes: int = DEFAULT_CLOSE_WINDOW_MINUTES,
                           line: float = None) -> Optional[float]:
    close_start = start_time_utc - timedelta(minutes=close_window_minutes)
    close_end = start_time_utc + timedelta(minutes=2)

    query = """
        SELECT MAX(odds_decimal)
        FROM pgr_odds_snapshots
        WHERE event_id = %s
        AND market_type = %s
        AND selection = %s
        AND timestamp_utc BETWEEN %s AND %s
    """
    params = [event_id, market_type, selection, close_start, close_end]

    if line is not None:
        query += " AND line = %s"
        params.append(line)

    row = db_helper.execute(query, tuple(params), fetch='one')
    if row and row[0]:
        return float(row[0])
    return None


def compute_clv_for_bet(bet_id: int, event_id: str, market_type: str,
                        selection: str, bet_odds: float,
                        start_time_utc: datetime,
                        close_window: int = DEFAULT_CLOSE_WINDOW_MINUTES,
                        line: float = None) -> Optional[CLVRecord]:
    closing = get_closing_best_price(event_id, market_type, selection,
                                     start_time_utc, close_window, line)
    if closing is None:
        return None

    clv = compute_clv(bet_odds, closing)

    record = CLVRecord(
        bet_id=bet_id,
        event_id=event_id,
        market_type=market_type,
        selection=selection,
        bet_odds=bet_odds,
        closing_odds=closing,
        clv_pct=clv,
        close_window_minutes=close_window,
        close_timestamp_utc=start_time_utc,
    )

    try:
        db_helper.execute("""
            INSERT INTO pgr_clv_records
            (bet_lifecycle_id, event_id, market_type, selection,
             bet_odds, closing_odds, clv_pct, close_window_minutes, close_timestamp_utc)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            bet_id, event_id, market_type, selection,
            bet_odds, closing, clv, close_window, start_time_utc,
        ))
    except Exception as e:
        logger.error(f"Store CLV record error: {e}")

    return record


def classify_time_bucket(minutes_to_kick: float) -> str:
    for name, lo, hi in TIME_BUCKETS:
        if lo <= minutes_to_kick < hi:
            return name
    return '24h+'


def detect_sharpness(event_id: str, market_type: str, selection: str,
                     bet_odds: float, line: float = None) -> List[str]:
    tags = []

    rows = db_helper.execute("""
        SELECT odds_decimal, timestamp_utc, bookmaker
        FROM pgr_odds_snapshots
        WHERE event_id = %s AND market_type = %s AND selection = %s
        ORDER BY timestamp_utc ASC
    """, (event_id, market_type, selection), fetch='all') or []

    if len(rows) < 2:
        return tags

    first_odds = float(rows[0][0])
    last_odds = float(rows[-1][0])

    if last_odds < first_odds * 0.97:
        tags.append('steam_move_down')
    elif last_odds > first_odds * 1.03:
        tags.append('steam_move_up')

    if bet_odds > last_odds * 1.02:
        tags.append('got_best_price')
    elif bet_odds < last_odds * 0.98:
        tags.append('price_dropped')

    odds_values = [float(r[0]) for r in rows]
    if len(odds_values) > 3:
        recent = odds_values[-3:]
        if all(recent[i] < recent[i-1] for i in range(1, len(recent))):
            tags.append('consistent_shortening')
        elif all(recent[i] > recent[i-1] for i in range(1, len(recent))):
            tags.append('consistent_drifting')

    bookmakers_at_latest = {}
    for r in reversed(rows):
        bk = r[2]
        if bk not in bookmakers_at_latest:
            bookmakers_at_latest[bk] = float(r[0])
    if len(bookmakers_at_latest) > 2:
        vals = list(bookmakers_at_latest.values())
        spread = max(vals) - min(vals)
        avg = statistics.mean(vals)
        if avg > 0 and spread / avg > 0.05:
            tags.append('high_book_spread')

    return tags


def rank_candidates(candidates: List[EdgeResult], top_n: int = 20) -> List[EdgeResult]:
    for c in candidates:
        c.sharpness_tags = detect_sharpness(
            c.event_id, c.market_type, c.selection, c.book_odds
        )

    scored = []
    for c in candidates:
        score = (
            c.ev_pct * 0.35 +
            c.edge_pct * 0.25 +
            c.confidence * 50 * 0.20 +
            (c.expected_clv_pct or 0) * 0.10 +
            (10 if 'got_best_price' in c.sharpness_tags else 0) * 0.05 +
            (-10 if 'price_dropped' in c.sharpness_tags else 0) * 0.05
        )
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_n]]


def build_edge_results(event_id: str, home_team: str, away_team: str,
                       league_id: str, league_name: str,
                       market_states: List[Dict],
                       fair_odds_map: Dict[str, 'FairOddsResult'],
                       start_time_utc: datetime,
                       gating_status: str = 'LEARNING_ONLY') -> List[EdgeResult]:
    results = []
    now = datetime.now(timezone.utc)
    minutes_to_kick = (start_time_utc.replace(tzinfo=timezone.utc) - now).total_seconds() / 60 if start_time_utc else 0
    time_bucket = classify_time_bucket(max(0, minutes_to_kick))

    for ms in market_states:
        mkt = ms.get('market_type', '')
        sel = ms.get('selection', '')
        line = ms.get('line')
        best_price = ms.get('best_price', 0)
        best_bk = ms.get('best_bookmaker', '')
        disp = ms.get('dispersion', 0)

        fo_key = f"{mkt}|{sel}|{line}"
        fo = fair_odds_map.get(fo_key)
        if not fo:
            fo_key_simple = f"{mkt}|{sel}"
            fo = fair_odds_map.get(fo_key_simple)
        if not fo or fo.fair_odds <= 1.0:
            continue

        edge = compute_edge(best_price, fo.fair_odds)
        ev = compute_ev(fo.calibrated_prob or fo.model_prob, best_price)

        if ev <= 0:
            continue

        result = EdgeResult(
            event_id=event_id,
            home_team=home_team,
            away_team=away_team,
            league_id=league_id,
            league_name=league_name,
            market_type=mkt,
            selection=sel,
            line=line,
            book_odds=best_price,
            bookmaker=best_bk,
            fair_odds=fo.fair_odds,
            model_prob=fo.calibrated_prob or fo.model_prob,
            edge_pct=edge,
            ev_pct=ev,
            confidence=fo.confidence,
            confidence_badge=fo.confidence_badge,
            timing_bucket=time_bucket,
            start_time_utc=start_time_utc,
            volatility=fo.volatility,
            gating_status=gating_status,
        )
        results.append(result)

    return results


def update_timing_stats(sport: str, league_id: str, market_type: str,
                        time_bucket: str, is_win: bool, clv: float, ev: float):
    try:
        db_helper.execute("""
            INSERT INTO pgr_timing_stats
            (sport, league_id, market_type, time_bucket, total_bets, wins, roi_pct, avg_clv, avg_ev)
            VALUES (%s,%s,%s,%s, 1, %s, 0, %s, %s)
            ON CONFLICT (sport, league_id, market_type, time_bucket)
            DO UPDATE SET
                total_bets = pgr_timing_stats.total_bets + 1,
                wins = pgr_timing_stats.wins + %s,
                avg_clv = (pgr_timing_stats.avg_clv * pgr_timing_stats.total_bets + %s)
                          / (pgr_timing_stats.total_bets + 1),
                avg_ev = (pgr_timing_stats.avg_ev * pgr_timing_stats.total_bets + %s)
                         / (pgr_timing_stats.total_bets + 1),
                updated_at = NOW()
        """, (
            sport, league_id, market_type, time_bucket,
            1 if is_win else 0, clv, ev,
            1 if is_win else 0, clv, ev,
        ))
    except Exception as e:
        logger.error(f"Update timing stats error: {e}")


def get_timing_stats(sport: str = 'football',
                     league_id: str = None,
                     market_type: str = None) -> List[Dict]:
    query = "SELECT sport, league_id, market_type, time_bucket, total_bets, wins, roi_pct, avg_clv, avg_ev FROM pgr_timing_stats WHERE sport = %s"
    params = [sport]
    if league_id:
        query += " AND league_id = %s"
        params.append(league_id)
    if market_type:
        query += " AND market_type = %s"
        params.append(market_type)
    query += " ORDER BY total_bets DESC"

    rows = db_helper.execute(query, tuple(params), fetch='all') or []
    return [
        {
            'sport': r[0], 'league_id': r[1], 'market_type': r[2],
            'time_bucket': r[3], 'total_bets': r[4], 'wins': r[5],
            'roi_pct': float(r[6]) if r[6] else 0,
            'avg_clv': float(r[7]) if r[7] else 0,
            'avg_ev': float(r[8]) if r[8] else 0,
        }
        for r in rows
    ]


def get_clv_analytics(sport: str = 'football', market_type: str = None,
                      league_id: str = None, limit: int = 200) -> Dict:
    query = """
        SELECT c.market_type, c.bet_odds, c.closing_odds, c.clv_pct,
               b.league_id, b.selection, b.result, b.confidence_badge,
               c.close_window_minutes
        FROM pgr_clv_records c
        JOIN pgr_bet_lifecycle b ON c.bet_lifecycle_id = b.id
        WHERE b.sport = %s
    """
    params = [sport]
    if market_type:
        query += " AND c.market_type = %s"
        params.append(market_type)
    if league_id:
        query += " AND b.league_id = %s"
        params.append(league_id)
    query += " ORDER BY c.created_at DESC LIMIT %s"
    params.append(limit)

    rows = db_helper.execute(query, tuple(params), fetch='all') or []

    if not rows:
        return {'total': 0, 'avg_clv': 0, 'positive_pct': 0, 'records': []}

    clvs = [float(r[3]) for r in rows]
    positive = sum(1 for c in clvs if c > 0)

    by_market = {}
    by_league = {}
    records = []
    for r in rows:
        mkt = r[0]
        clv_val = float(r[3])
        league = r[4]

        if mkt not in by_market:
            by_market[mkt] = []
        by_market[mkt].append(clv_val)

        if league not in by_league:
            by_league[league] = []
        by_league[league].append(clv_val)

        records.append({
            'market_type': mkt, 'bet_odds': float(r[1]),
            'closing_odds': float(r[2]), 'clv_pct': clv_val,
            'league_id': league, 'selection': r[5],
            'result': r[6], 'confidence': r[7],
        })

    return {
        'total': len(rows),
        'avg_clv': round(statistics.mean(clvs), 3) if clvs else 0,
        'positive_pct': round(positive / len(clvs) * 100, 1) if clvs else 0,
        'by_market': {m: {'avg': round(statistics.mean(v), 3), 'count': len(v)} for m, v in by_market.items()},
        'by_league': {l: {'avg': round(statistics.mean(v), 3), 'count': len(v)} for l, v in by_league.items()},
        'records': records[:50],
    }

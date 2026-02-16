"""
PGR Module 5 — Bet Lifecycle + Audit + Reporting
==================================================
State machine: candidate → published → placed → settled
Full audit logging. Weekly report generation.
Duplicate prevention. Daily exposure limits.
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from db_helper import db_helper
from pgr_models import BetLifecycle, AuditEntry, WeeklyReport

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    'candidate': ['published', 'voided'],
    'published': ['placed', 'voided'],
    'placed': ['settled', 'voided'],
    'settled': [],
    'voided': [],
}

MAX_DAILY_BETS = {
    'moneyline': 10,
    'totals': 10,
    'asian_handicap': 5,
    'btts': 8,
    'corners': 20,
    'cards': 20,
    'double_chance': 5,
    'draw_no_bet': 5,
}
MAX_DAILY_TOTAL = 50


def _log_audit(bet_id: int, action: str, old_status: str = None,
               new_status: str = None, details: Dict = None, source: str = 'system'):
    try:
        db_helper.execute("""
            INSERT INTO pgr_audit_log
            (bet_lifecycle_id, action, old_status, new_status, details, timestamp_utc, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            bet_id, action, old_status, new_status,
            json.dumps(details or {}), datetime.now(timezone.utc), source,
        ))
    except Exception as e:
        logger.error(f"Audit log error: {e}")


def create_candidate(bet: BetLifecycle) -> Optional[int]:
    existing = db_helper.execute("""
        SELECT id FROM pgr_bet_lifecycle
        WHERE event_id = %s AND market_type = %s AND selection = %s
        AND COALESCE(line, -999) = COALESCE(%s, -999)
        AND bookmaker = %s
    """, (bet.event_id, bet.market_type, bet.selection, bet.line, bet.bookmaker), fetch='one')

    if existing:
        logger.info(f"Duplicate prevented: {bet.event_id}/{bet.market_type}/{bet.selection}")
        return None

    today_count = db_helper.execute("""
        SELECT COUNT(*) FROM pgr_bet_lifecycle
        WHERE sport = %s AND DATE(created_at) = CURRENT_DATE
        AND status NOT IN ('voided')
    """, (bet.sport,), fetch='one')
    if today_count and today_count[0] >= MAX_DAILY_TOTAL:
        logger.warning(f"Daily total limit reached: {today_count[0]}/{MAX_DAILY_TOTAL}")
        return None

    market_count = db_helper.execute("""
        SELECT COUNT(*) FROM pgr_bet_lifecycle
        WHERE sport = %s AND market_type = %s AND DATE(created_at) = CURRENT_DATE
        AND status NOT IN ('voided')
    """, (bet.sport, bet.market_type), fetch='one')
    market_limit = MAX_DAILY_BETS.get(bet.market_type, 10)
    if market_count and market_count[0] >= market_limit:
        logger.warning(f"Daily market limit for {bet.market_type}: {market_count[0]}/{market_limit}")
        return None

    request_id = bet.request_id or str(uuid.uuid4())[:12]

    try:
        row = db_helper.execute("""
            INSERT INTO pgr_bet_lifecycle
            (event_id, home_team, away_team, league_id, league_name, sport,
             market_type, selection, line, odds_decimal, bookmaker,
             fair_odds, model_prob, edge_pct, ev_pct,
             confidence, confidence_badge, status, gating_status,
             stake_units, start_time_utc, model_version, request_id,
             tags, notes, expected_clv_pct, volatility, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            RETURNING id
        """, (
            bet.event_id, bet.home_team, bet.away_team,
            bet.league_id, bet.league_name, bet.sport,
            bet.market_type, bet.selection, bet.line,
            bet.odds_decimal, bet.bookmaker,
            bet.fair_odds, bet.model_prob, bet.edge_pct, bet.ev_pct,
            bet.confidence, bet.confidence_badge,
            'candidate', bet.gating_status,
            bet.stake_units, bet.start_time_utc,
            bet.model_version, request_id,
            bet.tags, bet.notes,
            bet.expected_clv_pct, bet.volatility,
        ), fetch='one')

        bet_id = row[0] if row else None
        if bet_id:
            _log_audit(bet_id, 'created', None, 'candidate', {
                'odds': bet.odds_decimal, 'ev': bet.ev_pct,
                'edge': bet.edge_pct, 'confidence': bet.confidence,
                'model_version': bet.model_version,
            })
        return bet_id
    except Exception as e:
        logger.error(f"Create candidate error: {e}")
        return None


def transition(bet_id: int, new_status: str, details: Dict = None,
               source: str = 'system') -> bool:
    row = db_helper.execute("""
        SELECT status FROM pgr_bet_lifecycle WHERE id = %s
    """, (bet_id,), fetch='one')
    if not row:
        logger.error(f"Bet {bet_id} not found")
        return False

    old_status = row[0]
    allowed = VALID_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        logger.error(f"Invalid transition: {old_status} -> {new_status}")
        return False

    ts_field = {
        'published': 'published_at',
        'placed': 'placed_at',
        'settled': 'settled_at',
    }.get(new_status)

    now = datetime.now(timezone.utc)

    try:
        if ts_field:
            db_helper.execute(f"""
                UPDATE pgr_bet_lifecycle
                SET status = %s, {ts_field} = %s
                WHERE id = %s
            """, (new_status, now, bet_id))
        else:
            db_helper.execute("""
                UPDATE pgr_bet_lifecycle SET status = %s WHERE id = %s
            """, (new_status, bet_id))

        _log_audit(bet_id, f'transition_{new_status}', old_status, new_status, details, source)
        return True
    except Exception as e:
        logger.error(f"Transition error: {e}")
        return False


def settle_bet(bet_id: int, result: str, profit_loss: float,
               closing_odds: float = None, clv_pct: float = None) -> bool:
    row = db_helper.execute("""
        SELECT status FROM pgr_bet_lifecycle WHERE id = %s
    """, (bet_id,), fetch='one')
    if not row:
        return False
    if row[0] not in ('placed', 'published', 'candidate'):
        return False

    try:
        db_helper.execute("""
            UPDATE pgr_bet_lifecycle
            SET status = 'settled', result = %s, profit_loss = %s,
                closing_odds = %s, clv_pct = %s, settled_at = NOW()
            WHERE id = %s
        """, (result, profit_loss, closing_odds, clv_pct, bet_id))

        _log_audit(bet_id, 'settled', row[0], 'settled', {
            'result': result, 'profit_loss': profit_loss,
            'closing_odds': closing_odds, 'clv_pct': clv_pct,
        })
        return True
    except Exception as e:
        logger.error(f"Settle error: {e}")
        return False


def get_bet_history(bet_id: int) -> List[Dict]:
    rows = db_helper.execute("""
        SELECT action, old_status, new_status, details, timestamp_utc, source
        FROM pgr_audit_log
        WHERE bet_lifecycle_id = %s
        ORDER BY timestamp_utc ASC
    """, (bet_id,), fetch='all') or []

    return [
        {
            'action': r[0], 'old_status': r[1], 'new_status': r[2],
            'details': r[3] if isinstance(r[3], dict) else json.loads(r[3]) if r[3] else {},
            'timestamp': r[4].isoformat() if r[4] else None,
            'source': r[5],
        }
        for r in rows
    ]


def get_lifecycle_stats(sport: str = 'football', days: int = 30) -> Dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    row = db_helper.execute("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'candidate') as candidates,
            COUNT(*) FILTER (WHERE status = 'published') as published,
            COUNT(*) FILTER (WHERE status = 'placed') as placed,
            COUNT(*) FILTER (WHERE status = 'settled') as settled,
            COUNT(*) FILTER (WHERE status = 'voided') as voided,
            COUNT(*) FILTER (WHERE result = 'won') as wins,
            COUNT(*) FILTER (WHERE result = 'lost') as losses,
            COALESCE(SUM(profit_loss) FILTER (WHERE status = 'settled'), 0) as profit,
            COALESCE(AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL), 0) as avg_clv,
            COALESCE(AVG(ev_pct), 0) as avg_ev,
            COALESCE(AVG(odds_decimal) FILTER (WHERE status = 'settled'), 0) as avg_odds
        FROM pgr_bet_lifecycle
        WHERE sport = %s AND created_at >= %s
    """, (sport, cutoff), fetch='one')

    if not row:
        return {}

    settled = row[3] or 0
    wins = row[5] or 0
    hit_rate = (wins / settled * 100) if settled > 0 else 0
    profit = float(row[7])
    roi = (profit / settled * 100) if settled > 0 else 0

    return {
        'candidates': row[0], 'published': row[1], 'placed': row[2],
        'settled': settled, 'voided': row[4],
        'wins': wins, 'losses': row[6], 'hit_rate': round(hit_rate, 1),
        'profit_units': round(profit, 2), 'roi': round(roi, 2),
        'avg_clv': round(float(row[8]), 3),
        'avg_ev': round(float(row[9]), 2),
        'avg_odds': round(float(row[10]), 3),
    }


def generate_weekly_report(week_start: datetime = None) -> WeeklyReport:
    if week_start is None:
        today = datetime.now(timezone.utc).date()
        week_start_date = today - timedelta(days=today.weekday())
    else:
        week_start_date = week_start.date() if isinstance(week_start, datetime) else week_start

    week_end_date = week_start_date + timedelta(days=6)

    rows = db_helper.execute("""
        SELECT market_type, league_id, result, profit_loss, clv_pct,
               ev_pct, odds_decimal, confidence_badge
        FROM pgr_bet_lifecycle
        WHERE status = 'settled'
        AND settled_at::date BETWEEN %s AND %s
    """, (week_start_date, week_end_date), fetch='all') or []

    report = WeeklyReport(
        week_start=str(week_start_date),
        week_end=str(week_end_date),
    )

    if not rows:
        return report

    by_market = {}
    by_league = {}

    for r in rows:
        mkt = r[0]
        league = r[1]
        result = r[2]
        pl = float(r[3]) if r[3] else 0
        clv = float(r[4]) if r[4] else 0
        ev = float(r[5]) if r[5] else 0
        odds = float(r[6]) if r[6] else 0

        report.total_bets += 1
        report.settled += 1
        report.profit_units += pl
        report.avg_clv += clv
        report.avg_ev += ev
        report.avg_odds += odds

        if result == 'won':
            report.wins += 1
        elif result == 'lost':
            report.losses += 1

        if mkt not in by_market:
            by_market[mkt] = {'bets': 0, 'wins': 0, 'profit': 0, 'clv': 0}
        by_market[mkt]['bets'] += 1
        by_market[mkt]['profit'] += pl
        by_market[mkt]['clv'] += clv
        if result == 'won':
            by_market[mkt]['wins'] += 1

        if league not in by_league:
            by_league[league] = {'bets': 0, 'wins': 0, 'profit': 0}
        by_league[league]['bets'] += 1
        by_league[league]['profit'] += pl
        if result == 'won':
            by_league[league]['wins'] += 1

    n = report.total_bets
    if n > 0:
        report.hit_rate = round(report.wins / n * 100, 1)
        report.roi_pct = round(report.profit_units / n * 100, 2)
        report.avg_clv = round(report.avg_clv / n, 3)
        report.avg_ev = round(report.avg_ev / n, 2)
        report.avg_odds = round(report.avg_odds / n, 3)
        report.profit_units = round(report.profit_units, 2)

    for m in by_market:
        bm = by_market[m]
        bm['roi'] = round(bm['profit'] / bm['bets'] * 100, 2) if bm['bets'] > 0 else 0
        bm['clv'] = round(bm['clv'] / bm['bets'], 3) if bm['bets'] > 0 else 0

    best_market = max(by_market.items(), key=lambda x: x[1]['profit'], default=('', {'profit': 0}))
    worst_market = min(by_market.items(), key=lambda x: x[1]['profit'], default=('', {'profit': 0}))
    top_league = max(by_league.items(), key=lambda x: x[1]['profit'], default=('', {'profit': 0}))

    report.best_market = best_market[0]
    report.worst_market = worst_market[0]
    report.top_league = top_league[0]
    report.by_market = by_market
    report.by_league = by_league

    try:
        db_helper.execute("""
            INSERT INTO pgr_weekly_reports (week_start, week_end, report_data)
            VALUES (%s, %s, %s)
            ON CONFLICT (week_start) DO UPDATE SET
                report_data = EXCLUDED.report_data, created_at = NOW()
        """, (week_start_date, week_end_date, json.dumps(report.model_dump())))
    except Exception as e:
        logger.error(f"Save weekly report error: {e}")

    return report


def get_bets_feed(status: str = None, gating_status: str = None,
                  sport: str = 'football', market_type: str = None,
                  league_id: str = None, min_ev: float = None,
                  min_confidence: float = None, sort: str = 'newest',
                  limit: int = 30, offset: int = 0,
                  show_learning: bool = False) -> Dict:
    query = """
        SELECT id, event_id, home_team, away_team, league_id, league_name,
               sport, market_type, selection, line, odds_decimal, bookmaker,
               fair_odds, model_prob, edge_pct, ev_pct,
               confidence, confidence_badge, status, gating_status,
               result, profit_loss, closing_odds, clv_pct,
               start_time_utc, created_at, tags, notes, expected_clv_pct, volatility
        FROM pgr_bet_lifecycle
        WHERE sport = %s
    """
    count_query = "SELECT COUNT(*) FROM pgr_bet_lifecycle WHERE sport = %s"
    params = [sport]
    count_params = [sport]

    if not show_learning:
        query += " AND gating_status = 'PRODUCTION'"
        count_query += " AND gating_status = 'PRODUCTION'"
    if status:
        query += " AND status = %s"
        count_query += " AND status = %s"
        params.append(status)
        count_params.append(status)
    if gating_status:
        query += " AND gating_status = %s"
        count_query += " AND gating_status = %s"
        params.append(gating_status)
        count_params.append(gating_status)
    if market_type:
        query += " AND market_type = %s"
        count_query += " AND market_type = %s"
        params.append(market_type)
        count_params.append(market_type)
    if league_id:
        query += " AND league_id = %s"
        count_query += " AND league_id = %s"
        params.append(league_id)
        count_params.append(league_id)
    if min_ev is not None:
        query += " AND ev_pct >= %s"
        count_query += " AND ev_pct >= %s"
        params.append(min_ev)
        count_params.append(min_ev)
    if min_confidence is not None:
        query += " AND confidence >= %s"
        count_query += " AND confidence >= %s"
        params.append(min_confidence)
        count_params.append(min_confidence)

    sort_map = {
        'newest': 'created_at DESC',
        'kickoff': 'start_time_utc ASC NULLS LAST',
        'ev': 'ev_pct DESC',
        'edge': 'edge_pct DESC',
        'odds': 'odds_decimal DESC',
        'confidence': 'confidence DESC',
    }
    query += f" ORDER BY {sort_map.get(sort, 'created_at DESC')}"
    query += " LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    total_row = db_helper.execute(count_query, tuple(count_params), fetch='one')
    total = total_row[0] if total_row else 0

    rows = db_helper.execute(query, tuple(params), fetch='all') or []

    bets = []
    for r in rows:
        tags = r[26] if isinstance(r[26], list) else []
        bets.append({
            'id': r[0], 'event_id': r[1],
            'home_team': r[2], 'away_team': r[3],
            'league_id': r[4], 'league_name': r[5],
            'sport': r[6], 'market_type': r[7],
            'selection': r[8], 'line': r[9],
            'odds_decimal': float(r[10]),
            'bookmaker': r[11],
            'fair_odds': float(r[12]),
            'model_prob': round(float(r[13]), 4),
            'edge_pct': round(float(r[14]), 2),
            'ev_pct': round(float(r[15]), 2),
            'confidence': round(float(r[16]), 3),
            'confidence_badge': r[17],
            'status': r[18], 'gating_status': r[19],
            'result': r[20],
            'profit_loss': round(float(r[21]), 2) if r[21] else None,
            'closing_odds': float(r[22]) if r[22] else None,
            'clv_pct': round(float(r[23]), 2) if r[23] else None,
            'start_time_utc': r[24].isoformat() if r[24] else None,
            'created_at': r[25].isoformat() if r[25] else None,
            'tags': tags,
            'notes': r[27] or '',
            'expected_clv_pct': round(float(r[28]), 2) if r[28] else None,
            'volatility': round(float(r[29]), 2) if r[29] else None,
        })

    return {
        'bets': bets,
        'total': total,
        'limit': limit,
        'offset': offset,
    }

"""
PGR Module 6 — API Router
===========================
All endpoints for the PGR dashboard + admin.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException

from pgr_odds_ingestion import (
    get_latest_market_state, get_odds_history, get_upcoming_events, run_ingestion_cycle
)
from pgr_fair_odds_engine import compute_fair_odds
from pgr_edge_clv import get_clv_analytics, get_timing_stats, compute_edge, compute_ev
from pgr_gating import get_eligibility_map, get_discovery_view, is_publishable
from pgr_lifecycle import (
    get_bets_feed, get_lifecycle_stats, get_bet_history, generate_weekly_report
)
from db_helper import db_helper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pgr", tags=["PGR Analytics"])

ADMIN_KEY = os.getenv('ADMIN_API_KEY', '')


def _check_admin(key: str):
    if not ADMIN_KEY or key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")


@router.get("/health")
async def pgr_health():
    try:
        row = db_helper.execute("SELECT COUNT(*) FROM pgr_bet_lifecycle", fetch='one')
        bets = row[0] if row else 0
        snap_row = db_helper.execute("SELECT COUNT(*) FROM pgr_odds_snapshots", fetch='one')
        snaps = snap_row[0] if snap_row else 0
        return {
            'status': 'ok',
            'module': 'pgr_analytics_v2',
            'bets_tracked': bets,
            'odds_snapshots': snaps,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/bets")
async def pgr_bets_feed(
    status: Optional[str] = None,
    gating: Optional[str] = None,
    sport: str = 'football',
    market: Optional[str] = None,
    league: Optional[str] = None,
    min_ev: Optional[float] = None,
    min_confidence: Optional[float] = None,
    sort: str = 'newest',
    limit: int = 30,
    offset: int = 0,
    show_learning: bool = False,
):
    try:
        return get_bets_feed(
            status=status, gating_status=gating, sport=sport,
            market_type=market, league_id=league,
            min_ev=min_ev, min_confidence=min_confidence,
            sort=sort, limit=limit, offset=offset,
            show_learning=show_learning,
        )
    except Exception as e:
        logger.error(f"PGR bets feed error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bets/{bet_id}/history")
async def pgr_bet_audit(bet_id: int):
    try:
        return get_bet_history(bet_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def pgr_stats(sport: str = 'football', days: int = 30):
    try:
        return get_lifecycle_stats(sport=sport, days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-state/{event_id}")
async def pgr_market_state(event_id: str):
    try:
        states = get_latest_market_state(event_id)
        if not states:
            raise HTTPException(status_code=404, detail="No market data")
        return {'event_id': event_id, 'markets': states}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/odds-history/{event_id}")
async def pgr_odds_history(event_id: str,
                           market: Optional[str] = None,
                           selection: Optional[str] = None):
    try:
        history = get_odds_history(event_id, market_type=market, selection=selection)
        return {'event_id': event_id, 'history': history, 'count': len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/upcoming")
async def pgr_upcoming(hours: int = 48):
    try:
        events = get_upcoming_events(hours_ahead=hours)
        return {'events': events, 'count': len(events)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clv")
async def pgr_clv(sport: str = 'football',
                  market: Optional[str] = None,
                  league: Optional[str] = None,
                  limit: int = 200):
    try:
        return get_clv_analytics(sport=sport, market_type=market,
                                 league_id=league, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timing")
async def pgr_timing(sport: str = 'football',
                     league: Optional[str] = None,
                     market: Optional[str] = None):
    try:
        stats = get_timing_stats(sport=sport, league_id=league, market_type=market)
        return {'stats': stats, 'count': len(stats)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discovery")
async def pgr_discovery(sport: str = 'football', min_bets: int = 10):
    try:
        return get_discovery_view(sport=sport, min_bets=min_bets)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/eligibility")
async def pgr_eligibility(sport: str = 'football'):
    try:
        items = get_eligibility_map(sport=sport)
        return [e.model_dump() for e in items]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weekly-report")
async def pgr_weekly_report():
    try:
        report = generate_weekly_report()
        return report.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weekly-reports")
async def pgr_weekly_reports_list(limit: int = 12):
    try:
        rows = db_helper.execute("""
            SELECT week_start, week_end, report_data FROM pgr_weekly_reports
            ORDER BY week_start DESC LIMIT %s
        """, (limit,), fetch='all') or []
        return [
            {
                'week_start': str(r[0]),
                'week_end': str(r[1]),
                'data': r[2] if isinstance(r[2], dict) else {},
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/ingest")
async def admin_ingest(api_key: str = Query(...), sports_limit: int = 5):
    _check_admin(api_key)
    try:
        from pgr_odds_ingestion import SPORT_KEYS
        result = run_ingestion_cycle(sport_keys=SPORT_KEYS[:sports_limit])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/gating/override")
async def admin_gating_override(
    api_key: str = Query(...),
    sport: str = Query(...),
    league: str = Query(...),
    market: str = Query(...),
    status: str = Query(...),
    reason: str = Query(default='Manual override'),
):
    _check_admin(api_key)
    if status not in ('PRODUCTION', 'LEARNING_ONLY', 'DISABLED'):
        raise HTTPException(status_code=400, detail="Invalid status")
    try:
        db_helper.execute("""
            INSERT INTO league_market_status
            (sport, league_id, market_type, status, manual_override, manual_override_reason,
             promotion_reason, updated_at)
            VALUES (%s,%s,%s,%s,TRUE,%s,%s,NOW())
            ON CONFLICT (sport, league_id, market_type)
            DO UPDATE SET status = EXCLUDED.status,
                manual_override = TRUE,
                manual_override_reason = EXCLUDED.manual_override_reason,
                promotion_reason = EXCLUDED.promotion_reason,
                updated_at = NOW()
        """, (sport, league, market, status, reason, f'Manual: {reason}'))
        return {'ok': True, 'league': league, 'market': market, 'status': status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/audit")
async def admin_audit_log(api_key: str = Query(...),
                          bet_id: Optional[int] = None,
                          limit: int = 100):
    _check_admin(api_key)
    try:
        if bet_id:
            return get_bet_history(bet_id)
        rows = db_helper.execute("""
            SELECT a.id, a.bet_lifecycle_id, a.action, a.old_status,
                   a.new_status, a.details, a.timestamp_utc, a.source
            FROM pgr_audit_log a
            ORDER BY a.timestamp_utc DESC LIMIT %s
        """, (limit,), fetch='all') or []
        return [
            {
                'id': r[0], 'bet_id': r[1], 'action': r[2],
                'old_status': r[3], 'new_status': r[4],
                'details': r[5] if isinstance(r[5], dict) else {},
                'timestamp': r[6].isoformat() if r[6] else None,
                'source': r[7],
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

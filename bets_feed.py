"""
Bets Feed API Router
====================
Unified endpoint for serving all bets across sports to the website frontend.
Reads from football_opportunities, basketball_predictions, and player_props tables.

GET /api/bets - Main feed with filters, sorting, pagination, caching
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import OrderedDict

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from db_helper import db_helper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Bets Feed"])


class BetCard(BaseModel):
    id: str
    sport: str
    league: str
    match: str
    home_team: str
    away_team: str
    market: str
    selection: str
    odds: float
    kickoff: Optional[str] = None
    kickoff_epoch: Optional[int] = None
    status: str
    outcome: Optional[str] = None
    profit_units: Optional[float] = None
    ev_pct: Optional[float] = None
    confidence: Optional[float] = None
    trust_level: Optional[str] = None
    model_prob: Optional[float] = None
    actual_score: Optional[str] = None
    bookmaker: Optional[str] = None
    open_odds: Optional[float] = None
    close_odds: Optional[float] = None
    clv_pct: Optional[float] = None
    created_at: Optional[str] = None
    bet_category: Optional[str] = None
    is_top_pick: bool = False
    is_premium: bool = False


class BetsFeedResponse(BaseModel):
    bets: List[BetCard]
    total: int
    limit: int
    offset: int
    filters_applied: Dict[str, Any]
    generated_at: str


_cache: Dict[str, Any] = OrderedDict()
CACHE_TTL = 60
CACHE_MAX_SIZE = 100


def _get_cached(key: str) -> Optional[Any]:
    if key in _cache:
        entry = _cache[key]
        if time.time() - entry["ts"] < CACHE_TTL:
            _cache.move_to_end(key)
            return entry["data"]
        else:
            del _cache[key]
    return None


def _set_cached(key: str, data: Any):
    if len(_cache) >= CACHE_MAX_SIZE:
        _cache.popitem(last=False)
    _cache[key] = {"data": data, "ts": time.time()}


def _normalize_status(raw_status: Optional[str], raw_outcome: Optional[str] = None) -> str:
    s = (raw_outcome or raw_status or "").strip().lower()
    if s in ("won", "win"):
        return "won"
    if s in ("lost", "loss"):
        return "lost"
    if s in ("void", "voided", "cancelled"):
        return "void"
    if s in ("pending", ""):
        return "upcoming"
    if s in ("live", "in_play"):
        return "live"
    return "upcoming"


def _compute_profit_units(outcome: str, odds: float) -> Optional[float]:
    if outcome in ("won", "win"):
        return round(odds - 1, 2)
    elif outcome in ("lost", "loss"):
        return -1.0
    elif outcome in ("void", "voided"):
        return 0.0
    return None


def _build_football_query(
    date_from: Optional[str],
    date_to: Optional[str],
    league: Optional[str],
    market: Optional[str],
    status: Optional[str],
    min_odds: Optional[float],
    sort_by: str,
) -> tuple:
    conditions = ["(mode IS NULL OR mode != 'TEST')"]
    params: list = []

    if date_from:
        conditions.append("match_date >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("match_date <= %s")
        params.append(date_to)
    if league:
        conditions.append("LOWER(league) LIKE %s")
        params.append(f"%{league.lower()}%")
    if market:
        conditions.append("LOWER(market) LIKE %s")
        params.append(f"%{market.lower()}%")
    if min_odds is not None:
        conditions.append("odds >= %s")
        params.append(min_odds)
    if status:
        norm = status.lower()
        if norm == "won":
            conditions.append("outcome IN ('won','win')")
        elif norm == "lost":
            conditions.append("outcome IN ('lost','loss')")
        elif norm == "void":
            conditions.append("outcome IN ('void','voided','cancelled')")
        elif norm == "upcoming":
            conditions.append("(outcome IS NULL OR outcome = 'pending' OR outcome = '')")
        elif norm == "live":
            conditions.append("outcome = 'live'")
        elif norm == "settled":
            conditions.append("outcome IN ('won','win','lost','loss','void','voided')")

    where = " AND ".join(conditions)

    order = {
        "newest": "timestamp DESC",
        "kickoff": "kickoff_epoch ASC NULLS LAST",
        "odds": "odds DESC",
        "ev": "COALESCE(ev_sim, edge_percentage, 0) DESC",
    }.get(sort_by, "timestamp DESC")

    query = f"""
        SELECT id, home_team, away_team, league, market, selection, odds,
               match_date, kickoff_utc, kickoff_epoch, status, outcome, profit_loss,
               edge_percentage, ev_sim, confidence, trust_level, model_prob,
               actual_score, best_odds_bookmaker, open_odds, close_odds, clv_pct,
               created_at_utc, bet_category, timestamp
        FROM football_opportunities
        WHERE {where}
        ORDER BY {order}
    """
    return query, params


def _build_basketball_query(
    date_from: Optional[str],
    date_to: Optional[str],
    league: Optional[str],
    market: Optional[str],
    status: Optional[str],
    min_odds: Optional[float],
    sort_by: str,
) -> tuple:
    conditions = ["(mode IS NULL OR mode != 'TEST')"]
    params: list = []

    if date_from:
        conditions.append("commence_time >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("commence_time <= %s")
        params.append(f"{date_to} 23:59:59")
    if league:
        conditions.append("LOWER(league) LIKE %s")
        params.append(f"%{league.lower()}%")
    if market:
        conditions.append("LOWER(market) LIKE %s")
        params.append(f"%{market.lower()}%")
    if min_odds is not None:
        conditions.append("odds >= %s")
        params.append(min_odds)
    if status:
        norm = status.lower()
        if norm == "won":
            conditions.append("status IN ('won','win','WON','WIN')")
        elif norm == "lost":
            conditions.append("status IN ('lost','loss','LOST','LOSS')")
        elif norm == "void":
            conditions.append("status IN ('void','voided')")
        elif norm == "upcoming":
            conditions.append("(status IS NULL OR status = 'pending' OR status = '')")
        elif norm == "settled":
            conditions.append("status IN ('won','win','lost','loss','void','WON','WIN','LOST','LOSS')")

    where = " AND ".join(conditions)
    order = {
        "newest": "created_at DESC",
        "kickoff": "commence_time ASC NULLS LAST",
        "odds": "odds DESC",
        "ev": "COALESCE(ev_sim, ev_percentage, 0) DESC",
    }.get(sort_by, "created_at DESC")

    query = f"""
        SELECT id, match, league, market, selection, odds,
               commence_time, status, profit_units, ev_percentage, ev_sim,
               confidence, trust_level, sim_probability, bookmaker,
               open_odds, close_odds, clv_pct, created_at
        FROM basketball_predictions
        WHERE {where}
        ORDER BY {order}
    """
    return query, params


def _build_props_query(
    date_from: Optional[str],
    date_to: Optional[str],
    league: Optional[str],
    market: Optional[str],
    status: Optional[str],
    min_odds: Optional[float],
    sort_by: str,
) -> tuple:
    conditions = ["1=1"]
    params: list = []

    if date_from:
        conditions.append("commence_time >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("commence_time <= %s")
        params.append(f"{date_to} 23:59:59")
    if league:
        conditions.append("LOWER(league) LIKE %s")
        params.append(f"%{league.lower()}%")
    if market:
        conditions.append("LOWER(market) LIKE %s")
        params.append(f"%{market.lower()}%")
    if min_odds is not None:
        conditions.append("odds >= %s")
        params.append(min_odds)
    if status:
        norm = status.lower()
        if norm == "won":
            conditions.append("status IN ('won','win','WON')")
        elif norm == "lost":
            conditions.append("status IN ('lost','loss','LOST')")
        elif norm == "void":
            conditions.append("status IN ('void','voided')")
        elif norm == "upcoming":
            conditions.append("(status IS NULL OR status = 'pending' OR status = '')")
        elif norm == "settled":
            conditions.append("status IN ('won','win','lost','loss','void','WON','LOST')")

    where = " AND ".join(conditions)
    order = {
        "newest": "created_at DESC",
        "kickoff": "commence_time ASC NULLS LAST",
        "odds": "odds DESC",
        "ev": "COALESCE(edge_pct, 0) DESC",
    }.get(sort_by, "created_at DESC")

    query = f"""
        SELECT id, sport, league, home_team, away_team, player_name, market,
               selection, line, odds, commence_time, status, outcome,
               profit_loss, edge_pct, confidence, model_prob, bookmaker,
               open_odds, close_odds, clv_pct, created_at, notes
        FROM player_props
        WHERE {where}
        ORDER BY {order}
    """
    return query, params


def _row_to_football_card(row) -> BetCard:
    (rid, home, away, league, market, selection, odds,
     match_date, kickoff_utc, kickoff_epoch, status, outcome, profit_loss,
     edge_pct, ev_sim, confidence, trust_level, model_prob,
     actual_score, bookmaker, open_odds, close_odds, clv_pct,
     created_at_utc, bet_category, ts) = row

    norm_status = _normalize_status(status, outcome)
    ev = ev_sim if ev_sim is not None else (edge_pct if edge_pct else None)
    pu = _compute_profit_units(norm_status, odds or 0) if norm_status in ("won", "lost", "void") else None

    return BetCard(
        id=f"fb_{rid}",
        sport="football",
        league=league or "Unknown",
        match=f"{home} vs {away}",
        home_team=home or "",
        away_team=away or "",
        market=market or "",
        selection=selection or "",
        odds=round(float(odds), 2) if odds else 0,
        kickoff=kickoff_utc or match_date or None,
        kickoff_epoch=int(kickoff_epoch) if kickoff_epoch else None,
        status=norm_status,
        outcome=outcome,
        profit_units=pu,
        ev_pct=round(float(ev), 2) if ev is not None else None,
        confidence=float(confidence) if confidence else None,
        trust_level=trust_level,
        model_prob=round(float(model_prob), 4) if model_prob else None,
        actual_score=actual_score,
        bookmaker=bookmaker,
        open_odds=round(float(open_odds), 2) if open_odds else None,
        close_odds=round(float(close_odds), 2) if close_odds else None,
        clv_pct=round(float(clv_pct), 2) if clv_pct else None,
        created_at=created_at_utc or (datetime.utcfromtimestamp(ts).isoformat() if ts else None),
        bet_category=bet_category,
    )


def _row_to_basketball_card(row) -> BetCard:
    (rid, match_name, league, market, selection, odds,
     commence_time, status, profit_units, ev_pct, ev_sim,
     confidence, trust_level, sim_prob, bookmaker,
     open_odds, close_odds, clv_pct, created_at) = row

    norm_status = _normalize_status(status)
    parts = (match_name or "").split(" vs ", 1)
    home = parts[0].strip() if len(parts) > 0 else ""
    away = parts[1].strip() if len(parts) > 1 else ""
    ev = ev_sim if ev_sim is not None else (float(ev_pct) if ev_pct else None)
    pu = _compute_profit_units(norm_status, float(odds or 0)) if norm_status in ("won", "lost", "void") else None

    return BetCard(
        id=f"bb_{rid}",
        sport="basketball",
        league=league or "NCAAB",
        match=match_name or "",
        home_team=home,
        away_team=away,
        market=market or "",
        selection=selection or "",
        odds=round(float(odds), 2) if odds else 0,
        kickoff=commence_time.isoformat() if commence_time else None,
        kickoff_epoch=int(commence_time.timestamp()) if commence_time else None,
        status=norm_status,
        outcome=norm_status if norm_status in ("won", "lost", "void") else None,
        profit_units=pu,
        ev_pct=round(float(ev), 2) if ev is not None else None,
        confidence=float(confidence) if confidence else None,
        trust_level=trust_level,
        model_prob=round(float(sim_prob), 4) if sim_prob else None,
        bookmaker=bookmaker,
        open_odds=round(float(open_odds), 2) if open_odds else None,
        close_odds=round(float(close_odds), 2) if close_odds else None,
        clv_pct=round(float(clv_pct), 2) if clv_pct else None,
        created_at=created_at.isoformat() if created_at else None,
    )


def _row_to_props_card(row) -> BetCard:
    (rid, sport, league, home, away, player_name, market,
     selection, line, odds, commence_time, status, outcome,
     profit_loss, edge_pct, confidence, model_prob, bookmaker,
     open_odds, close_odds, clv_pct, created_at, notes) = row

    norm_status = _normalize_status(status, outcome)
    pu = _compute_profit_units(norm_status, float(odds or 0)) if norm_status in ("won", "lost", "void") else None

    line_str = f" {line}" if line else ""
    sel_display = f"{player_name} - {selection}{line_str}" if player_name else (selection or "")

    is_premium = bool(notes and "PREMIUM" in (notes or ""))

    return BetCard(
        id=f"pp_{rid}",
        sport=sport or "football",
        league=league or "Unknown",
        match=f"{home} vs {away}",
        home_team=home or "",
        away_team=away or "",
        market=f"prop_{market}" if market else "player_prop",
        selection=sel_display,
        odds=round(float(odds), 2) if odds else 0,
        kickoff=commence_time.isoformat() if commence_time else None,
        kickoff_epoch=int(commence_time.timestamp()) if commence_time else None,
        status=norm_status,
        outcome=outcome,
        profit_units=pu,
        ev_pct=round(float(edge_pct), 2) if edge_pct is not None else None,
        confidence=float(confidence) if confidence else None,
        model_prob=round(float(model_prob), 4) if model_prob else None,
        bookmaker=bookmaker,
        open_odds=round(float(open_odds), 2) if open_odds else None,
        close_odds=round(float(close_odds), 2) if close_odds else None,
        clv_pct=round(float(clv_pct), 2) if clv_pct else None,
        created_at=created_at.isoformat() if created_at else None,
        is_premium=is_premium,
    )


@router.get("/bets", response_model=BetsFeedResponse)
async def get_bets_feed(
    sport: Optional[str] = Query(None, description="Filter by sport: football, basketball, props"),
    league: Optional[str] = Query(None, description="Filter by league name (partial match)"),
    market: Optional[str] = Query(None, description="Filter by market type (partial match)"),
    status: Optional[str] = Query(None, description="Filter: upcoming, live, settled, won, lost, void"),
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    min_odds: Optional[float] = Query(None, description="Minimum odds filter"),
    sort: str = Query("newest", description="Sort: newest, kickoff, odds, ev"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Unified bets feed across all sports.
    Returns bet cards optimized for frontend display with compact + expandable views.
    """
    cache_key = f"bets:{sport}:{league}:{market}:{status}:{date_from}:{date_to}:{min_odds}:{sort}:{limit}:{offset}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    all_bets: List[BetCard] = []

    include_football = sport is None or sport.lower() == "football"
    include_basketball = sport is None or sport.lower() == "basketball"
    include_props = sport is None or sport.lower() == "props"

    if include_football:
        try:
            q, p = _build_football_query(date_from, date_to, league, market, status, min_odds, sort)
            rows = db_helper.execute(q, tuple(p), fetch='all') or []
            for row in rows:
                try:
                    all_bets.append(_row_to_football_card(row))
                except Exception as e:
                    logger.debug(f"Skip football row: {e}")
        except Exception as e:
            logger.error(f"Football query error: {e}")

    if include_basketball:
        try:
            q, p = _build_basketball_query(date_from, date_to, league, market, status, min_odds, sort)
            rows = db_helper.execute(q, tuple(p), fetch='all') or []
            for row in rows:
                try:
                    all_bets.append(_row_to_basketball_card(row))
                except Exception as e:
                    logger.debug(f"Skip basketball row: {e}")
        except Exception as e:
            logger.error(f"Basketball query error: {e}")

    if include_props:
        try:
            q, p = _build_props_query(date_from, date_to, league, market, status, min_odds, sort)
            rows = db_helper.execute(q, tuple(p), fetch='all') or []
            for row in rows:
                try:
                    all_bets.append(_row_to_props_card(row))
                except Exception as e:
                    logger.debug(f"Skip props row: {e}")
        except Exception as e:
            logger.error(f"Player props query error: {e}")

    sort_keys = {
        "newest": lambda b: b.created_at or "",
        "kickoff": lambda b: b.kickoff_epoch or 9999999999,
        "odds": lambda b: b.odds or 0,
        "ev": lambda b: b.ev_pct or -999,
    }
    reverse = sort != "kickoff"
    all_bets.sort(key=sort_keys.get(sort, sort_keys["newest"]), reverse=reverse)

    total = len(all_bets)
    page = all_bets[offset : offset + limit]

    response = BetsFeedResponse(
        bets=page,
        total=total,
        limit=limit,
        offset=offset,
        filters_applied={
            "sport": sport,
            "league": league,
            "market": market,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "min_odds": min_odds,
            "sort": sort,
        },
        generated_at=datetime.utcnow().isoformat(),
    )

    _set_cached(cache_key, response)
    return response


@router.get("/bets/stats")
async def get_bets_stats(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Quick stats summary for the bets feed header — all sports combined."""
    cache_key = f"stats_all:{date_from}:{date_to}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    won_total = 0
    lost_total = 0
    void_total = 0
    upcoming_total = 0
    profit_total = 0.0

    try:
        date_filter = ""
        params: list = []
        if date_from:
            date_filter += " AND match_date >= %s"
            params.append(date_from)
        if date_to:
            date_filter += " AND match_date <= %s"
            params.append(date_to)

        row = db_helper.execute(f"""
            SELECT
                COUNT(CASE WHEN outcome IN ('won','win') THEN 1 END),
                COUNT(CASE WHEN outcome IN ('lost','loss') THEN 1 END),
                COUNT(CASE WHEN outcome IN ('void','voided') THEN 1 END),
                COUNT(CASE WHEN outcome IS NULL OR outcome IN ('pending','') THEN 1 END),
                COALESCE(SUM(profit_loss), 0)
            FROM football_opportunities
            WHERE (mode IS NULL OR mode != 'TEST') {date_filter}
        """, tuple(params), fetch='one')
        if row:
            won_total += row[0] or 0
            lost_total += row[1] or 0
            void_total += row[2] or 0
            upcoming_total += row[3] or 0
            profit_total += float(row[4] or 0)
    except Exception as e:
        logger.error(f"Football stats error: {e}")

    try:
        bb_date_filter = ""
        bb_params: list = []
        if date_from:
            bb_date_filter += " AND commence_time >= %s"
            bb_params.append(date_from)
        if date_to:
            bb_date_filter += " AND commence_time <= %s"
            bb_params.append(f"{date_to} 23:59:59")

        row = db_helper.execute(f"""
            SELECT
                COUNT(CASE WHEN status IN ('won','win','WON') THEN 1 END),
                COUNT(CASE WHEN status IN ('lost','loss','LOST') THEN 1 END),
                COUNT(CASE WHEN status IN ('void','voided') THEN 1 END),
                COUNT(CASE WHEN status IS NULL OR status IN ('pending','') THEN 1 END),
                COALESCE(SUM(profit_units), 0)
            FROM basketball_predictions
            WHERE (mode IS NULL OR mode != 'TEST') {bb_date_filter}
        """, tuple(bb_params), fetch='one')
        if row:
            won_total += row[0] or 0
            lost_total += row[1] or 0
            void_total += row[2] or 0
            upcoming_total += row[3] or 0
            profit_total += float(row[4] or 0)
    except Exception as e:
        logger.error(f"Basketball stats error: {e}")

    settled = won_total + lost_total
    hit_rate = round(won_total / settled * 100, 1) if settled > 0 else 0
    total_bets = won_total + lost_total + void_total + upcoming_total

    result = {
        "total_bets": total_bets,
        "won": won_total,
        "lost": lost_total,
        "void": void_total,
        "upcoming": upcoming_total,
        "settled": settled,
        "hit_rate": hit_rate,
        "profit_units": round(profit_total, 2),
        "roi": round(profit_total / settled * 100, 1) if settled > 0 else 0,
        "generated_at": datetime.utcnow().isoformat(),
    }
    _set_cached(cache_key, result)
    return result


@router.get("/bets/sports")
async def get_available_sports():
    """List available sports and their bet counts for filter dropdowns."""
    cache_key = "sports_list"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    result = {"sports": [], "generated_at": datetime.utcnow().isoformat()}

    try:
        fb_count = db_helper.execute(
            "SELECT COUNT(*) FROM football_opportunities WHERE mode IS NULL OR mode != 'TEST'",
            fetch='one'
        )
        result["sports"].append({"key": "football", "label": "Football", "count": fb_count[0] if fb_count else 0})
    except Exception:
        pass

    try:
        bb_count = db_helper.execute(
            "SELECT COUNT(*) FROM basketball_predictions WHERE mode IS NULL OR mode != 'TEST'",
            fetch='one'
        )
        result["sports"].append({"key": "basketball", "label": "Basketball", "count": bb_count[0] if bb_count else 0})
    except Exception:
        pass

    try:
        pp_count = db_helper.execute("SELECT COUNT(*) FROM player_props", fetch='one')
        result["sports"].append({"key": "props", "label": "Player Props", "count": pp_count[0] if pp_count else 0})
    except Exception:
        pass

    _set_cached(cache_key, result)
    return result


@router.get("/bets/leagues")
async def get_available_leagues(sport: Optional[str] = Query(None)):
    """List available leagues for filter dropdown."""
    cache_key = f"leagues:{sport}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    leagues = set()

    if sport is None or sport == "football":
        try:
            rows = db_helper.execute(
                "SELECT DISTINCT league FROM football_opportunities WHERE league IS NOT NULL AND (mode IS NULL OR mode != 'TEST')",
                fetch='all'
            ) or []
            for r in rows:
                if r[0]:
                    leagues.add(r[0])
        except Exception:
            pass

    if sport is None or sport == "basketball":
        try:
            rows = db_helper.execute(
                "SELECT DISTINCT league FROM basketball_predictions WHERE league IS NOT NULL",
                fetch='all'
            ) or []
            for r in rows:
                if r[0]:
                    leagues.add(r[0])
        except Exception:
            pass

    if sport is None or sport == "props":
        try:
            rows = db_helper.execute(
                "SELECT DISTINCT league FROM player_props WHERE league IS NOT NULL",
                fetch='all'
            ) or []
            for r in rows:
                if r[0]:
                    leagues.add(r[0])
        except Exception:
            pass

    result = {"leagues": sorted(leagues), "count": len(leagues), "generated_at": datetime.utcnow().isoformat()}
    _set_cached(cache_key, result)
    return result

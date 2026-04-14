#!/usr/bin/env python3
"""
PGR Sports Analytics - Read-Only HTTP API
==========================================

This API provides read-only access to AI prediction data from the database.
All endpoints read from the existing PostgreSQL database only.
No external API calls are made from these endpoints.

ENDPOINTS:
- GET /api/health           - Health check
- GET /api/matches/today    - Today's matches with AI data
- GET /api/match/{match_id} - Detailed match AI data

USAGE:
Run with: uvicorn api:app --host 0.0.0.0 --port 8000
Or integrate with existing deployment.

FRAMEWORK: FastAPI (async, non-blocking)
DATABASE: PostgreSQL via SQLAlchemy (read-only queries)
"""

import os
import json
import logging
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from db_helper import db_helper
from auth_discord import router as discord_auth_router
from auth_admin import router as admin_auth_router
from auth_premium import (
    premium_middleware,
    ensure_users_table,
    ensure_dashboard_tokens_table,
    create_dashboard_token,
    activate_premium,
    deactivate_premium,
    deactivate_by_stripe_customer,
    activate_by_stripe_customer,
    is_admin_session,
    get_discord_id,
    is_premium,
)
from stripe_service import (
    ensure_stripe_events_table,
    is_duplicate_event,
    extract_discord_id,
    create_checkout_session,
    create_customer_portal,
    resolve_discord_id_from_subscription,
    grant_discord_role,
    revoke_discord_role,
)
from api_staking import router as staking_router
from modules.stryktipset.stryktipset_router import router as stryk_router
from bets_feed import router as bets_feed_router

try:
    from pgr_api_router import router as pgr_router
    PGR_AVAILABLE = True
except Exception as _pgr_err:
    PGR_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_RAW_SOURCE_MAP = {
    "the_odds_api": "Best Line",
    "odds_api":     "Best Line",
    "api_football": "",
    "football_api": "",
    "api-football": "",
    "odds-api":     "Best Line",
}

def _clean_bookmaker(name: str) -> str:
    if not name:
        return ""
    lower = name.strip().lower()
    if lower in _RAW_SOURCE_MAP:
        return _RAW_SOURCE_MAP[lower]
    if "odds_api" in lower or "odds-api" in lower:
        return "Best Line"
    if "api_football" in lower or "api-football" in lower or "football_api" in lower:
        return ""
    return name.strip()

# In-memory cache for match-scout responses (TTL 8 hours — covers a full match day)
_match_scout_cache: Dict[str, Any] = {}
_MATCH_SCOUT_TTL = 28800  # seconds

# =============================================================================
# FastAPI App Initialization
# =============================================================================

app = FastAPI(
    title="PGR Sports Analytics API",
    description="Read-only API for AI sports prediction data",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware (must be added before custom middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Premium auth middleware — protects /home, /preview, /api/bets, /bets
app.middleware("http")(premium_middleware)


@app.on_event("startup")
async def startup_event():
    """Bootstrap DB tables required for auth and payments."""
    ensure_users_table()
    ensure_dashboard_tokens_table()
    ensure_stripe_events_table()

# Include Discord OAuth router
app.include_router(discord_auth_router)
app.include_router(admin_auth_router)

# Include staking router
app.include_router(staking_router)

# Include Stryktipset router
app.include_router(stryk_router)

# Include Bets Feed router
app.include_router(bets_feed_router)

if PGR_AVAILABLE:
    app.include_router(pgr_router)
    logger.info("PGR Analytics router loaded")
else:
    logger.warning(f"PGR Analytics router not loaded: {_pgr_err}")

# =============================================================================
# Response Models
# =============================================================================

class HealthResponse(BaseModel):
    status: str
    engine: str
    version: str
    timestamp: str

class AIProabilities(BaseModel):
    home: Optional[float] = None
    draw: Optional[float] = None
    away: Optional[float] = None

class EVData(BaseModel):
    home_ml: Optional[float] = None
    draw_ml: Optional[float] = None
    away_ml: Optional[float] = None
    over_2_5: Optional[float] = None
    under_2_5: Optional[float] = None
    btts_yes: Optional[float] = None
    btts_no: Optional[float] = None

class MatchSummary(BaseModel):
    match_id: str
    league: str
    home_team: str
    away_team: str
    kickoff: str
    products_available: List[str]
    ai_probabilities: Optional[Dict[str, float]] = None
    ev: Optional[Dict[str, float]] = None
    confidence_score: Optional[float] = None

class MatchesResponse(BaseModel):
    matches: List[MatchSummary]
    count: int
    generated_at: str

# =============================================================================
# Helper Functions (Data Access Layer)
# =============================================================================

def get_today_matches_with_ai_data() -> List[Dict[str, Any]]:
    """
    Fetch today's matches from all prediction tables.
    Returns combined data from football, SGP, basketball, ML parlay tables.
    """
    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    
    matches = {}  # key: match_id or home_team+away_team
    
    # 1. Football opportunities (Exact Score & Value Singles)
    try:
        football_rows = db_helper.execute("""
            SELECT DISTINCT ON (home_team, away_team)
                match_id, home_team, away_team, league, match_date, kickoff_time,
                market, selection, odds, edge_percentage, confidence, model_prob
            FROM football_opportunities
            WHERE match_date >= %s AND match_date <= %s
            AND mode != 'TEST'
            ORDER BY home_team, away_team, timestamp DESC
        """, (str(today), str(tomorrow)), fetch='all') or []
        
        for row in football_rows:
            key = f"{row[1]}_{row[2]}"  # home_away
            if key not in matches:
                matches[key] = {
                    'match_id': row[0] or key,
                    'home_team': row[1],
                    'away_team': row[2],
                    'league': row[3] or 'Unknown',
                    'kickoff': row[5] or row[4] or str(today),
                    'products': set(),
                    'ev': {},
                    'confidence_score': None,
                    'model_prob': row[11]
                }
            
            market = row[6]
            if market == 'exact_score':
                matches[key]['products'].add('EXACT_SCORE')
            elif market == 'Value Single':
                matches[key]['products'].add('VALUE_SINGLE')
            
            # Add EV data
            edge = row[9]
            if edge:
                selection = row[7] or ''
                if 'home' in selection.lower():
                    matches[key]['ev']['home_ml'] = round(edge / 100, 3)
                elif 'away' in selection.lower():
                    matches[key]['ev']['away_ml'] = round(edge / 100, 3)
                elif 'draw' in selection.lower():
                    matches[key]['ev']['draw_ml'] = round(edge / 100, 3)
            
            if row[10]:  # confidence
                matches[key]['confidence_score'] = row[10] / 100 if row[10] > 1 else row[10]
                
    except Exception as e:
        logger.error(f"Error fetching football opportunities: {e}")
    
    # 2. SGP Predictions (removed)
    try:
        sgp_rows = []
        
        for row in sgp_rows:
            key = f"{row[1]}_{row[2]}"
            if key not in matches:
                matches[key] = {
                    'match_id': row[0] or key,
                    'home_team': row[1],
                    'away_team': row[2],
                    'league': row[3] or 'Unknown',
                    'kickoff': row[5] or row[4] or str(today),
                    'products': set(),
                    'ev': {},
                    'confidence_score': None
                }
            matches[key]['products'].add('SGP')
            
            # Parse SGP legs for EV data
            if row[7]:  # ev_percentage
                matches[key]['ev']['sgp_ev'] = round(row[7] / 100, 3)
                
    except Exception as e:
        logger.error(f"Error fetching SGP predictions: {e}")
    
    # 3. Basketball Predictions
    try:
        bball_rows = db_helper.execute("""
            SELECT DISTINCT ON (match)
                id, match, selection, odds, ev_percentage, confidence,
                commence_time
            FROM basketball_predictions
            WHERE DATE(commence_time) >= %s AND DATE(commence_time) <= %s
            AND COALESCE(mode, 'PROD') != 'TEST'
            ORDER BY match, created_at DESC
        """, (str(today), str(tomorrow)), fetch='all') or []
        
        for row in bball_rows:
            match_name = row[1]
            # Try to parse "Team A vs Team B" format
            if ' vs ' in match_name:
                parts = match_name.split(' vs ')
                home = parts[0].strip()
                away = parts[1].strip() if len(parts) > 1 else 'Unknown'
            else:
                home = match_name
                away = ''
            
            key = f"{home}_{away}"
            if key not in matches:
                matches[key] = {
                    'match_id': str(row[0]),
                    'home_team': home,
                    'away_team': away,
                    'league': 'College Basketball',
                    'kickoff': str(row[6]) if row[6] else str(today),
                    'products': set(),
                    'ev': {},
                    'confidence_score': None
                }
            matches[key]['products'].add('BASKETBALL')
            
            if row[4]:  # ev_percentage
                matches[key]['ev']['basketball_ev'] = round(row[4] / 100, 3)
            if row[5]:  # confidence
                matches[key]['confidence_score'] = row[5] / 100 if row[5] > 1 else row[5]
                
    except Exception as e:
        logger.error(f"Error fetching basketball predictions: {e}")
    
    # Convert to list and clean up
    result = []
    for key, m in matches.items():
        result.append({
            'match_id': m['match_id'],
            'league': m['league'],
            'home_team': m['home_team'],
            'away_team': m['away_team'],
            'kickoff': m['kickoff'],
            'products_available': list(m['products']),
            'ev': m['ev'] if m['ev'] else None,
            'confidence_score': m.get('confidence_score')
        })
    
    # Sort by kickoff time
    result.sort(key=lambda x: x['kickoff'])
    
    return result


def get_match_ai_details(match_id: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed AI data for a specific match.
    Searches across all prediction tables.
    """
    match_data = None
    products = {}
    
    # 1. Search football_opportunities
    try:
        rows = db_helper.execute("""
            SELECT match_id, home_team, away_team, league, match_date, kickoff_time,
                   market, selection, odds, edge_percentage, confidence, model_prob,
                   analysis
            FROM football_opportunities
            WHERE match_id = %s OR (home_team || '_' || away_team) = %s
            ORDER BY timestamp DESC
        """, (match_id, match_id), fetch='all') or []
        
        for row in rows:
            if not match_data:
                match_data = {
                    'match_id': row[0] or match_id,
                    'league': row[3] or 'Unknown',
                    'home_team': row[1],
                    'away_team': row[2],
                    'kickoff': row[5] or row[4],
                    'ai_probabilities': {},
                    'ev': {},
                    'correct_score_distribution': [],
                    'products': {}
                }
            
            market = row[6]
            selection = row[7]
            odds = row[8]
            ev = row[9]
            
            if market == 'exact_score':
                if 'EXACT_SCORE' not in products:
                    products['EXACT_SCORE'] = {
                        'selected': True,
                        'top_pick': {
                            'score': selection,
                            'odds': odds,
                            'ev': round(ev / 100, 3) if ev else None
                        }
                    }
                    # Add to correct score distribution
                    match_data['correct_score_distribution'].append({
                        'score': selection,
                        'probability': round(row[11], 3) if row[11] else None
                    })
            
            elif market == 'Value Single':
                if 'VALUE_SINGLE' not in products:
                    products['VALUE_SINGLE'] = {
                        'selected': True,
                        'picks': []
                    }
                products['VALUE_SINGLE']['picks'].append({
                    'market': selection,
                    'odds': odds,
                    'ev': round(ev / 100, 3) if ev else None
                })
                
                # Build EV dict
                if ev:
                    if 'home' in selection.lower():
                        match_data['ev']['home_ml'] = round(ev / 100, 3)
                    elif 'away' in selection.lower():
                        match_data['ev']['away_ml'] = round(ev / 100, 3)
                    elif 'draw' in selection.lower():
                        match_data['ev']['draw_ml'] = round(ev / 100, 3)
                    elif 'over' in selection.lower():
                        match_data['ev']['over_2_5'] = round(ev / 100, 3)
                    elif 'under' in selection.lower():
                        match_data['ev']['under_2_5'] = round(ev / 100, 3)
                    elif 'btts' in selection.lower() and 'yes' in selection.lower():
                        match_data['ev']['btts_yes'] = round(ev / 100, 3)
                        
    except Exception as e:
        logger.error(f"Error fetching football data for match {match_id}: {e}")
    
    # 2. Search SGP predictions (removed)
    try:
        rows = []
        
        for row in rows:
            if not match_data:
                match_data = {
                    'match_id': row[0] or match_id,
                    'league': row[3] or 'Unknown',
                    'home_team': row[1],
                    'away_team': row[2],
                    'kickoff': row[5] or row[4],
                    'ai_probabilities': {},
                    'ev': {},
                    'correct_score_distribution': [],
                    'products': {}
                }
            
            if 'SGP' not in products:
                products['SGP'] = {
                    'selected': True,
                    'parlays': []
                }
            
            try:
                legs = json.loads(row[6]) if row[6] else []
                leg_names = [l.get('name', l.get('market', 'Unknown')) for l in legs]
            except:
                leg_names = [row[7]] if row[7] else ['Unknown']
            
            products['SGP']['parlays'].append({
                'legs': leg_names,
                'odds': row[8],
                'ev': round(row[9] / 100, 3) if row[9] else None
            })
            
    except Exception as e:
        logger.error(f"Error fetching SGP data for match {match_id}: {e}")
    
    # 3. Search basketball
    try:
        rows = db_helper.execute("""
            SELECT id, match, selection, odds, ev_percentage, confidence, commence_time
            FROM basketball_predictions
            WHERE id::text = %s OR match LIKE %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (match_id, f"%{match_id}%"), fetch='all') or []
        
        for row in rows:
            if not match_data:
                match_name = row[1]
                if ' vs ' in match_name:
                    parts = match_name.split(' vs ')
                    home = parts[0].strip()
                    away = parts[1].strip() if len(parts) > 1 else ''
                else:
                    home = match_name
                    away = ''
                
                match_data = {
                    'match_id': str(row[0]),
                    'league': 'College Basketball',
                    'home_team': home,
                    'away_team': away,
                    'kickoff': str(row[6]) if row[6] else None,
                    'ai_probabilities': {},
                    'ev': {},
                    'correct_score_distribution': [],
                    'products': {}
                }
            
            products['BASKETBALL'] = {
                'selected': True,
                'picks': [{
                    'selection': row[2],
                    'odds': row[3],
                    'ev': round(row[4] / 100, 3) if row[4] else None
                }]
            }
            
    except Exception as e:
        logger.error(f"Error fetching basketball data for match {match_id}: {e}")
    
    if match_data:
        match_data['products'] = products
        
        # Clean up empty fields
        if not match_data['ai_probabilities']:
            del match_data['ai_probabilities']
        if not match_data['ev']:
            del match_data['ev']
        if not match_data['correct_score_distribution']:
            del match_data['correct_score_distribution']
    
    return match_data


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Returns status, engine name, version, and current timestamp.
    """
    return HealthResponse(
        status="ok",
        engine="pgr-sports-analytics",
        version="1.0.0",
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


@app.get("/api/matches/today", response_model=MatchesResponse, tags=["Matches"])
async def get_today_matches():
    """
    Get all matches for today with available AI prediction data.
    
    Returns matches from all products:
    - EXACT_SCORE: Exact score predictions
    - VALUE_SINGLE: Value singles (1X2, O/U, BTTS)
    - SGP: Same Game Parlays
    - BASKETBALL: College basketball predictions
    - ML_PARLAY: Moneyline parlays
    
    Each match includes:
    - Basic info (teams, league, kickoff)
    - List of available products
    - EV data (where available)
    - Confidence scores (where available)
    """
    try:
        matches_data = get_today_matches_with_ai_data()
        
        matches = []
        for m in matches_data:
            matches.append(MatchSummary(
                match_id=m['match_id'],
                league=m['league'],
                home_team=m['home_team'],
                away_team=m['away_team'],
                kickoff=m['kickoff'],
                products_available=m['products_available'],
                ai_probabilities=m.get('ai_probabilities'),
                ev=m.get('ev'),
                confidence_score=m.get('confidence_score')
            ))
        
        return MatchesResponse(
            matches=matches,
            count=len(matches),
            generated_at=datetime.utcnow().isoformat() + "Z"
        )
        
    except Exception as e:
        logger.error(f"Error in get_today_matches: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/match/{match_id}", tags=["Matches"])
async def get_match_details(match_id: str):
    """
    Get detailed AI prediction data for a specific match.
    
    Parameters:
    - match_id: The match ID (from database or home_away format)
    
    Returns comprehensive AI data including:
    - Basic match info
    - AI probabilities (1X2)
    - EV per market
    - Correct score distribution (top picks)
    - Product-specific data (VALUE_SINGLE, SGP, EXACT_SCORE, BASKETBALL)
    
    Returns 404 if match not found.
    """
    try:
        match_data = get_match_ai_details(match_id)
        
        if not match_data:
            raise HTTPException(
                status_code=404,
                detail={"error": "match_not_found"}
            )
        
        return match_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_match_details for {match_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/bookmaker-odds/{match_id}", tags=["Odds"])
async def get_bookmaker_odds(match_id: str):
    """
    Get bookmaker odds comparison for a specific match.
    
    Returns odds from all bookmakers for each available market/selection,
    highlighting the best odds and comparing to model fair odds.
    
    Parameters:
    - match_id: The match ID or home_away format
    
    Returns:
    - selections: List of selections with all bookmaker odds
    - Each selection includes: market, selection, odds_by_bookmaker, best_odds, avg_odds, fair_odds
    """
    try:
        rows = db_helper.execute("""
            SELECT 
                match_id, home_team, away_team, league, match_date, kickoff_time,
                market, selection, odds, model_prob,
                odds_by_bookmaker, best_odds_value, best_odds_bookmaker, avg_odds, fair_odds
            FROM football_opportunities
            WHERE (match_id = %s OR (home_team || '_' || away_team) = %s)
            AND mode != 'TEST'
            ORDER BY timestamp DESC
        """, (match_id, match_id), fetch='all') or []
        
        if not rows:
            raise HTTPException(
                status_code=404,
                detail={"error": "match_not_found", "message": "No odds data found for this match"}
            )
        
        match_info = {
            'match_id': rows[0][0] or match_id,
            'home_team': rows[0][1],
            'away_team': rows[0][2],
            'league': rows[0][3] or 'Unknown',
            'match_date': str(rows[0][4]) if rows[0][4] else None,
            'kickoff_time': rows[0][5]
        }
        
        selections = []
        seen = set()
        
        for row in rows:
            market = row[6]
            selection = row[7]
            key = f"{market}_{selection}"
            
            if key in seen:
                continue
            seen.add(key)
            
            odds_by_bookmaker = {}
            if row[10]:
                if isinstance(row[10], str):
                    try:
                        odds_by_bookmaker = json.loads(row[10])
                    except:
                        odds_by_bookmaker = {}
                elif isinstance(row[10], dict):
                    odds_by_bookmaker = row[10]
            
            fair_odds_val = float(row[14]) if row[14] else None
            if not fair_odds_val and row[9] and float(row[9]) > 0:
                fair_odds_val = round(1.0 / float(row[9]), 3)
            
            selection_data = {
                'market': market,
                'selection': selection,
                'current_odds': float(row[8]) if row[8] else None,
                'model_probability': round(float(row[9]) * 100, 1) if row[9] else None,
                'odds_by_bookmaker': odds_by_bookmaker,
                'best_odds': {
                    'value': float(row[11]) if row[11] else None,
                    'bookmaker': _clean_bookmaker(row[12] or '')
                } if row[11] else None,
                'avg_odds': float(row[13]) if row[13] else None,
                'fair_odds': fair_odds_val,
                'bookmaker_count': len(odds_by_bookmaker)
            }
            
            if fair_odds_val and row[11]:
                edge_vs_fair = ((float(row[11]) / fair_odds_val) - 1) * 100
                selection_data['edge_vs_fair_pct'] = round(edge_vs_fair, 2)
            
            selections.append(selection_data)
        
        return {
            'match': match_info,
            'selections': selections,
            'total_selections': len(selections),
            'generated_at': datetime.utcnow().isoformat() + "Z"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_bookmaker_odds for {match_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _fetch_sofascore_data(home_team: str, away_team: str, league: str):
    """Fetch form + H2H from SofaScore in threads (non-blocking). Returns (form_stats, h2h_stats)."""
    import asyncio

    def _sync_form():
        try:
            from sofascore_scraper import SofaScoreScraper
            scraper = SofaScoreScraper()
            return (scraper.get_team_form(home_team, league, last_n=5),
                    scraper.get_team_form(away_team, league, last_n=5))
        except Exception as e:
            logger.warning(f"SofaScore form error: {e}")
            return [], []

    def _sync_h2h():
        try:
            from sofascore_scraper import SofaScoreScraper
            scraper = SofaScoreScraper()
            return scraper.get_h2h_data(home_team, away_team, league)
        except Exception as e:
            logger.warning(f"SofaScore H2H error: {e}")
            return []

    # Run form (fast, ~5s) and H2H (slower, ~15s) with separate timeouts
    home_form, away_form, h2h_raw = [], [], []
    try:
        home_form, away_form = await asyncio.wait_for(
            asyncio.to_thread(_sync_form), timeout=12.0
        )
    except asyncio.TimeoutError:
        logger.warning("SofaScore form fetch timed out")

    try:
        h2h_raw = await asyncio.wait_for(
            asyncio.to_thread(_sync_h2h), timeout=20.0
        )
    except asyncio.TimeoutError:
        logger.warning("SofaScore H2H fetch timed out")

    def _agg_form(matches):
        if not matches:
            return None
        wins = sum(1 for m in matches if m['result'] == 'W')
        draws = sum(1 for m in matches if m['result'] == 'D')
        losses = sum(1 for m in matches if m['result'] == 'L')
        goals_for = goals_against = clean_sheets = 0
        for m in matches:
            try:
                hg, ag = map(int, m['score'].split('-'))
                gf, ga = (hg, ag) if m['home_away'] == 'H' else (ag, hg)
                goals_for += gf; goals_against += ga
                if ga == 0: clean_sheets += 1
            except Exception:
                pass
        n = len(matches)
        ppg = round((wins * 3 + draws) / n, 2) if n else 0
        return {
            "wins":           wins,
            "draws":          draws,
            "losses":         losses,
            "ppg":            ppg,
            "goals_scored":   round(goals_for / n, 2) if n else None,
            "goals_conceded": round(goals_against / n, 2) if n else None,
            "clean_sheets":   clean_sheets,
            "form_sequence":  [m['result'] for m in matches],
            "recent_matches": [{"date": m['date'], "opponent": m['opponent'],
                                "venue": m['home_away'], "score": m['score'],
                                "result": m['result']} for m in matches],
            "source":         "sofascore",
        }

    home_agg = _agg_form(home_form)
    away_agg = _agg_form(away_form)
    form_stats = {"home": home_agg, "away": away_agg} if (home_agg or away_agg) else None

    h2h_stats = None
    if h2h_raw:
        n = len(h2h_raw)
        hw = sum(1 for m in h2h_raw if m['home_team'] == home_team and m['home_score'] > m['away_score'])
        aw = sum(1 for m in h2h_raw if m['away_team'] == away_team and m['away_score'] > m['home_score'])
        dw = n - hw - aw
        total_g = sum(m['home_score'] + m['away_score'] for m in h2h_raw)
        btts    = sum(1 for m in h2h_raw if m['home_score'] > 0 and m['away_score'] > 0)
        over25  = sum(1 for m in h2h_raw if m['home_score'] + m['away_score'] > 2.5)
        h2h_stats = {
            "matches":        n,
            "home_wins":      hw,
            "away_wins":      aw,
            "draws":          dw,
            "avg_goals":      round(total_g / n, 2) if n else None,
            "btts_rate":      round(btts / n * 100, 1) if n else None,
            "over25_rate":    round(over25 / n * 100, 1) if n else None,
            "recent_matches": [{"date": m['date'], "home": m['home_team'], "away": m['away_team'],
                                "score": f"{m['home_score']}-{m['away_score']}"} for m in h2h_raw[:6]],
            "source":         "sofascore",
        }

    return form_stats, h2h_stats


@app.get("/api/match-scout/{match_id}", tags=["Matches"])
async def get_match_scout(match_id: str):
    """
    Full bettor intelligence for a single match:
    all markets, bookmaker odds, model probs, H2H, form, xG, standings, CLV, predicted score.
    """
    import time as _time, asyncio as _asyncio
    # ── Cache check ───────────────────────────────────────────────────────────
    _cache_key = match_id
    _cached = _match_scout_cache.get(_cache_key)
    if _cached and (_time.time() - _cached["_ts"]) < _MATCH_SCOUT_TTL:
        return _cached["data"]
    try:
        # ── 1. All opportunities for this match ──────────────────
        # cols: 0=match_id 1=home 2=away 3=league 4=match_date 5=kickoff_time
        #       6=market 7=selection 8=odds 9=edge_pct 10=confidence
        #       11=model_prob 12=calibrated_prob 13=sim_probability 14=ev_sim
        #       15=trust_level 16=tier 17=disagreement 18=profile_boost_score
        #       19=open_odds 20=close_odds 21=clv_pct 22=analysis
        #       23=odds_by_bookmaker 24=odds_source 25=best_odds_bookmaker 26=best_odds_value
        opp_rows = db_helper.execute("""
            SELECT match_id, home_team, away_team, league, match_date, kickoff_time,
                   market, selection, odds, edge_percentage, confidence,
                   model_prob, calibrated_prob, sim_probability, ev_sim,
                   trust_level, tier, disagreement, profile_boost_score,
                   open_odds, close_odds, clv_pct, analysis,
                   odds_by_bookmaker, odds_source, best_odds_bookmaker, best_odds_value
            FROM football_opportunities
            WHERE (match_id = %s OR (home_team || '_' || away_team) = %s
                   OR (home_team || ' vs ' || away_team) = %s)
              AND mode != 'TEST'
            ORDER BY timestamp DESC
        """, (match_id, match_id, match_id), fetch='all') or []

        if not opp_rows:
            raise HTTPException(status_code=404, detail={"error": "match_not_found"})

        first = opp_rows[0]
        home_team  = first[1]
        away_team  = first[2]
        league     = first[3] or ""
        match_date = str(first[4]) if first[4] else ""
        kickoff    = first[5] or match_date

        def _build_bookmakers(r):
            """Build bookmakers dict from odds_by_bookmaker column or single-entry fallback."""
            bk_raw = r[23]
            if bk_raw and isinstance(bk_raw, dict) and len(bk_raw) > 0:
                return {k: float(v) for k, v in bk_raw.items() if v}
            # Fallback: use best_odds_bookmaker if available, else odds_source label
            odds_val = float(r[8]) if r[8] else None
            if not odds_val:
                return {}
            best_bm   = r[25]  # best_odds_bookmaker
            best_val  = float(r[26]) if r[26] else None
            src       = r[24] or ""  # odds_source
            result = {}
            if best_bm and best_val:
                clean_bm = _clean_bookmaker(best_bm)
                if clean_bm:
                    result[clean_bm] = best_val
            # If pick odds differ from best (or no best), add pick's line
            label = _clean_bookmaker(src) or "Best Line"
            if label and label not in result:
                result[label] = odds_val
            return result

        # Build picks list
        from ev_core import confidence_tier as _conf_tier
        picks = []
        seen_sel = set()
        for r in opp_rows:
            key = f"{r[6]}|{r[7]}"
            if key in seen_sel:
                continue
            seen_sel.add(key)
            _ev_val   = round(float(r[9]), 1) if r[9] else None
            _conf_raw = float(r[10]) if r[10] is not None else 0.0
            picks.append({
                "market":           r[6],
                "selection":        r[7],
                "odds":             round(float(r[8]), 2) if r[8] else None,
                "ev_pct":           _ev_val,
                "confidence":       _conf_raw,
                "confidence_tier":  _conf_tier(_conf_raw),
                "model_prob":       round(float(r[11]), 3) if r[11] else None,
                "model_prob_pct":   round(float(r[11]) * 100, 1) if r[11] else None,
                "high_variance":    bool((_ev_val or 0) > 15),
                "calibrated_prob":  round(float(r[12]), 3) if r[12] else None,
                "sim_prob":         round(float(r[13]), 3) if r[13] else None,
                "ev_sim":           round(float(r[14]), 1) if r[14] else None,
                "bookmakers":       _build_bookmakers(r),
                "trust_level":      r[15],
                "tier":             r[16],
                "disagreement":     round(float(r[17]), 2) if r[17] else None,
                "boost_score":      round(float(r[18]), 2) if r[18] else None,
                "open_odds":        round(float(r[19]), 2) if r[19] else None,
                "close_odds":       round(float(r[20]), 2) if r[20] else None,
                "clv_pct":          round(float(r[21]), 1) if r[21] else None,
                "analysis_raw":     r[22],
            })

        # ── 2. Training data for this match ──────────────────────
        td = db_helper.execute("""
            SELECT home_form_goals_scored, home_form_goals_conceded,
                   home_form_clean_sheets, home_form_ppg,
                   home_form_wins, home_form_draws, home_form_losses,
                   away_form_goals_scored, away_form_goals_conceded,
                   away_form_clean_sheets, away_form_ppg,
                   away_form_wins, away_form_draws, away_form_losses,
                   home_xg, away_xg, total_xg,
                   h2h_matches_count, h2h_home_wins, h2h_away_wins, h2h_draws,
                   h2h_avg_goals, h2h_btts_rate, h2h_over25_rate,
                   home_position, away_position, home_points, away_points,
                   home_goal_diff, away_goal_diff,
                   predicted_home_goals, predicted_away_goals, predicted_score,
                   model_probability
            FROM training_data
            WHERE home_team = %s AND away_team = %s AND match_date = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (home_team, away_team, match_date), fetch='one')

        form_stats = None
        h2h_stats  = None
        standings  = None
        xg_stats   = None
        prediction = None

        if td:
            # Only populate form if at least one form field has real data
            _form_has_data = any(td[i] is not None for i in [0, 1, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13])
            if _form_has_data:
                form_stats = {
                    "home": {
                        "goals_scored":    round(float(td[0]), 2) if td[0] else None,
                        "goals_conceded":  round(float(td[1]), 2) if td[1] else None,
                        "clean_sheets":    td[2],
                        "ppg":             round(float(td[3]), 2) if td[3] else None,
                        "wins":            td[4], "draws": td[5], "losses": td[6],
                    },
                    "away": {
                        "goals_scored":    round(float(td[7]), 2) if td[7] else None,
                        "goals_conceded":  round(float(td[8]), 2) if td[8] else None,
                        "clean_sheets":    td[9],
                        "ppg":             round(float(td[10]), 2) if td[10] else None,
                        "wins":            td[11], "draws": td[12], "losses": td[13],
                    }
                }
            xg_stats = {
                "home_xg":  round(float(td[14]), 2) if td[14] else None,
                "away_xg":  round(float(td[15]), 2) if td[15] else None,
                "total_xg": round(float(td[16]), 2) if td[16] else None,
            }
            # Only populate h2h if there's actual historical data
            if td[17]:  # h2h_matches_count must be non-null and > 0
                h2h_stats = {
                    "matches":      td[17],
                    "home_wins":    td[18], "away_wins": td[19], "draws": td[20],
                    "avg_goals":    round(float(td[21]), 2) if td[21] else None,
                    "btts_rate":    round(float(td[22]) * 100, 1) if td[22] else None,
                    "over25_rate":  round(float(td[23]) * 100, 1) if td[23] else None,
                }
            standings = {
                "home_pos":  td[24], "away_pos":  td[25],
                "home_pts":  td[26], "away_pts":  td[27],
                "home_gd":   td[28], "away_gd":   td[29],
            }
            prediction = {
                "home_goals": round(float(td[30]), 2) if td[30] else None,
                "away_goals": round(float(td[31]), 2) if td[31] else None,
                "score":      td[32],
                "model_prob": round(float(td[33]), 3) if td[33] else None,
            }

        # ── 3. SofaScore fallback for form + H2H (up to 22 s) ──────
        if form_stats is None or h2h_stats is None:
            try:
                import asyncio as _aio
                ss_form, ss_h2h = await _aio.wait_for(
                    _fetch_sofascore_data(home_team, away_team, league),
                    timeout=22.0
                )
                if form_stats is None and ss_form:
                    form_stats = ss_form
                if h2h_stats is None and ss_h2h:
                    h2h_stats = ss_h2h
                # Persist fetched form/H2H to training_data so next request is instant
                if ss_form or ss_h2h:
                    try:
                        _hf = (ss_form or {}).get("home") or {}
                        _af = (ss_form or {}).get("away") or {}
                        _h2h = ss_h2h or {}
                        # Build odds_data JSON with recent match lists for pick cards
                        _odds_data = json.dumps({
                            "home_recent_matches": _hf.get("recent_matches") or [],
                            "away_recent_matches": _af.get("recent_matches") or [],
                            "h2h_recent_matches":  _h2h.get("recent_matches") or [],
                        })
                        _btts_val  = (_h2h.get("btts_rate") or 0) / 100 if _h2h.get("btts_rate") is not None else None
                        _o25_val   = (_h2h.get("over25_rate") or 0) / 100 if _h2h.get("over25_rate") is not None else None
                        # Check if a row already exists for this match
                        _existing_row = db_helper.execute("""
                            SELECT id, home_form_wins FROM training_data
                            WHERE home_team = %s AND away_team = %s AND match_date = %s
                            ORDER BY created_at DESC LIMIT 1
                        """, (home_team, away_team, match_date or None), fetch='one')
                        if _existing_row and _existing_row[1] is None:
                            # Row exists but has no form — UPDATE it with SofaScore data
                            db_helper.execute("""
                                UPDATE training_data SET
                                    home_form_goals_scored=%s, home_form_goals_conceded=%s,
                                    home_form_clean_sheets=%s, home_form_ppg=%s,
                                    home_form_wins=%s, home_form_draws=%s, home_form_losses=%s,
                                    away_form_goals_scored=%s, away_form_goals_conceded=%s,
                                    away_form_clean_sheets=%s, away_form_ppg=%s,
                                    away_form_wins=%s, away_form_draws=%s, away_form_losses=%s,
                                    h2h_matches_count=%s, h2h_home_wins=%s, h2h_away_wins=%s, h2h_draws=%s,
                                    h2h_avg_goals=%s, h2h_btts_rate=%s, h2h_over25_rate=%s,
                                    odds_data=%s, data_source='sofascore_ondemand'
                                WHERE id = %s
                            """, (
                                _hf.get("goals_scored"), _hf.get("goals_conceded"),
                                _hf.get("clean_sheets"), _hf.get("ppg"),
                                _hf.get("wins"), _hf.get("draws"), _hf.get("losses"),
                                _af.get("goals_scored"), _af.get("goals_conceded"),
                                _af.get("clean_sheets"), _af.get("ppg"),
                                _af.get("wins"), _af.get("draws"), _af.get("losses"),
                                _h2h.get("matches"), _h2h.get("home_wins"),
                                _h2h.get("away_wins"), _h2h.get("draws"),
                                _h2h.get("avg_goals"), _btts_val, _o25_val,
                                _odds_data, _existing_row[0],
                            ))
                            logger.info(f"✅ Updated training_data form/H2H for {home_team} vs {away_team} (id={_existing_row[0]})")
                        elif not _existing_row:
                            # No row at all — INSERT a new one
                            db_helper.execute("""
                                INSERT INTO training_data
                                    (home_team, away_team, league, match_date,
                                     home_form_goals_scored, home_form_goals_conceded,
                                     home_form_clean_sheets, home_form_ppg,
                                     home_form_wins, home_form_draws, home_form_losses,
                                     away_form_goals_scored, away_form_goals_conceded,
                                     away_form_clean_sheets, away_form_ppg,
                                     away_form_wins, away_form_draws, away_form_losses,
                                     h2h_matches_count, h2h_home_wins, h2h_away_wins, h2h_draws,
                                     h2h_avg_goals, h2h_btts_rate, h2h_over25_rate,
                                     odds_data, data_source)
                                VALUES (%s,%s,%s,%s,
                                        %s,%s,%s,%s,%s,%s,%s,
                                        %s,%s,%s,%s,%s,%s,%s,
                                        %s,%s,%s,%s,%s,%s,%s,
                                        %s,'sofascore_ondemand')
                            """, (
                                home_team, away_team, league, match_date or None,
                                _hf.get("goals_scored"), _hf.get("goals_conceded"),
                                _hf.get("clean_sheets"), _hf.get("ppg"),
                                _hf.get("wins"), _hf.get("draws"), _hf.get("losses"),
                                _af.get("goals_scored"), _af.get("goals_conceded"),
                                _af.get("clean_sheets"), _af.get("ppg"),
                                _af.get("wins"), _af.get("draws"), _af.get("losses"),
                                _h2h.get("matches"), _h2h.get("home_wins"),
                                _h2h.get("away_wins"), _h2h.get("draws"),
                                _h2h.get("avg_goals"), _btts_val, _o25_val,
                                _odds_data,
                            ))
                            logger.info(f"✅ Inserted training_data form/H2H for {home_team} vs {away_team}")
                        else:
                            logger.info(f"✅ Form/H2H already in training_data for {home_team} vs {away_team}, skipping")
                    except Exception as _save_err:
                        logger.warning(f"Could not persist SofaScore data: {_save_err}")
            except Exception as ss_err:
                logger.warning(f"SofaScore fallback skipped: {ss_err}")

        _result = {
            "match_id":   match_id,
            "home_team":  home_team,
            "away_team":  away_team,
            "league":     league,
            "match_date": match_date,
            "kickoff":    kickoff,
            "picks":      picks,
            "form":       form_stats,
            "h2h":        h2h_stats,
            "xg":         xg_stats,
            "standings":  standings,
            "prediction": prediction,
        }
        # ── Store in cache ─────────────────────────────────────
        import time as _t
        _match_scout_cache[_cache_key] = {"data": _result, "_ts": _t.time()}
        return _result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in match_scout {match_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/best-odds/today", tags=["Odds"])
async def get_today_best_odds():
    """
    Get all today's selections with best odds comparison.
    
    Returns a summary of all Value Singles for today with their best bookmaker odds,
    useful for line shopping and value identification.
    """
    try:
        today = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)
        
        rows = db_helper.execute("""
            SELECT 
                match_id, home_team, away_team, league, kickoff_time,
                market, selection, odds, model_prob, edge_percentage,
                odds_by_bookmaker, best_odds_value, best_odds_bookmaker, avg_odds, fair_odds
            FROM football_opportunities
            WHERE match_date >= %s AND match_date <= %s
            AND mode != 'TEST'
            AND market IN ('Value Single', 'over_under', 'btts', '1x2')
            ORDER BY edge_percentage DESC NULLS LAST
        """, (str(today), str(tomorrow)), fetch='all') or []
        
        picks = []
        for row in rows:
            odds_by_bookmaker = {}
            if row[10]:
                if isinstance(row[10], str):
                    try:
                        odds_by_bookmaker = json.loads(row[10])
                    except:
                        odds_by_bookmaker = {}
                elif isinstance(row[10], dict):
                    odds_by_bookmaker = row[10]
            
            top_bookmakers = []
            if odds_by_bookmaker:
                sorted_books = sorted(odds_by_bookmaker.items(), key=lambda x: x[1], reverse=True)
                top_bookmakers = [{'bookmaker': b, 'odds': o} for b, o in sorted_books[:5]]
            
            picks.append({
                'match_id': row[0],
                'match': f"{row[1]} vs {row[2]}",
                'league': row[3] or 'Unknown',
                'kickoff': row[4],
                'market': row[5],
                'selection': row[6],
                'current_odds': float(row[7]) if row[7] else None,
                'model_prob_pct': round(float(row[8]) * 100, 1) if row[8] else None,
                'ev_pct': round(float(row[9]), 2) if row[9] else None,
                'best_odds': float(row[11]) if row[11] else None,
                'best_bookmaker': row[12],
                'avg_odds': float(row[13]) if row[13] else None,
                'fair_odds': float(row[14]) if row[14] else None,
                'top_bookmakers': top_bookmakers
            })
        
        return {
            'picks': picks,
            'total_picks': len(picks),
            'date': str(today),
            'generated_at': datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Error in get_today_best_odds: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/performance", tags=["Analytics"])
async def get_performance_summary():
    """
    Get overall platform performance summary.
    
    Returns ROI, win rate, and profit by product type.
    """
    try:
        result = db_helper.execute("""
            SELECT 
                product,
                COUNT(*) as total_bets,
                SUM(CASE WHEN norm_result = 'WON' THEN 1 ELSE 0 END) as wins,
                SUM(stake) as total_staked,
                SUM(CASE WHEN norm_result = 'WON' THEN stake * odds ELSE 0 END) as returns
            FROM normalized_bets
            WHERE norm_result IN ('WON', 'LOST')
            GROUP BY product
            ORDER BY product
        """, fetch='all') or []
        
        products = []
        total_staked = 0
        total_returns = 0
        total_bets = 0
        total_wins = 0
        
        for row in result:
            staked = row[3] or 0
            returns = row[4] or 0
            profit = returns - staked
            roi = (profit / staked * 100) if staked > 0 else 0
            win_rate = (row[2] / row[1] * 100) if row[1] > 0 else 0
            
            products.append({
                'product': row[0],
                'total_bets': row[1],
                'wins': row[2],
                'win_rate': round(win_rate, 1),
                'roi': round(roi, 1),
                'profit': round(profit, 2)
            })
            
            total_staked += staked
            total_returns += returns
            total_bets += row[1]
            total_wins += row[2]
        
        overall_profit = total_returns - total_staked
        overall_roi = (overall_profit / total_staked * 100) if total_staked > 0 else 0
        overall_win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0
        
        return {
            'overall': {
                'total_bets': total_bets,
                'wins': total_wins,
                'win_rate': round(overall_win_rate, 1),
                'roi': round(overall_roi, 1),
                'profit': round(overall_profit, 2)
            },
            'by_product': products,
            'generated_at': datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Error in get_performance_summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# CLV (Closing Line Value) Endpoint
# =============================================================================

class CLVStatsResponse(BaseModel):
    avg_clv_all: Optional[float] = None
    avg_clv_last_100: Optional[float] = None
    positive_share: Optional[float] = None
    total_with_clv: int = 0
    generated_at: str

@app.get("/api/clv_stats", tags=["Analytics"])
async def get_clv_stats_endpoint():
    """
    Get Closing Line Value (CLV) statistics.
    Returns all CLV fields including recent_20 captures for the dashboard.
    """
    try:
        from clv_service import get_clv_stats
        stats = get_clv_stats()
        return JSONResponse(stats)
        
    except Exception as e:
        logger.error(f"Error in get_clv_stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/clv_breakdown", tags=["Analytics"])
async def get_clv_breakdown():
    """
    CLV breakdown by market + timing bucket.
    Used to identify which markets and timing patterns drive best CLV.
    """
    try:
        # Market breakdown
        market_rows = db_helper.execute("""
            SELECT
                market,
                COUNT(*)                                                                        AS total,
                COUNT(clv_pct)                                                                  AS with_clv,
                ROUND(100.0 * COUNT(clv_pct) / NULLIF(COUNT(*), 0), 1)                        AS coverage,
                ROUND(AVG(clv_pct)::numeric, 2)                                                AS avg_clv,
                ROUND(100.0 * SUM(CASE WHEN clv_pct > 0 THEN 1 ELSE 0 END)::numeric
                      / NULLIF(COUNT(clv_pct), 0), 1)                                         AS pos_rate,
                ROUND(100.0 * SUM(CASE WHEN steam_flag = 'early' THEN 1 ELSE 0 END)::numeric
                      / NULLIF(COUNT(clv_pct), 0), 1)                                         AS steam_early_rate
            FROM football_opportunities
            WHERE open_odds IS NOT NULL
            GROUP BY market
            ORDER BY with_clv DESC
        """, fetch='all') or []

        # Timing breakdown (hours before KO when pick was created)
        timing_rows = db_helper.execute("""
            SELECT
                CASE
                    WHEN (open_ts - kickoff_epoch) / 3600.0 < -12 THEN '>12h before KO'
                    WHEN (open_ts - kickoff_epoch) / 3600.0 < -6  THEN '6-12h before KO'
                    WHEN (open_ts - kickoff_epoch) / 3600.0 < -2  THEN '2-6h before KO'
                    ELSE '<2h before KO'
                END                                                                             AS timing_bucket,
                CASE
                    WHEN (open_ts - kickoff_epoch) / 3600.0 < -12 THEN 4
                    WHEN (open_ts - kickoff_epoch) / 3600.0 < -6  THEN 3
                    WHEN (open_ts - kickoff_epoch) / 3600.0 < -2  THEN 2
                    ELSE 1
                END                                                                             AS sort_key,
                COUNT(*)                                                                        AS total,
                COUNT(clv_pct)                                                                  AS with_clv,
                ROUND(100.0 * COUNT(clv_pct) / NULLIF(COUNT(*), 0), 1)                        AS coverage,
                ROUND(AVG(clv_pct)::numeric, 2)                                                AS avg_clv,
                ROUND(100.0 * SUM(CASE WHEN clv_pct > 0 THEN 1 ELSE 0 END)::numeric
                      / NULLIF(COUNT(clv_pct), 0), 1)                                         AS pos_rate
            FROM football_opportunities
            WHERE open_odds IS NOT NULL
              AND open_ts IS NOT NULL
              AND kickoff_epoch IS NOT NULL
              AND market = 'Value Single'
            GROUP BY 1, 2
            ORDER BY sort_key DESC
        """, fetch='all') or []

        # Steam stats
        steam_rows = db_helper.execute("""
            SELECT
                steam_flag,
                COUNT(*)                                AS n,
                ROUND(AVG(clv_pct)::numeric, 2)        AS avg_clv,
                ROUND(100.0 * SUM(CASE WHEN clv_pct > 0 THEN 1 ELSE 0 END)::numeric
                      / NULLIF(COUNT(*), 0), 1)         AS pos_rate
            FROM football_opportunities
            WHERE clv_pct IS NOT NULL AND steam_flag IS NOT NULL
            GROUP BY steam_flag
            ORDER BY n DESC
        """, fetch='all') or []

        return JSONResponse({
            "markets": [
                {
                    "market":           r[0],
                    "total":            r[1],
                    "with_clv":         r[2],
                    "coverage":         float(r[3]) if r[3] else 0,
                    "avg_clv":          float(r[4]) if r[4] else None,
                    "pos_rate":         float(r[5]) if r[5] else None,
                    "steam_early_rate": float(r[6]) if r[6] else None,
                }
                for r in market_rows
            ],
            "timing": [
                {
                    "bucket":   r[0],
                    "total":    r[2],
                    "with_clv": r[3],
                    "coverage": float(r[4]) if r[4] else 0,
                    "avg_clv":  float(r[5]) if r[5] else None,
                    "pos_rate": float(r[6]) if r[6] else None,
                }
                for r in timing_rows
            ],
            "steam": [
                {
                    "flag":     r[0],
                    "n":        r[1],
                    "avg_clv":  float(r[2]) if r[2] else None,
                    "pos_rate": float(r[3]) if r[3] else None,
                }
                for r in steam_rows
            ],
        })
    except Exception as e:
        logger.error(f"Error in get_clv_breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/injuries/upcoming", tags=["Analytics"])
async def get_upcoming_injuries(hours: int = 48):
    """
    Returns upcoming matches with known injury absences from the proactive injury cache.
    Polled every 6h from API-Football for Big 5 + European cups (next 48h).
    """
    try:
        from proactive_injury_poller import ProactiveInjuryPoller
        from api_football_client import APIFootballClient
        af_client = APIFootballClient()
        poller = ProactiveInjuryPoller(af_client, db_helper)
        summary = poller.get_upcoming_injury_summary(hours_ahead=hours)
        stats = poller.get_stats()
        return JSONResponse({
            "matches": summary,
            "meta": {
                "hours_ahead": hours,
                "total_matches": len(summary),
                **stats,
            }
        })
    except Exception as e:
        logger.error(f"Error in get_upcoming_injuries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/injuries/match", tags=["Analytics"])
async def get_match_injuries(home: str, away: str):
    """
    Returns injury report for a specific match (by team name, fuzzy match).
    Used by the dashboard and predictor to pre-check absences.
    """
    try:
        from proactive_injury_poller import ProactiveInjuryPoller
        from api_football_client import APIFootballClient
        af_client = APIFootballClient()
        poller = ProactiveInjuryPoller(af_client, db_helper)
        report = poller.get_injuries_for_match(home, away)
        return JSONResponse(report)
    except Exception as e:
        logger.error(f"Error in get_match_injuries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/hockey/stats", tags=["Analytics"])
async def get_hockey_stats():
    """Hockey stats from learning_bets for the Railway dashboard."""
    try:
        db = db_helper
        summary = db.execute("""
            SELECT sport_key,
                COUNT(*) FILTER (WHERE outcome IN ('won','lost')) AS settled,
                COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
                COUNT(*) FILTER (WHERE outcome = 'lost') AS losses,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END),0) AS profit,
                ROUND(AVG(CASE WHEN outcome IN ('won','lost') THEN odds END)::numeric,2) AS avg_odds
            FROM learning_bets
            WHERE sport_category = 'HOCKEY'
            GROUP BY sport_key ORDER BY settled DESC
        """, fetch='all')

        by_market = db.execute("""
            SELECT market,
                COUNT(*) FILTER (WHERE outcome IN ('won','lost')) AS settled,
                COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
                COUNT(*) FILTER (WHERE outcome = 'lost') AS losses,
                COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END),0) AS profit
            FROM learning_bets
            WHERE sport_category = 'HOCKEY'
            GROUP BY market ORDER BY settled DESC
        """, fetch='all')

        totals = db.execute("""
            SELECT COUNT(*) FILTER (WHERE outcome IN ('won','lost')) AS settled,
                   COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
                   COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                   COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END),0) AS profit
            FROM learning_bets WHERE sport_category = 'HOCKEY'
        """, fetch='one')

        upcoming = db.execute("""
            SELECT home_team, away_team, league, market, selection, line, odds,
                   TO_CHAR(commence_time AT TIME ZONE 'Europe/Stockholm', 'YYYY-MM-DD HH24:MI') AS ko
            FROM learning_bets
            WHERE sport_category = 'HOCKEY'
              AND status = 'pending'
              AND commence_time > NOW()
            ORDER BY commence_time ASC
            LIMIT 50
        """, fetch='all')

        def to_float(v):
            return float(v) if v is not None else 0.0

        LEAGUE_MAP = {
            'Icehockey Nhl': 'NHL', 'Icehockey Sweden Hockey League': 'SHL',
            'Icehockey Sweden Allsvenskan': 'Allsvenskan', 'Icehockey Ahl': 'AHL',
        }
        MARKET_MAP = {'h2h': 'Moneyline', 'totals': 'Over/Under', 'h2h_lay': 'Lay ML', 'spreads': 'Puck Line'}

        t = totals or (0, 0, 0, 0)
        settled, wins, pending, profit = int(t[0] or 0), int(t[1] or 0), int(t[2] or 0), to_float(t[3])
        hit_rate = round(wins / settled * 100, 1) if settled > 0 else 0

        def fmt_pick(sel, line):
            if line is not None:
                sign = f"+{float(line)}" if float(line) >= 0 else str(float(line))
                return f"{sel} ({sign})"
            return sel or "—"

        return JSONResponse({
            "totals": {"settled": settled, "wins": wins, "losses": settled - wins,
                       "pending": pending, "profit": profit, "hit_rate": hit_rate},
            "by_league": [{"sport_key": r[0], "settled": int(r[1] or 0), "wins": int(r[2] or 0),
                           "losses": int(r[3] or 0), "pending": int(r[4] or 0),
                           "profit": to_float(r[5]), "avg_odds": to_float(r[6])}
                          for r in (summary or [])],
            "by_market": [{"market": r[0], "settled": int(r[1] or 0), "wins": int(r[2] or 0),
                           "losses": int(r[3] or 0), "profit": to_float(r[4])}
                          for r in (by_market or [])],
            "upcoming": [{"home_team": r[0], "away_team": r[1],
                          "league": LEAGUE_MAP.get(r[2], r[2]),
                          "market": MARKET_MAP.get(r[3], r[3]),
                          "selection": fmt_pick(r[4], r[5]),
                          "odds": to_float(r[6]), "kickoff": r[7]}
                         for r in (upcoming or [])],
        })
    except Exception as e:
        logger.error(f"Error in get_hockey_stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/nba/stats", tags=["Analytics"])
async def get_nba_stats():
    """NBA game-level stats (Moneyline, Totals, AH) from learning_bets for the Railway dashboard."""
    try:
        db = db_helper
        MARKET_LABELS = {'h2h': 'Moneyline', 'totals': 'Totals (O/U)', 'spreads': 'AH / Spread'}

        by_market = db.execute("""
            SELECT market,
                COUNT(*) FILTER (WHERE outcome IN ('won','lost')) AS settled,
                COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
                COUNT(*) FILTER (WHERE outcome = 'lost') AS losses,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END),0) AS profit,
                ROUND(AVG(CASE WHEN outcome IN ('won','lost') THEN odds END)::numeric,2) AS avg_odds
            FROM learning_bets
            WHERE sport_category = 'NBA'
            GROUP BY market ORDER BY settled DESC
        """, fetch='all')

        totals_row = db.execute("""
            SELECT COUNT(*) FILTER (WHERE outcome IN ('won','lost')) AS settled,
                   COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
                   COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                   COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END),0) AS profit
            FROM learning_bets WHERE sport_category = 'NBA'
        """, fetch='one')

        upcoming = db.execute("""
            SELECT home_team, away_team, league, market, selection, line, odds,
                   TO_CHAR(commence_time AT TIME ZONE 'Europe/Stockholm', 'YYYY-MM-DD HH24:MI') AS ko
            FROM learning_bets
            WHERE sport_category = 'NBA'
              AND status = 'pending'
              AND commence_time > NOW()
            ORDER BY commence_time ASC
            LIMIT 50
        """, fetch='all')

        def to_float(v):
            return float(v) if v is not None else 0.0

        def fmt_pick(sel, line):
            if line is not None:
                sign = f"+{float(line)}" if float(line) >= 0 else str(float(line))
                return f"{sel} ({sign})"
            return sel or "—"

        t = totals_row or (0, 0, 0, 0)
        settled, wins, pending, profit = int(t[0] or 0), int(t[1] or 0), int(t[2] or 0), to_float(t[3])
        hit_rate = round(wins / settled * 100, 1) if settled > 0 else 0

        return JSONResponse({
            "totals": {"settled": settled, "wins": wins, "losses": settled - wins,
                       "pending": pending, "profit": profit, "hit_rate": hit_rate},
            "by_market": [{"market": MARKET_LABELS.get(r[0], r[0]),
                           "market_key": r[0],
                           "settled": int(r[1] or 0), "wins": int(r[2] or 0),
                           "losses": int(r[3] or 0), "pending": int(r[4] or 0),
                           "profit": to_float(r[5]), "avg_odds": to_float(r[6])}
                          for r in (by_market or [])],
            "upcoming": [{"home_team": r[0], "away_team": r[1],
                          "league": (r[2] or '').replace('Basketball Nba','NBA').replace('basketball_nba','NBA'),
                          "market": MARKET_LABELS.get(r[3], r[3]),
                          "selection": fmt_pick(r[4], r[5]),
                          "odds": to_float(r[6]), "kickoff": r[7]}
                         for r in (upcoming or [])],
        })
    except Exception as e:
        logger.error(f"Error in get_nba_stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/units/daily", tags=["Analytics"])
async def get_daily_units(days: int = 30):
    """
    Get daily profit/loss in units for the last N days.
    
    Parameters:
    - days: Number of days to look back (default 30)
    
    Returns:
    - daily_units: List of {date, units, bet_count} sorted by date desc
    - month_summary: Current month total units
    - best_day: Best performing day
    - worst_day: Worst performing day
    """
    try:
        from daily_units_service import get_daily_units as fetch_daily_units
        result = fetch_daily_units(days_back=days)
        result['generated_at'] = datetime.utcnow().isoformat() + "Z"
        return result
        
    except Exception as e:
        logger.error(f"Error in get_daily_units: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/bets/recent", tags=["Analytics"])
async def get_recent_bets(limit: int = 50, product: Optional[str] = None):
    """
    Get recent bets with CLV data for bet history display.
    
    Parameters:
    - limit: Maximum number of bets to return (default 50)
    - product: Filter by product type (optional)
    
    Returns list of bets with:
    - Basic bet info (teams, selection, odds, result)
    - CLV data (open_odds, close_odds, clv_pct)
    """
    try:
        query = """
            SELECT id, match_id, home_team, away_team, market, selection,
                   odds, open_odds, close_odds, clv_pct, outcome, profit_loss,
                   match_date, trust_level, edge_percentage
            FROM football_opportunities
            WHERE bet_placed = true
            ORDER BY timestamp DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, (limit,), fetch='all') or []
        
        bets = []
        for row in rows:
            bets.append({
                'id': row[0],
                'match_id': row[1],
                'home_team': row[2],
                'away_team': row[3],
                'market': row[4],
                'selection': row[5],
                'odds': row[6],
                'open_odds': row[7],
                'close_odds': row[8],
                'clv_pct': round(row[9], 2) if row[9] else None,
                'outcome': row[10],
                'profit_loss': row[11],
                'match_date': row[12],
                'trust_level': row[13],
                'ev': row[14]
            })
        
        return {
            'bets': bets,
            'count': len(bets),
            'generated_at': datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Error in get_recent_bets: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Monte Carlo Simulation Endpoint
# =============================================================================

from monte_carlo_simulator import simulate_match, calc_ev, fair_odds

class OneXTwoProb(BaseModel):
    home: float
    draw: float
    away: float

class SimulationResult(BaseModel):
    scores: Dict[str, float]
    one_x_two: OneXTwoProb
    btts_yes: float
    over_25: float
    over_35: float

class ValueHint(BaseModel):
    market: str
    selection: str
    model_prob: float
    market_odds: Optional[float] = None
    fair_odds: Optional[float] = None
    edge: float
    ev: float

class SimulationResponse(BaseModel):
    home_team: str
    away_team: str
    home_xg: float
    away_xg: float
    simulation: SimulationResult
    value_hints: List[ValueHint]
    top_scores: List[Dict[str, Any]]

@app.get("/api/simulate", response_model=SimulationResponse, tags=["Monte Carlo"])
async def simulate_match_endpoint(
    home_xg: float = 1.5,
    away_xg: float = 1.2,
    home_team: str = "Home",
    away_team: str = "Away",
    n_sim: int = 10000,
    home_odds: Optional[float] = None,
    draw_odds: Optional[float] = None,
    away_odds: Optional[float] = None,
    over25_odds: Optional[float] = None,
    btts_odds: Optional[float] = None
):
    """
    Run Monte Carlo simulation for a match.
    
    Simulates 10,000 matches using Poisson distribution and returns:
    - Exact score probabilities
    - 1X2, BTTS, Over/Under probabilities
    - Value hints comparing model vs market odds
    """
    try:
        sim = simulate_match(home_xg, away_xg, n_sim=n_sim)
        
        value_hints = []
        
        p1 = sim["one_x_two"]["1"]
        px = sim["one_x_two"]["X"]
        p2 = sim["one_x_two"]["2"]
        
        if home_odds:
            ev1 = calc_ev(p1, home_odds)
            value_hints.append(ValueHint(
                market="1X2", selection="1",
                model_prob=p1, market_odds=home_odds,
                fair_odds=fair_odds(p1),
                edge=ev1["edge"], ev=ev1["ev"]
            ))
        
        if draw_odds:
            evx = calc_ev(px, draw_odds)
            value_hints.append(ValueHint(
                market="1X2", selection="X",
                model_prob=px, market_odds=draw_odds,
                fair_odds=fair_odds(px),
                edge=evx["edge"], ev=evx["ev"]
            ))
        
        if away_odds:
            ev2 = calc_ev(p2, away_odds)
            value_hints.append(ValueHint(
                market="1X2", selection="2",
                model_prob=p2, market_odds=away_odds,
                fair_odds=fair_odds(p2),
                edge=ev2["edge"], ev=ev2["ev"]
            ))
        
        if over25_odds:
            ev_over = calc_ev(sim["over_25"], over25_odds)
            value_hints.append(ValueHint(
                market="OVER_2_5", selection="over",
                model_prob=sim["over_25"], market_odds=over25_odds,
                fair_odds=fair_odds(sim["over_25"]),
                edge=ev_over["edge"], ev=ev_over["ev"]
            ))
        
        if btts_odds:
            ev_btts = calc_ev(sim["btts_yes"], btts_odds)
            value_hints.append(ValueHint(
                market="BTTS", selection="yes",
                model_prob=sim["btts_yes"], market_odds=btts_odds,
                fair_odds=fair_odds(sim["btts_yes"]),
                edge=ev_btts["edge"], ev=ev_btts["ev"]
            ))
        
        value_hints.sort(key=lambda x: x.ev, reverse=True)
        
        sorted_scores = sorted(sim["scores"].items(), key=lambda x: x[1], reverse=True)[:5]
        top_scores = [
            {"score": score, "probability": prob, "fair_odds": fair_odds(prob)}
            for score, prob in sorted_scores
        ]
        
        return SimulationResponse(
            home_team=home_team,
            away_team=away_team,
            home_xg=home_xg,
            away_xg=away_xg,
            simulation=SimulationResult(
                scores=sim["scores"],
                one_x_two=OneXTwoProb(
                    home=sim["one_x_two"]["1"],
                    draw=sim["one_x_two"]["X"],
                    away=sim["one_x_two"]["2"]
                ),
                btts_yes=sim["btts_yes"],
                over_25=sim["over_25"],
                over_35=sim["over_35"]
            ),
            value_hints=value_hints,
            top_scores=top_scores
        )
        
    except Exception as e:
        logger.error(f"Error in simulate_match: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Daily Card Endpoint - Central Router Integration
# =============================================================================

class DailyCardSummary(BaseModel):
    total_singles: int
    total_parlays: int
    total_bets: int
    average_ev: float
    by_trust_tier: Dict[str, int]
    by_market_type: Dict[str, int]
    by_product: Dict[str, int]
    l1_count: int
    l2_count: int
    l3_count: int

class ProfileBoostDetails(BaseModel):
    """Details from Profile Boost Engine."""
    raw_ev: Optional[float] = None
    boosted_ev: Optional[float] = None
    raw_confidence: Optional[float] = None
    boosted_confidence: Optional[float] = None
    boost_score: Optional[float] = None
    top_factors: Optional[List[Dict[str, Any]]] = None


class MarketWeightDetails(BaseModel):
    """Details from Market Weight Engine."""
    market_weight: Optional[float] = None
    final_ev: Optional[float] = None
    confidence_factor: Optional[float] = None


class DailyCardBet(BaseModel):
    fixture_id: str
    match: str
    market: str
    market_key: str
    market_type: str
    product_type: str
    selection: str
    line: Optional[float]
    odds: float
    probability: float
    ev: float
    confidence: float
    trust_tier: str
    drift_score: Optional[float]
    profile_boost: Optional[ProfileBoostDetails] = None
    market_weight: Optional[MarketWeightDetails] = None


class HiddenValueBet(BaseModel):
    """A hidden value / soft edge pick."""
    fixture_id: str
    match: str
    home_team: str
    away_team: str
    market_key: str
    selection: str
    odds: float
    raw_ev: float
    boosted_ev: float
    final_ev: float
    raw_confidence: float
    boosted_confidence: float
    boost_score: float
    market_weight: float
    soft_edge_score: float
    category: str
    trust_tier: str
    reason: str
    profile_boost_factors: Optional[List[Dict[str, Any]]] = None

class RoutingStats(BaseModel):
    total_picks: int = 0
    by_product: Dict[str, int] = {}
    by_market: Dict[str, int] = {}
    by_trust_tier: Dict[str, int] = {}
    average_ev: float = 0.0
    products_covered: List[str] = []
    market_diversity: int = 0
    balance_score: float = 0.0

class SyndicateEngineStatus(BaseModel):
    """Status of the syndicate engines."""
    profile_boost_engine: bool = True
    market_weight_engine: bool = True
    hidden_value_scanner: bool = True
    version: str = "1.0"


class DailyCardResponse(BaseModel):
    date: str
    value_singles: List[DailyCardBet]
    totals: List[DailyCardBet]
    btts: List[DailyCardBet]
    corners: List[DailyCardBet]
    shots: List[DailyCardBet]
    cards: List[DailyCardBet]
    corner_handicaps: List[DailyCardBet]
    parlays: List[Dict]
    hidden_value_picks: List[HiddenValueBet] = []
    summary: DailyCardSummary
    routing_stats: Optional[RoutingStats] = None
    markets_covered: List[str] = []
    syndicate_engines: Optional[SyndicateEngineStatus] = None

@app.get("/api/daily_card", response_model=DailyCardResponse)
async def get_daily_card():
    """
    Get the complete daily betting card with all products.
    
    Returns predictions from all market engines:
    - Value Singles (ML, AH, DC, DNB)
    - Totals (Over/Under Goals)
    - BTTS (Both Teams To Score)
    - Corners (Match/Team Totals)
    - Shots (Team Shots Over/Under)
    - Cards (Match/Team Cards)
    - Corner Handicaps
    - Parlays (Multi-Match, ML)
    
    Each bet includes:
    - Trust tier (L1_HIGH_TRUST, L2_MEDIUM_TRUST, L3_SOFT_VALUE)
    - Expected Value (EV)
    - Model probability and confidence
    - Odds drift score (when available)
    """
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        all_bets = []
        
        value_singles_query = """
            SELECT match_id, home_team, away_team, market, selection,
                   odds, edge_percentage as ev, confidence, model_prob, trust_level
            FROM football_opportunities
            WHERE match_date LIKE %s AND mode != 'TEST'
            AND status = 'pending'
            ORDER BY edge_percentage DESC
            LIMIT 50
        """
        
        vs_rows = db_helper.execute(value_singles_query, (f"{today}%",)) or []
        value_singles = []
        for row in vs_rows:
            value_singles.append({
                "fixture_id": str(row.get("match_id", "")),
                "match": f"{row.get('home_team', '')} vs {row.get('away_team', '')}",
                "market": row.get("market", ""),
                "market_key": row.get("market", ""),
                "market_type": "ML" if "WIN" in row.get("market", "") else "TOTALS",
                "product_type": "VALUE_SINGLES",
                "selection": row.get("selection", ""),
                "line": None,
                "odds": float(row.get("odds", 0)),
                "probability": float(row.get("model_prob", 0)) * 100,
                "ev": float(row.get("ev", 0)),
                "confidence": float(row.get("confidence", 0)) * 100,
                "trust_tier": row.get("trust_level", "L3_SOFT_VALUE"),
                "drift_score": None
            })
        
        totals = [b for b in value_singles if "OVER" in b.get("market", "").upper() or "UNDER" in b.get("market", "").upper()]
        btts = [b for b in value_singles if "BTTS" in b.get("market", "").upper()]
        corners = [b for b in value_singles if "CORNER" in b.get("market", "").upper()]
        cards = [b for b in value_singles if "CARD" in b.get("market", "").upper()]
        remaining_singles = [b for b in value_singles if b not in totals + btts + corners + cards]
        
        by_trust = {"L1_HIGH_TRUST": 0, "L2_MEDIUM_TRUST": 0, "L3_SOFT_VALUE": 0}
        by_market = {}
        by_product = {"VALUE_SINGLES": len(remaining_singles), "TOTALS": len(totals), 
                      "BTTS": len(btts), "CORNERS": len(corners), "CARDS": len(cards)}
        
        for bet in value_singles:
            tier = bet.get("trust_tier", "L3_SOFT_VALUE")
            by_trust[tier] = by_trust.get(tier, 0) + 1
            mtype = bet.get("market_type", "UNKNOWN")
            by_market[mtype] = by_market.get(mtype, 0) + 1
        
        total_bets = len(value_singles)
        avg_ev = sum(b.get("ev", 0) for b in value_singles) / max(1, total_bets)
        
        summary = DailyCardSummary(
            total_singles=total_bets,
            total_parlays=0,
            total_bets=total_bets,
            average_ev=round(avg_ev, 1),
            by_trust_tier=by_trust,
            by_market_type=by_market,
            by_product=by_product,
            l1_count=by_trust.get("L1_HIGH_TRUST", 0),
            l2_count=by_trust.get("L2_MEDIUM_TRUST", 0),
            l3_count=by_trust.get("L3_SOFT_VALUE", 0)
        )
        
        routing_stats = RoutingStats(
            total_picks=total_bets,
            by_product=by_product,
            by_market=by_market,
            by_trust_tier=by_trust,
            average_ev=round(avg_ev, 1),
            products_covered=list(by_product.keys()),
            market_diversity=len(by_market),
            balance_score=50.0
        )
        
        return DailyCardResponse(
            date=str(today),
            value_singles=[DailyCardBet(**b) for b in remaining_singles],
            totals=[DailyCardBet(**b) for b in totals],
            btts=[DailyCardBet(**b) for b in btts],
            corners=[DailyCardBet(**b) for b in corners],
            shots=[],
            cards=[DailyCardBet(**b) for b in cards],
            corner_handicaps=[],
            parlays=[],
            hidden_value_picks=[],
            summary=summary,
            routing_stats=routing_stats,
            markets_covered=list(by_product.keys()),
            syndicate_engines=SyndicateEngineStatus()
        )
        
    except Exception as e:
        logger.error(f"Error getting daily card: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market_stats")
async def get_market_stats():
    """
    Get ROI statistics broken down by market type.
    """
    try:
        query = """
            SELECT 
                market,
                COUNT(*) as total_bets,
                SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) as losses,
                AVG(edge_percentage) as avg_ev,
                SUM(CASE WHEN status = 'won' THEN odds - 1 ELSE -1 END) as profit_units
            FROM football_opportunities
            WHERE status IN ('won', 'lost')
            GROUP BY market
            ORDER BY profit_units DESC
        """
        
        rows = db_helper.execute(query) or []
        
        stats = []
        for row in rows:
            total = row.get("total_bets", 0)
            wins = row.get("wins", 0)
            profit = row.get("profit_units", 0)
            
            stats.append({
                "market": row.get("market", ""),
                "total_bets": total,
                "wins": wins,
                "losses": row.get("losses", 0),
                "hit_rate": round(wins / max(1, total) * 100, 1),
                "avg_ev": round(float(row.get("avg_ev", 0)), 1),
                "profit_units": round(float(profit), 2),
                "roi": round(float(profit) / max(1, total) * 100, 1)
            })
        
        return {"market_stats": stats, "generated_at": datetime.utcnow().isoformat()}
        
    except Exception as e:
        logger.error(f"Error getting market stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Syndicate Engines Endpoints
# =============================================================================

@app.get("/api/syndicate/status")
async def get_syndicate_status():
    """
    Get status of all syndicate engines:
    - Profile Boost Engine
    - Market Weight Engine
    - Hidden Value Scanner
    """
    try:
        from profile_boost_engine import ProfileBoostEngine
        from market_weight_engine import MarketWeightEngine
        from hidden_value_scanner import HiddenValueScanner
        from profile_boost_config import get_profile_boost_config
        from market_weight_config import get_market_weight_config
        from hidden_value_config import get_hidden_value_config
        
        pb_config = get_profile_boost_config()
        mw_config = get_market_weight_config()
        hv_config = get_hidden_value_config()
        
        return {
            "status": "operational",
            "version": "1.0",
            "engines": {
                "profile_boost": {
                    "active": True,
                    "alpha_ev": pb_config.alpha_ev,
                    "beta_confidence": pb_config.beta_confidence,
                    "features": list(pb_config.feature_weights.keys()),
                },
                "market_weight": {
                    "active": True,
                    "window_days": mw_config.rolling_window_days,
                    "weight_range": [mw_config.min_weight, mw_config.max_weight],
                    "markets_tracked": len(mw_config.market_group_mapping),
                },
                "hidden_value": {
                    "active": True,
                    "ev_range": hv_config.ev_near_miss_range,
                    "max_picks_per_day": hv_config.max_picks_per_day,
                    "min_score": hv_config.min_soft_edge_score,
                },
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting syndicate status: {e}")
        return {
            "status": "error",
            "error": str(e),
            "generated_at": datetime.utcnow().isoformat(),
        }


@app.post("/api/syndicate/boost")
async def calculate_profile_boost(
    base_ev: float,
    base_confidence: float,
    market_type: str,
    tempo_index: float = 1.0,
    is_derby: bool = False,
    referee_cards_pg: float = 3.5,
):
    """
    Calculate profile boost for a pick (for testing/debugging).
    
    Returns the boosted EV and confidence with explanation.
    """
    try:
        from profile_boost_engine import ProfileBoostEngine
        
        engine = ProfileBoostEngine()
        
        context = {
            "tempo_index": tempo_index,
            "is_derby": is_derby,
            "referee_stats": {"cards_per_match": referee_cards_pg},
            "wing_play_index": 1.0,
            "formation_aggression": 1.0,
            "pressure_index": 1.0,
            "form_momentum": 0,
        }
        
        result = engine.calculate_boost(base_ev, base_confidence, market_type, context)
        
        return {
            "market_type": market_type,
            "raw_ev": round(result.raw_ev * 100, 2),
            "boosted_ev": round(result.boosted_ev * 100, 2),
            "raw_confidence": round(result.raw_confidence * 100, 1),
            "boosted_confidence": round(result.boosted_confidence * 100, 1),
            "boost_score": round(result.boost_score, 3),
            "top_factors": [
                {"factor": f[0], "score": round(f[1], 3)}
                for f in result.contributing_factors
            ],
        }
    except Exception as e:
        logger.error(f"Error calculating profile boost: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/syndicate/market_weights")
async def get_market_weights():
    """
    Get current market weights based on historical performance.
    """
    try:
        from market_weight_engine import MarketWeightEngine
        
        engine = MarketWeightEngine()
        weights = engine.get_all_weights()
        
        result = {}
        for market_key, wr in weights.items():
            result[market_key] = {
                "weight": round(wr.weight, 3),
                "confidence_factor": round(wr.confidence_factor, 2),
                "group": wr.market_group,
                "stats": None,
            }
            if wr.stats:
                result[market_key]["stats"] = {
                    "total_bets": wr.stats.total_bets,
                    "roi": round(wr.stats.roi * 100, 1),
                    "win_rate": round(wr.stats.win_rate * 100, 1),
                }
        
        return {
            "market_weights": result,
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting market weights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# LIVE LEARNING MODE Endpoints
# =============================================================================

@app.get("/api/live_learning/status")
async def get_live_learning_status():
    """
    Get current LIVE LEARNING MODE status and configuration.
    """
    try:
        from live_learning_config import get_live_learning_config, is_live_learning_active
        from live_learning_tracker import get_live_learning_tracker
        
        config = get_live_learning_config()
        tracker = get_live_learning_tracker()
        session_stats = tracker.get_session_stats()
        
        return {
            "mode": "LIVE_LEARNING",
            "active": is_live_learning_active(),
            "version": config.version,
            "activated_at": config.activated_at.isoformat() if config.activated_at else None,
            "session_stats": session_stats,
            "config": {
                "capture_all_picks": config.capture_all_picks,
                "capture_trust_tiers": config.capture_trust_tiers,
                "enable_clv_tracking": config.enable_clv_tracking,
                "ev_filter_enabled": config.ev_filter_enabled,
                "unit_based_tracking": config.unit_based_tracking,
                "market_weight_learning_enabled": config.market_weight_learning_enabled,
            },
            "syndicate_engines": {
                "profile_boost": config.enable_profile_boost,
                "market_weight": config.enable_market_weight,
                "hidden_value_scanner": config.enable_hidden_value_scanner,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting live learning status: {e}")
        return {
            "mode": "LIVE_LEARNING",
            "active": True,
            "error": str(e),
            "generated_at": datetime.utcnow().isoformat(),
        }


@app.get("/api/live_learning/progress")
async def get_live_learning_progress():
    """
    Get LIVE LEARNING MODE progress with results by trust tier.
    """
    try:
        from live_learning_tracker import get_live_learning_tracker
        
        tracker = get_live_learning_tracker()
        progress = tracker.get_learning_progress()
        
        return progress
        
    except Exception as e:
        logger.error(f"Error getting live learning progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/live_learning/picks")
async def get_live_learning_picks(
    trust_tier: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """
    Get picks captured in LIVE LEARNING MODE.
    
    Optional filters:
    - trust_tier: L1_HIGH_TRUST, L2_MEDIUM_TRUST, L3_SOFT_VALUE, HIDDEN_VALUE
    - status: pending, won, lost
    - limit: max number of picks to return
    """
    try:
        query = """
            SELECT 
                match_id, home_team, away_team, league, match_date, kickoff_time,
                market, selection, odds, trust_level,
                open_odds, close_odds, clv_pct,
                raw_ev, boosted_ev, weighted_ev,
                profile_boost_score, profile_boost_factors, market_weight,
                hidden_value_score, hidden_value_status,
                status, profit_loss, model_prob, confidence
            FROM football_opportunities
            WHERE mode = 'LIVE_LEARNING'
        """
        params = []
        
        if trust_tier:
            query += " AND trust_level = %s"
            params.append(trust_tier)
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        rows = db_helper.execute(query, tuple(params)) or []
        
        picks = []
        for row in rows:
            picks.append({
                "match_id": row.get("match_id"),
                "match": f"{row.get('home_team')} vs {row.get('away_team')}",
                "league": row.get("league"),
                "match_date": row.get("match_date"),
                "market": row.get("market"),
                "selection": row.get("selection"),
                "odds": float(row.get("odds", 0)),
                "trust_tier": row.get("trust_level"),
                "clv": {
                    "open_odds": float(row.get("open_odds", 0) or 0),
                    "close_odds": float(row.get("close_odds", 0) or 0),
                    "clv_pct": float(row.get("clv_pct", 0) or 0),
                },
                "ev": {
                    "raw": float(row.get("raw_ev", 0) or 0) * 100,
                    "boosted": float(row.get("boosted_ev", 0) or 0) * 100,
                    "weighted": float(row.get("weighted_ev", 0) or 0) * 100,
                },
                "syndicate": {
                    "profile_boost_score": float(row.get("profile_boost_score", 0) or 0),
                    "market_weight": float(row.get("market_weight", 1) or 1),
                    "hidden_value_score": float(row.get("hidden_value_score", 0) or 0) if row.get("hidden_value_score") else None,
                    "hidden_value_status": row.get("hidden_value_status"),
                },
                "status": row.get("status"),
                "profit_units": float(row.get("profit_loss", 0) or 0),
                "model_prob": float(row.get("model_prob", 0) or 0) * 100,
                "confidence": float(row.get("confidence", 0) or 0),
            })
        
        return {
            "mode": "LIVE_LEARNING",
            "picks": picks,
            "count": len(picks),
            "filters": {
                "trust_tier": trust_tier,
                "status": status,
                "limit": limit,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error getting live learning picks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/live_learning/settle")
async def settle_live_learning_pick(
    match_id: str,
    market: str,
    selection: str,
    won: bool,
    closing_odds: Optional[float] = None
):
    """
    Settle a LIVE LEARNING pick result.
    
    - Calculates units profit/loss
    - Updates CLV if closing_odds provided
    - Triggers market weight learning
    """
    try:
        from live_learning_tracker import get_live_learning_tracker
        
        tracker = get_live_learning_tracker()
        
        if closing_odds:
            tracker.update_clv(match_id, market, selection, closing_odds)
        
        result = tracker.settle_result(match_id, market, selection, won, closing_odds)
        
        return result
        
    except Exception as e:
        logger.error(f"Error settling pick: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Discord ROI/Stats Webhook
# =============================================================================

@app.get("/api/discord/stats")
async def send_discord_stats_endpoint():
    """
    Manually trigger Discord ROI/stats update.
    Sends current performance metrics to Discord webhook.
    """
    try:
        from discord_roi_webhook import send_discord_stats, get_roi_stats
        
        stats = get_roi_stats()
        success = send_discord_stats("📊 Manual stats update requested")
        
        return {
            "success": success,
            "stats_preview": {
                "all_time_roi": stats.get("all_time", {}).get("roi", 0),
                "all_time_units": stats.get("all_time", {}).get("units", 0),
                "pending": stats.get("pending", 0)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error sending Discord stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/picks/today")
async def get_today_picks():
    """
    Get picks (PROD + VALUE_OPP) for the next 48h — today + tomorrow.
    Returns upcoming, live, and settled picks. PROD is preferred over VALUE_OPP
    when both exist for the same match/market (DISTINCT ON ordering).
    """
    try:
        from datetime import date, timezone, timedelta
        import time

        now_utc = datetime.utcnow()
        day_start = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0)

        today_str = day_start.strftime('%Y-%m-%d')
        tomorrow_str = (day_start + timedelta(days=2)).strftime('%Y-%m-%d')  # 48h window
        now_epoch = int(now_utc.timestamp())
        cutoff_epoch = now_epoch - 14400  # 4 hours after kickoff → move to history

        rows = db_helper.execute("""
            SELECT * FROM (
                SELECT DISTINCT ON (home_team, away_team, market)
                    id, home_team, away_team, market, selection, odds,
                    edge_percentage, confidence, outcome, profit_loss,
                    odds_by_bookmaker, best_odds_value, best_odds_bookmaker,
                    league, trust_level, kickoff_time, match_date,
                    open_odds, clv_pct, mode,
                    model_prob, disagreement, clv_status, hidden_value_status,
                    timestamp, kickoff_epoch, clv_score, clv_tier
                FROM football_opportunities
                WHERE (
                    mode IN ('PROD', 'VALUE_OPP')
                    OR market IN ('Corners', 'Cards')
                )
                  AND (outcome IS NULL OR outcome = '' OR outcome IN ('pending', 'unknown'))
                  AND match_date >= %s
                  AND match_date < %s
                  AND (
                      (kickoff_epoch IS NOT NULL AND kickoff_epoch > %s)
                      OR (kickoff_epoch IS NULL AND (
                          kickoff_time IS NULL
                          OR match_date IS NULL
                          OR NOT (kickoff_time ~ '^\d{2}:\d{2}')
                          OR (match_date::date + kickoff_time::time) > NOW() - INTERVAL '4 hours'
                      ))
                  )
                ORDER BY home_team, away_team, market,
                         (CASE WHEN mode='PROD' THEN 0 ELSE 1 END),
                         COALESCE(edge_percentage, 0) DESC,
                         id DESC
            ) sub
            ORDER BY kickoff_epoch ASC NULLS LAST, id DESC
        """, (today_str, tomorrow_str, cutoff_epoch), fetch='all') or []

        picks = []
        for r in rows:
            outcome = (r[8] or '').upper()
            status = 'upcoming'
            if outcome in ('WON', 'WIN'):
                status = 'won'
            elif outcome in ('LOST', 'LOSS'):
                status = 'lost'
            elif outcome == 'VOID':
                status = 'void'

            ko_time = r[15]
            match_date = str(r[16]) if r[16] else ''
            kickoff_epoch_val = r[25]

            ko_str = ''
            kickoff_epoch_iso = ''   # UTC ISO built from epoch when available
            if kickoff_epoch_val:
                try:
                    import pytz
                    sthlm = pytz.timezone('Europe/Stockholm')
                    dt_utc = datetime.utcfromtimestamp(kickoff_epoch_val).replace(tzinfo=pytz.utc)
                    ko_str = dt_utc.astimezone(sthlm).strftime('%H:%M')
                    kickoff_epoch_iso = dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
                except Exception:
                    ko_str = ''
            if not ko_str and ko_time:
                ko_str = str(ko_time)[:5] if len(str(ko_time)) >= 5 else str(ko_time)
            if not ko_str and match_date:
                ko_str = match_date

            market_icons = {
                'OVER_UNDER': '⚽', 'CORNERS': '⛳', 'CARDS': '🟨',
                'BTTS': '🎯', 'HOME_WIN': '🏠', 'AWAY_WIN': '✈️',
                'DRAW': '🤝', 'VALUE_SINGLE': '💎', 'DOUBLE_CHANCE': '🛡️',
            }
            mkt = (r[3] or '').upper()
            icon = next((v for k, v in market_icons.items() if k in mkt), '⚽')

            # Real EV: (model_prob - implied_prob) × 100  — not the capped DB value
            model_p = float(r[20]) if r[20] else None
            odds_f  = float(r[5])  if r[5]  else None
            if model_p and odds_f and odds_f > 1.0:
                ev_raw = (model_p - 1.0 / odds_f) * 100
                is_outlier = ev_raw > 40.0
                ev_val = round(min(ev_raw, 40.0), 1)
            else:
                ev_raw = float(r[6]) if r[6] else 0
                is_outlier = ev_raw > 40.0
                ev_val = round(min(ev_raw, 40.0), 1)

            book = r[12] or ''
            mode_val = r[19] or 'PROD'
            layer = 'PRO PICK' if mode_val == 'PROD' else 'VALUE OPP'

            # Build full ISO kickoff string — prefer UTC from epoch (avoids midnight date bug)
            if kickoff_epoch_iso:
                kickoff_iso = kickoff_epoch_iso
            elif match_date and ko_str and ':' in ko_str:
                kickoff_iso = f"{match_date}T{ko_str}:00"
            elif match_date:
                kickoff_iso = match_date
            else:
                kickoff_iso = ''

            picks.append({
                'id': r[0],
                'home_team': r[1] or '',
                'away_team': r[2] or '',
                'market': r[3] or '',
                'selection': r[4] or '',
                'odds': float(r[5]) if r[5] else 0,
                'edge_pct': ev_val,
                'ev_pct': ev_val,
                'ev': ev_val,
                'confidence': round(float(r[7]), 2) if r[7] else 0,
                'outcome': outcome,
                'status': status,
                'profit_loss': round(float(r[9]), 2) if r[9] else None,
                'odds_by_bookmaker': r[10],
                'best_odds_value': float(r[11]) if r[11] else None,
                'best_odds_bookmaker': book,
                'bookmaker': book,
                'best_book': book,
                'league': r[13] or '',
                'trust_level': r[14] or '',
                'kickoff_str': ko_str,
                'kickoff': kickoff_iso,
                'kickoff_time': kickoff_iso,
                'match_date': match_date,
                'open_odds': float(r[17]) if r[17] else None,
                'clv_pct': round(float(r[18]), 2) if r[18] else None,
                'icon': icon,
                'layer': layer,
                'badge': layer,
                'mode': mode_val,
                'model_prob': round(float(r[20]), 3) if r[20] else None,
                'disagreement': round(float(r[21]), 3) if r[21] else None,
                'clv_status': r[22] or None,
                'hidden_value_status': r[23] or None,
                'created_ts': int(r[24]) if r[24] else None,
                'age_minutes': int((time.time() - int(r[24])) / 60) if r[24] else None,
                'is_outlier': is_outlier,
            })

        # ── Embed training_data for all matches in ONE batch query ──
        # Collect unique (home, away, date) combos
        _uniq_matches = list({
            (p['home_team'], p['away_team'], p['match_date'])
            for p in picks
            if p['home_team'] and p['away_team'] and p['match_date']
        })
        _td_map = {}
        if _uniq_matches:
            try:
                _placeholders = ",".join(
                    ["(%s,%s,%s)"] * len(_uniq_matches)
                )
                _flat = [v for tup in _uniq_matches for v in tup]
                _td_rows = db_helper.execute(f"""
                    SELECT home_team, away_team, match_date,
                           home_form_goals_scored, home_form_goals_conceded,
                           home_form_clean_sheets, home_form_ppg,
                           home_form_wins, home_form_draws, home_form_losses,
                           away_form_goals_scored, away_form_goals_conceded,
                           away_form_clean_sheets, away_form_ppg,
                           away_form_wins, away_form_draws, away_form_losses,
                           home_xg, away_xg, total_xg,
                           h2h_matches_count, h2h_home_wins, h2h_away_wins, h2h_draws,
                           h2h_avg_goals, h2h_btts_rate, h2h_over25_rate,
                           home_position, away_position, home_points, away_points,
                           home_goal_diff, away_goal_diff,
                           predicted_home_goals, predicted_away_goals, predicted_score,
                           model_probability, odds_data
                    FROM training_data
                    WHERE (home_team, away_team, match_date) IN ({_placeholders})
                    ORDER BY created_at DESC
                """, _flat, fetch='all') or []
                # Keep only the most recent row per match
                for _tr in _td_rows:
                    _key = (_tr[0], _tr[1], str(_tr[2]))
                    if _key not in _td_map:
                        _td_map[_key] = _tr
            except Exception as _td_err:
                logger.warning(f"training_data batch fetch failed: {_td_err}")

        # Attach scout_data to each pick
        for p in picks:
            _key = (p['home_team'], p['away_team'], p['match_date'])
            _tr = _td_map.get(_key)
            _form = None; _h2h = None; _xg = None; _std = None; _pred = None
            if _tr:
                # Parse odds_data JSON (index 37) for recent match lists
                _odds_payload = {}
                try:
                    _od_raw = _tr[37]
                    if _od_raw:
                        _odds_payload = json.loads(_od_raw) if isinstance(_od_raw, str) else _od_raw
                except Exception:
                    pass
                _home_recent = _odds_payload.get('home_recent_matches', [])
                _away_recent = _odds_payload.get('away_recent_matches', [])
                _h2h_recent  = _odds_payload.get('h2h_recent_matches', [])

                _form_has = any(_tr[i] is not None for i in [3,4,6,7,8,9,10,11,13,14,15,16])
                if _form_has or _home_recent or _away_recent:
                    _form = {
                        "home": {"goals_scored": round(float(_tr[3]),2) if _tr[3] else None,
                                 "goals_conceded": round(float(_tr[4]),2) if _tr[4] else None,
                                 "clean_sheets": _tr[5],
                                 "ppg": round(float(_tr[6]),2) if _tr[6] else None,
                                 "wins": _tr[7], "draws": _tr[8], "losses": _tr[9],
                                 "recent_matches": _home_recent or None},
                        "away": {"goals_scored": round(float(_tr[10]),2) if _tr[10] else None,
                                 "goals_conceded": round(float(_tr[11]),2) if _tr[11] else None,
                                 "clean_sheets": _tr[12],
                                 "ppg": round(float(_tr[13]),2) if _tr[13] else None,
                                 "wins": _tr[14], "draws": _tr[15], "losses": _tr[16],
                                 "recent_matches": _away_recent or None},
                    }
                _xg = {"home_xg": round(float(_tr[17]),2) if _tr[17] else None,
                       "away_xg": round(float(_tr[18]),2) if _tr[18] else None,
                       "total_xg": round(float(_tr[19]),2) if _tr[19] else None}
                if _tr[20] or _h2h_recent:
                    _h2h = {"matches": _tr[20], "home_wins": _tr[21],
                            "away_wins": _tr[22], "draws": _tr[23],
                            "avg_goals": round(float(_tr[24]),2) if _tr[24] else None,
                            "btts_rate": round(float(_tr[25])*100,1) if _tr[25] else None,
                            "over25_rate": round(float(_tr[26])*100,1) if _tr[26] else None,
                            "recent_matches": _h2h_recent or None}
                _std = {"home_pos": _tr[27], "away_pos": _tr[28],
                        "home_pts": _tr[29], "away_pts": _tr[30],
                        "home_gd": _tr[31], "away_gd": _tr[32]}
                _pred = {"home_goals": round(float(_tr[33]),2) if _tr[33] else None,
                         "away_goals": round(float(_tr[34]),2) if _tr[34] else None,
                         "score": _tr[35],
                         "model_prob": round(float(_tr[36]),3) if _tr[36] else None}
            # Build bookmakers dict from odds_by_bookmaker
            _bk_raw = p.get('odds_by_bookmaker')
            _bk = {}
            if _bk_raw and isinstance(_bk_raw, dict):
                _bk = {k: float(v) for k, v in _bk_raw.items() if v}
            elif p.get('best_odds_bookmaker') and p.get('best_odds_value'):
                _bk = {p['best_odds_bookmaker']: p['best_odds_value']}
            p['scout_data'] = {
                "match_id": str(p['id']),
                "home_team": p['home_team'],
                "away_team": p['away_team'],
                "league": p['league'],
                "match_date": p['match_date'],
                "kickoff": p['kickoff_str'],
                "picks": [{
                    "market": p['market'],
                    "selection": p['selection'],
                    "odds": p['odds'],
                    "ev_pct": p['ev'],
                    "confidence": p['confidence'],
                    "model_prob": p['model_prob'],
                    "trust_level": p['trust_level'],
                    "disagreement": p['disagreement'],
                    "open_odds": p['open_odds'],
                    "clv_pct": p['clv_pct'],
                    "bookmakers": _bk,
                }],
                "form": _form,
                "h2h": _h2h,
                "xg": _xg,
                "standings": _std,
                "prediction": _pred,
            }

        total = len(picks)
        won = sum(1 for p in picks if p['status'] == 'won')
        lost = sum(1 for p in picks if p['status'] == 'lost')
        settled = won + lost
        hit_rate = round(won / settled * 100, 1) if settled > 0 else None

        today_picks = [p for p in picks if p['match_date'] == today_str]
        sharp_count = sum(1 for p in picks if p.get('clv_tier') == 'SHARP')
        return {
            'picks': picks,
            'total': total,
            'won': won,
            'lost': lost,
            'settled': settled,
            'hit_rate': hit_rate,
            'date': day_start.strftime('%Y-%m-%d'),
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'is_demo': False,
            'has_today_picks': len(today_picks) > 0,
            'today_count': len(today_picks),
            'sharp_count': sharp_count,
        }

    except Exception as e:
        logger.error(f"Error in get_today_picks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scanner/daily-stats")
async def get_scanner_daily_stats():
    """
    Returns today's scanner volume stats for the UI header:
    - edges_found: all opportunities identified today (PROD + VALUE_OPP + WATCHLIST, pending)
    - high_confidence: CLV tier SHARP (score 5-6) — the actual edge picks
    """
    try:
        now_utc = datetime.utcnow()
        today_str = now_utc.strftime('%Y-%m-%d')
        cutoff_epoch = int(now_utc.timestamp()) - 14400  # 4h grace

        rows = db_helper.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN clv_tier = 'SHARP' THEN 1 ELSE 0 END) AS sharp_count,
                   SUM(CASE WHEN clv_tier = 'VOLUME' THEN 1 ELSE 0 END) AS volume_count
            FROM football_opportunities
            WHERE match_date = %s
              AND mode IN ('PROD', 'VALUE_OPP', 'WATCHLIST')
              AND (outcome IS NULL OR outcome = '' OR outcome IN ('pending', 'unknown'))
              AND (kickoff_epoch IS NULL OR kickoff_epoch > %s)
        """, (today_str, cutoff_epoch), fetch='one')

        total = int(rows[0]) if rows and rows[0] else 0
        sharp = int(rows[1]) if rows and rows[1] else 0
        volume = int(rows[2]) if rows and rows[2] else 0

        return {
            'edges_found': total,
            'high_confidence': sharp,
            'volume_plays': volume,
            'date': today_str,
        }
    except Exception as e:
        logger.error(f"Error in get_scanner_daily_stats: {e}")
        return {'edges_found': 0, 'high_confidence': 0, 'volume_plays': 0, 'date': ''}


@app.get("/api/analysis/today")
async def get_analysis_today():
    """
    VALUE_OPP opportunities for today — pure market analysis data.
    NOT picks, NOT bets. Displayed in the dashboard Analysis section only.
    """
    try:
        now_utc   = datetime.utcnow()
        day_start = datetime(now_utc.year, now_utc.month, now_utc.day)
        today_str = day_start.strftime('%Y-%m-%d')
        cutoff_ep = int((now_utc.timestamp())) - 4 * 3600

        rows = db_helper.execute("""
            SELECT id, home_team, away_team, selection, market,
                   odds, edge_percentage, confidence, league,
                   kickoff_time, match_date, model_prob, kickoff_epoch
            FROM football_opportunities
            WHERE mode = 'VALUE_OPP'
              AND (outcome IS NULL OR outcome = '' OR outcome IN ('pending','unknown'))
              AND match_date >= %s
              AND (
                  (kickoff_epoch IS NOT NULL AND kickoff_epoch > %s)
                  OR (kickoff_epoch IS NULL AND (
                      kickoff_time IS NULL OR match_date IS NULL
                      OR NOT (kickoff_time ~ '^\\d{2}:\\d{2}')
                      OR (match_date::date + kickoff_time::time) > NOW() - INTERVAL '4 hours'
                  ))
              )
            ORDER BY edge_percentage DESC
            LIMIT 50
        """, (today_str, cutoff_ep), fetch='all') or []

        items = []
        for r in rows:
            ko_ep  = int(r[12]) if r[12] else None
            ko_str = ''
            if ko_ep:
                try:
                    import pytz
                    sthlm = pytz.timezone('Europe/Stockholm')
                    dt_ko = datetime.utcfromtimestamp(ko_ep).replace(tzinfo=pytz.utc)
                    ko_str = dt_ko.astimezone(sthlm).strftime('%H:%M')
                    kickoff_iso = datetime.utcfromtimestamp(ko_ep).strftime('%Y-%m-%dT%H:%M:%SZ')
                except Exception:
                    ko_str = str(r[9] or '')[:5]
                    kickoff_iso = f"{r[10]}T{ko_str}:00" if r[10] else ''
            else:
                ko_str = str(r[9] or '')[:5]
                kickoff_iso = f"{r[10]}T{ko_str}:00" if r[10] and ko_str else str(r[10] or '')

            model_p = float(r[11]) if r[11] else None
            odds_f  = float(r[5])  if r[5]  else None
            ev_val  = round((model_p - 1.0 / odds_f) * 100, 1) if (model_p and odds_f and odds_f > 1.0) else round(float(r[6] or 0), 1)

            items.append({
                'id':          r[0],
                'home_team':   r[1] or '',
                'away_team':   r[2] or '',
                'match':       f"{r[1] or ''} vs {r[2] or ''}",
                'selection':   r[3] or '',
                'market':      r[4] or '',
                'odds':        float(r[5] or 0),
                'ev':          ev_val,
                'confidence':  round(float(r[7] or 0), 1),
                'league':      r[8] or '',
                'kickoff_str': ko_str,
                'kickoff_time': kickoff_iso,
                'match_date':  str(r[10] or ''),
            })

        return {'analysis': items, 'count': len(items)}

    except Exception as e:
        logger.error(f"Error in get_analysis_today: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/picks/history")
async def get_picks_history(days: int = 90):
    """
    Get historical PROD picks (settled) from the last N days (default 90).
    Used for the History tab in the dashboard.
    """
    try:
        now_utc = datetime.utcnow()
        day_start = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0)
        window_start = (day_start - timedelta(days=min(days, 365))).strftime('%Y-%m-%d')

        now_epoch_h = int(datetime.utcnow().timestamp())
        cutoff_epoch_h = now_epoch_h - 14400  # 4h past kickoff

        rows = db_helper.execute("""
            SELECT id, home_team, away_team, market, selection, odds,
                   edge_percentage, confidence, outcome, profit_loss,
                   odds_by_bookmaker, best_odds_value, best_odds_bookmaker,
                   league, trust_level, kickoff_time, match_date,
                   open_odds, clv_pct, mode, kickoff_epoch, model_prob
            FROM football_opportunities
            WHERE mode = 'PROD'
              AND match_date >= %s
              AND (
                  -- Settled picks always show in history
                  (outcome IS NOT NULL AND outcome NOT IN ('', 'pending', 'unknown'))
                  -- Unsettled but past kickoff by >4h (epoch-based)
                  OR (
                      (outcome IS NULL OR outcome IN ('', 'pending', 'unknown'))
                      AND kickoff_epoch IS NOT NULL
                      AND kickoff_epoch < %s
                  )
                  -- Unsettled, no epoch, use match_date+kickoff_time
                  OR (
                      (outcome IS NULL OR outcome IN ('', 'pending', 'unknown'))
                      AND kickoff_epoch IS NULL
                      AND kickoff_time ~ '^\d{2}:\d{2}'
                      AND match_date IS NOT NULL
                      AND (match_date::date + kickoff_time::time) < NOW() - INTERVAL '4 hours'
                  )
              )
            ORDER BY match_date DESC, COALESCE(kickoff_epoch, 0) DESC, kickoff_time DESC NULLS LAST
        """, (window_start, cutoff_epoch_h), fetch='all') or []

        picks = []
        for r in rows:
            outcome = (r[8] or '').upper()
            status = 'pending'
            if outcome in ('WON', 'WIN'):
                status = 'won'
            elif outcome in ('LOST', 'LOSS'):
                status = 'lost'
            elif outcome == 'VOID':
                status = 'void'

            ko_time = r[15]
            match_date = str(r[16]) if r[16] else ''
            kickoff_epoch_h = r[20]

            # Build ko_str: prefer epoch→Stockholm time, else kickoff_time column
            ko_str = ''
            if kickoff_epoch_h:
                try:
                    import pytz
                    sthlm = pytz.timezone('Europe/Stockholm')
                    dt_ko = datetime.utcfromtimestamp(kickoff_epoch_h).replace(tzinfo=pytz.utc)
                    ko_str = dt_ko.astimezone(sthlm).strftime('%H:%M')
                except Exception:
                    pass
            if not ko_str and ko_time:
                ko_str = str(ko_time)[:5]
            if not ko_str:
                ko_str = match_date

            mode_val = r[19] or 'PROD'
            layer = 'PRO PICK' if mode_val == 'PROD' else 'VALUE OPP'

            # Unsettled but past kickoff → show as "pending_result"
            if not outcome and kickoff_epoch_h and kickoff_epoch_h < cutoff_epoch_h:
                status = 'pending_result'

            # Real EV from model_prob × odds
            model_p_h = float(r[21]) if r[21] else None
            odds_h    = float(r[5])  if r[5]  else None
            if model_p_h and odds_h and odds_h > 1.0:
                ev_raw_h = (model_p_h - 1.0 / odds_h) * 100
            else:
                ev_raw_h = float(r[6]) if r[6] else 0
            is_outlier_h = ev_raw_h > 40.0
            ev_h = round(min(ev_raw_h, 40.0), 1)

            # Full ISO kickoff string
            kickoff_iso_h = ''
            if match_date and ko_str and ':' in ko_str:
                kickoff_iso_h = f"{match_date}T{ko_str}:00"
            elif match_date:
                kickoff_iso_h = match_date

            picks.append({
                'id': r[0],
                'home_team': r[1] or '',
                'away_team': r[2] or '',
                'match': (r[1] or '') + ' vs ' + (r[2] or ''),
                'market': r[3] or '',
                'selection': r[4] or '',
                'odds': float(r[5]) if r[5] else 0,
                'ev_pct': ev_h,
                'edge_pct': ev_h,
                'ev': ev_h,
                'confidence': round(float(r[7]), 1) if r[7] else 0,
                'outcome': outcome,
                'status': status,
                'profit_loss': round(float(r[9]), 2) if r[9] else None,
                'best_odds_bookmaker': _clean_bookmaker(r[12] or ''),
                'bookmaker': _clean_bookmaker(r[12] or ''),
                'league': r[13] or '',
                'kickoff_str': ko_str,
                'kickoff': kickoff_iso_h,
                'kickoff_time': kickoff_iso_h,
                'match_date': match_date,
                'clv_pct': round(float(r[18]), 2) if r[18] else None,
                'layer': layer,
                'mode': mode_val,
                'is_outlier': is_outlier_h,
            })

        total = len(picks)
        won = sum(1 for p in picks if p['status'] == 'won')
        lost = sum(1 for p in picks if p['status'] == 'lost')
        void_ = sum(1 for p in picks if p['status'] == 'void')
        settled = won + lost
        hit_rate = round(won / settled * 100, 1) if settled > 0 else None
        total_pl = round(sum(p['profit_loss'] for p in picks if p['profit_loss'] is not None), 2)

        return {
            'picks': picks,
            'total': total,
            'won': won,
            'lost': lost,
            'void': void_,
            'settled': settled,
            'hit_rate': hit_rate,
            'total_pl': total_pl,
            'days': days,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }

    except Exception as e:
        logger.error(f"Error in get_picks_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/history", tags=["Analytics"])
async def get_learning_history(sport: str = "HOCKEY", days: int = 90):
    """Get hockey/NBA historical picks from learning_bets for the History sub-tab."""
    try:
        MARKET_LABELS = {
            'h2h': 'Moneyline', 'totals': 'Over/Under', 'h2h_lay': 'Lay ML',
            'spreads': 'AH / Spread',
        }
        LEAGUE_LABELS = {
            # Raw API sport_key format
            'icehockey_nhl': 'NHL', 'icehockey_sweden_hockey_league': 'SHL',
            'icehockey_sweden_allsvenskan': 'Allsvenskan', 'icehockey_ahl': 'AHL',
            'basketball_nba': 'NBA', 'basketball_ncaab': 'NCAAB',
            # Title-cased format as stored in learning_bets.league
            'Icehockey Nhl': 'NHL', 'Icehockey Sweden Hockey League': 'SHL',
            'Icehockey Sweden Allsvenskan': 'Allsvenskan', 'Icehockey Ahl': 'AHL',
            'Basketball Nba': 'NBA', 'Basketball Ncaab': 'NCAAB',
        }
        sport_upper = sport.upper()
        safe_days = min(int(days), 730)

        rows = db_helper.execute(f"""
            SELECT id, home_team, away_team, league, market, selection, line,
                   odds, outcome, profit_loss, status,
                   TO_CHAR(COALESCE(settled_at, commence_time)::date, 'YYYY-MM-DD') AS match_date,
                   COALESCE(settled_at, commence_time) AS sort_ts
            FROM learning_bets
            WHERE sport_category = %s
              AND commence_time > NOW() - INTERVAL '{safe_days} days'
              AND outcome IN ('won', 'lost', 'void', 'push')
            ORDER BY sort_ts DESC NULLS LAST
            LIMIT 500
        """, (sport_upper,), fetch='all') or []

        picks = []
        for r in rows:
            outcome = (r[8] or '').lower()
            status = outcome if outcome in ('won', 'lost', 'void', 'push') else 'pending'
            pl = float(r[9]) if r[9] is not None else None
            line_val = float(r[6]) if r[6] is not None else None
            selection = r[5] or ''
            if line_val is not None:
                sign = f"+{line_val}" if line_val >= 0 else str(line_val)
                selection_display = f"{selection} ({sign})"
            else:
                selection_display = selection
            picks.append({
                'id': r[0],
                'match': f"{r[1]} vs {r[2]}",
                'match_date': r[11] or '—',
                'league': LEAGUE_LABELS.get(r[3], (r[3] or '').replace('_', ' ').title()),
                'market': MARKET_LABELS.get(r[4], r[4] or '—'),
                'selection': selection_display,
                'odds': round(float(r[7]), 2) if r[7] else None,
                'status': status,
                'profit_loss': pl,
            })

        won = sum(1 for p in picks if p['status'] == 'won')
        lost = sum(1 for p in picks if p['status'] == 'lost')
        settled = won + lost
        hit_rate = round(won / settled * 100, 1) if settled > 0 else None
        total_pl = round(sum(p['profit_loss'] for p in picks if p['profit_loss'] is not None), 2)

        return {
            'picks': picks,
            'total': len(picks),
            'won': won, 'lost': lost, 'settled': settled,
            'hit_rate': hit_rate,
            'total_pl': total_pl,
            'sport': sport_upper,
            'days': safe_days,
        }

    except Exception as e:
        logger.error(f"Error in get_learning_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats/summary")
async def get_stats_summary(days: int = 90):
    """
    Unified performance stats from football_opportunities.
    Returns both all-time and the selected rolling window.
    Filter: (mode='PROD' AND bet_placed=true) OR mode='VALUE_OPP'
    """
    try:
        days = max(1, min(days, 365))
        now_utc    = datetime.utcnow()
        day_start  = datetime(now_utc.year, now_utc.month, now_utc.day)
        today_str  = day_start.strftime('%Y-%m-%d')
        window_str = (day_start - timedelta(days=days)).strftime('%Y-%m-%d')

        BASE_FILTER = "mode = 'PROD'"

        def _stats(rows):
            total    = int(rows[0] or 0)
            won      = int(rows[1] or 0)
            lost     = int(rows[2] or 0)
            total_pl = float(rows[3] or 0)
            settled  = won + lost
            return {
                "total":    total,
                "won":      won,
                "lost":     lost,
                "settled":  settled,
                "total_pl": round(total_pl, 2),
                "hit_rate": round(won / settled * 100, 1) if settled > 0 else 0,
                "roi":      round(total_pl / settled * 100, 1) if settled > 0 else 0,
            }

        all_time_row = db_helper.execute(f"""
            SELECT COUNT(*),
                   COUNT(CASE WHEN UPPER(outcome) IN ('WON','WIN')   THEN 1 END),
                   COUNT(CASE WHEN UPPER(outcome) IN ('LOST','LOSS') THEN 1 END),
                   COALESCE(SUM(CASE
                       WHEN UPPER(outcome) IN ('WON','WIN')   THEN odds - 1
                       WHEN UPPER(outcome) IN ('LOST','LOSS') THEN -1
                       ELSE 0 END), 0)
            FROM football_opportunities
            WHERE {BASE_FILTER}
        """, fetch='one')

        period_row = db_helper.execute(f"""
            SELECT COUNT(*),
                   COUNT(CASE WHEN UPPER(outcome) IN ('WON','WIN')   THEN 1 END),
                   COUNT(CASE WHEN UPPER(outcome) IN ('LOST','LOSS') THEN 1 END),
                   COALESCE(SUM(CASE
                       WHEN UPPER(outcome) IN ('WON','WIN')   THEN odds - 1
                       WHEN UPPER(outcome) IN ('LOST','LOSS') THEN -1
                       ELSE 0 END), 0)
            FROM football_opportunities
            WHERE ({BASE_FILTER})
              AND match_date >= %s
              AND match_date < %s
        """, (window_str, today_str), fetch='one')

        return JSONResponse({
            "all_time": _stats(all_time_row) if all_time_row else {},
            "period":   {
                **(_stats(period_row) if period_row else {}),
                "days":  days,
                "label": f"Last {days} days",
            },
        })
    except Exception as e:
        logger.error(f"Error in get_stats_summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats/roi")
async def get_roi_stats_endpoint():
    """
    Get current ROI and performance statistics.
    Returns all-time, monthly, weekly, and daily stats.
    """
    try:
        from discord_roi_webhook import get_roi_stats
        
        stats = get_roi_stats()
        stats["timestamp"] = datetime.utcnow().isoformat()
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting ROI stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Manual Settlement API (for corners/cards that fail auto-verification)
# REQUIRES API KEY AUTHENTICATION - Internal operator use only
# =============================================================================

def verify_admin_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Verify admin API key for internal endpoints."""
    admin_key = os.environ.get("ADMIN_API_KEY")
    if not admin_key:
        raise HTTPException(status_code=503, detail="Manual settlement not configured - ADMIN_API_KEY not set")
    if not x_api_key or x_api_key != admin_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True


class ManualSettleRequest(BaseModel):
    bet_id: int
    result: str  # WON, LOST, VOID
    home_corners: Optional[int] = None
    away_corners: Optional[int] = None
    home_cards: Optional[int] = None
    away_cards: Optional[int] = None
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    reason: Optional[str] = None


@app.post("/api/manual/settle", tags=["Manual Settlement"], include_in_schema=False)
async def manual_settle_bet(request: ManualSettleRequest, x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Manually settle a bet that failed automatic verification.
    Used for corners/cards bets where API data is unavailable.
    REQUIRES X-API-Key header for authentication.
    """
    verify_admin_key(x_api_key)
    try:
        from flashscore_stats_scraper import settle_bet_manually
        
        corners = None
        cards = None
        goals = None
        
        if request.home_corners is not None and request.away_corners is not None:
            corners = (request.home_corners, request.away_corners)
        if request.home_cards is not None and request.away_cards is not None:
            cards = (request.home_cards, request.away_cards)
        if request.home_goals is not None and request.away_goals is not None:
            goals = (request.home_goals, request.away_goals)
        
        success = settle_bet_manually(
            bet_id=request.bet_id,
            result=request.result,
            corners=corners,
            cards=cards,
            goals=goals,
            reason=request.reason,
            operator='api'
        )
        
        return {
            "success": success,
            "bet_id": request.bet_id,
            "result": request.result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Manual settlement error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/manual/pending", tags=["Manual Settlement"])
async def get_pending_manual_review(market: Optional[str] = None, limit: int = 50):
    """
    Get bets that need manual review (failed auto-verification).
    Filter by market: 'Corners', 'Cards', or None for all.
    """
    try:
        from flashscore_stats_scraper import ManualResultsManager
        
        manager = ManualResultsManager()
        pending = manager.get_pending_manual_review(market=market, limit=limit)
        
        return {
            "count": len(pending),
            "pending_bets": pending,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Pending review error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/verification/metrics", tags=["Manual Settlement"])
async def get_verification_metrics(days: int = 7):
    """
    Get verification success rates by market and source.
    Shows which sources are reliable for different market types.
    """
    try:
        from flashscore_stats_scraper import VerificationMetrics
        
        metrics = VerificationMetrics()
        rates = metrics.get_success_rates(days=days)
        
        return {
            "period_days": days,
            "success_rates": rates,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/manual/audit", tags=["Manual Settlement"])
async def get_manual_audit_log(limit: int = 100):
    """
    Get audit log of all manual settlements.
    Shows who settled what and when.
    """
    try:
        from db_helper import db_helper
        
        query = """
            SELECT id, bet_id, bet_table, home_team, away_team, match_date,
                   selection, market, result, reason, source, operator, created_at
            FROM manual_results
            ORDER BY created_at DESC
            LIMIT %s
        """
        
        rows = db_helper.fetch_all(query, [limit])
        
        results = []
        for row in rows:
            results.append({
                "id": row.get("id"),
                "bet_id": row.get("bet_id"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "match_date": str(row.get("match_date")) if row.get("match_date") else None,
                "market": row.get("market"),
                "selection": row.get("selection"),
                "result": row.get("result"),
                "reason": row.get("reason"),
                "operator": row.get("operator"),
                "created_at": str(row.get("created_at")) if row.get("created_at") else None
            })
        
        return {
            "count": len(results),
            "audit_log": results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Audit log error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/league_rankings", tags=["Self-Learning"])
async def get_league_rankings(
    sport: str = "football",
    window: str = "all_time"
):
    try:
        rows = db_helper.execute("""
            SELECT dimension_key, dimension_label, total_bets, wins, losses,
                   roi_pct, hit_rate, avg_clv, profit_units, avg_odds, score
            FROM learning_stats
            WHERE sport = %s AND dimension = 'league' AND window_type = %s
              AND total_bets >= 5
            ORDER BY score DESC
        """, (sport, window), fetch='all') or []
        return [{
            'league': row[0], 'label': row[1], 'total_bets': row[2],
            'wins': row[3], 'losses': row[4], 'roi_pct': float(row[5]),
            'hit_rate': float(row[6]), 'avg_clv': float(row[7]),
            'profit_units': float(row[8]), 'avg_odds': float(row[9]),
            'score': float(row[10]),
        } for row in rows]
    except Exception as e:
        logger.error(f"League rankings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/market_rankings", tags=["Self-Learning"])
async def get_market_rankings(
    sport: str = "football",
    window: str = "all_time"
):
    try:
        rows = db_helper.execute("""
            SELECT dimension_key, dimension_label, total_bets, wins, losses,
                   roi_pct, hit_rate, avg_clv, profit_units, avg_odds, score
            FROM learning_stats
            WHERE sport = %s AND dimension = 'market' AND window_type = %s
              AND total_bets >= 5
            ORDER BY score DESC
        """, (sport, window), fetch='all') or []
        return [{
            'market': row[0], 'label': row[1], 'total_bets': row[2],
            'wins': row[3], 'losses': row[4], 'roi_pct': float(row[5]),
            'hit_rate': float(row[6]), 'avg_clv': float(row[7]),
            'profit_units': float(row[8]), 'avg_odds': float(row[9]),
            'score': float(row[10]),
        } for row in rows]
    except Exception as e:
        logger.error(f"Market rankings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/league_market", tags=["Self-Learning"])
async def get_league_market_combos(
    sport: str = "football",
    window: str = "all_time",
    min_bets: int = 10
):
    try:
        rows = db_helper.execute("""
            SELECT dimension_key, dimension_label, total_bets, wins, losses,
                   roi_pct, hit_rate, avg_clv, profit_units, avg_odds, score
            FROM learning_stats
            WHERE sport = %s AND dimension = 'league_market' AND window_type = %s
              AND total_bets >= %s
            ORDER BY score DESC
        """, (sport, window, min_bets), fetch='all') or []
        result = []
        for row in rows:
            key = str(row[0])
            parts = key.split('|', 1) if '|' in key else [key, '']
            result.append({
                'league': parts[0], 'market': parts[1] if len(parts) > 1 else '',
                'label': row[1], 'total_bets': row[2],
                'wins': row[3], 'losses': row[4], 'roi_pct': float(row[5]),
                'hit_rate': float(row[6]), 'avg_clv': float(row[7]),
                'profit_units': float(row[8]), 'avg_odds': float(row[9]),
                'score': float(row[10]),
            })
        return result
    except Exception as e:
        logger.error(f"League-market combos error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/promotion_status", tags=["Self-Learning"])
async def get_promotion_status(sport: str = "football"):
    try:
        rows = db_helper.execute("""
            SELECT league_id, league_name, market_type, status, total_bets,
                   roi_pct, avg_clv, profit_units, manual_override,
                   promotion_reason, last_promotion_change, updated_at
            FROM league_market_status
            WHERE sport = %s
            ORDER BY 
                CASE status 
                    WHEN 'PRODUCTION' THEN 1 
                    WHEN 'LEARNING_ONLY' THEN 2 
                    WHEN 'DISABLED' THEN 3 
                END,
                total_bets DESC
        """, (sport,), fetch='all') or []
        return [{
            'league': row[0], 'league_name': row[1], 'market': row[2],
            'status': row[3], 'total_bets': row[4],
            'roi_pct': float(row[5] or 0), 'avg_clv': float(row[6] or 0),
            'profit_units': float(row[7] or 0),
            'manual_override': bool(row[8]),
            'reason': row[9],
            'last_change': str(row[10]) if row[10] else None,
            'updated': str(row[11]) if row[11] else None,
        } for row in rows]
    except Exception as e:
        logger.error(f"Promotion status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/global_stats", tags=["Self-Learning"])
async def get_global_learning_stats():
    try:
        rows = db_helper.execute("""
            SELECT sport, window_type, total_bets, wins, losses,
                   roi_pct, hit_rate, avg_clv, profit_units, avg_odds, score
            FROM learning_stats
            WHERE dimension = 'global'
            ORDER BY sport, window_type
        """, fetch='all') or []
        result = {}
        for row in rows:
            sport = row[0]
            window = row[1]
            if sport not in result:
                result[sport] = {}
            result[sport][window] = {
                'total_bets': row[2], 'wins': row[3], 'losses': row[4],
                'roi_pct': float(row[5]), 'hit_rate': float(row[6]),
                'avg_clv': float(row[7]), 'profit_units': float(row[8]),
                'avg_odds': float(row[9]), 'score': float(row[10]),
            }
        return result
    except Exception as e:
        logger.error(f"Global stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/live_tracker")
async def live_tracker_api(market: str = "all"):
    try:
        from live_cards_tracker import get_tracker_data_json
        data = get_tracker_data_json(market)
        return {"picks": data, "count": len(data)}
    except Exception as e:
        logger.error(f"Live tracker error: {e}")
        return {"picks": [], "count": 0, "error": str(e)}


STATIC_DIR = Path(__file__).parent / "static"

# =============================================================================
# Stripe — Checkout, Portal, Webhook
# =============================================================================

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


@app.get("/stripe/checkout", include_in_schema=False)
async def stripe_checkout_redirect(request: Request):
    """
    GET /stripe/checkout  →  redirect straight to Stripe Checkout.
    Reads discord_id from the session cookie so the user doesn't need to
    pass anything — just click "Subscribe" on the upgrade page.
    """
    discord_id = get_discord_id(request)
    if not discord_id:
        return RedirectResponse("/login", status_code=302)
    try:
        url = create_checkout_session(discord_id)
        return RedirectResponse(url, status_code=303)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stripe/checkout", include_in_schema=False)
async def stripe_checkout_json(request: Request):
    """
    POST /stripe/checkout  →  return JSON { checkout_url: "..." }.
    Accepts optional body: { discord_id, plan }.
    Falls back to reading discord_id from session cookie.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    discord_id = body.get("discord_id") or get_discord_id(request)
    plan = body.get("plan", "premium")

    if not discord_id:
        raise HTTPException(status_code=400, detail="discord_id required")
    try:
        url = create_checkout_session(discord_id, plan)
        return JSONResponse({"checkout_url": url})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stripe/portal", include_in_schema=False)
async def stripe_portal(request: Request):
    """
    POST /stripe/portal  →  return JSON { portal_url: "..." }.
    Accepts optional body: { stripe_customer_id }.
    Falls back to looking up the customer ID from the DB via discord_id.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    customer_id = body.get("stripe_customer_id")
    if not customer_id:
        discord_id = get_discord_id(request)
        if discord_id:
            row = db_helper.execute(
                "SELECT stripe_customer_id FROM pgr_users WHERE discord_user_id = %s",
                (discord_id,), fetch='one'
            )
            customer_id = row[0] if row else None

    if not customer_id:
        raise HTTPException(status_code=400, detail="stripe_customer_id not found")
    try:
        url = create_customer_portal(customer_id)
        return JSONResponse({"portal_url": url})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/stripe", include_in_schema=False)
async def stripe_webhook(request: Request):
    """
    Receive Stripe events and update premium status + Discord role.

    Supported events:
      checkout.session.completed        → activate premium + grant Discord role
      invoice.paid / payment_succeeded  → re-activate / extend premium + grant role
      customer.subscription.deleted     → deactivate + revoke role
      customer.subscription.updated     → handle status changes
      invoice.payment_failed            → deactivate premium
    """
    import stripe as stripe_lib

    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe_lib.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            logger.warning(f"Stripe webhook signature invalid: {e}")
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    else:
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id   = event.get("id")
    event_type = event.get("type", "")
    data_obj   = event.get("data", {}).get("object", {})
    logger.info(f"Stripe event received: {event_type} ({event_id})")

    # Idempotency guard
    if event_id and is_duplicate_event(event_id):
        logger.info(f"Duplicate Stripe event ignored: {event_id}")
        return JSONResponse({"received": True, "duplicate": True})

    try:
        # ── 1. Checkout completed ──────────────────────────────────────────
        if event_type == "checkout.session.completed":
            discord_id      = extract_discord_id(data_obj)
            customer_id     = data_obj.get("customer")
            subscription_id = data_obj.get("subscription")

            if discord_id:
                activate_premium(
                    discord_id=discord_id,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                )
                await grant_discord_role(discord_id)
                logger.info(f"Premium activated via checkout for discord={discord_id}")
            else:
                logger.warning("checkout.session.completed: no discord_id found in metadata")

        # ── 2. Invoice paid (renewal) ──────────────────────────────────────
        elif event_type in ("invoice.paid", "invoice.payment_succeeded"):
            customer_id     = data_obj.get("customer")
            subscription_id = data_obj.get("subscription")
            discord_id      = extract_discord_id(data_obj)

            if not discord_id and subscription_id:
                discord_id = resolve_discord_id_from_subscription(subscription_id)

            if discord_id:
                activate_premium(
                    discord_id=discord_id,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                )
                await grant_discord_role(discord_id)
                logger.info(f"Premium renewed for discord={discord_id}")
            elif customer_id:
                activate_by_stripe_customer(customer_id, subscription_id)
                logger.info(f"Premium renewed for stripe_customer={customer_id}")

        # ── 3. Subscription deleted ────────────────────────────────────────
        elif event_type == "customer.subscription.deleted":
            customer_id = data_obj.get("customer")
            discord_id  = extract_discord_id(data_obj)

            if discord_id:
                deactivate_premium(discord_id)
                await revoke_discord_role(discord_id)
                logger.info(f"Premium revoked for discord={discord_id}")
            elif customer_id:
                deactivate_by_stripe_customer(customer_id)
                logger.info(f"Premium revoked for stripe_customer={customer_id}")

        # ── 4. Subscription updated ────────────────────────────────────────
        elif event_type == "customer.subscription.updated":
            status      = data_obj.get("status")
            customer_id = data_obj.get("customer")
            discord_id  = extract_discord_id(data_obj)
            subscription_id = data_obj.get("id")

            if status in ("canceled", "unpaid", "past_due"):
                if discord_id:
                    deactivate_premium(discord_id)
                    await revoke_discord_role(discord_id)
                elif customer_id:
                    deactivate_by_stripe_customer(customer_id)
                logger.info(f"Premium deactivated (status={status}) for discord={discord_id}")
            elif status == "active" and discord_id:
                activate_premium(
                    discord_id=discord_id,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                )
                await grant_discord_role(discord_id)
                logger.info(f"Premium re-activated (subscription updated) for discord={discord_id}")

        # ── 5. Payment failed ──────────────────────────────────────────────
        elif event_type == "invoice.payment_failed":
            customer_id = data_obj.get("customer")
            discord_id  = extract_discord_id(data_obj)
            if discord_id:
                deactivate_premium(discord_id)
            elif customer_id:
                deactivate_by_stripe_customer(customer_id)
            logger.info(f"Premium deactivated (payment_failed) for discord={discord_id or customer_id}")

    except Exception as e:
        logger.error(f"Stripe webhook handler error: {e}", exc_info=True)

    return JSONResponse({"received": True})


# =============================================================================
# Public config endpoint (non-sensitive config for frontend)
# =============================================================================

@app.get("/api/config", include_in_schema=False)
async def public_config():
    """Return non-sensitive public configuration used by frontend pages."""
    return JSONResponse({
        "stripe_payment_link": os.getenv("STRIPE_PAYMENT_LINK") or os.getenv("STRIPE_PAYMENT_399", ""),
        "env": os.getenv("ENV", "dev"),
    })


# =============================================================================
# Public teaser endpoint — no auth required
# =============================================================================

@app.get("/api/public/value-spots", include_in_schema=False)
async def public_value_spots():
    """
    Returns 1–2 real recent value picks as a teaser on the login page.
    No auth required. Redacted: no analysis JSON, no CLV, no bookmaker detail.
    """
    try:
        # Try upcoming kickoffs first (next 24h) with solid edge
        now_epoch = int(__import__("time").time())
        rows = db_helper.execute("""
            SELECT home_team, away_team, league, market, selection,
                   odds, edge_percentage, model_prob, kickoff_epoch
            FROM football_opportunities
            WHERE kickoff_epoch BETWEEN %s AND %s
              AND edge_percentage >= 15
              AND mode != 'TEST'
              AND bet_placed = TRUE
            ORDER BY edge_percentage DESC NULLS LAST
            LIMIT 2
        """, (now_epoch, now_epoch + 86400), fetch="all") or []

        # Fallback: recent picks from last 48h, lower edge bar
        if not rows:
            rows = db_helper.execute("""
                SELECT home_team, away_team, league, market, selection,
                       odds, edge_percentage, model_prob, kickoff_epoch
                FROM football_opportunities
                WHERE timestamp > %s
                  AND edge_percentage >= 12
                  AND mode != 'TEST'
                  AND bet_placed = TRUE
                ORDER BY edge_percentage DESC NULLS LAST
                LIMIT 2
            """, (now_epoch - 172800,), fetch="all") or []

        if not rows:
            return {"spots": [], "live": False}

        spots = []
        for r in rows:
            home, away, league, market, selection = r[0], r[1], r[2], r[3], r[4]
            odds       = float(r[5]) if r[5] else None
            edge       = float(r[6]) if r[6] else None
            model_prob = float(r[7]) if r[7] else None
            ko_epoch   = int(r[8]) if r[8] else None
            is_live    = ko_epoch and ko_epoch > now_epoch if ko_epoch else False

            implied_prob = round(100 / odds) if odds else None
            model_pct    = round(model_prob * 100) if model_prob else None

            spots.append({
                "match":        f"{home} vs {away}",
                "league":       league or "",
                "market":       market or "",
                "selection":    selection or "",
                "odds":         round(odds, 2) if odds else None,
                "edge":         round(edge, 1) if edge else None,
                "model_pct":    model_pct,
                "implied_pct":  implied_prob,
                "is_live":      is_live,
            })

        return {"spots": spots, "live": any(s["is_live"] for s in spots)}
    except Exception as e:
        logger.error(f"public_value_spots error: {e}")
        return {"spots": [], "live": False}


@app.get("/api/public/verify-ev", include_in_schema=False)
async def verify_ev(model_prob: float, odds: float, fair_odds: float = 0.0):
    """
    Public EV audit endpoint — verify any pick's calculation.

    Query params:
      model_prob  — our model's win probability, 0–1  (e.g. 0.52)
      odds        — decimal odds                       (e.g. 2.20)
      fair_odds   — no-vig fair price (optional)       (e.g. 2.10)

    Returns three distinct metrics:
      ev_pct        — EV%  = (p × odds − 1) × 100   (industry standard)
      prob_gap_pct  — probability gap vs bookmaker
      edge_fair_pct — edge vs no-vig fair odds (if fair_odds supplied)
    """
    try:
        from ev_core import verify as _verify
        if not (0.0 < model_prob < 1.0):
            return {"error": "model_prob must be between 0 and 1"}
        if odds <= 1.0:
            return {"error": "odds must be greater than 1.0"}
        result = _verify(model_prob, odds, fair_odds if fair_odds > 1.0 else None)
        result["formula"] = "EV% = (model_prob × odds − 1) × 100"
        result["note"] = (
            "EV% uses model probability. "
            "edge_fair_pct uses devigged market probability. "
            "prob_gap_pct is raw probability difference — not EV."
        )
        return result
    except Exception as e:
        logger.error(f"verify_ev error: {e}")
        return {"error": str(e)}


@app.post("/api/verify-code", include_in_schema=False)
async def verify_member_code(request: Request):
    import os
    try:
        body = await request.json()
        code = str(body.get("code", "")).strip()
    except Exception:
        return JSONResponse({"valid": False, "error": "bad_request"}, status_code=400)
    valid_code = (os.getenv("PREMIUM_CODE") or os.getenv("ADMIN_PASSWORD") or "").strip()
    if not valid_code:
        return JSONResponse({"valid": False, "error": "not_configured"})
    return JSONResponse({"valid": code == valid_code})


# Auth pages (public — no premium required)
# =============================================================================

@app.get("/login", include_in_schema=False)
async def login_page():
    return HTMLResponse(content=(STATIC_DIR / "login.html").read_text())

@app.get("/upgrade", include_in_schema=False)
async def upgrade_page():
    return HTMLResponse(content=(STATIC_DIR / "upgrade.html").read_text())


# =============================================================================
# Root — smart redirect based on auth state
# =============================================================================

@app.get("/", include_in_schema=False)
async def root_redirect(request: Request):
    """
    Serve the public value scanner (home.html) for everyone.
    Premium gate is handled client-side via /api/verify-code.
    Admin sessions are redirected to the internal dashboard.
    """
    if is_admin_session(request):
        return RedirectResponse("/home", status_code=302)
    return HTMLResponse(content=(STATIC_DIR / "home.html").read_text())


# =============================================================================
# Protected app routes
# =============================================================================

_raw_streamlit_url = os.getenv("STREAMLIT_DASHBOARD_URL", "")
if _raw_streamlit_url and not _raw_streamlit_url.startswith("http"):
    _raw_streamlit_url = "https://" + _raw_streamlit_url
STREAMLIT_DASHBOARD_URL = _raw_streamlit_url or None


@app.get("/pgrdashboard", include_in_schema=False)
@app.get("/goto-dashboard", include_in_schema=False)
async def goto_dashboard(request: Request):
    """
    Token-based bridge to the dashboard.

    - Admin sessions go directly to /home (FastAPI-served dashboard).
    - Premium Discord users get a one-time token and are redirected to
      the Streamlit URL if configured, otherwise /home.
    - Non-premium authenticated users are sent to /upgrade.
    - Unauthenticated requests are sent to /login.
    """
    if is_admin_session(request):
        # Admins go directly to the FastAPI home dashboard — no Streamlit needed
        return RedirectResponse("/home", status_code=302)

    discord_id = get_discord_id(request)
    if not discord_id:
        return RedirectResponse("/login", status_code=302)

    if not is_premium(discord_id):
        return RedirectResponse("/upgrade", status_code=302)

    token = create_dashboard_token(discord_id)
    if STREAMLIT_DASHBOARD_URL:
        return RedirectResponse(f"{STREAMLIT_DASHBOARD_URL}?token={token}", status_code=302)
    # Fallback if Streamlit URL not configured
    return RedirectResponse("/home", status_code=302)


@app.get("/home", include_in_schema=False)
async def home_dashboard():
    return HTMLResponse(content=(STATIC_DIR / "home.html").read_text())

@app.get("/app", include_in_schema=False)
async def app_alias():
    return HTMLResponse(content=(STATIC_DIR / "home.html").read_text())

@app.get("/preview", include_in_schema=False)
async def preview_dashboard():
    return HTMLResponse(content=(STATIC_DIR / "preview.html").read_text())

@app.get("/value", include_in_schema=False)
async def value_dashboard():
    return HTMLResponse(content=(STATIC_DIR / "value_dashboard.html").read_text())

@app.get("/opportunities", include_in_schema=False)
async def opportunities_alias():
    return HTMLResponse(content=(STATIC_DIR / "value_dashboard.html").read_text())


# =============================================================================
# Internal / legacy routes (not user-facing)
# =============================================================================

@app.get("/pgr", include_in_schema=False)
async def pgr_dashboard():
    return HTMLResponse(content=(STATIC_DIR / "pgr_dashboard.html").read_text())

@app.get("/edge-finder", include_in_schema=False)
async def edge_finder_alias():
    return HTMLResponse(content=(STATIC_DIR / "pgr_dashboard.html").read_text())

# =============================================================================
# SECRET ADMIN DASHBOARD
# =============================================================================

@app.get("/admin", include_in_schema=False)
async def admin_dashboard(request: Request):
    from auth_premium import is_admin_session
    if not is_admin_session(request):
        return RedirectResponse("/admin-login", status_code=302)
    return HTMLResponse(content=(STATIC_DIR / "admin.html").read_text())


def _build_recent(rows, f):
    import json as _json, math as _math
    result = []
    for r in (rows or []):
        analysis_raw = r[15]
        analysis = {}
        try:
            if analysis_raw and str(analysis_raw).startswith('{'):
                analysis = _json.loads(analysis_raw)
        except Exception:
            pass

        pred_score = ""
        pred_winner = ""  # "H", "D", "A"
        eh = analysis.get('expected_home_goals')
        ea = analysis.get('expected_away_goals')
        if eh is not None and ea is not None:
            ph = int(_math.floor(eh))
            pa = int(_math.floor(ea))
            pred_score = f"{ph}-{pa}"
            if eh > ea + 0.15:
                pred_winner = "H"
            elif ea > eh + 0.15:
                pred_winner = "A"
            else:
                pred_winner = "D"

        result.append({
            "id": r[0], "home": r[1], "away": r[2],
            "league": r[3], "market": r[4], "selection": r[5],
            "odds": f(r[6]), "outcome": r[7] or "—",
            "pl": f(r[8]), "edge": f(r[9]), "conf": f(r[10]),
            "ko": r[11] or "—", "score": r[12] or "",
            "date": str(r[14]) if r[14] else "",
            "pred_score": pred_score,
            "pred_winner": pred_winner,
        })
    return result


@app.get("/api/admin/data", include_in_schema=False)
async def admin_data(request: Request, x_admin_key: Optional[str] = Header(None)):
    """Protected admin data endpoint. Accepts cookie session OR x-admin-key header."""
    from auth_premium import is_admin_session
    admin_pw  = os.environ.get("ADMIN_PASSWORD", "")
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    key_ok    = x_admin_key and (x_admin_key == admin_pw or x_admin_key == admin_key)
    if not is_admin_session(request) and not key_ok:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db = db_helper

    # Overall summary
    summary = db.execute("""
        SELECT
            COUNT(*) FILTER (WHERE outcome IN ('won','lost','void')) AS settled,
            COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
            COUNT(*) FILTER (WHERE outcome = 'lost') AS losses,
            COUNT(*) FILTER (WHERE outcome = 'void') AS voids,
            COUNT(*) FILTER (WHERE (outcome IS NULL OR outcome = '' OR outcome = 'pending') AND status='pending') AS pending,
            ROUND(SUM(CASE WHEN outcome='won' THEN odds-1 WHEN outcome='lost' THEN -1 ELSE 0 END)::numeric,2) AS profit,
            ROUND(AVG(CASE WHEN outcome IN ('won','lost') THEN odds END)::numeric,2) AS avg_odds
        FROM football_opportunities WHERE mode = 'PROD'
    """, fetch='one')

    # By market
    by_market = db.execute("""
        SELECT market,
            COUNT(*) FILTER (WHERE outcome IN ('won','lost')) AS settled,
            COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
            COUNT(*) FILTER (WHERE outcome = 'lost') AS losses,
            ROUND(SUM(CASE WHEN outcome='won' THEN odds-1 WHEN outcome='lost' THEN -1 ELSE 0 END)::numeric,2) AS profit,
            ROUND(AVG(CASE WHEN outcome IN ('won','lost') THEN odds END)::numeric,2) AS avg_odds
        FROM football_opportunities WHERE mode='PROD'
        GROUP BY market ORDER BY settled DESC LIMIT 15
    """, fetch='all')

    # By league (top 15)
    by_league = db.execute("""
        SELECT league,
            COUNT(*) FILTER (WHERE outcome IN ('won','lost')) AS settled,
            COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
            COUNT(*) FILTER (WHERE outcome = 'lost') AS losses,
            ROUND(SUM(CASE WHEN outcome='won' THEN odds-1 WHEN outcome='lost' THEN -1 ELSE 0 END)::numeric,2) AS profit,
            ROUND(AVG(CASE WHEN outcome IN ('won','lost') THEN odds END)::numeric,2) AS avg_odds
        FROM football_opportunities WHERE mode='PROD'
        GROUP BY league ORDER BY settled DESC LIMIT 15
    """, fetch='all')

    # Daily profit last 30 days
    daily = db.execute("""
        SELECT
            DATE(COALESCE(kickoff_utc::timestamptz, TO_TIMESTAMP("timestamp"))) AS day,
            COUNT(*) FILTER (WHERE outcome IN ('won','lost')) AS settled,
            COUNT(*) FILTER (WHERE outcome = 'won') AS wins,
            ROUND(SUM(CASE WHEN outcome='won' THEN odds-1 WHEN outcome='lost' THEN -1 ELSE 0 END)::numeric,2) AS profit
        FROM football_opportunities
        WHERE mode='PROD'
          AND DATE(COALESCE(kickoff_utc::timestamptz, TO_TIMESTAMP("timestamp"))) >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY day ORDER BY day DESC
    """, fetch='all')

    # Recent picks (last 100 settled)
    recent = db.execute("""
        SELECT
            id, home_team, away_team, league, market, selection, odds,
            outcome, profit_loss,
            ROUND(edge_percentage::numeric,1) AS edge,
            ROUND(confidence::numeric,2) AS conf,
            TO_CHAR(COALESCE(kickoff_utc::timestamptz, TO_TIMESTAMP("timestamp")), 'YYYY-MM-DD HH24:MI') AS ko,
            actual_score, settled_timestamp, match_date, analysis
        FROM football_opportunities
        WHERE mode='PROD' AND outcome IN ('won','lost','void')
        ORDER BY settled_timestamp DESC NULLS LAST, "timestamp" DESC
        LIMIT 100
    """, fetch='all')

    # Pending picks
    pending_picks = db.execute("""
        SELECT id, home_team, away_team, league, market, selection, odds,
               ROUND(edge_percentage::numeric,1) AS edge,
               TO_CHAR(COALESCE(kickoff_utc::timestamptz, TO_TIMESTAMP("timestamp")), 'YYYY-MM-DD HH24:MI') AS ko
        FROM football_opportunities
        WHERE mode='PROD' AND (outcome IS NULL OR outcome='' OR outcome='pending') AND status='pending'
          AND COALESCE(kickoff_utc::timestamptz, TO_TIMESTAMP("timestamp")) > NOW() - INTERVAL '2 days'
        ORDER BY COALESCE(kickoff_utc::timestamptz, TO_TIMESTAMP("timestamp")) ASC
        LIMIT 20
    """, fetch='all')

    # Last verification run (latest settled_timestamp)
    last_verify = db.execute("""
        SELECT MAX(settled_timestamp) FROM football_opportunities WHERE mode='PROD'
    """, fetch='one')

    def f(v): return float(v) if v is not None else 0.0
    def i(v): return int(v) if v is not None else 0

    s = summary or (0,0,0,0,0,0,0)
    settled, wins, losses, voids, pending_cnt, profit, avg_odds = i(s[0]),i(s[1]),i(s[2]),i(s[3]),i(s[4]),f(s[5]),f(s[6])
    # ROI denominator = wins+losses only (voids return stake so excluded)
    staked_bets = wins + losses
    hit_rate = round(wins / staked_bets * 100, 1) if staked_bets > 0 else 0
    roi = round(profit / staked_bets * 100, 1) if staked_bets > 0 else 0

    push_subs = 0
    try:
        from push_service import PushService
        push_subs = PushService().count()
    except Exception:
        pass

    return JSONResponse({
        "summary": {
            "settled": settled, "wins": wins, "losses": losses, "voids": voids,
            "pending": pending_cnt, "profit": profit, "avg_odds": avg_odds,
            "hit_rate": hit_rate, "roi": roi, "push_subs": push_subs
        },
        "by_market": [{"market": r[0], "settled": i(r[1]), "wins": i(r[2]), "losses": i(r[3]),
                        "profit": f(r[4]), "avg_odds": f(r[5])} for r in (by_market or [])],
        "by_league": [{"league": r[0], "settled": i(r[1]), "wins": i(r[2]), "losses": i(r[3]),
                        "profit": f(r[4]), "avg_odds": f(r[5])} for r in (by_league or [])],
        "daily": [{"day": str(r[0]), "settled": i(r[1]), "wins": i(r[2]), "profit": f(r[3])} for r in (daily or [])],
        "recent": _build_recent(recent, f),
        "pending": [{"id": r[0], "match": f"{r[1]} vs {r[2]}", "league": r[3], "market": r[4],
                      "selection": r[5], "odds": f(r[6]), "edge": f(r[7]), "ko": r[8] or "—"} for r in (pending_picks or [])],
        "last_verify": (datetime.utcfromtimestamp(float(last_verify[0])).strftime('%Y-%m-%d %H:%M UTC') if last_verify and last_verify[0] else None),
    })


# PWA root-scope routes — sw.js MUST be served from / scope to control full app
@app.get("/sw.js", include_in_schema=False)
async def serve_sw():
    return FileResponse(str(STATIC_DIR / "sw.js"), media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

@app.get("/manifest.json", include_in_schema=False)
async def serve_manifest():
    return FileResponse(str(STATIC_DIR / "manifest.json"), media_type="application/manifest+json")

@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return Response(status_code=204)

_ALLOWED_ICONS = {"icon-192.png", "icon-512.png", "icon-maskable-192.png"}


@app.get("/icons/{filename}", include_in_schema=False)
async def serve_icon(filename: str):
    if filename not in _ALLOWED_ICONS:
        raise HTTPException(status_code=404)
    icon_path = STATIC_DIR / "icons" / filename
    if icon_path.exists() and icon_path.suffix in (".png", ".ico", ".svg"):
        return FileResponse(str(icon_path), media_type="image/png")
    return Response(status_code=404)

# =============================================================================
# WEB PUSH NOTIFICATION ENDPOINTS
# =============================================================================

@app.get("/api/push/vapid-key", include_in_schema=False)
async def push_vapid_key():
    """Return the VAPID public key for client-side subscription."""
    key = os.environ.get("VAPID_PUBLIC_KEY", "")
    return {"publicKey": key}


class PushSubscribeBody(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    userAgent: Optional[str] = ""


@app.post("/api/push/subscribe", include_in_schema=False)
async def push_subscribe(body: PushSubscribeBody):
    """Save a push subscription from the browser."""
    try:
        from push_service import PushService
        svc = PushService()
        ok = svc.save_subscription(body.endpoint, body.p256dh, body.auth, body.userAgent or "")
        return {"ok": ok, "subscribers": svc.count()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/push/unsubscribe", include_in_schema=False)
async def push_unsubscribe(endpoint: str):
    """Remove a push subscription."""
    try:
        from push_service import PushService
        PushService().delete_subscription(endpoint)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PushSendBody(BaseModel):
    title: str
    body: str
    url: Optional[str] = "/"


@app.post("/api/push/send", include_in_schema=False)
async def push_send(request: Request, payload: PushSendBody,
                    x_admin_key: Optional[str] = Header(None)):
    """Admin-only: broadcast a push notification to all subscribers.
    Accepts either the pgr_admin_session cookie OR x-admin-key header."""
    from auth_premium import is_admin_session
    admin_pw  = os.environ.get("ADMIN_PASSWORD", "")
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    key_ok    = x_admin_key and (x_admin_key == admin_pw or x_admin_key == admin_key)
    if not is_admin_session(request) and not key_ok:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        from push_service import PushService
        result = PushService().send_to_all(payload.title, payload.body, payload.url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_push_test_last: dict = {}

@app.get("/api/push/debug", include_in_schema=False)
async def push_debug():
    """Debug endpoint — returns key metadata without exposing key values."""
    import os, base64
    pub  = os.getenv("VAPID_PUBLIC_KEY", "")
    priv = os.getenv("VAPID_PRIVATE_KEY", "")
    decoded_ok = False
    decoded_len = 0
    pem_header = ""
    try:
        padding = "=" * ((4 - len(priv) % 4) % 4)
        decoded = base64.urlsafe_b64decode(priv + padding)
        decoded_ok = True
        decoded_len = len(decoded)
        pem_header = decoded.decode("utf-8").split("\n")[0]
    except Exception as e:
        pem_header = f"decode_error: {e}"
    return {
        "pub_len":      len(pub),
        "pub_start":    pub[:12] + "...",
        "priv_len":     len(priv),
        "decoded_ok":   decoded_ok,
        "decoded_len":  decoded_len,
        "pem_header":   pem_header,
    }

@app.post("/api/push/self-test", include_in_schema=False)
async def push_self_test(request: Request):
    """Fire a test push to all subscribers — no auth, rate-limited to 1/min."""
    import time
    now = time.time()
    ip  = request.client.host if request.client else "unknown"
    if now - _push_test_last.get(ip, 0) < 60:
        raise HTTPException(status_code=429, detail="Rate limit: 1 test per minute")
    _push_test_last[ip] = now
    try:
        from push_service import PushService
        svc    = PushService()
        count  = svc.count()
        if count == 0:
            return {"ok": False, "detail": "No subscribers registered yet"}
        result = svc.send_to_all(
            "🔒 Sharp Entry Found",
            "CLV Score: 5/6\nBTTS Yes @2.25\nEntry window open",
            url="/"
        )
        return {"ok": True, "subscribers": count, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/push/clear-all", include_in_schema=False)
async def push_clear_all(request: Request, x_admin_key: Optional[str] = Header(None)):
    """Clear ALL push subscriptions from DB — use after VAPID key rotation."""
    from auth_premium import is_admin_session
    admin_pw  = os.environ.get("ADMIN_PASSWORD", "")
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    key_ok    = x_admin_key and (x_admin_key == admin_pw or x_admin_key == admin_key)
    if not is_admin_session(request) and not key_ok:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        from db_connection import DatabaseConnection
        with DatabaseConnection.get_cursor() as cur:
            cur.execute("DELETE FROM push_subscriptions")
            deleted = cur.rowcount
        logger.info(f"push/clear-all: deleted {deleted} subscriptions")
        return {"ok": True, "deleted": deleted, "message": "All subscriptions cleared. Users must re-subscribe."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

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
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db_helper import db_helper
from auth_discord import router as discord_auth_router
from api_staking import router as staking_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include Discord OAuth router
app.include_router(discord_auth_router)

# Include staking router
app.include_router(staking_router)

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
    
    # 2. SGP Predictions
    try:
        sgp_rows = db_helper.execute("""
            SELECT DISTINCT ON (home_team, away_team)
                match_id, home_team, away_team, league, match_date, kickoff_time,
                legs, ev_percentage, parlay_probability
            FROM sgp_predictions
            WHERE match_date >= %s AND match_date <= %s
            AND mode != 'TEST'
            ORDER BY home_team, away_team, timestamp DESC
        """, (str(today), str(tomorrow)), fetch='all') or []
        
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
    
    # 4. ML Parlay
    try:
        ml_rows = db_helper.execute("""
            SELECT id, legs, combined_ev, confidence_score, match_date
            FROM ml_parlay_predictions
            WHERE match_date >= %s AND match_date <= %s
            AND COALESCE(mode, 'PROD') != 'TEST'
            ORDER BY created_at DESC
            LIMIT 10
        """, (str(today), str(tomorrow)), fetch='all') or []
        
        for row in ml_rows:
            try:
                legs = json.loads(row[1]) if row[1] else []
                for leg in legs:
                    home = leg.get('home_team', '')
                    away = leg.get('away_team', '')
                    key = f"{home}_{away}"
                    if key in matches:
                        matches[key]['products'].add('ML_PARLAY')
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error fetching ML parlay: {e}")
    
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
    
    # 2. Search SGP predictions
    try:
        rows = db_helper.execute("""
            SELECT match_id, home_team, away_team, league, match_date, kickoff_time,
                   legs, parlay_description, bookmaker_odds, ev_percentage
            FROM sgp_predictions
            WHERE match_id = %s OR (home_team || '_' || away_team) = %s
            ORDER BY timestamp DESC
            LIMIT 5
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
                    'bookmaker': row[12]
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

@app.get("/api/clv_stats", response_model=CLVStatsResponse, tags=["Analytics"])
async def get_clv_stats_endpoint():
    """
    Get Closing Line Value (CLV) statistics.
    
    CLV measures whether you got better odds than the closing line.
    Positive CLV indicates long-term betting edge.
    
    Returns:
    - avg_clv_all: Average CLV across all bets with closing odds
    - avg_clv_last_100: Average CLV of last 100 bets
    - positive_share: Percentage of bets with positive CLV
    - total_with_clv: Total number of bets with CLV data
    """
    try:
        from clv_service import get_clv_stats
        stats = get_clv_stats()
        
        return CLVStatsResponse(
            avg_clv_all=stats.get('avg_clv_all'),
            avg_clv_last_100=stats.get('avg_clv_last_100'),
            positive_share=stats.get('positive_share'),
            total_with_clv=stats.get('total_with_clv', 0),
            generated_at=datetime.utcnow().isoformat() + "Z"
        )
        
    except Exception as e:
        logger.error(f"Error in get_clv_stats: {e}")
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
# Run with: uvicorn api:app --host 0.0.0.0 --port 8000
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

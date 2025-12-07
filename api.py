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
# Run with: uvicorn api:app --host 0.0.0.0 --port 8000
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

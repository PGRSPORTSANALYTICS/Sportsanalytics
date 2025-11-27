"""
Women's Football 1X2 (Match Winner) Predictor
Generates Home/Draw/Away predictions with EV-based filtering
Uses The Odds API for real bookmaker odds
"""

import logging
import os
import requests
from typing import List, Dict, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
import psycopg2
from psycopg2.extras import execute_values

from db_connection import DatabaseConnection
from women_league_detector import get_women_detector
from api_football_client import APIFootballClient
from api_cache_manager import APICacheManager

logger = logging.getLogger(__name__)

# Women's football sport keys for The Odds API
WOMEN_ODDS_SPORT_KEYS = [
    'soccer_england_wsl',           # Women's Super League (England)
    'soccer_usa_nwsl',              # NWSL (USA)
    'soccer_germany_frauen_bundesliga',  # Frauen-Bundesliga (Germany)
    'soccer_france_feminine',       # Division 1 Feminine (France)
    'soccer_spain_primera_femenina',  # Liga F (Spain)
    'soccer_italy_serie_a_women',   # Serie A Femminile (Italy)
    'soccer_uefa_womens_champions_league',  # UWCL
]

# EV thresholds per mode
EV_THRESHOLDS = {
    'TRAIN': 0.03,  # 3% EV during data collection (women's markets are softer)
    'PROD': 0.05    # 5% EV in production
}

# Current operating mode
CURRENT_MODE = 'TRAIN'  # Change to 'PROD' at launch

# League-specific goal averages for women's football
WOMEN_LEAGUE_AVG_GOALS = {
    'default': {'home': 1.5, 'away': 1.2},  # Conservative defaults
    'wsl': {'home': 1.8, 'away': 1.4},  # Women's Super League
    'nwsl': {'home': 1.7, 'away': 1.3},  # US NWSL
}


@dataclass
class Women1X2Prediction:
    """Women's Match Winner prediction"""
    match_id: str
    league: str
    league_id: int
    home_team: str
    away_team: str
    match_date: str
    kickoff_time: str
    selection: str  # 'HOME', 'DRAW', 'AWAY'
    implied_prob: float
    model_prob: float
    odds: float
    ev_percentage: float
    stake: float
    notes: Dict


class Women1X2Predictor:
    """Generate 1X2 predictions for women's football using real odds"""
    
    def __init__(self, mode: str = CURRENT_MODE):
        self.mode = mode
        self.ev_threshold = EV_THRESHOLDS[mode]
        self.detector = get_women_detector()
        self.api_client = APIFootballClient()
        
        # The Odds API integration
        self.odds_api_key = os.getenv('THE_ODDS_API_KEY')
        self.odds_base_url = "https://api.the-odds-api.com/v4"
        self.cache_manager = APICacheManager('odds_api_women', quota_limit=450)
        self.odds_cache: Dict[str, Dict] = {}  # Team name -> odds mapping
        
        logger.info(f"🎯 Women's 1X2 Predictor initialized (Mode: {mode}, EV Threshold: {self.ev_threshold:.1%})")
        if self.odds_api_key:
            logger.info("✅ The Odds API key loaded for real women's odds")
        else:
            logger.warning("⚠️ THE_ODDS_API_KEY not found - will use synthetic odds")
    
    def get_upcoming_women_matches(self) -> List[Dict]:
        """Fetch upcoming women's matches (cached)"""
        logger.info("📅 Fetching women's football matches...")
        
        # Get women's leagues
        women_leagues = self.detector.get_women_leagues()
        
        all_fixtures = []
        for league in women_leagues:
            try:
                # Fetch fixtures using cache (24h TTL)
                fixtures = self.api_client.get_upcoming_fixtures_cached(
                    league_ids=[league['league_id']],
                    days_ahead=7
                )
                
                if fixtures:
                    for fx in fixtures:
                        fx['is_women'] = True
                        fx['league_config'] = league
                        all_fixtures.append(fx)
                        
            except Exception as e:
                logger.error(f"❌ Error fetching {league['league_name']}: {e}")
                continue
        
        logger.info(f"✅ Found {len(all_fixtures)} women's matches")
        return all_fixtures
    
    def get_league_averages(self, league_name: str) -> Dict[str, float]:
        """Get league-specific goal averages"""
        league_key = league_name.lower()
        
        for key in WOMEN_LEAGUE_AVG_GOALS:
            if key in league_key:
                return WOMEN_LEAGUE_AVG_GOALS[key]
        
        return WOMEN_LEAGUE_AVG_GOALS['default']
    
    def calculate_1x2_probabilities(self, fixture: Dict) -> Optional[Dict]:
        """
        Calculate 1X2 probabilities using Poisson distribution
        
        Returns dict with HOME/DRAW/AWAY probabilities
        """
        try:
            home_team = fixture.get('teams', {}).get('home', {}).get('name')
            away_team = fixture.get('teams', {}).get('away', {}).get('name')
            league_name = fixture.get('league', {}).get('name', 'default')
            
            # Get league-specific averages
            league_avgs = self.get_league_averages(league_name)
            home_xg = league_avgs['home']
            away_xg = league_avgs['away']
            
            # Poisson calculation for match outcomes
            from scipy.stats import poisson
            import numpy as np
            
            # Calculate probability matrix (scores 0-5)
            prob_matrix = np.zeros((6, 6))
            for i in range(6):
                for j in range(6):
                    prob_matrix[i][j] = poisson.pmf(i, home_xg) * poisson.pmf(j, away_xg)
            
            # Aggregate probabilities
            home_win_prob = np.sum(np.tril(prob_matrix, -1))  # Home score > Away score
            draw_prob = np.sum(np.diag(prob_matrix))  # Home score = Away score
            away_win_prob = np.sum(np.triu(prob_matrix, 1))  # Away score > Home score
            
            # Normalize to ensure sum = 1.0
            total = home_win_prob + draw_prob + away_win_prob
            
            return {
                'HOME': home_win_prob / total,
                'DRAW': draw_prob / total,
                'AWAY': away_win_prob / total
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculating probabilities: {e}")
            return None
    
    def fetch_women_odds_from_api(self) -> Dict[str, Dict]:
        """Fetch all women's football odds from The Odds API"""
        if not self.odds_api_key:
            logger.warning("⚠️ No Odds API key - cannot fetch real odds")
            return {}
        
        all_odds: Dict[str, Dict] = {}
        
        for sport_key in WOMEN_ODDS_SPORT_KEYS:
            try:
                cache_key = f"women_h2h_{sport_key}"
                cached = self.cache_manager.get_cached_response(cache_key, f'odds/{sport_key}')
                
                if cached is not None:
                    for event in cached:
                        match_key = self._create_match_key(event.get('home_team', ''), event.get('away_team', ''))
                        if match_key:
                            all_odds[match_key] = self._extract_h2h_odds(event)
                    continue
                
                if not self.cache_manager.check_quota_available():
                    logger.warning("⚠️ Odds API quota exhausted")
                    break
                
                url = f"{self.odds_base_url}/sports/{sport_key}/odds"
                params = {
                    'apiKey': self.odds_api_key,
                    'regions': 'eu,uk',
                    'markets': 'h2h',
                    'oddsFormat': 'decimal'
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 404:
                    continue
                
                response.raise_for_status()
                self.cache_manager.increment_request_count()
                
                events = response.json()
                
                if events:
                    self.cache_manager.cache_response(cache_key, f'odds/{sport_key}', events, ttl_hours=1)
                    logger.info(f"✅ Fetched {len(events)} women's matches from {sport_key}")
                    
                    for event in events:
                        match_key = self._create_match_key(event.get('home_team', ''), event.get('away_team', ''))
                        if match_key:
                            all_odds[match_key] = self._extract_h2h_odds(event)
                
            except Exception as e:
                logger.debug(f"⚠️ Error fetching {sport_key}: {e}")
                continue
        
        logger.info(f"📊 Total women's matches with real odds: {len(all_odds)}")
        self.odds_cache = all_odds
        return all_odds
    
    def _create_match_key(self, home: str, away: str) -> Optional[str]:
        """Create a normalized match key for matching fixtures to odds"""
        if not home or not away:
            return None
        home_norm = home.lower().replace(' ', '').replace('-', '').replace('.', '')[:15]
        away_norm = away.lower().replace(' ', '').replace('-', '').replace('.', '')[:15]
        return f"{home_norm}_{away_norm}"
    
    def _extract_h2h_odds(self, event: Dict) -> Dict:
        """Extract best h2h odds from event"""
        odds = {'HOME': None, 'DRAW': None, 'AWAY': None, 'bookmaker': None}
        
        home_team = event.get('home_team', '')
        away_team = event.get('away_team', '')
        
        for bookmaker in event.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                if market.get('key') == 'h2h':
                    for outcome in market.get('outcomes', []):
                        name = outcome.get('name', '')
                        price = outcome.get('price', 0)
                        
                        if name == home_team:
                            if odds['HOME'] is None or price > odds['HOME']:
                                odds['HOME'] = price
                        elif name == away_team:
                            if odds['AWAY'] is None or price > odds['AWAY']:
                                odds['AWAY'] = price
                        elif name.lower() == 'draw':
                            if odds['DRAW'] is None or price > odds['DRAW']:
                                odds['DRAW'] = price
                        
                        if odds['bookmaker'] is None:
                            odds['bookmaker'] = bookmaker.get('key', 'Unknown')
        
        return odds
    
    def get_1x2_odds(self, fixture: Dict) -> Optional[Dict]:
        """Get 1X2 odds from The Odds API or fallback to synthetic"""
        try:
            home_team = fixture.get('teams', {}).get('home', {}).get('name', '')
            away_team = fixture.get('teams', {}).get('away', {}).get('name', '')
            
            # Try to find real odds from cache
            match_key = self._create_match_key(home_team, away_team)
            
            if match_key and match_key in self.odds_cache:
                real_odds = self.odds_cache[match_key]
                if real_odds.get('HOME') and real_odds.get('DRAW') and real_odds.get('AWAY'):
                    logger.debug(f"✅ Real odds found for {home_team} vs {away_team}")
                    return {
                        'HOME': real_odds['HOME'],
                        'DRAW': real_odds['DRAW'],
                        'AWAY': real_odds['AWAY'],
                        'source': 'the_odds_api',
                        'bookmaker': real_odds.get('bookmaker', 'Unknown')
                    }
            
            # Fallback: synthetic odds (will rarely pass EV threshold)
            probs = self.calculate_1x2_probabilities(fixture)
            if not probs:
                return None
            
            margin = 0.05
            return {
                'HOME': round(1.0 / (probs['HOME'] * (1 + margin)), 2),
                'DRAW': round(1.0 / (probs['DRAW'] * (1 + margin)), 2),
                'AWAY': round(1.0 / (probs['AWAY'] * (1 + margin)), 2),
                'source': 'synthetic'
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting odds: {e}")
            return None
    
    def calculate_ev(self, model_prob: float, odds: float) -> float:
        """Calculate expected value: (model_prob * odds) - 1"""
        return (model_prob * odds) - 1.0
    
    def calculate_kelly_stake(self, model_prob: float, odds: float, bankroll: float = 100.0) -> float:
        """Kelly Criterion stake sizing (fractional Kelly = 25%)"""
        implied_prob = 1.0 / odds
        edge = model_prob - implied_prob
        
        if edge <= 0:
            return 0.0
        
        kelly_fraction = edge / (odds - 1)
        fractional_kelly = kelly_fraction * 0.25  # 25% Kelly
        
        stake = bankroll * fractional_kelly
        return max(min(stake, 10.0), 1.0)  # Cap between $1-$10
    
    def generate_predictions(self) -> List[Women1X2Prediction]:
        """Generate 1X2 predictions for women's matches"""
        logger.info(f"🎯 Generating women's 1X2 predictions (Mode: {self.mode})...")
        
        # Fetch real odds from The Odds API first
        logger.info("📊 Fetching real women's football odds from The Odds API...")
        self.fetch_women_odds_from_api()
        
        fixtures = self.get_upcoming_women_matches()
        predictions = []
        real_odds_count = 0
        synthetic_odds_count = 0
        
        for fixture in fixtures:
            try:
                # Get probabilities and odds
                probs = self.calculate_1x2_probabilities(fixture)
                odds = self.get_1x2_odds(fixture)
                
                if not probs or not odds:
                    continue
                
                # Track odds source
                if odds.get('source') == 'the_odds_api':
                    real_odds_count += 1
                else:
                    synthetic_odds_count += 1
                
                # Find best EV bet
                best_selection = None
                best_ev = -1
                
                for selection in ['HOME', 'DRAW', 'AWAY']:
                    model_prob = probs[selection]
                    selection_odds = odds[selection]
                    ev = self.calculate_ev(model_prob, selection_odds)
                    
                    if ev > best_ev:
                        best_ev = ev
                        best_selection = selection
                
                # Filter by EV threshold
                if best_ev < self.ev_threshold:
                    continue
                
                # Calculate stake
                stake = self.calculate_kelly_stake(
                    probs[best_selection],
                    odds[best_selection]
                )
                
                # Create prediction
                match_info = fixture.get('fixture', {})
                teams = fixture.get('teams', {})
                league_info = fixture.get('league', {})
                
                prediction = Women1X2Prediction(
                    match_id=str(match_info.get('id')),
                    league=league_info.get('name', 'Unknown'),
                    league_id=league_info.get('id'),
                    home_team=teams.get('home', {}).get('name', 'Unknown'),
                    away_team=teams.get('away', {}).get('name', 'Unknown'),
                    match_date=match_info.get('date', '')[:10],
                    kickoff_time=match_info.get('date', ''),
                    selection=best_selection,
                    implied_prob=1.0 / odds[best_selection],
                    model_prob=probs[best_selection],
                    odds=odds[best_selection],
                    ev_percentage=best_ev * 100,
                    stake=stake,
                    notes={
                        'all_probs': probs,
                        'all_odds': odds,
                        'mode': self.mode
                    }
                )
                
                predictions.append(prediction)
                
                logger.info(f"✅ {prediction.home_team} vs {prediction.away_team} | "
                           f"{prediction.selection} @ {prediction.odds} | EV: {prediction.ev_percentage:.1f}%")
                
            except Exception as e:
                logger.error(f"❌ Error processing fixture: {e}")
                continue
        
        logger.info(f"🎯 Generated {len(predictions)} women's 1X2 predictions")
        logger.info(f"📊 Odds sources: {real_odds_count} real (The Odds API), {synthetic_odds_count} synthetic")
        return predictions
    
    def save_predictions(self, predictions: List[Women1X2Prediction]) -> int:
        """Save predictions to database"""
        if not predictions:
            logger.info("📊 No predictions to save")
            return 0
        
        with DatabaseConnection.get_connection() as conn:
            try:
                cur = conn.cursor()
                
                # Prepare data for batch insert
                data = []
                for pred in predictions:
                    data.append((
                        pred.match_id,
                        pred.league,
                        pred.league_id,
                        pred.home_team,
                        pred.away_team,
                        pred.match_date,
                        pred.kickoff_time,
                        pred.selection,
                        pred.implied_prob,
                        pred.model_prob,
                        pred.odds,
                        pred.ev_percentage,
                        pred.stake,
                        self.mode,
                        psycopg2.extras.Json(pred.notes),
                        'PROD'  # Production mode for ROI tracking
                    ))
                
                # Batch insert with ON CONFLICT DO NOTHING
                execute_values(
                    cur,
                    """
                    INSERT INTO women_match_winner_predictions 
                    (match_id, league, league_id, home_team, away_team, match_date, 
                     kickoff_time, selection, implied_prob, model_prob, odds, 
                     ev_percentage, stake, source_mode, notes, mode)
                    VALUES %s
                    ON CONFLICT (match_id) DO NOTHING
                    """,
                    data
                )
                
                saved_count = cur.rowcount
                logger.info(f"💾 Saved {saved_count} women's 1X2 predictions to database")
                
                return saved_count
                
            except Exception as e:
                logger.error(f"❌ Error saving predictions: {e}")
                return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    predictor = Women1X2Predictor(mode='TRAIN')
    predictions = predictor.generate_predictions()
    saved = predictor.save_predictions(predictions)
    
    print(f"\n{'='*60}")
    print(f"🎯 Women's 1X2 Prediction Summary")
    print(f"{'='*60}")
    print(f"Mode: {predictor.mode}")
    print(f"EV Threshold: {predictor.ev_threshold:.1%}")
    print(f"Predictions Generated: {len(predictions)}")
    print(f"Predictions Saved: {saved}")
    print(f"{'='*60}\n")

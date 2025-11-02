"""
🚀 ENHANCED EXACT SCORE PREDICTOR
Combines all advanced features for maximum accuracy
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Import our new modules
try:
    from advanced_features import AdvancedFeaturesAPI, OddsMovementTracker
    from neural_score_predictor import NeuralScorePredictor, ensemble_exact_score_prediction
    ADVANCED_FEATURES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Advanced features not available: {e}")
    ADVANCED_FEATURES_AVAILABLE = False

# Import injury scraper for fallback when API-Football is unavailable
try:
    from injury_scraper import InjuryScraper
    INJURY_SCRAPER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Injury scraper not available: {e}")
    INJURY_SCRAPER_AVAILABLE = False

# Import SofaScore scraper for H2H and form data fallback
try:
    from sofascore_scraper import SofaScoreScraper
    SOFASCORE_SCRAPER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ SofaScore scraper not available: {e}")
    SOFASCORE_SCRAPER_AVAILABLE = False


class EnhancedExactScorePredictor:
    """
    🧠 ENHANCED PREDICTOR
    Combines multiple prediction methods for better accuracy
    """
    
    def __init__(self, db_path='data/real_football.db'):
        self.db_path = db_path
        
        # Initialize advanced features
        self.advanced_api = None
        self.odds_tracker = None
        self.neural_predictor = None
        self.injury_scraper = None
        self.sofascore_scraper = None
        
        if ADVANCED_FEATURES_AVAILABLE:
            try:
                self.advanced_api = AdvancedFeaturesAPI()
                self.odds_tracker = OddsMovementTracker(db_path)
                self.neural_predictor = NeuralScorePredictor()
                self.neural_predictor.load_model()  # Try to load pre-trained model
                logger.info("✅ Enhanced predictor initialized with all features")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize all features: {e}")
        
        # Initialize injury scraper as fallback
        if INJURY_SCRAPER_AVAILABLE:
            try:
                self.injury_scraper = InjuryScraper()
                logger.info("✅ Injury scraper initialized for fallback data")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize injury scraper: {e}")
        
        # Initialize SofaScore scraper as fallback for H2H and form data
        if SOFASCORE_SCRAPER_AVAILABLE:
            try:
                self.sofascore_scraper = SofaScoreScraper(db_path)
                logger.info("✅ SofaScore scraper initialized for H2H/form fallback")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize SofaScore scraper: {e}")
    
    def get_team_ids(self, home_team: str, away_team: str, league_id: Optional[int] = None) -> Tuple[Optional[int], Optional[int]]:
        """
        Get API-Football team IDs by searching for team names
        Uses caching to minimize API calls
        """
        import requests
        import time
        
        if not self.advanced_api or not self.advanced_api.api_key:
            return None, None
        
        def search_team(team_name: str) -> Optional[int]:
            """Search for team ID by name"""
            cache_key = f"team_id_{team_name}"
            
            # Check cache
            if cache_key in self.advanced_api.cache:
                cached_id, timestamp = self.advanced_api.cache[cache_key]
                if time.time() - timestamp < 86400:  # Cache for 24 hours
                    return cached_id
            
            try:
                # Search for team (API-Football uses 'search' parameter, not 'name')
                params = {'search': team_name}
                data = self.advanced_api._make_request('teams', params)
                
                if data and 'response' in data and data['response']:
                    # Get the first matching team
                    team_id = data['response'][0]['team']['id']
                    # Cache the result
                    self.advanced_api.cache[cache_key] = (team_id, time.time())
                    return team_id
            except Exception as e:
                logger.warning(f"⚠️ Team search failed for {team_name}: {e}")
            
            return None
        
        home_id = search_team(home_team)
        away_id = search_team(away_team)
        
        return home_id, away_id
    
    def enrich_prediction_data(self, match: Dict, xg_data: Dict) -> Dict:
        """
        🔥 CORE ENHANCEMENT
        Enrich match data with ALL advanced features
        
        Returns enriched analysis dict with:
        - Team form (last 5 matches)
        - Head-to-head history
        - League standings
        - Injury/lineup data
        - Odds movement tracking
        """
        enriched = {
            'xg_prediction': xg_data,
            'home_form': {},
            'away_form': {},
            'h2h': {},
            'home_standings': {},
            'away_standings': {},
            'odds_movement': {},
            'lineups': {}
        }
        
        if not self.advanced_api:
            logger.warning("⚠️ Advanced API not available, using defaults")
            return enriched
        
        try:
            # Get team IDs via real API search
            home_team = match['home_team']
            away_team = match['away_team']
            league_id = match.get('league_id')
            
            # 🔧 FIX: Use real team ID lookup instead of placeholder
            home_id, away_id = self.get_team_ids(home_team, away_team, league_id)
            
            if not home_id or not away_id:
                logger.warning(f"⚠️ Could not find team IDs for {home_team} vs {away_team}, using defaults")
                enriched['_real_data_available'] = False
                return enriched
            
            enriched['_real_data_available'] = True
            logger.info(f"✅ Found team IDs: {home_team}={home_id}, {away_team}={away_id}")
            
            # 1. TEAM FORM (last 5 matches)
            form_data_obtained = False
            try:
                logger.info(f"📊 Fetching team form from API-Football")
                enriched['home_form'] = self.advanced_api.get_team_form(home_id, last_n=5)
                enriched['away_form'] = self.advanced_api.get_team_form(away_id, last_n=5)
                form_data_obtained = True
                logger.info(f"✅ API-Football form data obtained")
            except Exception as e:
                logger.warning(f"⚠️ API-Football form data failed: {e}")
            
            # Fallback to SofaScore scraper if API-Football failed
            if not form_data_obtained and self.sofascore_scraper:
                logger.info(f"📊 Fetching team form from SofaScore scraper")
                try:
                    league_name = match.get('league', 'Premier League')
                    enriched['home_form'] = self.sofascore_scraper.get_team_form(home_team, league_name, last_n=5)
                    enriched['away_form'] = self.sofascore_scraper.get_team_form(away_team, league_name, last_n=5)
                    logger.info(f"✅ SofaScore form data obtained")
                except Exception as e:
                    logger.warning(f"⚠️ SofaScore form scraper failed: {e}")
            
            # 2. HEAD-TO-HEAD HISTORY
            h2h_data_obtained = False
            try:
                logger.info(f"🔄 Fetching H2H from API-Football")
                enriched['h2h'] = self.advanced_api.get_head_to_head(home_id, away_id, last_n=10)
                h2h_data_obtained = True
                logger.info(f"✅ API-Football H2H data obtained")
            except Exception as e:
                logger.warning(f"⚠️ API-Football H2H failed: {e}")
            
            # Fallback to SofaScore scraper if API-Football failed
            if not h2h_data_obtained and self.sofascore_scraper:
                logger.info(f"🔄 Fetching H2H from SofaScore scraper")
                try:
                    league_name = match.get('league', 'Premier League')
                    enriched['h2h'] = self.sofascore_scraper.get_h2h_data(home_team, away_team, league_name)
                    logger.info(f"✅ SofaScore H2H data obtained")
                except Exception as e:
                    logger.warning(f"⚠️ SofaScore H2H scraper failed: {e}")
            
            # 3. LEAGUE STANDINGS (if league info available)
            standings_obtained = False
            if 'league_id' in match and 'season' in match:
                try:
                    logger.info(f"📈 Fetching league standings from API-Football")
                    standings = self.advanced_api.get_league_standings(
                        match['league_id'], 
                        match['season']
                    )
                    enriched['home_standings'] = standings.get(home_id, {})
                    enriched['away_standings'] = standings.get(away_id, {})
                    standings_obtained = True
                    logger.info(f"✅ API-Football standings obtained")
                except Exception as e:
                    logger.warning(f"⚠️ API-Football standings failed: {e}")
            
            # Fallback to SofaScore scraper if API-Football failed
            if not standings_obtained and self.sofascore_scraper:
                logger.info(f"📈 Fetching league standings from SofaScore scraper")
                try:
                    league_name = match.get('league', 'Premier League')
                    standings_list = self.sofascore_scraper.get_league_standings(league_name)
                    
                    # Convert list to dict by team name
                    for standing in standings_list:
                        if standing['team'] == home_team:
                            enriched['home_standings'] = standing
                        if standing['team'] == away_team:
                            enriched['away_standings'] = standing
                    
                    logger.info(f"✅ SofaScore standings obtained")
                except Exception as e:
                    logger.warning(f"⚠️ SofaScore standings scraper failed: {e}")
            
            # 4. INJURIES AND LINEUPS
            # Initialize with default structure
            enriched['lineups'] = {
                'home_injuries': 0,
                'away_injuries': 0,
                'key_players_out': [],
                'lineups_confirmed': False,
                'home_formation': None,
                'away_formation': None
            }
            
            injury_data_obtained = False
            
            # Try API-Football first if fixture_id available
            if 'fixture_id' in match and self.advanced_api:
                try:
                    logger.info(f"🏥 Fetching injuries and lineups from API-Football")
                    api_lineups = self.advanced_api.get_injuries_and_lineups(match['fixture_id'])
                    if api_lineups:
                        enriched['lineups'] = api_lineups
                        injury_data_obtained = True
                        logger.info(f"✅ API-Football injuries obtained")
                except Exception as e:
                    logger.warning(f"⚠️ API-Football injuries failed: {e}")
            
            # Fallback to injury scraper if API-Football failed or unavailable
            if not injury_data_obtained and self.injury_scraper:
                logger.info(f"🏥 Fetching injuries from web scraper (API-Football unavailable)")
                try:
                    # Map league name for scraper
                    league_name = match.get('league', 'Premier League')
                    
                    # Get injuries for both teams
                    home_injuries_list = self.injury_scraper.get_team_injuries(home_team, league_name, use_cache=True)
                    away_injuries_list = self.injury_scraper.get_team_injuries(away_team, league_name, use_cache=True)
                    
                    # Always update lineups with scraper data (even if lists are empty)
                    enriched['lineups'] = {
                        'home_injuries': len(home_injuries_list),
                        'away_injuries': len(away_injuries_list),
                        'key_players_out': [
                            {'team': home_team, 'player': inj['player'], 'injury': inj['injury_type']}
                            for inj in home_injuries_list
                        ] + [
                            {'team': away_team, 'player': inj['player'], 'injury': inj['injury_type']}
                            for inj in away_injuries_list
                        ],
                        'lineups_confirmed': False,
                        'home_formation': None,
                        'away_formation': None
                    }
                    
                    logger.info(f"✅ Scraped injuries: {home_team} ({len(home_injuries_list)}), {away_team} ({len(away_injuries_list)})")
                    injury_data_obtained = True
                    
                except Exception as e:
                    logger.warning(f"⚠️ Injury scraper failed: {e}, using default empty structure")
            
            # 5. ODDS MOVEMENT TRACKING
            match_id = match.get('id', f"{home_team}_vs_{away_team}")
            
            # Record current odds for tracking
            if self.odds_tracker and 'odds' in match:
                self.odds_tracker.record_odds(
                    match_id=match_id,
                    market='exact_score',
                    selection=f"{match['home_team']} vs {match['away_team']}",
                    odds=match.get('odds', 10.0)
                )
            
            # Get odds movement analysis
            if self.odds_tracker:
                enriched['odds_movement'] = self.odds_tracker.get_odds_movement(
                    match_id=match_id,
                    market='exact_score',
                    selection=f"{match['home_team']} vs {match['away_team']}"
                )
            
            logger.info("✅ Match data enriched with advanced features")
            
        except Exception as e:
            logger.error(f"❌ Error enriching data: {e}")
        
        return enriched
    
    def predict_with_ensemble(self, xg_home: float, xg_away: float, 
                            enriched_data: Dict) -> Dict[str, float]:
        """
        🎯 ENSEMBLE PREDICTION
        Combines multiple prediction methods
        """
        # Get neural network predictions if available
        neural_probs = None
        if self.neural_predictor:
            try:
                # Create feature vector from enriched data
                # (In production, this would be properly engineered)
                features = self._create_feature_vector(xg_home, xg_away, enriched_data)
                predictions = self.neural_predictor.predict_score_probabilities(features)
                if predictions:
                    neural_probs = predictions[0]
            except Exception as e:
                logger.warning(f"⚠️ Neural prediction failed: {e}")
        
        # Get H2H-based historical patterns
        h2h_probs = self._extract_h2h_patterns(enriched_data.get('h2h', {}))
        
        # Use ensemble method
        ensemble_probs = ensemble_exact_score_prediction(
            xg_home=xg_home,
            xg_away=xg_away,
            neural_probs=neural_probs,
            historical_h2h=h2h_probs
        )
        
        return ensemble_probs
    
    def _create_feature_vector(self, xg_home: float, xg_away: float, 
                               enriched_data: Dict) -> List[List[float]]:
        """
        Create feature vector for neural network
        """
        import numpy as np
        
        home_form = enriched_data.get('home_form', {})
        away_form = enriched_data.get('away_form', {})
        h2h = enriched_data.get('h2h', {})
        home_standings = enriched_data.get('home_standings', {})
        away_standings = enriched_data.get('away_standings', {})
        odds_movement = enriched_data.get('odds_movement', {})
        lineups = enriched_data.get('lineups', {})
        
        features = [
            # xG features
            xg_home, xg_away, xg_home + xg_away, xg_home - xg_away,
            xg_home / max(xg_away, 0.1),
            
            # Team form
            home_form.get('win_rate', 0.4),
            away_form.get('win_rate', 0.4),
            home_form.get('goals_per_game', 1.2),
            away_form.get('goals_per_game', 1.2),
            home_form.get('conceded_per_game', 1.2),
            away_form.get('conceded_per_game', 1.2),
            home_form.get('clean_sheet_rate', 0.2),
            away_form.get('clean_sheet_rate', 0.2),
            
            # H2H
            h2h.get('team1_win_rate', 0.33),
            h2h.get('avg_total_goals', 2.5),
            h2h.get('over_2_5_rate', 0.5),
            h2h.get('btts_rate', 0.6),
            
            # League position
            home_standings.get('rank', 10),
            away_standings.get('rank', 10),
            abs(home_standings.get('rank', 10) - away_standings.get('rank', 10)),
            
            # Odds movement
            odds_movement.get('movement_percent', 0),
            odds_movement.get('velocity', 0),
            1 if odds_movement.get('sharp_money_indicator') else 0,
            
            # Injuries/lineups
            1 if lineups.get('lineups_confirmed') else 0,
            lineups.get('home_injuries', 0) + lineups.get('away_injuries', 0)
        ]
        
        return np.array([features])
    
    def _extract_h2h_patterns(self, h2h_data: Dict) -> Optional[Dict[str, float]]:
        """
        Extract common score patterns from H2H history
        """
        if not h2h_data or h2h_data.get('total_matches', 0) == 0:
            return None
        
        # Simplified H2H pattern extraction
        avg_goals_1 = h2h_data.get('avg_team1_goals', 1.5)
        avg_goals_2 = h2h_data.get('avg_team2_goals', 1.5)
        
        # Create rough distribution based on H2H averages
        from scipy.stats import poisson
        
        h2h_probs = {}
        for home_goals in range(7):
            for away_goals in range(7):
                score = f"{home_goals}-{away_goals}"
                prob_home = poisson.pmf(home_goals, avg_goals_1)
                prob_away = poisson.pmf(away_goals, avg_goals_2)
                h2h_probs[score] = prob_home * prob_away
        
        # Normalize
        total = sum(h2h_probs.values())
        h2h_probs = {k: v/total for k, v in h2h_probs.items()}
        
        return h2h_probs
    
    def calculate_prediction_quality(self, enriched_data: Dict) -> float:
        """
        Calculate overall prediction quality score (0-100)
        Based on data availability and confidence factors
        """
        quality = 50  # Base quality
        
        # Bonus for team form data
        if enriched_data.get('home_form', {}).get('matches_played', 0) >= 5:
            quality += 10
        if enriched_data.get('away_form', {}).get('matches_played', 0) >= 5:
            quality += 10
        
        # Bonus for H2H history
        h2h_matches = enriched_data.get('h2h', {}).get('total_matches', 0)
        if h2h_matches >= 5:
            quality += 10
        elif h2h_matches >= 3:
            quality += 5
        
        # Bonus for odds movement data (sharp money indicator)
        if enriched_data.get('odds_movement', {}).get('sharp_money_indicator'):
            quality += 15
        
        # Bonus for confirmed lineups
        if enriched_data.get('lineups', {}).get('lineups_confirmed'):
            quality += 10
        
        # Penalty for injuries
        injuries = enriched_data.get('lineups', {}).get('home_injuries', 0) + \
                  enriched_data.get('lineups', {}).get('away_injuries', 0)
        quality -= min(injuries * 3, 15)
        
        return min(100, max(30, quality))

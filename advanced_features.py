"""
🚀 ADVANCED FEATURES MODULE
Enhanced prediction features for better accuracy
"""

import os
import requests
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import statistics
import logging
from api_cache_manager import APICacheManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AdvancedFeaturesAPI:
    """Advanced features for better predictions using API-Football"""
    
    def __init__(self, cache_manager: Optional[APICacheManager] = None):
        self.api_key = os.getenv('API_FOOTBALL_KEY')
        if not self.api_key:
            raise ValueError("❌ API_FOOTBALL_KEY required for advanced features")
        
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            'x-apisports-key': self.api_key
        }
        
        # Use persistent cache if provided, fallback to in-memory
        self.cache_manager = cache_manager
        self.cache = {}  # Always provide for backward compatibility
        self.cache_duration = 3600
        
        if cache_manager:
            logger.info("🚀 Advanced Features API initialized with PERSISTENT cache")
        else:
            logger.info("🚀 Advanced Features API initialized with in-memory cache (FALLBACK)")
    
    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """Make API request with caching and rate limiting"""
        cache_key = f"{endpoint}_{json.dumps(params, sort_keys=True)}"
        
        # Use persistent cache if available
        if self.cache_manager:
            # Check persistent cache first
            cached_response = self.cache_manager.get_cached_response(cache_key, endpoint)
            if cached_response:
                return cached_response
            
            # Check quota before making request
            if not self.cache_manager.check_quota_available():
                logger.warning(f"⚠️ API quota exhausted for {self.cache_manager.api_name}")
                return None
        else:
            # Fallback: Check in-memory cache
            if cache_key in self.cache:
                cached_data, timestamp = self.cache[cache_key]
                if time.time() - timestamp < self.cache_duration:
                    return cached_data
        
        # Make request
        try:
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Cache response
                if self.cache_manager:
                    # Determine TTL based on endpoint
                    ttl_hours = self._get_ttl_for_endpoint(endpoint)
                    self.cache_manager.cache_response(cache_key, endpoint, data, ttl_hours)
                    self.cache_manager.increment_request_count()
                else:
                    # Fallback: in-memory cache
                    self.cache[cache_key] = (data, time.time())
                
                time.sleep(0.5)  # Rate limiting
                return data
            else:
                logger.warning(f"⚠️ API request failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"❌ Request error: {e}")
            return None
    
    def _get_ttl_for_endpoint(self, endpoint: str) -> int:
        """Get cache TTL (hours) based on endpoint type"""
        if 'fixtures' in endpoint or 'standings' in endpoint:
            return 24  # Fixtures and standings: 24 hours
        elif 'injuries' in endpoint:
            return 2  # Injuries: 2 hours (changes frequently)
        elif 'players' in endpoint or 'statistics' in endpoint:
            return 12  # Player stats: 12 hours
        else:
            return 24  # Default: 24 hours
    
    def get_team_form(self, team_id: int, last_n: int = 5) -> Dict:
        """
        Get detailed team form for last N matches
        Returns: win rate, goals, clean sheets, etc.
        """
        try:
            # Get last N fixtures for the team
            data = self._make_request('fixtures', {
                'team': team_id,
                'last': last_n,
                'status': 'FT'
            })
            
            if not data or 'response' not in data:
                return self._default_form()
            
            fixtures = data['response']
            
            if not fixtures:
                return self._default_form()
            
            wins, draws, losses = 0, 0, 0
            goals_scored, goals_conceded = 0, 0
            clean_sheets = 0
            home_goals, away_goals = 0, 0
            home_matches, away_matches = 0, 0
            
            for fixture in fixtures:
                teams = fixture['teams']
                goals = fixture['goals']
                
                # Determine if home or away
                is_home = teams['home']['id'] == team_id
                
                if is_home:
                    home_matches += 1
                    scored = goals['home']
                    conceded = goals['away']
                    home_goals += scored
                else:
                    away_matches += 1
                    scored = goals['away']
                    conceded = goals['home']
                    away_goals += scored
                
                goals_scored += scored
                goals_conceded += conceded
                
                if conceded == 0:
                    clean_sheets += 1
                
                # Determine result
                if scored > conceded:
                    wins += 1
                elif scored == conceded:
                    draws += 1
                else:
                    losses += 1
            
            total_matches = len(fixtures)
            
            return {
                'matches_played': total_matches,
                'wins': wins,
                'draws': draws,
                'losses': losses,
                'win_rate': wins / total_matches if total_matches > 0 else 0,
                'points_per_game': (wins * 3 + draws) / total_matches if total_matches > 0 else 0,
                'goals_scored': goals_scored,
                'goals_conceded': goals_conceded,
                'goals_per_game': goals_scored / total_matches if total_matches > 0 else 0,
                'conceded_per_game': goals_conceded / total_matches if total_matches > 0 else 0,
                'goal_difference': goals_scored - goals_conceded,
                'clean_sheet_rate': clean_sheets / total_matches if total_matches > 0 else 0,
                'home_goals_avg': home_goals / home_matches if home_matches > 0 else 0,
                'away_goals_avg': away_goals / away_matches if away_matches > 0 else 0,
                'form_string': f"{'W' * wins}{'D' * draws}{'L' * losses}"
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting team form: {e}")
            return self._default_form()
    
    def get_head_to_head(self, team1_id: int, team2_id: int, last_n: int = 10) -> Dict:
        """
        Get head-to-head statistics between two teams
        """
        try:
            data = self._make_request('fixtures/headtohead', {
                'h2h': f"{team1_id}-{team2_id}",
                'last': last_n
            })
            
            if not data or 'response' not in data:
                return self._default_h2h()
            
            fixtures = data['response']
            
            if not fixtures:
                return self._default_h2h()
            
            team1_wins, team2_wins, draws = 0, 0, 0
            total_goals = 0
            team1_goals, team2_goals = 0, 0
            over_2_5 = 0
            btts = 0
            
            for fixture in fixtures:
                teams = fixture['teams']
                goals = fixture['goals']
                
                home_id = teams['home']['id']
                home_goals = goals['home']
                away_goals = goals['away']
                
                total_goals += home_goals + away_goals
                
                # Track which team won
                if home_id == team1_id:
                    team1_goals += home_goals
                    team2_goals += away_goals
                    if home_goals > away_goals:
                        team1_wins += 1
                    elif away_goals > home_goals:
                        team2_wins += 1
                    else:
                        draws += 1
                else:
                    team1_goals += away_goals
                    team2_goals += home_goals
                    if away_goals > home_goals:
                        team1_wins += 1
                    elif home_goals > away_goals:
                        team2_wins += 1
                    else:
                        draws += 1
                
                # Over 2.5 and BTTS
                if (home_goals + away_goals) > 2.5:
                    over_2_5 += 1
                if home_goals > 0 and away_goals > 0:
                    btts += 1
            
            total_matches = len(fixtures)
            
            return {
                'total_matches': total_matches,
                'team1_wins': team1_wins,
                'team2_wins': team2_wins,
                'draws': draws,
                'team1_win_rate': team1_wins / total_matches if total_matches > 0 else 0,
                'avg_total_goals': total_goals / total_matches if total_matches > 0 else 0,
                'avg_team1_goals': team1_goals / total_matches if total_matches > 0 else 0,
                'avg_team2_goals': team2_goals / total_matches if total_matches > 0 else 0,
                'over_2_5_rate': over_2_5 / total_matches if total_matches > 0 else 0,
                'btts_rate': btts / total_matches if total_matches > 0 else 0
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting H2H: {e}")
            return self._default_h2h()
    
    def get_league_standings(self, league_id: int, season: int) -> Dict[int, Dict]:
        """
        Get league standings for position-based features
        Returns dict mapping team_id to standings data
        """
        try:
            data = self._make_request('standings', {
                'league': league_id,
                'season': season
            })
            
            if not data or 'response' not in data or not data['response']:
                return {}
            
            standings = {}
            
            for league_data in data['response']:
                if 'league' not in league_data or 'standings' not in league_data['league']:
                    continue
                
                for group in league_data['league']['standings']:
                    for team_standing in group:
                        team_id = team_standing['team']['id']
                        standings[team_id] = {
                            'rank': team_standing['rank'],
                            'points': team_standing['points'],
                            'goals_diff': team_standing['goalsDiff'],
                            'form': team_standing.get('form', ''),
                            'home_wins': team_standing['home']['win'],
                            'away_wins': team_standing['away']['win'],
                            'home_goals': team_standing['home']['goals']['for'],
                            'away_goals': team_standing['away']['goals']['for']
                        }
            
            return standings
        
        except Exception as e:
            logger.error(f"❌ Error getting standings: {e}")
            return {}
    
    def get_injuries_and_lineups(self, fixture_id: int) -> Dict:
        """
        Get injuries and expected lineups for a match
        """
        try:
            # Get injuries
            injuries_data = self._make_request('injuries', {
                'fixture': fixture_id
            })
            
            injuries = {
                'home_injuries': 0,
                'away_injuries': 0,
                'key_players_out': []
            }
            
            if injuries_data and 'response' in injuries_data:
                for injury in injuries_data['response']:
                    team_id = injury['team']['id']
                    player_name = injury['player']['name']
                    injuries['key_players_out'].append({
                        'team_id': team_id,
                        'player': player_name
                    })
            
            # Get lineups if available (usually 1-2 hours before match)
            lineups_data = self._make_request('fixtures/lineups', {
                'fixture': fixture_id
            })
            
            lineups = {
                'lineups_confirmed': False,
                'home_formation': None,
                'away_formation': None
            }
            
            if lineups_data and 'response' in lineups_data and lineups_data['response']:
                lineups['lineups_confirmed'] = True
                if len(lineups_data['response']) >= 2:
                    lineups['home_formation'] = lineups_data['response'][0].get('formation')
                    lineups['away_formation'] = lineups_data['response'][1].get('formation')
            
            return {**injuries, **lineups}
        
        except Exception as e:
            logger.error(f"❌ Error getting injuries/lineups: {e}")
            return {
                'home_injuries': 0,
                'away_injuries': 0,
                'key_players_out': [],
                'lineups_confirmed': False,
                'home_formation': None,
                'away_formation': None
            }
    
    def get_enhanced_fixture_data(self, fixture_id: int) -> Dict:
        """
        Get comprehensive fixture data including statistics
        """
        try:
            # Get fixture statistics
            stats_data = self._make_request('fixtures/statistics', {
                'fixture': fixture_id
            })
            
            if not stats_data or 'response' not in stats_data or not stats_data['response']:
                return {}
            
            # Parse statistics
            stats = {
                'home_possession': 50,
                'away_possession': 50,
                'home_shots': 0,
                'away_shots': 0,
                'home_shots_on_target': 0,
                'away_shots_on_target': 0
            }
            
            if len(stats_data['response']) >= 2:
                home_stats = stats_data['response'][0].get('statistics', [])
                away_stats = stats_data['response'][1].get('statistics', [])
                
                for stat in home_stats:
                    if stat['type'] == 'Ball Possession':
                        stats['home_possession'] = int(stat['value'].replace('%', '')) if stat['value'] else 50
                    elif stat['type'] == 'Total Shots':
                        stats['home_shots'] = int(stat['value']) if stat['value'] else 0
                    elif stat['type'] == 'Shots on Goal':
                        stats['home_shots_on_target'] = int(stat['value']) if stat['value'] else 0
                
                for stat in away_stats:
                    if stat['type'] == 'Ball Possession':
                        stats['away_possession'] = int(stat['value'].replace('%', '')) if stat['value'] else 50
                    elif stat['type'] == 'Total Shots':
                        stats['away_shots'] = int(stat['value']) if stat['value'] else 0
                    elif stat['type'] == 'Shots on Goal':
                        stats['away_shots_on_target'] = int(stat['value']) if stat['value'] else 0
            
            return stats
        
        except Exception as e:
            logger.error(f"❌ Error getting fixture data: {e}")
            return {}
    
    def _default_form(self) -> Dict:
        """Default form data when API fails"""
        return {
            'matches_played': 5,
            'wins': 2,
            'draws': 1,
            'losses': 2,
            'win_rate': 0.4,
            'points_per_game': 1.4,
            'goals_scored': 6,
            'goals_conceded': 6,
            'goals_per_game': 1.2,
            'conceded_per_game': 1.2,
            'goal_difference': 0,
            'clean_sheet_rate': 0.2,
            'home_goals_avg': 1.3,
            'away_goals_avg': 1.1,
            'form_string': 'WWDLL'
        }
    
    def _default_h2h(self) -> Dict:
        """Default H2H data when API fails"""
        return {
            'total_matches': 0,
            'team1_wins': 0,
            'team2_wins': 0,
            'draws': 0,
            'team1_win_rate': 0.33,
            'avg_total_goals': 2.5,
            'avg_team1_goals': 1.2,
            'avg_team2_goals': 1.3,
            'over_2_5_rate': 0.5,
            'btts_rate': 0.6
        }


class OddsMovementTracker:
    """Track odds movements to detect sharp money"""
    
    def __init__(self, db_path='data/real_football.db'):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize odds tracking table"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS odds_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                market TEXT NOT NULL,
                selection TEXT NOT NULL,
                odds REAL NOT NULL,
                bookmaker TEXT,
                timestamp INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_odds_match 
            ON odds_movements(match_id, market, timestamp)
        ''')
        
        conn.commit()
        conn.close()
    
    def record_odds(self, match_id: str, market: str, selection: str, 
                    odds: float, bookmaker: str = 'average'):
        """Record current odds for movement tracking"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO odds_movements 
                (match_id, market, selection, odds, bookmaker, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (match_id, market, selection, odds, bookmaker, int(time.time())))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Error recording odds: {e}")
    
    def get_odds_movement(self, match_id: str, market: str, selection: str) -> Dict:
        """
        Analyze odds movement for a specific selection
        Returns opening odds, current odds, movement direction, velocity
        """
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT odds, timestamp
                FROM odds_movements
                WHERE match_id = ? AND market = ? AND selection = ?
                ORDER BY timestamp ASC
            ''', (match_id, market, selection))
            
            records = cursor.fetchall()
            conn.close()
            
            if not records:
                return {
                    'opening_odds': 0,
                    'current_odds': 0,
                    'movement_percent': 0,
                    'movement_direction': 'stable',
                    'velocity': 0,
                    'sharp_money_indicator': False
                }
            
            opening_odds = records[0][0]
            current_odds = records[-1][0]
            
            movement_percent = ((current_odds - opening_odds) / opening_odds * 100) if opening_odds > 0 else 0
            
            # Determine direction
            if movement_percent > 2:
                direction = 'drifting'  # Odds increasing (less confidence)
            elif movement_percent < -2:
                direction = 'steaming'  # Odds decreasing (more confidence / sharp money)
            else:
                direction = 'stable'
            
            # Calculate velocity (change rate)
            if len(records) > 1:
                time_diff = records[-1][1] - records[0][1]
                velocity = abs(movement_percent) / max(time_diff / 3600, 1)  # % per hour
            else:
                velocity = 0
            
            # Sharp money indicator: rapid steam move
            sharp_money = direction == 'steaming' and velocity > 5
            
            return {
                'opening_odds': opening_odds,
                'current_odds': current_odds,
                'movement_percent': movement_percent,
                'movement_direction': direction,
                'velocity': velocity,
                'sharp_money_indicator': sharp_money
            }
        
        except Exception as e:
            logger.error(f"❌ Error analyzing odds movement: {e}")
            return {
                'opening_odds': 0,
                'current_odds': 0,
                'movement_percent': 0,
                'movement_direction': 'stable',
                'velocity': 0,
                'sharp_money_indicator': False
            }

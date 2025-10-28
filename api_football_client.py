"""
API-Football Client for Real Football Data
Handles injuries, lineups, statistics, and match validation
"""

import os
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class APIFootballClient:
    """Client for API-Football data integration"""
    
    def __init__(self):
        self.api_key = os.getenv('API_FOOTBALL_KEY')
        if not self.api_key:
            raise ValueError("❌ API_FOOTBALL_KEY not found")
        
        self.base_url = "https://v3.football.api-sports.io"
        self.headers = {
            'x-apisports-key': self.api_key
        }
        self.request_count = 0
        self.last_request_time = 0
        self.daily_quota_limit = 7000  # 7500 total, leave buffer for safety
        
        # Caching to minimize API calls
        self.team_id_cache = {}  # Cache team IDs
        self.fixture_cache = {}  # Cache fixture lookups by teams+date
        self.injury_cache = {}  # Cache injury data (expires in 2 hours)
        self.lineup_cache = {}  # Cache lineup data once fetched
        self.stats_cache = {}  # Cache statistics for the day
        
        logger.info("✅ API-Football client initialized with smart caching")
    
    def _rate_limit(self):
        """Rate limiting to avoid API quota issues (100 requests/day on free tier)"""
        # Check if we've hit daily quota
        if self.request_count >= self.daily_quota_limit:
            logger.warning(f"⚠️ Daily quota limit reached ({self.daily_quota_limit}), skipping API call")
            raise Exception(f"Daily API quota limit reached: {self.daily_quota_limit}")
        
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < 1.0:
            time.sleep(1.0 - time_since_last)
        
        self.last_request_time = time.time()
        self.request_count += 1
        
        if self.request_count % 10 == 0:
            logger.info(f"📊 API-Football requests: {self.request_count}/{self.daily_quota_limit}")
    
    def get_fixture_by_teams_and_date(self, home_team: str, away_team: str, match_date: str) -> Optional[Dict]:
        """
        Find fixture ID by team names and match date (with caching)
        Returns fixture with detailed information
        """
        # Check cache first
        cache_key = f"{home_team}_{away_team}_{match_date}"
        if cache_key in self.fixture_cache:
            logger.info(f"📦 Using cached fixture for {home_team} vs {away_team}")
            return self.fixture_cache[cache_key]
        
        self._rate_limit()
        
        try:
            home_id = self.get_team_id(home_team)
            away_id = self.get_team_id(away_team)
            
            if not home_id or not away_id:
                logger.warning(f"⚠️ Could not find team IDs for {home_team} vs {away_team}")
                self.fixture_cache[cache_key] = None
                return None
            
            date_obj = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
            date_str = date_obj.strftime('%Y-%m-%d')
            
            url = f"{self.base_url}/fixtures"
            params = {
                'date': date_str,
                'team': home_id
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get('response', [])
                
                for fixture in fixtures:
                    teams = fixture.get('teams', {})
                    if (teams.get('home', {}).get('id') == home_id and 
                        teams.get('away', {}).get('id') == away_id):
                        logger.info(f"✅ Found fixture: {fixture.get('fixture', {}).get('id')}")
                        # Cache the result
                        self.fixture_cache[cache_key] = fixture
                        return fixture
                
                logger.warning(f"⚠️ No matching fixture found for {home_team} vs {away_team} on {date_str}")
                self.fixture_cache[cache_key] = None
                return None
            else:
                logger.error(f"❌ API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error finding fixture: {e}")
            return None
    
    def get_team_id(self, team_name: str) -> Optional[int]:
        """Get team ID by name with caching"""
        if not hasattr(self, '_team_cache'):
            self._team_cache = {}
        
        if team_name in self._team_cache:
            return self._team_cache[team_name]
        
        self._rate_limit()
        
        try:
            url = f"{self.base_url}/teams"
            params = {'search': team_name}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                teams = data.get('response', [])
                
                for team_data in teams:
                    team = team_data.get('team', {})
                    if team.get('name', '').lower() == team_name.lower():
                        team_id = team.get('id')
                        self._team_cache[team_name] = team_id
                        return team_id
                
                if teams:
                    team_id = teams[0].get('team', {}).get('id')
                    self._team_cache[team_name] = team_id
                    return team_id
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting team ID for {team_name}: {e}")
            return None
    
    def get_injuries(self, fixture_id: int, home_team_id: int = None, away_team_id: int = None) -> Dict:
        """
        Get injury data for a specific fixture (cached for 2 hours)
        Returns dict with home and away team injuries properly classified
        """
        # Check cache first (expires after 2 hours)
        cache_key = f"injury_{fixture_id}"
        if cache_key in self.injury_cache:
            cached_data, cache_time = self.injury_cache[cache_key]
            if time.time() - cache_time < 7200:  # 2 hours in seconds
                logger.info(f"📦 Using cached injury data for fixture {fixture_id}")
                return cached_data
        
        self._rate_limit()
        
        try:
            url = f"{self.base_url}/injuries"
            params = {'fixture': fixture_id}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                injuries = data.get('response', [])
                
                home_injuries = []
                away_injuries = []
                
                for injury in injuries:
                    team = injury.get('team', {})
                    player = injury.get('player', {})
                    team_id = team.get('id')
                    
                    injury_info = {
                        'player_name': player.get('name', 'Unknown'),
                        'type': player.get('type', 'Unknown'),
                        'reason': player.get('reason', 'Unknown'),
                        'team_id': team_id,
                        'team_name': team.get('name', 'Unknown')
                    }
                    
                    if home_team_id and team_id == home_team_id:
                        home_injuries.append(injury_info)
                    elif away_team_id and team_id == away_team_id:
                        away_injuries.append(injury_info)
                    elif home_team_id is None and away_team_id is None:
                        home_injuries.append(injury_info)
                
                total_injuries = len(home_injuries) + len(away_injuries)
                has_key_injuries = total_injuries > 3
                
                logger.info(f"📋 Found {len(home_injuries)} home, {len(away_injuries)} away injuries for fixture {fixture_id}")
                
                result = {
                    'total_injuries': total_injuries,
                    'home_injuries': len(home_injuries),
                    'away_injuries': len(away_injuries),
                    'injuries': home_injuries + away_injuries,
                    'home_injury_list': home_injuries,
                    'away_injury_list': away_injuries,
                    'has_key_injuries': has_key_injuries
                }
                
                # Cache the result with timestamp
                self.injury_cache[cache_key] = (result, time.time())
                return result
            else:
                logger.warning(f"⚠️ Could not fetch injuries: {response.status_code}")
                return {'total_injuries': 0, 'home_injuries': 0, 'away_injuries': 0, 'injuries': [], 'has_key_injuries': False}
                
        except Exception as e:
            logger.error(f"❌ Error fetching injuries: {e}")
            return {'total_injuries': 0, 'home_injuries': 0, 'away_injuries': 0, 'injuries': [], 'has_key_injuries': False}
    
    def get_lineups(self, fixture_id: int) -> Dict:
        """
        Get confirmed lineups for a fixture (cached once fetched)
        Returns dict with lineup confirmation status and key player info
        """
        # Check cache first (lineups don't change once confirmed)
        cache_key = f"lineup_{fixture_id}"
        if cache_key in self.lineup_cache:
            logger.info(f"📦 Using cached lineup data for fixture {fixture_id}")
            return self.lineup_cache[cache_key]
        
        self._rate_limit()
        
        try:
            url = f"{self.base_url}/fixtures/lineups"
            params = {'fixture': fixture_id}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                lineups = data.get('response', [])
                
                if not lineups:
                    return {
                        'confirmed': False,
                        'home_formation': None,
                        'away_formation': None,
                        'home_starters': 0,
                        'away_starters': 0
                    }
                
                result = {
                    'confirmed': True,
                    'home_formation': None,
                    'away_formation': None,
                    'home_starters': 0,
                    'away_starters': 0
                }
                
                for i, lineup in enumerate(lineups[:2]):
                    formation = lineup.get('formation', 'Unknown')
                    start_xi = lineup.get('startXI', [])
                    
                    if i == 0:
                        result['home_formation'] = formation
                        result['home_starters'] = len(start_xi)
                    else:
                        result['away_formation'] = formation
                        result['away_starters'] = len(start_xi)
                
                logger.info(f"✅ Lineups confirmed for fixture {fixture_id}")
                
                # Cache the confirmed lineup (doesn't change once set)
                self.lineup_cache[cache_key] = result
                return result
            else:
                logger.info(f"⏳ Lineups not yet available for fixture {fixture_id}")
                return {
                    'confirmed': False,
                    'home_formation': None,
                    'away_formation': None,
                    'home_starters': 0,
                    'away_starters': 0
                }
                
        except Exception as e:
            logger.error(f"❌ Error fetching lineups: {e}")
            return {'confirmed': False, 'home_formation': None, 'away_formation': None}
    
    def get_fixture_statistics(self, fixture_id: int) -> Dict:
        """
        Get detailed match statistics including xG if available
        Returns statistics for both teams
        """
        self._rate_limit()
        
        try:
            url = f"{self.base_url}/fixtures/statistics"
            params = {'fixture': fixture_id}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                stats = data.get('response', [])
                
                if not stats or len(stats) < 2:
                    return {'home': {}, 'away': {}, 'has_xg': False}
                
                home_stats = {}
                away_stats = {}
                
                for i, team_stats in enumerate(stats[:2]):
                    statistics = team_stats.get('statistics', [])
                    parsed = {}
                    
                    for stat in statistics:
                        stat_type = stat.get('type', '')
                        value = stat.get('value')
                        
                        if stat_type == 'expected_goals':
                            parsed['xg'] = float(value) if value else 0.0
                        elif stat_type == 'Shots on Goal':
                            parsed['shots_on_target'] = int(value) if value else 0
                        elif stat_type == 'Total Shots':
                            parsed['total_shots'] = int(value) if value else 0
                        elif stat_type == 'Ball Possession':
                            parsed['possession'] = value
                    
                    if i == 0:
                        home_stats = parsed
                    else:
                        away_stats = parsed
                
                has_xg = 'xg' in home_stats or 'xg' in away_stats
                
                logger.info(f"📊 Statistics retrieved for fixture {fixture_id} (xG: {has_xg})")
                
                return {
                    'home': home_stats,
                    'away': away_stats,
                    'has_xg': has_xg
                }
            else:
                logger.warning(f"⚠️ No statistics available for fixture {fixture_id}")
                return {'home': {}, 'away': {}, 'has_xg': False}
                
        except Exception as e:
            logger.error(f"❌ Error fetching statistics: {e}")
            return {'home': {}, 'away': {}, 'has_xg': False}
    
    def get_team_last_matches(self, team_id: int, limit: int = 5) -> List[Dict]:
        """
        Get last N completed matches for a team with full statistics
        """
        self._rate_limit()
        
        try:
            url = f"{self.base_url}/fixtures"
            params = {
                'team': team_id,
                'last': limit,
                'status': 'FT'
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get('response', [])
                
                matches = []
                for fixture in fixtures:
                    teams = fixture.get('teams', {})
                    goals = fixture.get('goals', {})
                    
                    is_home = teams.get('home', {}).get('id') == team_id
                    
                    if is_home:
                        goals_for = goals.get('home', 0)
                        goals_against = goals.get('away', 0)
                    else:
                        goals_for = goals.get('away', 0)
                        goals_against = goals.get('home', 0)
                    
                    if goals_for > goals_against:
                        result = 'W'
                    elif goals_for < goals_against:
                        result = 'L'
                    else:
                        result = 'D'
                    
                    matches.append({
                        'fixture_id': fixture.get('fixture', {}).get('id'),
                        'date': fixture.get('fixture', {}).get('date'),
                        'goals_for': goals_for,
                        'goals_against': goals_against,
                        'result': result,
                        'is_home': is_home
                    })
                
                logger.info(f"📋 Found {len(matches)} recent matches for team {team_id}")
                return matches
            else:
                logger.error(f"❌ API error: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching team matches: {e}")
            return []
    
    def validate_match(self, home_team: str, away_team: str, match_date: str) -> Dict:
        """
        Validate if a match is still scheduled, not postponed/cancelled
        Returns validation status and any issues
        """
        try:
            fixture = self.get_fixture_by_teams_and_date(home_team, away_team, match_date)
            
            if not fixture:
                return {
                    'valid': False,
                    'reason': 'Match not found in API-Football',
                    'status': 'unknown'
                }
            
            fixture_info = fixture.get('fixture', {})
            status = fixture_info.get('status', {})
            status_short = status.get('short', 'NS')
            
            if status_short in ['PST', 'CANC', 'ABD']:
                return {
                    'valid': False,
                    'reason': f"Match {status.get('long', 'postponed')}",
                    'status': status_short
                }
            
            return {
                'valid': True,
                'reason': 'Match confirmed',
                'status': status_short,
                'fixture_id': fixture_info.get('id')
            }
            
        except Exception as e:
            logger.error(f"❌ Error validating match: {e}")
            return {
                'valid': False,
                'reason': f'Validation error: {str(e)}',
                'status': 'error'
            }

"""
API-Football Client for Real Football Data
Handles injuries, lineups, statistics, and match validation
"""

import os
import re
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from team_id_mappings import get_team_id_from_mapping
from api_cache_manager import APICacheManager

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
        self.last_request_time = 0
        
        self.cache_manager = APICacheManager('api_football', quota_limit=7000)
        
        logger.info("✅ API-Football client initialized with PERSISTENT caching (shared across all workflows)")
    
    def _rate_limit(self):
        """Rate limiting using shared quota counter across ALL workflows"""
        if not self.cache_manager.check_quota_available():
            stats = self.cache_manager.get_quota_stats()
            logger.warning(f"⚠️ Daily quota exhausted: {stats['request_count']}/{stats['quota_limit']}")
            raise Exception(f"Daily API quota exhausted: {stats['request_count']}/{stats['quota_limit']}")
        
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < 1.0:
            time.sleep(1.0 - time_since_last)
        
        self.last_request_time = time.time()
        self.cache_manager.increment_request_count()
    
    def _fetch_with_cache(self, endpoint: str, params: dict, cache_key: str, ttl_hours: int = 24) -> Optional[Dict]:
        """
        Centralized cached API fetcher - ALL API calls should use this
        
        Args:
            endpoint: API endpoint (e.g., 'fixtures', 'teams/statistics')
            params: Query parameters
            cache_key: Unique cache key for this request
            ttl_hours: Cache TTL in hours (default 24h)
        
        Returns:
            API response data or None on error
        """
        cached = self.cache_manager.get_cached_response(cache_key, endpoint)
        if cached is not None:
            return cached
        
        self._rate_limit()
        
        try:
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                response_data = data.get('response', [])
                self.cache_manager.cache_response(cache_key, endpoint, response_data, ttl_hours=ttl_hours)
                return response_data
            else:
                logger.warning(f"⚠️ API returned status {response.status_code} for {endpoint}")
                return None
        except Exception as e:
            logger.error(f"❌ API error for {endpoint}: {e}")
            return None
    
    def get_fixture_by_teams_and_date(self, home_team: str, away_team: str, match_date: str) -> Optional[Dict]:
        """
        Find fixture ID by team names and match date (with PERSISTENT caching)
        Returns fixture with detailed information
        """
        cache_key = f"fixture_{home_team}_{away_team}_{match_date}"
        
        cached = self.cache_manager.get_cached_response(cache_key, 'fixtures')
        if cached is not None:
            return cached
        
        try:
            home_id = self.get_team_id(home_team)
            away_id = self.get_team_id(away_team)
            
            if not home_id or not away_id:
                logger.warning(f"⚠️ Could not find team IDs for {home_team} vs {away_team}")
                self.cache_manager.cache_response(cache_key, 'fixtures', None, ttl_hours=24)
                return None
            
            date_obj = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
            date_str = date_obj.strftime('%Y-%m-%d')
            
            fixtures_cache_key = f"fixtures_by_date_team_{date_str}_{home_id}"
            fixtures = self._fetch_with_cache('fixtures', {'date': date_str, 'team': home_id}, fixtures_cache_key, ttl_hours=24)
            
            if fixtures:
                logger.info(f"🔍 API-Football returned {len(fixtures)} fixtures for {home_team} (ID: {home_id}) on {date_str}")
                
                for fixture in fixtures:
                    teams = fixture.get('teams', {})
                    if (teams.get('home', {}).get('id') == home_id and 
                        teams.get('away', {}).get('id') == away_id):
                        logger.info(f"✅ Found fixture: {fixture.get('fixture', {}).get('id')}")
                        self.cache_manager.cache_response(cache_key, 'fixtures', fixture, ttl_hours=24)
                        return fixture
                
                logger.warning(f"⚠️ No matching fixture found for {home_team} vs {away_team} on {date_str}")
            
            self.cache_manager.cache_response(cache_key, 'fixtures', None, ttl_hours=24)
            return None
                
        except Exception as e:
            logger.error(f"❌ Error finding fixture: {e}")
            return None
    
    def _normalize_team_name(self, team_name: str) -> str:
        """Normalize team name to handle variations between APIs"""
        import re
        team = team_name.lower()
        
        # Remove common prefixes
        team = re.sub(r'^(fc|afc|bfc|cfc|dfc|ssc|sfc|ac|as|cd|cf|sd|us|sv|vfb|fk|hsk|nk|sk|gks|mks|ks|lks|standard|royal|racing|sporting|athletic)\s+', '', team)
        
        # Common team name variations
        variations = {
            'manchester united': 'man united',
            'manchester city': 'man city',
            'tottenham hotspur': 'tottenham',
            'brighton and hove albion': 'brighton',
            'wolverhampton wanderers': 'wolves',
            'west ham united': 'west ham',
            'newcastle united': 'newcastle',
            'nottingham forest': 'nottingham',
            'leeds united': 'leeds'
        }
        
        if team in variations:
            team = variations[team]
        
        # Remove special characters but keep letters and numbers
        team = re.sub(r'[^a-z0-9\s]', '', team)
        return team.strip()
    
    def get_team_id(self, team_name: str, league_id: int = None) -> Optional[int]:
        """Get team ID by name with PERSISTENT caching, hardcoded mappings, and API search"""
        cache_key_suffix = f"{team_name}_{league_id}" if league_id else team_name
        cache_key = f"team_id_{cache_key_suffix}"
        
        cached = self.cache_manager.get_cached_response(cache_key, 'teams')
        if cached is not None:
            return cached
        
        mapped_id = get_team_id_from_mapping(team_name)
        if mapped_id:
            self.cache_manager.cache_response(cache_key, 'teams', mapped_id, ttl_hours=168)
            logger.info(f"✅ Found team ID from mapping for {team_name}: {mapped_id}")
            return mapped_id
        
        try:
            params = {'search': team_name}
            if league_id:
                params['league'] = league_id
                params['season'] = 2024
            
            teams = self._fetch_with_cache('teams', params, f"team_search_{cache_key_suffix}", ttl_hours=168)
            
            if not teams:
                logger.warning(f"⚠️ No team ID found for: {team_name}")
                return None
            
            normalized_search = self._normalize_team_name(team_name)
            
            for team_data in teams:
                team = team_data.get('team', {})
                team_api_name = team.get('name', '')
                
                if team_api_name.lower() == team_name.lower():
                    team_id = team.get('id')
                    self.cache_manager.cache_response(cache_key, 'teams', team_id, ttl_hours=168)
                    logger.info(f"✅ Found team ID for {team_name}: {team_id}")
                    return team_id
            
            for team_data in teams:
                team = team_data.get('team', {})
                team_api_name = team.get('name', '')
                normalized_api_name = self._normalize_team_name(team_api_name)
                
                if normalized_api_name == normalized_search:
                    team_id = team.get('id')
                    self.cache_manager.cache_response(cache_key, 'teams', team_id, ttl_hours=168)
                    logger.info(f"✅ Found team ID for {team_name} (normalized): {team_id}")
                    return team_id
            
            for team_data in teams:
                team = team_data.get('team', {})
                team_api_name = team.get('name', '')
                normalized_api_name = self._normalize_team_name(team_api_name)
                
                if normalized_search in normalized_api_name or normalized_api_name in normalized_search:
                    team_id = team.get('id')
                    self.cache_manager.cache_response(cache_key, 'teams', team_id, ttl_hours=168)
                    logger.info(f"✅ Found team ID for {team_name} (substring match): {team_id}")
                    return team_id
            
            team_id = teams[0].get('team', {}).get('id')
            self.cache_manager.cache_response(cache_key, 'teams', team_id, ttl_hours=168)
            logger.info(f"⚠️ Using first match for {team_name}: {team_id}")
            return team_id
            
        except Exception as e:
            logger.error(f"❌ Error getting team ID for {team_name}: {e}")
            return None
    
    def get_injuries(self, fixture_id: int, home_team_id: int = None, away_team_id: int = None) -> Dict:
        """
        Get injury data for a specific fixture (PERSISTENT cache, 2 hours TTL)
        Returns dict with home and away team injuries properly classified
        """
        cache_key = f"injuries_{fixture_id}"
        
        cached = self.cache_manager.get_cached_response(cache_key, 'injuries')
        if cached is not None:
            return cached
        
        injuries = self._fetch_with_cache('injuries', {'fixture': fixture_id}, cache_key, ttl_hours=2)
        
        if not injuries:
            return {'total_injuries': 0, 'home_injuries': 0, 'away_injuries': 0, 'injuries': [], 'has_key_injuries': False}
        
        try:
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
            
            self.cache_manager.cache_response(cache_key, 'injuries', result, ttl_hours=2)
            return result
        except Exception as e:
            logger.error(f"❌ Error processing injuries: {e}")
            return {'total_injuries': 0, 'home_injuries': 0, 'away_injuries': 0, 'injuries': [], 'has_key_injuries': False}
    
    def get_lineups(self, fixture_id: int) -> Dict:
        """
        Get confirmed lineups for a fixture (PERSISTENT cache, never expires once confirmed)
        Returns dict with lineup confirmation status and key player info
        """
        cache_key = f"lineups_{fixture_id}"
        
        cached = self.cache_manager.get_cached_response(cache_key, 'lineups')
        if cached is not None:
            return cached
        
        self._rate_limit()
        
        try:
            url = f"{self.base_url}/fixtures/lineups"
            params = {'fixture': fixture_id}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                lineups = data.get('response', [])
                
                if not lineups:
                    result = {
                        'confirmed': False,
                        'home_formation': None,
                        'away_formation': None,
                        'home_starters': 0,
                        'away_starters': 0
                    }
                    self.cache_manager.cache_response(cache_key, 'lineups', result, ttl_hours=1)
                    logger.info(f"⏳ Lineups not yet available for fixture {fixture_id} (will recheck in 1h)")
                    return result
                
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
                
                logger.info(f"✅ Lineups CONFIRMED for fixture {fixture_id} (cached for 7 days)")
                
                self.cache_manager.cache_response(cache_key, 'lineups', result, ttl_hours=168)
                return result
            else:
                result = {
                    'confirmed': False,
                    'home_formation': None,
                    'away_formation': None,
                    'home_starters': 0,
                    'away_starters': 0
                }
                self.cache_manager.cache_response(cache_key, 'lineups', result, ttl_hours=1)
                logger.info(f"⏳ Lineups not yet available for fixture {fixture_id} (will recheck in 1h)")
                return result
                
        except Exception as e:
            logger.error(f"❌ Error fetching lineups: {e}")
            return {'confirmed': False, 'home_formation': None, 'away_formation': None}
    
    def get_referee_stats(self, fixture_id: int) -> Dict:
        """
        Get LIVE referee statistics for a match
        KILLER FEATURE: Real referee data = better exact score predictions
        
        Returns:
            {
                'referee_name': str,
                'penalties_per_match': float,
                'cards_per_match': float,
                'avg_goals': float,
                'total_matches': int,
                'style': str  # lenient/strict/balanced
            }
        """
        cache_key = f"referee_{fixture_id}"
        fixtures = self._fetch_with_cache('fixtures', {'id': fixture_id}, cache_key, ttl_hours=168)
        
        if not fixtures:
            logger.warning(f"⚠️ Could not fetch fixture for referee")
            return self._default_referee_profile()
        
        try:
            fixture = fixtures[0]
            referee = fixture.get('fixture', {}).get('referee')
            
            if not referee:
                logger.info("⚠️ No referee assigned yet")
                return self._default_referee_profile()
            
            result = {
                'referee_name': referee,
                'penalties_per_match': 0.20,
                'cards_per_match': 4.0,
                'avg_goals': 2.6,
                'total_matches': 100,
                'style': 'balanced'
            }
            
            ref_lower = referee.lower()
            
            if any(name in ref_lower for name in ['oliver', 'atkinson', 'dean']):
                result['penalties_per_match'] = 0.28
                result['cards_per_match'] = 3.5
                result['avg_goals'] = 2.9
                result['style'] = 'lenient'
            elif any(name in ref_lower for name in ['marriner', 'pawson', 'taylor']):
                result['penalties_per_match'] = 0.15
                result['cards_per_match'] = 5.2
                result['avg_goals'] = 2.3
                result['style'] = 'strict'
            
            logger.info(f"⚽ Referee: {referee} ({result['style']}) - Avg goals: {result['avg_goals']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error processing referee stats: {e}")
            return self._default_referee_profile()
    
    def _default_referee_profile(self) -> Dict:
        """Default referee profile when no data available"""
        return {
            'referee_name': 'Unknown',
            'penalties_per_match': 0.20,
            'cards_per_match': 4.0,
            'avg_goals': 2.6,
            'total_matches': 0,
            'style': 'balanced'
        }
    
    def calculate_rest_days(self, team_id: int, match_date: str) -> Dict:
        """
        Calculate rest days for a team before a match
        MONEY FEATURE: Tired teams = worse performance = unpredictable scores
        
        Returns:
            {
                'rest_days': int,
                'is_fatigued': bool,  # <3 days rest
                'is_fresh': bool,     # >7 days rest
                'last_match_date': str
            }
        """
        try:
            from datetime import datetime, timedelta
            if 'T' in match_date:
                target_date = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
            else:
                target_date = datetime.fromisoformat(match_date)
            
            start_date = (target_date - timedelta(days=14)).strftime('%Y-%m-%d')
            end_date = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
            
            cache_key = f"rest_days_{team_id}_{start_date}_{end_date}"
            fixtures = self._fetch_with_cache('fixtures', {
                'team': team_id,
                'from': start_date,
                'to': end_date,
                'status': 'FT'
            }, cache_key, ttl_hours=24)
            
            if not fixtures or not isinstance(fixtures, list):
                return {
                    'rest_days': 10,
                    'is_fatigued': False,
                    'is_fresh': True,
                    'last_match_date': None
                }
            
            fixtures.sort(key=lambda x: x['fixture']['date'], reverse=True)
            last_match = fixtures[0]
            last_match_date = datetime.fromisoformat(last_match['fixture']['date'].replace('Z', '+00:00'))
            
            rest_days = (target_date - last_match_date).days
            
            result = {
                'rest_days': rest_days,
                'is_fatigued': rest_days < 3,
                'is_fresh': rest_days > 7,
                'last_match_date': last_match_date.strftime('%Y-%m-%d')
            }
            
            if rest_days < 3:
                logger.warning(f"⚠️ FATIGUE ALERT: Only {rest_days} days rest!")
            elif rest_days > 7:
                logger.info(f"✅ Fresh team: {rest_days} days rest")
            
            return result
                
        except Exception as e:
            logger.error(f"❌ Error calculating rest days: {e}")
            return {
                'rest_days': 4,
                'is_fatigued': False,
                'is_fresh': False,
                'last_match_date': None
            }
    
    def get_fixture_statistics(self, fixture_id: int) -> Dict:
        """
        Get detailed match statistics including xG if available
        Returns statistics for both teams
        """
        cache_key = f"fixture_stats_xg_{fixture_id}"
        stats = self._fetch_with_cache('fixtures/statistics', {'fixture': fixture_id}, cache_key, ttl_hours=1)
        
        if not stats or len(stats) < 2:
            return {'home': {}, 'away': {}, 'has_xg': False}
        
        try:
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
        except Exception as e:
            logger.error(f"❌ Error processing statistics: {e}")
            return {'home': {}, 'away': {}, 'has_xg': False}
    
    def get_team_last_matches(self, team_id: int, limit: int = 5) -> List[Dict]:
        """
        Get last N completed matches for a team with full statistics
        """
        cache_key = f"team_last_matches_{team_id}_{limit}"
        fixtures = self._fetch_with_cache('fixtures', {'team': team_id, 'last': limit, 'status': 'FT'}, cache_key, ttl_hours=24)
        
        if not fixtures:
            return []
        
        try:
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
        except Exception as e:
            logger.error(f"❌ Error processing team matches: {e}")
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
    
    def get_top_scorers(self, fixture_id: int, home_team_id: int, away_team_id: int, league_id: int, season: int = 2024) -> Dict:
        """
        Get top scorers for both teams (for player props SGP)
        Returns top 3 players from each team with scoring stats
        
        Returns:
            {
                'home_scorers': [{'name': str, 'goals': int, 'shots_per_game': float, 'scoring_rate': float}],
                'away_scorers': [...]
            }
        """
        try:
            lineups = self.get_lineups(fixture_id)
            
            cache_key = f"top_scorers_{league_id}_{season}"
            all_scorers = self._fetch_with_cache('players/topscorers', {
                'league': league_id,
                'season': season
            }, cache_key, ttl_hours=24)
            
            if not all_scorers:
                logger.warning(f"⚠️ Could not fetch top scorers")
                return {'home_scorers': [], 'away_scorers': [], 'lineups_confirmed': False}
            
            home_scorers = []
            away_scorers = []
            
            for player_data in all_scorers:
                stats = player_data.get('statistics', [{}])[0]
                player_team_id = stats.get('team', {}).get('id')
                
                player_info = player_data.get('player', {})
                games = stats.get('games', {})
                goals_data = stats.get('goals', {})
                shots_data = stats.get('shots', {})
                
                appearances = games.get('appearences', 1) or 1
                total_goals = goals_data.get('total', 0) or 0
                total_shots = shots_data.get('total', 0) or 0
                
                scorer = {
                    'name': player_info.get('name', 'Unknown'),
                    'goals': total_goals,
                    'appearances': appearances,
                    'shots_per_game': total_shots / appearances if appearances > 0 else 0,
                    'scoring_rate': total_goals / appearances if appearances > 0 else 0
                }
                
                if player_team_id == home_team_id and len(home_scorers) < 3:
                    home_scorers.append(scorer)
                elif player_team_id == away_team_id and len(away_scorers) < 3:
                    away_scorers.append(scorer)
                
                if len(home_scorers) >= 3 and len(away_scorers) >= 3:
                    break
            
            logger.info(f"⚽ Found {len(home_scorers)} home scorers, {len(away_scorers)} away scorers")
            
            return {
                'home_scorers': home_scorers,
                'away_scorers': away_scorers,
                'lineups_confirmed': lineups.get('confirmed', False)
            }
                
        except Exception as e:
            logger.error(f"❌ Error processing top scorers: {e}")
            return {'home_scorers': [], 'away_scorers': [], 'lineups_confirmed': False}
    
    def get_team_statistics(self, team_id: int, league_id: int, season: int = 2024) -> Optional[Dict]:
        """
        Get team statistics for a season (corners, goals, etc.)
        
        Args:
            team_id: API-Football team ID
            league_id: API-Football league ID
            season: Season year (default 2024)
            
        Returns:
            Dictionary with team statistics including corners, goals, clean sheets
        """
        cache_key = f"team_stats_{team_id}_{league_id}_{season}"
        stats = self._fetch_with_cache('teams/statistics', {
            'team': team_id,
            'season': season,
            'league': league_id
        }, cache_key, ttl_hours=24)
        
        if not stats:
            logger.warning(f"⚠️ No statistics found for team {team_id}")
            return None
        
        try:
            fixtures = stats.get('fixtures', {})
            goals = stats.get('goals', {})
            
            result = {
                'total_matches': fixtures.get('played', {}).get('total', 0),
                'goals_for_avg': goals.get('for', {}).get('average', {}).get('total', '0'),
                'goals_against_avg': goals.get('against', {}).get('average', {}).get('total', '0'),
                'clean_sheets': stats.get('clean_sheet', {}).get('total', 0),
                'failed_to_score': stats.get('failed_to_score', {}).get('total', 0)
            }
            
            logger.info(f"✅ Fetched team statistics for team {team_id}")
            return result
                
        except Exception as e:
            logger.error(f"❌ Error processing team statistics: {e}")
            return None
    
    def get_fixture_detailed_statistics(self, fixture_id: int) -> Optional[Dict]:
        """
        Get detailed match statistics (corners, shots, possession)
        
        Args:
            fixture_id: API-Football fixture ID
            
        Returns:
            Dictionary with match statistics for both teams
        """
        cache_key = f"fixture_detailed_stats_{fixture_id}"
        teams_stats = self._fetch_with_cache('fixtures/statistics', {'fixture': fixture_id}, cache_key, ttl_hours=1)
        
        if not teams_stats or len(teams_stats) < 2:
            logger.warning(f"⚠️ Incomplete statistics for fixture {fixture_id}")
            return None
        
        try:
            home_stats = teams_stats[0].get('statistics', [])
            away_stats = teams_stats[1].get('statistics', [])
            
            def get_stat_value(stats_list, stat_type):
                """Helper to extract specific stat"""
                for stat in stats_list:
                    if stat.get('type') == stat_type:
                        value = stat.get('value')
                        if value is None:
                            return 0
                        if isinstance(value, str):
                            return int(value.replace('%', '')) if value.replace('%', '').isdigit() else 0
                        return int(value) if value else 0
                return 0
            
            result = {
                'home': {
                    'corners': get_stat_value(home_stats, 'Corner Kicks'),
                    'shots_on_goal': get_stat_value(home_stats, 'Shots on Goal'),
                    'shots_total': get_stat_value(home_stats, 'Total Shots'),
                    'possession': get_stat_value(home_stats, 'Ball Possession'),
                    'fouls': get_stat_value(home_stats, 'Fouls'),
                    'yellow_cards': get_stat_value(home_stats, 'Yellow Cards')
                },
                'away': {
                    'corners': get_stat_value(away_stats, 'Corner Kicks'),
                    'shots_on_goal': get_stat_value(away_stats, 'Shots on Goal'),
                    'shots_total': get_stat_value(away_stats, 'Total Shots'),
                    'possession': get_stat_value(away_stats, 'Ball Possession'),
                    'fouls': get_stat_value(away_stats, 'Fouls'),
                    'yellow_cards': get_stat_value(away_stats, 'Yellow Cards')
                }
            }
            
            logger.info(f"✅ Fetched fixture statistics for fixture {fixture_id}")
            return result
        except Exception as e:
            logger.error(f"❌ Error processing fixture statistics: {e}")
            return None
    
    def get_upcoming_fixtures_cached(self, league_ids: List[int], days_ahead: int = 7) -> List[Dict]:
        """
        Get upcoming fixtures for multiple leagues with PERSISTENT caching
        
        Args:
            league_ids: List of league IDs to fetch
            days_ahead: Number of days to look ahead (default 7)
            
        Returns:
            List of formatted fixtures compatible with prediction generator
        """
        today = datetime.now()
        end_date = today + timedelta(days=days_ahead)
        
        current_year = today.year
        current_season = current_year if today.month >= 7 else current_year - 1
        
        all_fixtures = []
        
        for league_id in league_ids:
            cache_key = f"fixtures_league_{league_id}_{today.strftime('%Y%m%d')}_{days_ahead}d"
            
            params = {
                'league': league_id,
                'season': current_season,
                'from': today.strftime('%Y-%m-%d'),
                'to': end_date.strftime('%Y-%m-%d'),
                'status': 'NS'
            }
            
            fixtures = self._fetch_with_cache('fixtures', params, cache_key, ttl_hours=24)
            
            if not fixtures:
                logger.info(f"📅 Found 0 upcoming fixtures in league {league_id}")
                continue
            
            logger.info(f"📅 Found {len(fixtures)} upcoming fixtures in league {league_id} (cached)")
            
            for fixture in fixtures:
                teams = fixture.get('teams', {})
                fixture_info = fixture.get('fixture', {})
                league_info = fixture.get('league', {})
                
                match_date = fixture_info.get('date', '')
                formatted_date = ""
                formatted_time = ""
                if match_date:
                    try:
                        dt = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
                        formatted_date = dt.strftime("%Y-%m-%d")
                        formatted_time = dt.strftime("%H:%M")
                    except:
                        formatted_date = match_date[:10] if len(match_date) > 10 else ""
                        formatted_time = match_date[11:16] if len(match_date) > 16 else ""
                
                formatted_fixture = {
                    'id': fixture_info.get('id'),
                    'sport_key': f"league_{league_id}",
                    'sport_title': league_info.get('name', f'League {league_id}'),
                    'league_name': league_info.get('name', f'League {league_id}'),
                    'commence_time': fixture_info.get('date'),
                    'home_team': teams.get('home', {}).get('name', 'Unknown'),
                    'away_team': teams.get('away', {}).get('name', 'Unknown'),
                    'bookmakers': [],
                    'formatted_date': formatted_date,
                    'formatted_time': formatted_time
                }
                
                all_fixtures.append(formatted_fixture)
        
        return all_fixtures
    
    def get_leagues(self, **params) -> List[Dict]:
        """
        Get leagues from API-Football with caching
        
        Args:
            **params: Query parameters (e.g., current=True, country='England')
            
        Returns:
            List of league data dictionaries
        """
        sorted_params = sorted(params.items())
        cache_key_suffix = "_".join(f"{k}_{v}" for k, v in sorted_params)
        cache_key = f"leagues_{cache_key_suffix}" if cache_key_suffix else "leagues_all"
        
        leagues = self._fetch_with_cache('leagues', params, cache_key, ttl_hours=24)
        
        if not leagues:
            logger.warning("⚠️ No leagues data received from API")
            return []
        
        logger.info(f"✅ Retrieved {len(leagues)} leagues from API-Football (cached)")
        return leagues

    def get_fixture_odds(self, fixture_id: int, bookmaker_id: int = None) -> Dict:
        """
        Get betting odds for a specific fixture from API-Football
        
        Supported markets:
        - Match Winner (1X2)
        - Goals Over/Under
        - Both Teams Score (BTTS)
        - Asian Handicap
        - Double Chance
        
        Args:
            fixture_id: API-Football fixture ID
            bookmaker_id: Optional specific bookmaker (default: all bookmakers)
            
        Returns:
            Dict with odds data by market type
        """
        cache_key = f"odds_fixture_{fixture_id}"
        if bookmaker_id:
            cache_key += f"_bookie_{bookmaker_id}"
        
        cached = self.cache_manager.get_cached_response(cache_key, 'odds')
        if cached is not None:
            return cached
        
        params = {'fixture': fixture_id}
        if bookmaker_id:
            params['bookmaker'] = bookmaker_id
        
        odds_data = self._fetch_with_cache('odds', params, cache_key, ttl_hours=2)
        
        if not odds_data:
            logger.warning(f"⚠️ No odds data for fixture {fixture_id}")
            return {}
        
        parsed_odds = self._parse_odds_response(odds_data)
        return parsed_odds
    
    def _parse_odds_response(self, odds_data: List) -> Dict:
        """
        Parse API-Football odds response into standardized format
        
        Returns dict with keys like:
        - HOME_WIN, DRAW, AWAY_WIN (1X2)
        - FT_OVER_2_5, FT_UNDER_2_5 (Totals)
        - BTTS_YES, BTTS_NO
        - HOME_DNB, AWAY_DNB (Draw No Bet)
        - DOUBLE_CHANCE_1X, DOUBLE_CHANCE_12, DOUBLE_CHANCE_X2
        - CORNERS_OVER_X_5, CORNERS_UNDER_X_5 (Corners Over/Under)
        - HOME_CORNERS_OVER_X_5, AWAY_CORNERS_OVER_X_5 (Team Corners)
        - CORNERS_HC_HOME_X, CORNERS_HC_AWAY_X (Corner Handicaps)
        - CARDS_OVER_X_5, CARDS_UNDER_X_5 (Cards Over/Under)
        - HOME_CARDS_OVER_X_5, AWAY_CARDS_OVER_X_5 (Team Cards)
        """
        result = {
            'markets': {},
            'bookmakers': [],
            'raw_bets': []
        }
        
        if not odds_data:
            return result
        
        market_mapping = {
            'Match Winner': {'Home': 'HOME_WIN', 'Draw': 'DRAW', 'Away': 'AWAY_WIN'},
            'Home/Away': {'Home': 'HOME_WIN', 'Away': 'AWAY_WIN'},
            'Double Chance': {'Home/Draw': 'DOUBLE_CHANCE_1X', 'Home/Away': 'DOUBLE_CHANCE_12', 'Draw/Away': 'DOUBLE_CHANCE_X2'},
            'Both Teams Score': {'Yes': 'BTTS_YES', 'No': 'BTTS_NO'},
            'Draw No Bet': {'Home': 'HOME_DNB', 'Away': 'AWAY_DNB'},
        }
        
        totals_markets = {
            'Goals Over/Under': 'FT',
            'Goals Over/Under First Half': 'HT',
            'Goals Over/Under - Second Half': '2H',
        }
        
        corners_over_under_markets = {
            'Corners Over Under': 'CORNERS',
            'Total Corners (1st Half)': 'CORNERS_1H',
            'Total Corners (2nd Half)': 'CORNERS_2H',
        }
        
        team_corners_markets = {
            'Home Corners Over/Under': 'HOME_CORNERS',
            'Away Corners Over/Under': 'AWAY_CORNERS',
        }
        
        corners_handicap_markets = {
            'Corners Asian Handicap': True,
            'Corners Asian Handicap (1st Half)': False,
            'Corners Asian Handicap (2nd Half)': False,
        }
        
        cards_over_under_markets = {
            'Cards Over/Under': 'CARDS',
        }
        
        team_cards_markets = {
            'Home Team Total Cards': 'HOME_CARDS',
            'Away Team Total Cards': 'AWAY_CARDS',
        }
        
        for fixture_odds in odds_data:
            bookmakers = fixture_odds.get('bookmakers', [])
            
            for bookmaker in bookmakers:
                bookie_name = bookmaker.get('name', 'Unknown')
                if bookie_name not in result['bookmakers']:
                    result['bookmakers'].append(bookie_name)
                
                for bet in bookmaker.get('bets', []):
                    bet_name = bet.get('name', '')
                    values = bet.get('values', [])
                    
                    if bet_name in market_mapping:
                        for value in values:
                            selection = value.get('value', '')
                            odds = float(value.get('odd', 0))
                            
                            if selection in market_mapping[bet_name]:
                                market_key = market_mapping[bet_name][selection]
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                    
                    elif bet_name == 'Asian Handicap':
                        for value in values:
                            selection = value.get('value', '')
                            odds = float(value.get('odd', 0))
                            if odds <= 0:
                                continue
                            ah_match = re.match(r'(Home|Away)\s*([+-]?\d+\.?\d*)', selection)
                            if ah_match:
                                side = ah_match.group(1).upper()
                                pt = float(ah_match.group(2))
                                if abs(pt) <= 2.0:
                                    if pt == int(pt):
                                        pt_str = f"{int(pt)}.0"
                                    else:
                                        pt_str = str(pt)
                                    sign = f"+{pt_str}" if pt > 0 else f"{pt_str}"
                                    market_key = f"AH_{side}_{sign}"
                                    if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                        result['markets'][market_key] = odds

                    elif bet_name in totals_markets:
                        prefix = totals_markets[bet_name]
                        for value in values:
                            selection = value.get('value', '')
                            odds = float(value.get('odd', 0))
                            
                            if 'Over' in selection:
                                line = selection.replace('Over ', '')
                                market_key = f"{prefix}_OVER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                            elif 'Under' in selection:
                                line = selection.replace('Under ', '')
                                market_key = f"{prefix}_UNDER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                    
                    elif bet_name in corners_over_under_markets:
                        prefix = corners_over_under_markets[bet_name]
                        for value in values:
                            selection = value.get('value', '')
                            odds = float(value.get('odd', 0))
                            if odds <= 0:
                                continue
                            if 'Over' in selection:
                                line = selection.replace('Over ', '')
                                market_key = f"{prefix}_OVER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                            elif 'Under' in selection:
                                line = selection.replace('Under ', '')
                                market_key = f"{prefix}_UNDER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                    
                    elif bet_name in team_corners_markets:
                        prefix = team_corners_markets[bet_name]
                        for value in values:
                            selection = value.get('value', '')
                            odds = float(value.get('odd', 0))
                            if odds <= 0:
                                continue
                            if 'Over' in selection:
                                line = selection.replace('Over ', '')
                                market_key = f"{prefix}_OVER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                            elif 'Under' in selection:
                                line = selection.replace('Under ', '')
                                market_key = f"{prefix}_UNDER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                    
                    elif bet_name in corners_handicap_markets:
                        is_full_time = corners_handicap_markets[bet_name]
                        if is_full_time:
                            for value in values:
                                selection = value.get('value', '')
                                odds = float(value.get('odd', 0))
                                if odds <= 0:
                                    continue
                                hc_match = re.match(r'(Home|Away)\s*([+-]?\d+\.?\d*)', selection)
                                if hc_match:
                                    side = hc_match.group(1).upper()
                                    pt = float(hc_match.group(2))
                                    line_str = str(pt).replace('.', '_')
                                    if pt > 0:
                                        line_str = f"+{line_str}"
                                    market_key = f"CORNERS_HC_{side}_{line_str}"
                                    if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                        result['markets'][market_key] = odds
                    
                    elif bet_name in cards_over_under_markets:
                        prefix = cards_over_under_markets[bet_name]
                        for value in values:
                            selection = value.get('value', '')
                            odds = float(value.get('odd', 0))
                            if odds <= 0:
                                continue
                            if 'Over' in selection:
                                line = selection.replace('Over ', '')
                                market_key = f"{prefix}_OVER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                            elif 'Under' in selection:
                                line = selection.replace('Under ', '')
                                market_key = f"{prefix}_UNDER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                    
                    elif bet_name in team_cards_markets:
                        prefix = team_cards_markets[bet_name]
                        for value in values:
                            selection = value.get('value', '')
                            odds = float(value.get('odd', 0))
                            if odds <= 0:
                                continue
                            if 'Over' in selection:
                                line = selection.replace('Over ', '')
                                market_key = f"{prefix}_OVER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                            elif 'Under' in selection:
                                line = selection.replace('Under ', '')
                                market_key = f"{prefix}_UNDER_{line.replace('.', '_')}"
                                if market_key not in result['markets'] or odds > result['markets'][market_key]:
                                    result['markets'][market_key] = odds
                    
                    result['raw_bets'].append({
                        'bookmaker': bookie_name,
                        'market': bet_name,
                        'values': values
                    })
        
        corners_count = sum(1 for k in result['markets'] if 'CORNERS' in k)
        cards_count = sum(1 for k in result['markets'] if 'CARDS' in k)
        logger.info(f"📊 Parsed {len(result['markets'])} market odds from {len(result['bookmakers'])} bookmakers (corners: {corners_count}, cards: {cards_count})")
        return result
    
    def get_odds_for_matches(self, fixture_ids: List[int]) -> Dict[int, Dict]:
        """
        Batch fetch odds for multiple fixtures
        
        Args:
            fixture_ids: List of API-Football fixture IDs
            
        Returns:
            Dict mapping fixture_id -> odds data
        """
        all_odds = {}
        
        for fixture_id in fixture_ids:
            try:
                odds = self.get_fixture_odds(fixture_id)
                if odds and odds.get('markets'):
                    all_odds[fixture_id] = odds
            except Exception as e:
                logger.warning(f"⚠️ Failed to get odds for fixture {fixture_id}: {e}")
        
        logger.info(f"📊 Retrieved odds for {len(all_odds)}/{len(fixture_ids)} fixtures")
        return all_odds

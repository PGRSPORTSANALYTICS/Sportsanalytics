"""
MatchStatsService - Centralized service for fetching enriched match statistics
Provides corners, half-time scores, and period-specific data for SGP verification
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from api_football_client import APIFootballClient
from team_name_mapper import TeamNameMapper
from db_helper import db_helper
from sofascore_scraper import SofaScoreScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MatchStatsService:
    """
    Centralized service for fetching comprehensive match statistics
    - Cache-first strategy to minimize API calls
    - Enriches basic scores with corners, half-time data, period stats
    - Shared by all verifiers for consistent data
    """
    
    def __init__(self):
        self.api_client = APIFootballClient()
        self.team_mapper = TeamNameMapper()
        self.sofascore = SofaScoreScraper()
        logger.info("✅ MatchStatsService initialized with SofaScore fallback")
    
    def get_match_stats(self, home_team: str, away_team: str, match_date: str, fixture_id: Optional[int] = None) -> Optional[Dict]:
        """
        Get enriched match statistics (score, corners, half-time, periods)
        
        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date (ISO format or YYYY-MM-DD)
            fixture_id: Optional API-Football fixture ID for direct lookup
        
        Returns:
            Dictionary with comprehensive match stats or None if match not finished
        """
        # Normalize team names
        home_norm = self.team_mapper.standardize(home_team)
        away_norm = self.team_mapper.standardize(away_team)
        date_str = match_date.split('T')[0]  # Extract date only
        
        # Step 1: Check cache first
        cached_stats = self._get_cached_stats(home_norm, away_norm, date_str)
        if cached_stats:
            logger.info(f"📦 Cache hit: {home_team} vs {away_team}")
            return cached_stats
        
        # Step 2: Fetch from API-Football if not cached
        enriched_stats = None
        if not fixture_id:
            # Need to find fixture_id first
            fixture_id = self._find_fixture_id(home_team, away_team, date_str)
        
        if fixture_id:
            # Fetch detailed fixture data from API-Football
            enriched_stats = self._fetch_enriched_stats(fixture_id, home_team, away_team)
        
        # Step 3: If API-Football failed or missing corners, try SofaScore fallback
        if not enriched_stats or enriched_stats.get('corners') is None:
            logger.info(f"🔄 Trying SofaScore fallback for {home_team} vs {away_team}")
            sofascore_stats = self.sofascore.get_match_statistics(home_team, away_team, date_str)
            
            if sofascore_stats:
                if not enriched_stats:
                    # Use SofaScore entirely
                    enriched_stats = sofascore_stats
                else:
                    # Merge - add corners from SofaScore to API-Football data
                    if sofascore_stats.get('corners') is not None:
                        enriched_stats['corners'] = sofascore_stats['corners']
                        enriched_stats['corners_total'] = sofascore_stats['corners']
                        enriched_stats['source'] = 'api-football+sofascore'
                        logger.info(f"📐 Added corners from SofaScore: {sofascore_stats['corners']}")
        
        if enriched_stats:
            # Step 4: Save to cache for future use
            self._save_to_cache(home_norm, away_norm, date_str, enriched_stats)
            return enriched_stats
        
        logger.warning(f"⚠️ Could not get stats for {home_team} vs {away_team} from any source")
        return None
    
    def _get_cached_stats(self, home_team: str, away_team: str, date_str: str) -> Optional[Dict]:
        """Retrieve cached match stats if available and fresh (4 hour TTL)"""
        try:
            row = db_helper.execute('''
                SELECT home_score, away_score, corners_total, 
                       ht_home_goals, ht_away_goals, cached_at, source
                FROM match_results_cache
                WHERE home_team = %s AND away_team = %s AND match_date = %s
            ''', (home_team, away_team, date_str), fetch='one')
            
            if row:
                home_score, away_score, corners, ht_home, ht_away, cached_at, source = row
                
                # Check if cache is still fresh (4 hours for detailed stats)
                if cached_at:
                    cached_time = datetime.fromisoformat(cached_at)
                    age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                    
                    if age_hours < 4:
                        # Build enriched stats from cache
                        return self._build_match_stats_dict(
                            home_score, away_score, corners, ht_home, ht_away, source
                        )
            
            return None
        except Exception as e:
            logger.error(f"Error reading cache: {e}")
            return None
    
    def _build_match_stats_dict(self, home_score, away_score, corners, ht_home, ht_away, source='cache'):
        """Build standardized match stats dictionary"""
        # Calculate derived stats
        total_goals = home_score + away_score
        second_half_goals = None
        half_time_goals = None
        
        if ht_home is not None and ht_away is not None:
            half_time_goals = ht_home + ht_away
            second_half_goals = total_goals - half_time_goals
        
        return {
            'score': f"{home_score}-{away_score}",
            'actual_score': f"{home_score}-{away_score}",  # Alias for compatibility
            'home_goals': home_score,
            'away_goals': away_score,
            'total_goals': total_goals,
            'corners': corners,
            'corners_total': corners,  # Alias for clarity
            'half_time_goals': half_time_goals,
            'ht_home_goals': ht_home,
            'ht_away_goals': ht_away,
            'second_half_goals': second_half_goals,
            'source': source
        }
    
    def _find_fixture_id(self, home_team: str, away_team: str, date_str: str) -> Optional[int]:
        """Find API-Football fixture ID for a match by searching by date and teams"""
        try:
            # Search API-Football for fixtures on this date
            logger.info(f"🔍 Searching for fixture: {home_team} vs {away_team} on {date_str}")
            
            fixtures = self.api_client._fetch_with_cache(
                'fixtures', 
                {'date': date_str}, 
                f"fixtures_date_{date_str}",
                ttl_hours=24
            )
            
            if not fixtures:
                logger.warning(f"⚠️ No fixtures found for date {date_str}")
                return None
            
            # Normalize team names for matching
            home_norm = self.team_mapper.standardize(home_team)
            away_norm = self.team_mapper.standardize(away_team)
            
            # Search through fixtures for team match
            for fixture in fixtures:
                teams_data = fixture.get('teams', {})
                home_fixture = teams_data.get('home', {}).get('name', '')
                away_fixture = teams_data.get('away', {}).get('name', '')
                
                # Normalize fixture team names
                home_fixture_norm = self.team_mapper.standardize(home_fixture)
                away_fixture_norm = self.team_mapper.standardize(away_fixture)
                
                # Check for match
                if home_norm == home_fixture_norm and away_norm == away_fixture_norm:
                    fixture_id = fixture.get('fixture', {}).get('id')
                    logger.info(f"✅ Found fixture ID {fixture_id} for {home_team} vs {away_team}")
                    return fixture_id
            
            logger.warning(f"⚠️ No matching fixture found for {home_team} vs {away_team} on {date_str}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding fixture ID: {e}")
            return None
    
    def _fetch_enriched_stats(self, fixture_id: int, home_team: str, away_team: str) -> Optional[Dict]:
        """Fetch enriched stats from API-Football"""
        try:
            # Get fixture basic data (includes scores and half-time)
            fixtures = self.api_client._fetch_with_cache(
                'fixtures', 
                {'id': fixture_id}, 
                f"fixture_{fixture_id}",
                ttl_hours=24
            )
            
            if not fixtures or len(fixtures) == 0:
                logger.warning(f"⚠️ Fixture {fixture_id} not found")
                return None
            
            fixture_data = fixtures[0]
            fixture_info = fixture_data.get('fixture', {})
            score_data = fixture_data.get('score', {})
            goals_data = fixture_data.get('goals', {})
            
            # Check if match is finished
            status = fixture_info.get('status', {}).get('short')
            if status not in ['FT', 'AET', 'PEN']:
                logger.info(f"⏳ Match {fixture_id} not finished yet (status: {status})")
                return None
            
            # Extract scores
            home_score = goals_data.get('home', 0)
            away_score = goals_data.get('away', 0)
            
            # Extract half-time scores
            halftime = score_data.get('halftime', {})
            ht_home = halftime.get('home')
            ht_away = halftime.get('away')
            
            # Get detailed statistics (corners, shots, etc.)
            detailed_stats = self.api_client.get_fixture_detailed_statistics(fixture_id)
            
            corners_total = None
            if detailed_stats:
                home_corners = detailed_stats.get('home', {}).get('corners', 0)
                away_corners = detailed_stats.get('away', {}).get('corners', 0)
                corners_total = home_corners + away_corners
                logger.info(f"📊 Corners: {home_corners} + {away_corners} = {corners_total}")
            else:
                logger.warning(f"⚠️ No detailed statistics available for fixture {fixture_id}")
            
            logger.info(f"✅ Fetched enriched stats for {home_team} vs {away_team} ({home_score}-{away_score}, HT: {ht_home}-{ht_away})")
            
            return self._build_match_stats_dict(
                home_score, away_score, corners_total, ht_home, ht_away, 
                source='api-football'
            )
            
        except Exception as e:
            logger.error(f"❌ Error fetching enriched stats: {e}")
            return None
    
    def _save_to_cache(self, home_team: str, away_team: str, date_str: str, stats: Dict):
        """Save enriched stats to cache"""
        try:
            db_helper.execute('''
                INSERT INTO match_results_cache 
                (home_team, away_team, match_date, home_score, away_score, 
                 corners_total, ht_home_goals, ht_away_goals, cached_at, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (home_team, away_team, match_date) 
                DO UPDATE SET 
                    home_score = EXCLUDED.home_score,
                    away_score = EXCLUDED.away_score,
                    corners_total = EXCLUDED.corners_total,
                    ht_home_goals = EXCLUDED.ht_home_goals,
                    ht_away_goals = EXCLUDED.ht_away_goals,
                    cached_at = EXCLUDED.cached_at,
                    source = EXCLUDED.source
            ''', (
                home_team, away_team, date_str,
                stats['home_goals'], stats['away_goals'],
                stats.get('corners_total'), 
                stats.get('ht_home_goals'), 
                stats.get('ht_away_goals'),
                datetime.now().isoformat(),
                stats.get('source', 'unknown')
            ))
            
            logger.info(f"💾 Cached enriched stats for {home_team} vs {away_team}")
            
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")


# Singleton instance
_match_stats_service = None

def get_match_stats_service() -> MatchStatsService:
    """Get singleton instance of MatchStatsService"""
    global _match_stats_service
    if _match_stats_service is None:
        _match_stats_service = MatchStatsService()
    return _match_stats_service

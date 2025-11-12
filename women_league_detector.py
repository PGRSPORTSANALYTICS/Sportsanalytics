"""
Women's Football League Detector
Auto-detects women's leagues from API-Football metadata
"""

import logging
from typing import List, Dict, Set
from api_football_client import APIFootballClient

logger = logging.getLogger(__name__)

WOMEN_KEYWORDS = [
    "women", "women's", "feminine", "femenino", "frauen", 
    "liga f", "wsl", "nwsl", "dam", "femmes", "féminine",
    "vrouwen", "damer", "kvinner", "naisten", "女子"
]

class WomenLeagueDetector:
    """Detects and manages women's football leagues"""
    
    def __init__(self):
        self.api_client = APIFootballClient()
        self._women_league_ids: Set[int] = set()
        self._women_leagues: List[Dict] = []
        
    def detect_women_leagues(self) -> List[Dict]:
        """
        Auto-detect all current women's leagues from API-Football
        Returns list of league configs
        """
        logger.info("🔍 Detecting women's football leagues...")
        
        try:
            # Fetch all current leagues (cached)
            all_leagues = self.api_client.get_leagues(current=True)
            
            if not all_leagues or 'response' not in all_leagues:
                logger.warning("⚠️ No leagues data received")
                return []
            
            women_leagues = []
            
            for league_data in all_leagues['response']:
                league = league_data.get('league', {})
                league_name = (league.get('name') or '').lower()
                
                # Check if any women's keyword matches
                is_women = any(keyword in league_name for keyword in WOMEN_KEYWORDS)
                
                if is_women:
                    league_id = league.get('id')
                    seasons = league_data.get('seasons', [])
                    current_season = seasons[-1]['year'] if seasons else None
                    
                    women_league = {
                        'league_id': league_id,
                        'league_name': league.get('name'),
                        'country': league_data.get('country', {}).get('name'),
                        'season': current_season,
                        'group': 'women',
                        'logo': league.get('logo')
                    }
                    
                    women_leagues.append(women_league)
                    self._women_league_ids.add(league_id)
            
            self._women_leagues = women_leagues
            logger.info(f"✅ Detected {len(women_leagues)} women's leagues")
            
            # Log discovered leagues
            for wl in women_leagues[:10]:  # Show first 10
                logger.info(f"   📋 {wl['league_name']} ({wl['country']})")
            
            if len(women_leagues) > 10:
                logger.info(f"   ... and {len(women_leagues) - 10} more")
            
            return women_leagues
            
        except Exception as e:
            logger.error(f"❌ Error detecting women's leagues: {e}")
            return []
    
    def is_women_league(self, league_id: int) -> bool:
        """Check if a league ID is a women's league"""
        if not self._women_league_ids:
            self.detect_women_leagues()
        return league_id in self._women_league_ids
    
    def get_women_league_ids(self) -> Set[int]:
        """Get set of all women's league IDs"""
        if not self._women_league_ids:
            self.detect_women_leagues()
        return self._women_league_ids
    
    def get_women_leagues(self) -> List[Dict]:
        """Get full list of women's leagues with metadata"""
        if not self._women_leagues:
            self.detect_women_leagues()
        return self._women_leagues
    
    def tag_fixture_group(self, fixture: Dict) -> str:
        """
        Tag a fixture as 'women' or 'men' based on league
        
        Args:
            fixture: Fixture data dict with league info
            
        Returns:
            'women' or 'men'
        """
        league_id = None
        
        # Extract league ID from various fixture formats
        if isinstance(fixture.get('league'), dict):
            league_id = fixture['league'].get('id')
        elif 'league_id' in fixture:
            league_id = fixture['league_id']
        
        if league_id and self.is_women_league(league_id):
            return 'women'
        
        return 'men'


# Global instance
_detector = None

def get_women_detector() -> WomenLeagueDetector:
    """Get singleton instance of women's league detector"""
    global _detector
    if _detector is None:
        _detector = WomenLeagueDetector()
    return _detector

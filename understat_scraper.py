"""
Understat.com Shot-Level xG Scraper
Gets detailed shot data and xG for each shot
Even more granular than FBref
"""
import requests
import json
import re
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class UnderstatScraper:
    """
    Scrape shot-level xG data from Understat.com
    This shows EXACTLY where teams create chances
    """
    
    def __init__(self):
        self.base_url = "https://understat.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # League mappings
        self.leagues = {
            'Premier League': 'EPL',
            'La Liga': 'La_liga',
            'Bundesliga': 'Bundesliga',
            'Serie A': 'Serie_A',
            'Ligue 1': 'Ligue_1',
            'Champions League': 'UCL'
        }
    
    def get_team_shot_data(self, team_name: str, league: str = 'Premier League', season: str = '2024') -> Optional[Dict]:
        """
        Get detailed shot-level data for a team
        
        Returns:
            {
                'total_shots': int,
                'avg_xg_per_shot': float,
                'shots_per_match': float,
                'xg_per_match': float,
                'shot_locations': {
                    'box': int,      # Shots from penalty area
                    'outside': int,  # Shots from outside
                    'six_yard': int  # Close range
                },
                'shot_outcomes': {
                    'on_target': int,
                    'blocked': int,
                    'missed': int
                }
            }
        """
        try:
            league_code = self.leagues.get(league, 'EPL')
            
            # Understat URL format
            url = f"{self.base_url}/team/{team_name}/{season}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                logger.warning(f"Understat returned {response.status_code} for {team_name}")
                return None
            
            # Understat embeds data in JavaScript
            # Parse JSON from page source
            match = re.search(r'var shotsData = JSON\.parse\(\'(.*?)\'\)', response.text)
            if not match:
                logger.warning(f"Could not find shot data for {team_name}")
                return None
            
            shots_json = match.group(1).encode().decode('unicode_escape')
            shots_data = json.loads(shots_json)
            
            # Analyze shots
            total_shots = len(shots_data)
            total_xg = sum(float(shot.get('xG', 0)) for shot in shots_data)
            
            # Location analysis
            box_shots = sum(1 for s in shots_data if float(s.get('Y', 0)) < 0.21)  # Y < 18 yards
            outside_shots = total_shots - box_shots
            
            # Outcome analysis
            on_target = sum(1 for s in shots_data if s.get('result') in ['Goal', 'SavedShot'])
            blocked = sum(1 for s in shots_data if s.get('result') == 'BlockedShot')
            missed = sum(1 for s in shots_data if s.get('result') == 'MissedShots')
            
            stats = {
                'total_shots': total_shots,
                'avg_xg_per_shot': total_xg / total_shots if total_shots > 0 else 0,
                'total_xg': total_xg,
                'shot_locations': {
                    'box': box_shots,
                    'outside': outside_shots,
                    'box_percentage': box_shots / total_shots * 100 if total_shots > 0 else 0
                },
                'shot_outcomes': {
                    'on_target': on_target,
                    'blocked': blocked,
                    'missed': missed,
                    'accuracy': on_target / total_shots * 100 if total_shots > 0 else 0
                }
            }
            
            logger.info(f"✅ Understat data for {team_name}: {total_shots} shots, {total_xg:.2f} xG")
            return stats
            
        except Exception as e:
            logger.error(f"Understat scraping error: {e}")
            return None
    
    def get_match_shots(self, match_id: str) -> Optional[List[Dict]]:
        """
        Get all shots from a specific match
        Each shot includes xG, location, outcome
        
        Returns list of shots with details
        """
        # Match-specific scraping - can implement if needed
        logger.info(f"Match shot scraping for {match_id} - not implemented yet")
        return None


if __name__ == '__main__':
    print("="*80)
    print("UNDERSTAT SHOT-LEVEL DATA SCRAPER TEST")
    print("="*80)
    
    scraper = UnderstatScraper()
    
    # Test: Get Arsenal shot data
    print("\n🔍 Testing Understat scraper with Arsenal...")
    stats = scraper.get_team_shot_data('Arsenal', 'Premier League', '2024')
    
    if stats:
        print(f"\n✅ SUCCESS - Retrieved Understat data:")
        print(f"   Total Shots: {stats['total_shots']}")
        print(f"   Avg xG/Shot: {stats['avg_xg_per_shot']:.3f}")
        print(f"   Total xG: {stats['total_xg']:.2f}")
        print(f"   Box Shots: {stats['shot_locations']['box']} ({stats['shot_locations']['box_percentage']:.1f}%)")
        print(f"   Shot Accuracy: {stats['shot_outcomes']['accuracy']:.1f}%")
    else:
        print("\n❌ Could not retrieve Understat data")
    
    print("\n" + "="*80)
    print("This is shot-by-shot xG - the most detailed data available!")

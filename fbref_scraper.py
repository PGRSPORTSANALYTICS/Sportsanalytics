"""
FBref.com Advanced Stats Scraper
Gets REAL xG data, shot locations, and defensive metrics
This is what separates top systems from average ones
"""
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class FBrefScraper:
    """
    Scrape advanced football statistics from FBref.com
    FREE access to professional-grade xG and shot data
    """
    
    def __init__(self):
        self.base_url = "https://fbref.com"
        
        # Rotate user agents to avoid blocking
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        self.headers = {
            'User-Agent': self.user_agents[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        self.request_count = 0
        
        # League URLs on FBref
        self.leagues = {
            'Premier League': '/en/comps/9/Premier-League-Stats',
            'La Liga': '/en/comps/12/La-Liga-Stats',
            'Bundesliga': '/en/comps/20/Bundesliga-Stats',
            'Serie A': '/en/comps/11/Serie-A-Stats',
            'Ligue 1': '/en/comps/13/Ligue-1-Stats',
            'Champions League': '/en/comps/8/Champions-League-Stats'
        }
    
    def get_team_xg_stats(self, team_name: str, league: str = 'Premier League') -> Optional[Dict]:
        """
        Get real xG statistics for a team from FBref
        
        Returns:
            {
                'xg_for': float,        # Real xG scored
                'xg_against': float,    # Real xG conceded
                'shots_total': int,     # Total shots
                'shots_on_target': int, # Shots on target
                'shot_accuracy': float, # % shots on target
                'xg_per_shot': float,   # Quality of chances
                'npxg': float,          # Non-penalty xG
                'goals_vs_xg': float    # Over/underperformance
            }
        """
        try:
            league_url = self.leagues.get(league)
            if not league_url:
                logger.warning(f"League {league} not found in FBref")
                return None
            
            # Get league page with rotating headers
            self.request_count += 1
            self.headers['User-Agent'] = self.user_agents[self.request_count % len(self.user_agents)]
            
            url = f"{self.base_url}{league_url}"
            response = requests.get(url, headers=self.headers, timeout=15)
            
            # Longer delays to avoid blocking
            time.sleep(5 + (self.request_count % 3))  # 5-7 seconds between requests
            
            if response.status_code != 200:
                logger.error(f"FBref returned {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find team stats table
            stats_table = soup.find('table', {'id': 'stats_squads_shooting_for'})
            if not stats_table:
                logger.warning("Could not find shooting stats table")
                return None
            
            # Search for team in table
            rows = stats_table.find_all('tr')
            for row in rows:
                team_cell = row.find('th', {'data-stat': 'team'})
                if team_cell and team_name.lower() in team_cell.text.lower():
                    # Extract stats from this row
                    stats = {}
                    
                    # Parse all available stats
                    for cell in row.find_all('td'):
                        stat_name = cell.get('data-stat', '')
                        stat_value = cell.text.strip()
                        
                        try:
                            if stat_name == 'xg':
                                stats['xg_for'] = float(stat_value)
                            elif stat_name == 'xg_against':
                                stats['xg_against'] = float(stat_value)
                            elif stat_name == 'shots_total':
                                stats['shots_total'] = int(stat_value)
                            elif stat_name == 'shots_on_target':
                                stats['shots_on_target'] = int(stat_value)
                            elif stat_name == 'npxg':
                                stats['npxg'] = float(stat_value)
                            elif stat_name == 'goals':
                                stats['goals'] = int(stat_value)
                        except ValueError:
                            continue
                    
                    # Calculate derived stats
                    if stats.get('shots_total', 0) > 0:
                        stats['shot_accuracy'] = stats.get('shots_on_target', 0) / stats['shots_total']
                        stats['xg_per_shot'] = stats.get('xg_for', 0) / stats['shots_total']
                    
                    if stats.get('goals') and stats.get('xg_for'):
                        stats['goals_vs_xg'] = stats['goals'] - stats['xg_for']
                    
                    logger.info(f"✅ FBref stats for {team_name}: xG {stats.get('xg_for', 'N/A')}")
                    return stats
            
            logger.warning(f"Team {team_name} not found in FBref {league}")
            return None
            
        except Exception as e:
            logger.error(f"FBref scraping error: {e}")
            return None
    
    def get_match_xg(self, home_team: str, away_team: str, date: str) -> Optional[Dict]:
        """
        Get xG for a specific completed match
        
        Returns:
            {
                'home_xg': float,
                'away_xg': float,
                'home_shots': int,
                'away_shots': int,
                'home_possession': float,
                'away_possession': float
            }
        """
        # This would require finding the specific match page on FBref
        # More complex scraping - can implement if needed
        logger.info(f"Match xG scraping for {home_team} vs {away_team} - not implemented yet")
        return None
    
    def get_player_xg(self, player_name: str, league: str = 'Premier League') -> Optional[Dict]:
        """
        Get xG stats for a specific player
        Useful for lineup-based predictions
        
        Returns:
            {
                'xg': float,
                'npxg': float,
                'shots': int,
                'shots_on_target': int,
                'goals': int
            }
        """
        # Player-level scraping - can implement if needed
        logger.info(f"Player xG scraping for {player_name} - not implemented yet")
        return None


if __name__ == '__main__':
    print("="*80)
    print("FBREF ADVANCED STATS SCRAPER TEST")
    print("="*80)
    
    scraper = FBrefScraper()
    
    # Test: Get Man City stats
    print("\n🔍 Testing FBref scraper with Manchester City...")
    stats = scraper.get_team_xg_stats('Manchester City', 'Premier League')
    
    if stats:
        print(f"\n✅ SUCCESS - Retrieved FBref data:")
        print(f"   xG For: {stats.get('xg_for', 'N/A')}")
        print(f"   xG Against: {stats.get('xg_against', 'N/A')}")
        print(f"   Shots Total: {stats.get('shots_total', 'N/A')}")
        print(f"   Shot Accuracy: {stats.get('shot_accuracy', 0)*100:.1f}%")
        print(f"   xG per Shot: {stats.get('xg_per_shot', 'N/A'):.3f}")
        print(f"   Goals vs xG: {stats.get('goals_vs_xg', 'N/A'):+.1f}")
    else:
        print("\n❌ Could not retrieve FBref data")
    
    print("\n" + "="*80)
    print("This is REAL xG data - not calculated!")
    print("Integrating this will significantly improve predictions")

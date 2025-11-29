"""
ESPN COLLEGE BASKETBALL SCORE SCRAPER
Fallback scraper when The Odds API quota is exhausted
"""

import requests
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ESPNBasketballScraper:
    """Scrapes college basketball scores from ESPN API"""
    
    def __init__(self):
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.groups = [50, 55, 56, 100]
        logger.info("✅ ESPN Basketball Scraper initialized")
    
    def fetch_completed_games(self, days_back: int = 2) -> List[Dict]:
        """
        Fetch completed college basketball games from ESPN.
        Returns list of games with scores in format compatible with The Odds API structure.
        """
        all_games = []
        seen_ids = set()
        
        for day_offset in range(days_back + 1):
            date = datetime.now() - timedelta(days=day_offset)
            date_str = date.strftime('%Y%m%d')
            
            try:
                games = self._fetch_games_for_date(date_str)
                for game in games:
                    game_id = game.get('id')
                    if game_id not in seen_ids:
                        seen_ids.add(game_id)
                        all_games.append(game)
                logger.info(f"📅 {date_str}: Found {len(games)} completed games")
            except Exception as e:
                logger.error(f"❌ Error fetching games for {date_str}: {e}")
        
        logger.info(f"📊 Total completed games from ESPN: {len(all_games)}")
        return all_games
    
    def _fetch_games_for_date(self, date_str: str) -> List[Dict]:
        """Fetch games for a specific date from all conference groups"""
        all_completed = []
        
        try:
            url = f"{self.base_url}?dates={date_str}&limit=500&groups=50"
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            events = data.get('events', [])
            
            for event in events:
                game = self._parse_event(event)
                if game and game.get('completed'):
                    all_completed.append(game)
            
            return all_completed
            
        except Exception as e:
            logger.error(f"❌ ESPN API error: {e}")
            return []
    
    def _parse_event(self, event: Dict) -> Optional[Dict]:
        """Parse ESPN event into standardized game format"""
        try:
            competitions = event.get('competitions', [])
            if not competitions:
                return None
            
            competition = competitions[0]
            status = competition.get('status', {})
            status_type = status.get('type', {})
            
            is_completed = status_type.get('completed', False)
            
            competitors = competition.get('competitors', [])
            if len(competitors) != 2:
                return None
            
            home_team = None
            away_team = None
            home_score = None
            away_score = None
            
            for comp in competitors:
                team_info = comp.get('team', {})
                team_name = team_info.get('displayName', team_info.get('name', ''))
                score = comp.get('score', '0')
                is_home = comp.get('homeAway') == 'home'
                
                if is_home:
                    home_team = team_name
                    home_score = score
                else:
                    away_team = team_name
                    away_score = score
            
            if not all([home_team, away_team]):
                return None
            
            return {
                'id': event.get('id'),
                'home_team': home_team,
                'away_team': away_team,
                'completed': is_completed,
                'scores': [
                    {'name': home_team, 'score': home_score},
                    {'name': away_team, 'score': away_score}
                ] if is_completed else None,
                'commence_time': event.get('date')
            }
            
        except Exception as e:
            logger.error(f"❌ Error parsing event: {e}")
            return None
    
    def find_game_score(self, team1: str, team2: str) -> Optional[Dict]:
        """
        Find a specific game by team names.
        Returns game with scores or None if not found.
        """
        games = self.fetch_completed_games(days_back=2)
        
        for game in games:
            home = game.get('home_team', '')
            away = game.get('away_team', '')
            
            if self._teams_match(team1, team2, home, away):
                return game
        
        return None
    
    def _teams_match(self, team1: str, team2: str, home: str, away: str) -> bool:
        """Check if team names match (fuzzy matching)"""
        team1_clean = self._clean_team_name(team1)
        team2_clean = self._clean_team_name(team2)
        home_clean = self._clean_team_name(home)
        away_clean = self._clean_team_name(away)
        
        match1 = (self._fuzzy_match(team1_clean, home_clean) and 
                  self._fuzzy_match(team2_clean, away_clean))
        match2 = (self._fuzzy_match(team1_clean, away_clean) and 
                  self._fuzzy_match(team2_clean, home_clean))
        
        return match1 or match2
    
    def _clean_team_name(self, name: str) -> str:
        """Clean and normalize team name for matching"""
        name = name.lower().strip()
        removals = ['university', 'college', 'state', 'st.', 'univ.', 'univ']
        for r in removals:
            name = name.replace(r, '')
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    def _fuzzy_match(self, name1: str, name2: str, threshold: float = 0.6) -> bool:
        """Check if two names are similar enough"""
        if name1 in name2 or name2 in name1:
            return True
        
        ratio = SequenceMatcher(None, name1, name2).ratio()
        return ratio >= threshold
    
    def get_game_result(self, match_string: str) -> Optional[Tuple[int, int, str, str]]:
        """
        Get game result from match string like "Team1 vs Team2"
        Returns: (home_score, away_score, home_team, away_team) or None
        """
        try:
            parts = match_string.split(' vs ')
            if len(parts) != 2:
                return None
            
            team1, team2 = parts[0].strip(), parts[1].strip()
            game = self.find_game_score(team1, team2)
            
            if not game or not game.get('scores'):
                return None
            
            scores = game['scores']
            home_team = game['home_team']
            away_team = game['away_team']
            
            home_score = None
            away_score = None
            
            for s in scores:
                if s['name'] == home_team:
                    home_score = int(s['score']) if s['score'] else 0
                elif s['name'] == away_team:
                    away_score = int(s['score']) if s['score'] else 0
            
            if home_score is not None and away_score is not None:
                return (home_score, away_score, home_team, away_team)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting game result: {e}")
            return None


def test_scraper():
    """Test the ESPN scraper"""
    scraper = ESPNBasketballScraper()
    
    print("\n📊 Fetching today's completed games...")
    games = scraper.fetch_completed_games(days_back=1)
    
    print(f"\n✅ Found {len(games)} completed games:\n")
    for game in games[:10]:
        scores = game.get('scores', [])
        if scores and len(scores) >= 2:
            home = next((s for s in scores if s['name'] == game['home_team']), {})
            away = next((s for s in scores if s['name'] == game['away_team']), {})
            print(f"  {game['away_team']} {away.get('score', '?')} @ {game['home_team']} {home.get('score', '?')}")


if __name__ == "__main__":
    test_scraper()

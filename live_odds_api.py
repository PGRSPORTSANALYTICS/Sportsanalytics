"""
🎯 LIVE ODDS API INTEGRATION
Real betting odds from The Odds API (500 free requests/month)
Covers major soccer leagues including virtual/e-soccer when available
"""
import requests
import os
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class LiveOdds:
    """Real betting odds from The Odds API"""
    home_team: str
    away_team: str
    commence_time: str
    bookmaker: str
    market: str  # 'h2h', 'spreads', 'totals'
    odds_home: float = None
    odds_away: float = None
    odds_draw: float = None
    total_line: float = None  # For over/under markets
    total_over: float = None
    total_under: float = None

class TheOddsAPI:
    """Integration with The Odds API for real live betting odds"""
    
    def __init__(self):
        self.api_key = os.getenv('THE_ODDS_API_KEY')
        if not self.api_key:
            raise ValueError("THE_ODDS_API_KEY environment variable required!")
        
        self.base_url = "https://api.the-odds-api.com/v4"
        self.requests_used = 0
        self.max_requests = 500  # Free tier limit
        
    def get_available_sports(self) -> List[Dict]:
        """Get list of available sports (doesn't count against quota)"""
        url = f"{self.base_url}/sports"
        params = {'api_key': self.api_key}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Sports API error: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Sports API exception: {e}")
            return []
    
    def get_soccer_odds(self, regions='uk,us,eu', markets='totals') -> List[LiveOdds]:
        """Get live soccer odds from multiple leagues"""
        if self.requests_used >= self.max_requests:
            print(f"⚠️ API quota reached ({self.max_requests} requests)")
            return []
        
        # Focus on leagues that might have e-soccer/virtual games
        soccer_sports = [
            'soccer_epl',           # English Premier League (has virtual games)
            'soccer_efl_champ',     # English Championship  
            'soccer_germany_bundesliga',  # German Bundesliga (popular for e-soccer)
            'soccer_spain_la_liga', # Spanish La Liga
            'soccer_italy_serie_a', # Italian Serie A
            'soccer_france_ligue_one', # French Ligue 1
            'soccer_uefa_champs_league', # Champions League (e-soccer format)
            'soccer_uefa_europa_league', # Europa League
        ]
        
        all_odds = []
        
        for sport in soccer_sports:
            if self.requests_used >= self.max_requests:
                break
                
            odds = self._fetch_sport_odds(sport, regions, markets)
            all_odds.extend(odds)
            
            # Rate limiting - be nice to the API
            time.sleep(0.5)
        
        return all_odds
    
    def _fetch_sport_odds(self, sport: str, regions: str, markets: str) -> List[LiveOdds]:
        """Fetch odds for a specific sport"""
        url = f"{self.base_url}/sports/{sport}/odds"
        params = {
            'api_key': self.api_key,
            'regions': regions,
            'markets': markets,
            'oddsFormat': 'decimal',
            'dateFormat': 'iso'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            self.requests_used += 1
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_odds_response(data)
            else:
                print(f"❌ Odds API error for {sport}: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"❌ Odds API exception for {sport}: {e}")
            return []
    
    def _parse_odds_response(self, data: List[Dict]) -> List[LiveOdds]:
        """Parse The Odds API response into LiveOdds objects"""
        live_odds = []
        
        for game in data:
            home_team = game.get('home_team', '')
            away_team = game.get('away_team', '')
            commence_time = game.get('commence_time', '')
            
            # Process each bookmaker's odds
            for bookmaker in game.get('bookmakers', []):
                bookmaker_name = bookmaker.get('title', 'Unknown')
                
                # Process each market
                for market in bookmaker.get('markets', []):
                    market_key = market.get('key', '')
                    
                    if market_key == 'totals':  # Over/Under markets
                        for outcome in market.get('outcomes', []):
                            if outcome.get('name') == 'Over':
                                total_line = outcome.get('point', 2.5)
                                total_over = outcome.get('price', 2.0)
                                
                                # Find corresponding Under odds
                                total_under = None
                                for under_outcome in market.get('outcomes', []):
                                    if (under_outcome.get('name') == 'Under' and 
                                        under_outcome.get('point') == total_line):
                                        total_under = under_outcome.get('price', 2.0)
                                        break
                                
                                live_odds.append(LiveOdds(
                                    home_team=home_team,
                                    away_team=away_team,
                                    commence_time=commence_time,
                                    bookmaker=bookmaker_name,
                                    market='totals',
                                    total_line=total_line,
                                    total_over=total_over,
                                    total_under=total_under
                                ))
        
        return live_odds
    
    def get_usage_stats(self) -> Dict:
        """Get API usage statistics"""
        return {
            'requests_used': self.requests_used,
            'requests_remaining': max(0, self.max_requests - self.requests_used),
            'quota_percentage': (self.requests_used / self.max_requests) * 100
        }

def test_live_odds():
    """Test the live odds API integration"""
    try:
        api = TheOddsAPI()
        print("🔄 Testing The Odds API connection...")
        
        # Test sports list
        sports = api.get_available_sports()
        print(f"✅ Found {len(sports)} available sports")
        
        # Test soccer odds
        print("🔄 Fetching live soccer odds...")
        odds = api.get_soccer_odds()
        
        print(f"✅ Found {len(odds)} live betting opportunities")
        for i, odd in enumerate(odds[:5]):  # Show first 5
            if odd.market == 'totals':
                print(f"  {i+1}. {odd.home_team} vs {odd.away_team}")
                print(f"     Over {odd.total_line}: {odd.total_over}")
                print(f"     Bookmaker: {odd.bookmaker}")
        
        stats = api.get_usage_stats()
        print(f"\n📊 API Usage: {stats['requests_used']}/{stats['quota_percentage']:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ Live odds test failed: {e}")
        return False

if __name__ == "__main__":
    test_live_odds()
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
        
        # Comprehensive global league coverage for 24/7 betting opportunities
        soccer_sports = [
            # Major European Leagues (Prime Time EU)
            'soccer_epl',                    # English Premier League
            'soccer_efl_champ',             # English Championship
            'soccer_spain_la_liga',         # Spanish La Liga
            'soccer_italy_serie_a',         # Italian Serie A
            'soccer_germany_bundesliga',    # German Bundesliga
            'soccer_france_ligue_one',      # French Ligue 1
            'soccer_netherlands_eredivisie', # Dutch Eredivisie
            'soccer_portugal_primeira_liga', # Portuguese Primeira Liga
            'soccer_belgium_first_div',     # Belgian First Division
            'soccer_scotland_premiership',  # Scottish Premiership
            
            # European Cups (High Value)
            'soccer_uefa_champs_league',    # Champions League
            'soccer_uefa_europa_league',    # Europa League
            'soccer_uefa_conference_league',# Conference League
            
            # Nordic/Eastern Europe (Different Schedules)
            'soccer_sweden_allsvenskan',    # Swedish Allsvenskan
            'soccer_norway_eliteserien',    # Norwegian Eliteserien
            'soccer_denmark_superliga',     # Danish Superliga
            'soccer_poland_ekstraklasa',    # Polish Ekstraklasa
            'soccer_czech_1_liga',          # Czech First League
            'soccer_turkey_super_league',   # Turkish Super League
            'soccer_russia_premier_league', # Russian Premier League
            
            # South America (Different Time Zone - More Coverage)
            'soccer_brazil_serie_a',        # Brazilian Serie A
            'soccer_argentina_primera_division', # Argentinian Primera
            'soccer_chile_primera_division', # Chilean Primera
            'soccer_colombia_primera_a',    # Colombian Primera A
            'soccer_uruguay_primera_division', # Uruguayan Primera
            'soccer_conmebol_libertadores',  # Copa Libertadores
            'soccer_conmebol_sudamericana',  # Copa Sudamericana
            
            # North America (Evening Coverage)
            'soccer_usa_mls',               # Major League Soccer
            'soccer_mexico_liga_mx',        # Liga MX (Mexico)
            'soccer_canada_cpl',            # Canadian Premier League
            
            # Asia-Pacific (Early Coverage)
            'soccer_japan_j_league',        # Japanese J1 League
            'soccer_south_korea_k_league_1', # Korean K League 1
            'soccer_china_super_league',    # Chinese Super League
            'soccer_australia_a_league',    # Australian A-League
            'soccer_india_super_league',    # Indian Super League
            
            # Africa (Afternoon Coverage)  
            'soccer_south_africa_premier_division', # South African Premier
            'soccer_egypt_premier_league',  # Egyptian Premier League
            
            # Lower English Leagues (More Matches)
            'soccer_efl_league_one',        # English League One
            'soccer_efl_league_two',        # English League Two
            
            # International Competitions
            'soccer_uefa_nations_league',   # UEFA Nations League
            'soccer_fifa_world_cup',        # FIFA World Cup
            'soccer_uefa_euros',            # European Championship
            'soccer_conmebol_copa_america', # Copa America
            'soccer_international_friendlies', # International Friendlies
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
"""
🎯 SIMPLE REAL ODDS FETCHER
Direct integration with The Odds API for immediate real odds
"""
import requests
import os
import time
from typing import Dict, List, Optional

class RealOddsFetcher:
    """Simplified real odds fetcher for immediate use"""
    
    def __init__(self):
        self.api_key = os.getenv('THE_ODDS_API_KEY')
        if not self.api_key:
            raise ValueError("THE_ODDS_API_KEY required!")
        
        self.base_url = "https://api.the-odds-api.com/v4"
        self.last_fetch = 0
        self.cache = {}
        
    def get_live_soccer_totals(self) -> Dict[str, Dict]:
        """Get live soccer Over/Under odds for all matches"""
        current_time = time.time()
        
        # Cache for 2 minutes to conserve API quota
        if current_time - self.last_fetch < 120 and self.cache:
            print(f"📋 Using cached odds ({len(self.cache)} matches)")
            return self.cache
        
        print("🔄 Fetching REAL LIVE ODDS from bookmakers...")
        
        # Focus on major leagues with live games
        leagues = ['soccer_epl', 'soccer_germany_bundesliga', 'soccer_spain_la_liga']
        all_odds = {}
        
        for league in leagues:
            try:
                url = f"{self.base_url}/sports/{league}/odds"
                params = {
                    'api_key': self.api_key,
                    'regions': 'uk,us,eu',
                    'markets': 'totals',
                    'oddsFormat': 'decimal'
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    for game in data:
                        home = game.get('home_team', '')
                        away = game.get('away_team', '')
                        match_key = f"{home}_vs_{away}"
                        
                        # Extract Over/Under odds
                        odds_data = {'over': {}, 'under': {}}
                        
                        for bookmaker in game.get('bookmakers', []):
                            book_name = bookmaker.get('title', 'Unknown')
                            
                            for market in bookmaker.get('markets', []):
                                if market.get('key') == 'totals':
                                    for outcome in market.get('outcomes', []):
                                        line = outcome.get('point', 2.5)
                                        odds = outcome.get('price', 2.0)
                                        
                                        if outcome.get('name') == 'Over':
                                            if line not in odds_data['over']:
                                                odds_data['over'][line] = []
                                            odds_data['over'][line].append({
                                                'bookmaker': book_name,
                                                'odds': odds
                                            })
                                        elif outcome.get('name') == 'Under':
                                            if line not in odds_data['under']:
                                                odds_data['under'][line] = []
                                            odds_data['under'][line].append({
                                                'bookmaker': book_name,
                                                'odds': odds
                                            })
                        
                        if odds_data['over'] or odds_data['under']:
                            all_odds[match_key] = {
                                'home': home,
                                'away': away,
                                'league': league,
                                'odds': odds_data,
                                'commence_time': game.get('commence_time', '')
                            }
                
                # Small delay between requests
                time.sleep(0.5)
                
            except Exception as e:
                print(f"⚠️ Error fetching {league}: {e}")
                continue
        
        self.cache = all_odds
        self.last_fetch = current_time
        
        print(f"✅ Fetched REAL odds for {len(all_odds)} live matches")
        return all_odds
    
    def get_best_odds(self, match_key: str, market: str, line: float) -> Optional[float]:
        """Get best odds for a specific market"""
        if match_key not in self.cache:
            return None
        
        odds_list = self.cache[match_key]['odds'].get(market, {}).get(line, [])
        if not odds_list:
            return None
        
        # Return best (highest) odds
        return max(odds_item['odds'] for odds_item in odds_list)

def test_real_odds():
    """Test real odds fetching"""
    try:
        fetcher = RealOddsFetcher()
        odds = fetcher.get_live_soccer_totals()
        
        if odds:
            print(f"\n🎯 REAL LIVE ODDS SAMPLE:")
            for i, (match_key, match_data) in enumerate(list(odds.items())[:3]):
                print(f"\n{i+1}. {match_data['home']} vs {match_data['away']}")
                
                # Show Over odds
                for line, odds_list in match_data['odds']['over'].items():
                    best_odds = max(item['odds'] for item in odds_list)
                    print(f"   Over {line}: {best_odds}")
                
                # Show Under odds
                for line, odds_list in match_data['odds']['under'].items():
                    best_odds = max(item['odds'] for item in odds_list)
                    print(f"   Under {line}: {best_odds}")
        
        return True
    except Exception as e:
        print(f"❌ Real odds test failed: {e}")
        return False

if __name__ == "__main__":
    test_real_odds()
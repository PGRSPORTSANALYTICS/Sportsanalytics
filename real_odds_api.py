"""
🚀 REAL ODDS API INTEGRATION - LIVE BETTING CHAMPION
Connects to The Odds API using your actual API key for REAL e-soccer odds
"""

import os
import requests
import json
import time
from typing import Dict, List, Optional
from datetime import datetime

class RealOddsAPI:
    """🚀 REAL odds fetcher using The Odds API"""
    
    def __init__(self):
        self.api_key = os.getenv('THE_ODDS_API_KEY')
        if not self.api_key:
            raise ValueError("THE_ODDS_API_KEY environment variable not found!")
        
        self.base_url = "https://api.the-odds-api.com/v4"
        self.session = requests.Session()
        self.session.params['apiKey'] = self.api_key
        
        print("🚀 REAL ODDS API INITIALIZED")
        print(f"✅ API Key loaded: {self.api_key[:8]}...")
        
    def get_available_sports(self) -> List[Dict]:
        """Get all available sports from The Odds API"""
        
        url = f"{self.base_url}/sports"
        
        try:
            print("🔍 FETCHING AVAILABLE SPORTS FROM THE ODDS API...")
            response = self.session.get(url)
            response.raise_for_status()
            
            sports = response.json()
            
            print(f"✅ FOUND {len(sports)} AVAILABLE SPORTS")
            
            # Look for e-soccer, virtual football, or similar
            esoccer_sports = []
            football_sports = []
            
            for sport in sports:
                sport_key = sport['key'].lower()
                sport_title = sport['title'].lower()
                
                if any(term in sport_key or term in sport_title for term in 
                      ['esoccer', 'virtual', 'soccer', 'football']):
                    
                    if any(term in sport_key or term in sport_title for term in 
                          ['esoccer', 'virtual']):
                        esoccer_sports.append(sport)
                    elif any(term in sport_key or term in sport_title for term in 
                            ['soccer', 'football']):
                        football_sports.append(sport)
            
            print(f"🎮 E-SOCCER/VIRTUAL SPORTS FOUND: {len(esoccer_sports)}")
            for sport in esoccer_sports[:5]:  # Show first 5
                print(f"   ⚽ {sport['key']}: {sport['title']}")
            
            print(f"⚽ FOOTBALL/SOCCER SPORTS FOUND: {len(football_sports)}")
            for sport in football_sports[:5]:  # Show first 5
                print(f"   🏈 {sport['key']}: {sport['title']}")
            
            return sports
            
        except Exception as e:
            print(f"❌ ERROR FETCHING SPORTS: {e}")
            return []
    
    def get_live_odds(self, sport_key: str, regions: List[str] = None, 
                     markets: List[str] = None) -> List[Dict]:
        """Get live odds for a specific sport"""
        
        if regions is None:
            regions = ['eu', 'uk']  # European bookmakers
        if markets is None:
            markets = ['h2h', 'totals']  # Match result and totals (btts not supported)
            
        url = f"{self.base_url}/sports/{sport_key}/odds"
        
        params = {
            'regions': ','.join(regions),
            'markets': ','.join(markets),
            'oddsFormat': 'decimal',
            'dateFormat': 'iso'
        }
        
        try:
            print(f"🔍 FETCHING LIVE ODDS FOR {sport_key}...")
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            odds_data = response.json()
            
            print(f"✅ FOUND {len(odds_data)} LIVE MATCHES WITH ODDS")
            
            return odds_data
            
        except Exception as e:
            print(f"❌ ERROR FETCHING ODDS FOR {sport_key}: {e}")
            return []
    
    def find_esoccer_opportunities(self, sport_key: str) -> List[Dict]:
        """Find betting opportunities in e-soccer matches"""
        
        odds_data = self.get_live_odds(sport_key)
        opportunities = []
        
        for match in odds_data:
            try:
                # Extract match info
                home_team = match['home_team']
                away_team = match['away_team']
                commence_time = match['commence_time']
                
                # Check if match is live or starting soon
                commence_dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                now = datetime.now().astimezone()
                
                # Only consider matches starting within next 30 minutes or live
                time_diff = (commence_dt - now).total_seconds()
                if time_diff > 1800:  # More than 30 minutes away
                    continue
                
                # Process bookmaker odds
                for bookmaker in match.get('bookmakers', []):
                    bookmaker_name = bookmaker['key']
                    
                    for market in bookmaker.get('markets', []):
                        market_key = market['key']
                        
                        if market_key == 'totals':
                            # Over/Under opportunities
                            for outcome in market.get('outcomes', []):
                                name = outcome.get('name', '')
                                point = outcome.get('point', 0)
                                odds = outcome.get('price', 0)
                                
                                if odds > 1.5 and odds < 3.0:  # Reasonable odds range
                                    opportunity = {
                                        'match_id': f"{sport_key}_{home_team}_{away_team}",
                                        'home_team': home_team,
                                        'away_team': away_team,
                                        'market': f"{name} {point}",
                                        'odds': odds,
                                        'bookmaker': bookmaker_name,
                                        'commence_time': commence_time,
                                        'sport': sport_key,
                                        'time_to_start': time_diff
                                    }
                                    opportunities.append(opportunity)
                        
                        elif market_key == 'h2h':
                            # Head-to-head opportunities (for draw odds if available)
                            for outcome in market.get('outcomes', []):
                                name = outcome.get('name', '')
                                odds = outcome.get('price', 0)
                                
                                if 'draw' in name.lower() and odds > 2.5 and odds < 5.0:
                                    opportunity = {
                                        'match_id': f"{sport_key}_{home_team}_{away_team}",
                                        'home_team': home_team,
                                        'away_team': away_team,
                                        'market': "Draw",
                                        'odds': odds,
                                        'bookmaker': bookmaker_name,
                                        'commence_time': commence_time,
                                        'sport': sport_key,
                                        'time_to_start': time_diff
                                    }
                                    opportunities.append(opportunity)
                
            except Exception as e:
                print(f"❌ Error processing match: {e}")
                continue
        
        return opportunities
    
    def scan_all_esoccer(self) -> List[Dict]:
        """Scan all available sports for e-soccer opportunities"""
        
        print("🎯 SCANNING ALL SPORTS FOR E-SOCCER OPPORTUNITIES...")
        
        sports = self.get_available_sports()
        all_opportunities = []
        
        # Look for e-soccer specific sports first
        esoccer_sports = [s for s in sports if any(term in s['key'].lower() or term in s['title'].lower() 
                         for term in ['esoccer', 'virtual', 'fifa', 'pes'])]
        
        # If no specific e-soccer, try football/soccer sports
        if not esoccer_sports:
            football_sports = [s for s in sports if any(term in s['key'].lower() 
                              for term in ['soccer', 'football']) and 
                              'american' not in s['title'].lower()]
            esoccer_sports = football_sports[:3]  # Try first 3
        
        for sport in esoccer_sports:
            sport_key = sport['key']
            print(f"🔍 CHECKING {sport_key}: {sport['title']}")
            
            opportunities = self.find_esoccer_opportunities(sport_key)
            
            if opportunities:
                print(f"🔥 FOUND {len(opportunities)} OPPORTUNITIES IN {sport_key}")
                all_opportunities.extend(opportunities)
            else:
                print(f"   No opportunities in {sport_key}")
        
        return all_opportunities

class Bet365Connector:
    """🎯 Bet365 integration for real betting (placeholder structure)"""
    
    def __init__(self, username: str = None, password: str = None):
        self.username = username
        self.password = password
        self.logged_in = False
        
        print("🎯 BET365 CONNECTOR INITIALIZED")
        if not username:
            print("⚠️  No credentials provided - will operate in demo mode")
    
    def login(self) -> bool:
        """Login to bet365 (placeholder - needs real implementation)"""
        if not self.username or not self.password:
            print("❌ No credentials provided for bet365")
            return False
        
        # Real implementation would use selenium or API
        print(f"🔐 ATTEMPTING LOGIN TO BET365 as {self.username}")
        print("⚠️  Real bet365 integration requires web automation or API access")
        
        return False  # For now, until real implementation
    
    def place_bet(self, opportunity: Dict, stake: float) -> Dict:
        """Place a real bet (placeholder structure)"""
        
        if not self.logged_in:
            return {
                'success': False,
                'error': 'Not logged in to bet365',
                'bet_id': None
            }
        
        # Real implementation would place actual bet
        bet_info = {
            'match': f"{opportunity['home_team']} vs {opportunity['away_team']}",
            'market': opportunity['market'],
            'odds': opportunity['odds'],
            'stake': stake,
            'bookmaker': 'bet365'
        }
        
        print(f"🎯 PLACING REAL BET: {bet_info}")
        
        # Placeholder response
        return {
            'success': False,  # Set to True when real implementation is ready
            'bet_id': f"bet365_{int(time.time())}",
            'bet_info': bet_info,
            'error': 'Real betting not implemented yet'
        }

def main():
    """Test the real odds API"""
    
    print("🚀 TESTING REAL ODDS API CONNECTION")
    print("=" * 50)
    
    try:
        # Initialize real API
        api = RealOddsAPI()
        
        # Scan for opportunities
        opportunities = api.scan_all_esoccer()
        
        if opportunities:
            print(f"\n🔥 FOUND {len(opportunities)} REAL BETTING OPPORTUNITIES!")
            print("=" * 50)
            
            for i, opp in enumerate(opportunities[:5], 1):  # Show first 5
                print(f"\n🎯 REAL OPPORTUNITY #{i}:")
                print(f"   ⚽ {opp['home_team']} vs {opp['away_team']}")
                print(f"   📊 {opp['market']} @ {opp['odds']}")
                print(f"   🏢 Bookmaker: {opp['bookmaker']}")
                print(f"   ⏰ Starts in: {opp['time_to_start']:.0f} seconds")
                print(f"   🎮 Sport: {opp['sport']}")
        else:
            print("❌ NO OPPORTUNITIES FOUND")
            print("   This could mean:")
            print("   - No e-soccer sports available in The Odds API")
            print("   - No live matches at the moment")
            print("   - API quota exceeded")
        
        # Test bet365 connector
        print(f"\n🎯 TESTING BET365 CONNECTOR")
        print("=" * 30)
        bet365 = Bet365Connector()
        
        if opportunities:
            result = bet365.place_bet(opportunities[0], 50.0)
            print(f"Bet placement result: {result}")
        
    except Exception as e:
        print(f"❌ ERROR IN MAIN: {e}")

if __name__ == "__main__":
    main()
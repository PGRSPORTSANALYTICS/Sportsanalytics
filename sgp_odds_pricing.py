#!/usr/bin/env python3
"""
SGP Odds Pricing Service
Fetches real odds from The Odds API and prices SGP parlays
"""

import os
import logging
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class OddsPricingService:
    """
    Manages real odds fetching and SGP parlay pricing
    
    Features:
    - Fetches individual leg odds from The Odds API
    - Combines leg odds with parlay margin
    - Caches odds to minimize API calls
    - Graceful fallback for unsupported markets
    """
    
    def __init__(self, parlay_margin: float = 0.07):
        """
        Initialize odds pricing service
        
        Args:
            parlay_margin: Bookmaker's parlay margin (default 7%)
                          This mimics the vig bookmakers apply to parlays
        """
        self.parlay_margin = parlay_margin
        self.odds_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
        # Try to initialize The Odds API
        try:
            from real_odds_api import RealOddsAPI
            self.odds_api = RealOddsAPI()
            self.live_mode = True
            logger.info("✅ Live odds enabled via The Odds API")
        except Exception as e:
            self.odds_api = None
            self.live_mode = False
            logger.warning(f"⚠️ Live odds unavailable: {e}. Using simulated odds.")
    
    def _get_cache_key(self, home_team: str, away_team: str) -> str:
        """Generate cache key for match"""
        return f"{home_team}||{away_team}".lower()
    
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cached odds are still valid"""
        if not cache_entry:
            return False
        
        cached_time = cache_entry.get('timestamp', 0)
        age = time.time() - cached_time
        return age < self.cache_ttl
    
    def _fetch_match_odds(self, home_team: str, away_team: str, league: str) -> Optional[Dict]:
        """
        Fetch odds for a specific match from The Odds API
        
        Returns:
            Dict with market odds or None if not found
        """
        if not self.live_mode or not self.odds_api:
            return None
        
        cache_key = self._get_cache_key(home_team, away_team)
        
        # Check cache first
        if cache_key in self.odds_cache:
            cached = self.odds_cache[cache_key]
            if self._is_cache_valid(cached):
                logger.info(f"📦 Using cached odds for {home_team} vs {away_team}")
                return cached['odds']
        
        # Map league to sport key
        sport_key = self._map_league_to_sport_key(league)
        if not sport_key:
            logger.warning(f"⚠️ No sport key mapping for league: {league}")
            return None
        
        try:
            # Fetch odds from API
            # Note: The Odds API supports 'h2h' and 'totals', but not all bookmakers provide BTTS
            markets = ['h2h', 'totals']  # Match result, Over/Under
            odds_data = self.odds_api.get_live_odds(sport_key, markets=markets)
            
            # Find this specific match
            for match in odds_data:
                if (self._teams_match(match['home_team'], home_team) and 
                    self._teams_match(match['away_team'], away_team)):
                    
                    # Parse bookmaker odds
                    match_odds = self._parse_bookmaker_odds(match)
                    
                    # Cache the result
                    self.odds_cache[cache_key] = {
                        'odds': match_odds,
                        'timestamp': time.time()
                    }
                    
                    logger.info(f"✅ Fetched live odds for {home_team} vs {away_team}")
                    return match_odds
            
            logger.warning(f"⚠️ Match not found in odds feed: {home_team} vs {away_team}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error fetching odds: {e}")
            return None
    
    def _map_league_to_sport_key(self, league: str) -> Optional[str]:
        """Map league name to The Odds API sport key"""
        league_lower = league.lower()
        
        mapping = {
            'premier league': 'soccer_epl',
            'la liga': 'soccer_spain_la_liga',
            'serie a': 'soccer_italy_serie_a',
            'bundesliga': 'soccer_germany_bundesliga',
            'ligue 1': 'soccer_france_ligue_one',
            'champions league': 'soccer_uefa_champs_league',
            'europa league': 'soccer_uefa_europa_league',
            'eredivisie': 'soccer_netherlands_eredivisie',
            'primeira liga': 'soccer_portugal_primeira_liga',
            'belgian': 'soccer_belgium_first_div',
            'championship': 'soccer_efl_champ',
            'scottish premiership': 'soccer_scotland_premiership',
            'turkish': 'soccer_turkey_super_league',
            'allsvenskan': 'soccer_sweden_allsvenskan',
            'serie a brazil': 'soccer_brazil_campeonato',
            'mls': 'soccer_usa_mls'
        }
        
        for key, value in mapping.items():
            if key in league_lower:
                return value
        
        return None
    
    def _teams_match(self, api_team: str, our_team: str) -> bool:
        """Fuzzy team name matching"""
        api_lower = api_team.lower()
        our_lower = our_team.lower()
        
        # Direct match
        if api_lower == our_lower:
            return True
        
        # Substring match
        if api_lower in our_lower or our_lower in api_lower:
            return True
        
        # Check if main team name appears
        api_parts = api_lower.split()
        our_parts = our_lower.split()
        
        for api_part in api_parts:
            if len(api_part) > 3:  # Ignore short words like "fc", "cf"
                for our_part in our_parts:
                    if len(our_part) > 3 and (api_part in our_part or our_part in api_part):
                        return True
        
        return False
    
    def _parse_bookmaker_odds(self, match: Dict) -> Dict:
        """
        Parse bookmaker odds from The Odds API response
        
        Returns:
            Dict with structured odds by market
        """
        odds_by_market = {}
        
        if 'bookmakers' not in match or not match['bookmakers']:
            return odds_by_market
        
        # Use first bookmaker (typically best odds)
        bookmaker = match['bookmakers'][0]
        
        for market in bookmaker.get('markets', []):
            market_key = market['key']
            
            if market_key == 'h2h':
                # Match result odds
                for outcome in market['outcomes']:
                    if outcome['name'] == match['home_team']:
                        odds_by_market['home_win'] = outcome['price']
                    elif outcome['name'] == match['away_team']:
                        odds_by_market['away_win'] = outcome['price']
                    elif outcome['name'] == 'Draw':
                        odds_by_market['draw'] = outcome['price']
            
            elif market_key == 'totals':
                # Over/Under odds
                for outcome in market['outcomes']:
                    point = outcome.get('point', 2.5)
                    if outcome['name'] == 'Over':
                        odds_by_market[f'over_{point}'] = outcome['price']
                    elif outcome['name'] == 'Under':
                        odds_by_market[f'under_{point}'] = outcome['price']
            
            elif market_key == 'btts':
                # Both Teams To Score
                for outcome in market['outcomes']:
                    if outcome['name'] == 'Yes':
                        odds_by_market['btts_yes'] = outcome['price']
                    elif outcome['name'] == 'No':
                        odds_by_market['btts_no'] = outcome['price']
        
        return odds_by_market
    
    def get_leg_odds(self, leg: Dict, match_odds: Dict) -> Optional[float]:
        """
        Get bookmaker odds for a specific SGP leg
        
        Args:
            leg: Leg definition (market_type, outcome, line, etc.)
            match_odds: Parsed odds from bookmaker
        
        Returns:
            Decimal odds or None if not available
        """
        market_type = leg['market_type']
        outcome = leg['outcome']
        
        if market_type == 'OVER_UNDER_GOALS':
            line = leg.get('line', 2.5)
            if outcome == 'OVER':
                return match_odds.get(f'over_{line}')
            elif outcome == 'UNDER':
                return match_odds.get(f'under_{line}')
        
        elif market_type == 'BTTS':
            if outcome == 'YES':
                return match_odds.get('btts_yes')
            elif outcome == 'NO':
                return match_odds.get('btts_no')
        
        elif market_type == 'MATCH_RESULT':
            if outcome == 'HOME':
                return match_odds.get('home_win')
            elif outcome == 'AWAY':
                return match_odds.get('away_win')
            elif outcome == 'DRAW':
                return match_odds.get('draw')
        
        # Unsupported markets (player props, corners, half-time)
        return None
    
    def price_sgp_parlay(
        self, 
        home_team: str, 
        away_team: str, 
        league: str,
        legs: List[Dict],
        fair_odds: float
    ) -> Tuple[Optional[float], str, Dict]:
        """
        Price SGP parlay using real bookmaker odds
        
        Args:
            home_team: Home team name
            away_team: Away team name
            league: League name
            legs: List of SGP legs
            fair_odds: Model's fair value odds
        
        Returns:
            (bookmaker_odds, pricing_mode, metadata)
            pricing_mode: 'live' | 'hybrid' | 'simulated'
        """
        # Try to fetch real odds
        match_odds = self._fetch_match_odds(home_team, away_team, league)
        
        if not match_odds:
            # Fallback to simulation
            import random
            margin_factor = random.uniform(0.95, 1.15)
            simulated_odds = fair_odds * margin_factor
            
            return (
                simulated_odds, 
                'simulated',
                {'reason': 'match_not_found'}
            )
        
        # Try to get odds for each leg
        leg_odds = []
        unsupported_legs = []
        
        for i, leg in enumerate(legs):
            odds = self.get_leg_odds(leg, match_odds)
            
            if odds is not None:
                leg_odds.append({
                    'leg_index': i,
                    'market': leg['market_type'],
                    'odds': odds
                })
            else:
                unsupported_legs.append(leg['market_type'])
        
        # Check if we have all legs
        if len(leg_odds) == len(legs):
            # All legs have live odds - FULL LIVE PRICING
            combined_odds = 1.0
            for leg_data in leg_odds:
                combined_odds *= leg_data['odds']
            
            # Apply parlay margin (bookmakers reduce odds for parlays)
            # Convert to implied probability, add margin, convert back
            implied_prob = 1.0 / combined_odds
            adjusted_prob = implied_prob * (1 + self.parlay_margin)
            bookmaker_odds = 1.0 / min(adjusted_prob, 0.99)
            
            logger.info(f"✅ Full live pricing: {len(legs)} legs at {bookmaker_odds:.2f}x odds")
            
            return (
                bookmaker_odds,
                'live',
                {
                    'leg_count': len(legs),
                    'combined_raw_odds': combined_odds,
                    'parlay_margin': self.parlay_margin,
                    'leg_odds': leg_odds
                }
            )
        
        elif len(leg_odds) > 0:
            # Some legs have live odds - HYBRID PRICING
            # Use live odds for supported legs, fair value for unsupported
            combined_odds = 1.0
            
            for leg_data in leg_odds:
                combined_odds *= leg_data['odds']
            
            # For unsupported legs, use proportional fair odds
            # fair_odds is for entire parlay, so divide by live portion
            live_portion_prob = 1.0 / combined_odds
            full_fair_prob = 1.0 / fair_odds
            unsupported_prob = full_fair_prob / live_portion_prob
            unsupported_odds = 1.0 / max(unsupported_prob, 0.01)
            
            combined_odds *= unsupported_odds
            
            # Apply parlay margin
            implied_prob = 1.0 / combined_odds
            adjusted_prob = implied_prob * (1 + self.parlay_margin)
            bookmaker_odds = 1.0 / min(adjusted_prob, 0.99)
            
            logger.info(f"⚠️ Hybrid pricing: {len(leg_odds)}/{len(legs)} legs live, rest simulated")
            
            return (
                bookmaker_odds,
                'hybrid',
                {
                    'live_legs': len(leg_odds),
                    'total_legs': len(legs),
                    'unsupported_markets': unsupported_legs,
                    'leg_odds': leg_odds
                }
            )
        
        else:
            # No legs supported - FULL SIMULATION
            import random
            margin_factor = random.uniform(0.95, 1.15)
            simulated_odds = fair_odds * margin_factor
            
            logger.warning(f"❌ No live odds available for any leg. Unsupported: {unsupported_legs}")
            
            return (
                simulated_odds,
                'simulated',
                {
                    'reason': 'all_legs_unsupported',
                    'unsupported_markets': unsupported_legs
                }
            )


if __name__ == "__main__":
    # Test odds pricing service
    logging.basicConfig(level=logging.INFO)
    
    service = OddsPricingService()
    
    # Test match
    legs = [
        {'market_type': 'OVER_UNDER_GOALS', 'outcome': 'OVER', 'line': 2.5},
        {'market_type': 'BTTS', 'outcome': 'YES'}
    ]
    
    odds, mode, metadata = service.price_sgp_parlay(
        'Manchester City',
        'Liverpool',
        'Premier League',
        legs,
        fair_odds=3.5
    )
    
    print(f"\n✅ Pricing Result:")
    print(f"   Bookmaker Odds: {odds:.2f}x")
    print(f"   Pricing Mode: {mode}")
    print(f"   Metadata: {metadata}")

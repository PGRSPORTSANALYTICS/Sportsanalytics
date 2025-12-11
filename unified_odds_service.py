"""
🎯 UNIFIED ODDS SERVICE
Combines odds from multiple sources:
1. The Odds API (primary - 500 free requests/month)
2. API-Football (secondary - 7000 requests/day)

Provides best available odds across all markets:
- 1X2 (Match Winner)
- Over/Under (Totals)
- BTTS (Both Teams to Score)
- Double Chance
- Draw No Bet
- Asian Handicap
"""
import os
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class UnifiedOdds:
    """Unified odds from all sources"""
    fixture_id: str
    home_team: str
    away_team: str
    kickoff_time: str
    markets: Dict[str, float]
    source: str
    bookmakers: List[str]


class UnifiedOddsService:
    """
    Combines odds from The Odds API and API-Football
    
    Priority:
    1. The Odds API (more reliable, but limited quota)
    2. API-Football (backup with more markets)
    """
    
    def __init__(self):
        self.the_odds_api = None
        self.api_football = None
        
        try:
            from live_odds_api import TheOddsAPI
            self.the_odds_api = TheOddsAPI()
            logger.info("✅ The Odds API initialized")
        except Exception as e:
            logger.warning(f"⚠️ The Odds API not available: {e}")
        
        try:
            from api_football_client import APIFootballClient
            self.api_football = APIFootballClient()
            logger.info("✅ API-Football initialized for odds")
        except Exception as e:
            logger.warning(f"⚠️ API-Football not available: {e}")
        
        if not self.the_odds_api and not self.api_football:
            raise ValueError("❌ No odds API available!")
        
        logger.info("🎯 Unified Odds Service ready (dual-source mode)")
    
    def get_all_odds(self, sport_keys: Optional[List[str]] = None) -> Dict[str, UnifiedOdds]:
        """
        Fetch odds from all available sources and merge
        
        Returns:
            Dict mapping match_key -> UnifiedOdds
        """
        all_odds = {}
        
        if self.the_odds_api:
            try:
                odds_api_data = self._fetch_from_odds_api()
                for match_key, odds in odds_api_data.items():
                    all_odds[match_key] = odds
                logger.info(f"📊 The Odds API: {len(odds_api_data)} matches")
            except Exception as e:
                logger.warning(f"⚠️ The Odds API fetch failed: {e}")
        
        if self.api_football:
            try:
                api_football_data = self._fetch_from_api_football()
                
                for match_key, odds in api_football_data.items():
                    if match_key in all_odds:
                        all_odds[match_key] = self._merge_odds(all_odds[match_key], odds)
                    else:
                        all_odds[match_key] = odds
                
                logger.info(f"📊 API-Football: {len(api_football_data)} matches (merged)")
            except Exception as e:
                logger.warning(f"⚠️ API-Football fetch failed: {e}")
        
        logger.info(f"🎯 Total unified odds: {len(all_odds)} matches")
        return all_odds
    
    def _fetch_from_odds_api(self) -> Dict[str, UnifiedOdds]:
        """Fetch odds from The Odds API"""
        results = {}
        
        if not self.the_odds_api:
            return results
        
        try:
            live_odds = self.the_odds_api.get_soccer_odds(
                regions='uk,us,eu',
                markets='h2h,totals,spreads'
            )
            
            for odds in live_odds:
                match_key = self._create_match_key(odds.home_team, odds.away_team, odds.commence_time)
                
                markets = {}
                if odds.odds_home:
                    markets['HOME_WIN'] = odds.odds_home
                if odds.odds_draw:
                    markets['DRAW'] = odds.odds_draw
                if odds.odds_away:
                    markets['AWAY_WIN'] = odds.odds_away
                if odds.total_over:
                    line_key = f"FT_OVER_{str(odds.total_line).replace('.', '_')}"
                    markets[line_key] = odds.total_over
                if odds.total_under:
                    line_key = f"FT_UNDER_{str(odds.total_line).replace('.', '_')}"
                    markets[line_key] = odds.total_under
                
                if match_key not in results:
                    results[match_key] = UnifiedOdds(
                        fixture_id=match_key,
                        home_team=odds.home_team,
                        away_team=odds.away_team,
                        kickoff_time=odds.commence_time,
                        markets=markets,
                        source='the_odds_api',
                        bookmakers=[odds.bookmaker] if odds.bookmaker else []
                    )
                else:
                    for market, odd in markets.items():
                        if market not in results[match_key].markets or odd > results[match_key].markets[market]:
                            results[match_key].markets[market] = odd
                    if odds.bookmaker and odds.bookmaker not in results[match_key].bookmakers:
                        results[match_key].bookmakers.append(odds.bookmaker)
        
        except Exception as e:
            logger.error(f"❌ Error fetching from The Odds API: {e}")
        
        return results
    
    def _fetch_from_api_football(self) -> Dict[str, UnifiedOdds]:
        """Fetch odds from API-Football using fixtures with odds"""
        results = {}
        
        if not self.api_football:
            return results
        
        try:
            major_league_ids = [39, 140, 135, 78, 61, 88, 94, 144, 40, 41, 42]
            
            fixtures = self.api_football.get_upcoming_fixtures_cached(
                league_ids=major_league_ids,
                days_ahead=2
            )
            
            for fixture in fixtures[:50]:
                fixture_id = fixture.get('id')
                if not fixture_id:
                    continue
                
                try:
                    odds_data = self.api_football.get_fixture_odds(fixture_id)
                    
                    if odds_data and odds_data.get('markets'):
                        match_key = self._create_match_key(
                            fixture.get('home_team', ''),
                            fixture.get('away_team', ''),
                            fixture.get('commence_time', '')
                        )
                        
                        results[match_key] = UnifiedOdds(
                            fixture_id=str(fixture_id),
                            home_team=fixture.get('home_team', ''),
                            away_team=fixture.get('away_team', ''),
                            kickoff_time=fixture.get('commence_time', ''),
                            markets=odds_data['markets'],
                            source='api_football',
                            bookmakers=odds_data.get('bookmakers', [])
                        )
                except Exception as e:
                    logger.debug(f"⚠️ No odds for fixture {fixture_id}: {e}")
        
        except Exception as e:
            logger.error(f"❌ Error fetching from API-Football: {e}")
        
        return results
    
    def _create_match_key(self, home_team: str, away_team: str, kickoff_time: str) -> str:
        """Create unique match key for deduplication"""
        home_norm = home_team.lower().strip().replace(' ', '_')[:20]
        away_norm = away_team.lower().strip().replace(' ', '_')[:20]
        
        date_part = ''
        try:
            if 'T' in kickoff_time:
                date_part = kickoff_time.split('T')[0]
            else:
                date_part = kickoff_time[:10]
        except:
            date_part = datetime.now().strftime('%Y-%m-%d')
        
        return f"{home_norm}_vs_{away_norm}_{date_part}"
    
    def _merge_odds(self, primary: UnifiedOdds, secondary: UnifiedOdds) -> UnifiedOdds:
        """
        Merge odds from two sources, keeping best (highest) odds
        """
        merged_markets = primary.markets.copy()
        
        for market, odds in secondary.markets.items():
            if market not in merged_markets or odds > merged_markets[market]:
                merged_markets[market] = odds
        
        merged_bookmakers = list(set(primary.bookmakers + secondary.bookmakers))
        
        return UnifiedOdds(
            fixture_id=primary.fixture_id,
            home_team=primary.home_team,
            away_team=primary.away_team,
            kickoff_time=primary.kickoff_time,
            markets=merged_markets,
            source=f"{primary.source}+{secondary.source}",
            bookmakers=merged_bookmakers
        )
    
    def get_odds_for_match(self, home_team: str, away_team: str, match_date: Optional[str] = None) -> Optional[Dict]:
        """
        Get odds for a specific match from best available source
        
        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Optional date filter (YYYY-MM-DD)
            
        Returns:
            Dict with market odds or None
        """
        match_key = self._create_match_key(home_team, away_team, match_date or '')
        
        all_odds = self.get_all_odds()
        
        if match_key in all_odds:
            return all_odds[match_key].markets
        
        for key, odds in all_odds.items():
            if (odds.home_team.lower() in home_team.lower() or home_team.lower() in odds.home_team.lower()) and \
               (odds.away_team.lower() in away_team.lower() or away_team.lower() in odds.away_team.lower()):
                return odds.markets
        
        return None
    
    def get_market_coverage(self) -> Dict:
        """
        Get summary of available markets across all sources
        """
        all_odds = self.get_all_odds()
        
        market_counts = {}
        for match_odds in all_odds.values():
            for market in match_odds.markets.keys():
                market_counts[market] = market_counts.get(market, 0) + 1
        
        return {
            'total_matches': len(all_odds),
            'markets': market_counts,
            'sources': {
                'the_odds_api': self.the_odds_api is not None,
                'api_football': self.api_football is not None
            }
        }


def get_unified_odds_service() -> UnifiedOddsService:
    """Factory function to get UnifiedOddsService instance"""
    return UnifiedOddsService()


if __name__ == "__main__":
    print("🎯 Testing Unified Odds Service...")
    
    try:
        service = UnifiedOddsService()
        coverage = service.get_market_coverage()
        
        print(f"\n📊 Market Coverage:")
        print(f"   Total matches: {coverage['total_matches']}")
        print(f"   Active sources: {coverage['sources']}")
        print(f"\n📈 Markets available:")
        for market, count in sorted(coverage['markets'].items(), key=lambda x: -x[1])[:15]:
            print(f"      {market}: {count} matches")
    except Exception as e:
        print(f"❌ Error: {e}")

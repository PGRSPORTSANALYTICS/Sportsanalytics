"""
📊 CLV SERVICE - Closing Line Value Tracking
============================================
Fetches closing odds and calculates CLV for all bets.

CLV% = ((closing_odds - opening_odds) / opening_odds) * 100

A negative CLV means the closing odds shortened (you got better value
than the closing line), which is a strong indicator of long-term betting edge.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from db_helper import db_helper
from real_odds_api import RealOddsAPI
from datetime_utils import now_epoch, get_clv_capture_epoch, from_epoch, epoch_to_stockholm_display

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ODDS_SOURCE_DEFAULT = 'the_odds_api'
CLOSING_WINDOW_BEFORE_KICKOFF_MINUTES = 60  # Look up to 60 min before kickoff
CLOSING_WINDOW_AFTER_KICKOFF_MINUTES = 5    # Allow 5 min after kickoff for late capture
CLV_CAPTURE_MINUTES_BEFORE = 60              # Target bets starting within 60 min

class CLVService:
    """Service for tracking Closing Line Value"""
    
    def __init__(self):
        try:
            self.odds_api = RealOddsAPI()
            logger.info("✅ CLVService initialized with RealOddsAPI")
        except Exception as e:
            logger.warning(f"⚠️ CLVService: RealOddsAPI init failed: {e}")
            self.odds_api = None
    
    def get_candidates_for_closing_odds(self) -> List[Dict[str, Any]]:
        """
        Get bets that are candidates for closing odds collection.
        
        Candidates are bets where:
        - close_odds IS NULL
        - kickoff_epoch is within 60 min from now (before kickoff)
        - or up to 5 min after kickoff (late capture)
        - Football only (for now)
        
        Uses kickoff_epoch (seconds since Unix epoch) for precise timing.
        CLV capture window: 60 min before kickoff to 5 min after kickoff
        
        Returns:
            List of bet dicts with id, match_id, home_team, away_team, market, 
            selection, open_odds, kickoff_epoch
        """
        current_epoch = now_epoch()
        
        candidates = []
        
        try:
            window_start = current_epoch - (CLOSING_WINDOW_AFTER_KICKOFF_MINUTES * 60)
            window_end = current_epoch + (CLV_CAPTURE_MINUTES_BEFORE * 60)
            
            rows = db_helper.execute("""
                SELECT id, match_id, home_team, away_team, market, selection, 
                       open_odds, kickoff_time, match_date, league, kickoff_epoch, kickoff_utc
                FROM football_opportunities
                WHERE close_odds IS NULL
                  AND open_odds IS NOT NULL
                  AND status = 'pending'
                  AND kickoff_epoch IS NOT NULL
                  AND kickoff_epoch >= %s
                  AND kickoff_epoch <= %s
                ORDER BY kickoff_epoch ASC
            """, (window_start, window_end), fetch='all') or []
            
            for row in rows:
                row_dict = dict(row) if hasattr(row, '_mapping') else {
                    'id': row[0], 'match_id': row[1], 'home_team': row[2], 'away_team': row[3],
                    'market': row[4], 'selection': row[5], 'open_odds': row[6], 'kickoff_time': row[7],
                    'match_date': row[8], 'league': row[9], 'kickoff_epoch': row[10] if len(row) > 10 else None,
                    'kickoff_utc': row[11] if len(row) > 11 else None
                }
                
                kickoff_epoch = row_dict.get('kickoff_epoch')
                if kickoff_epoch is None:
                    continue
                
                seconds_to_kickoff = kickoff_epoch - current_epoch
                
                candidates.append({
                    'id': row_dict['id'],
                    'match_id': row_dict['match_id'],
                    'home_team': row_dict['home_team'],
                    'away_team': row_dict['away_team'],
                    'market': row_dict['market'],
                    'selection': row_dict['selection'],
                    'open_odds': row_dict['open_odds'],
                    'kickoff_time': row_dict['kickoff_time'],
                    'kickoff_epoch': kickoff_epoch,
                    'kickoff_utc': row_dict.get('kickoff_utc'),
                    'match_date': row_dict['match_date'],
                    'league': row_dict['league'],
                    'seconds_to_kickoff': seconds_to_kickoff
                })
            
            if candidates:
                logger.info(f"📊 CLV: Found {len(candidates)} candidates for closing odds capture")
                for c in candidates[:3]:
                    mins = c['seconds_to_kickoff'] // 60
                    logger.info(f"   • {c['home_team']} vs {c['away_team']} | kickoff in {mins} min")
            
            return candidates
            
        except Exception as e:
            logger.error(f"❌ CLV: Error fetching candidates: {e}")
            return []
    
    def _parse_kickoff_time(self, kickoff_time: Optional[str], match_date: Optional[str]) -> Optional[datetime]:
        """Parse kickoff time into datetime object"""
        if not kickoff_time and not match_date:
            return None
        
        formats = [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S+00:00',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
        ]
        
        time_str = kickoff_time or match_date
        if not time_str:
            return None
            
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        
        if match_date and len(match_date) == 10:
            try:
                dt = datetime.strptime(match_date, '%Y-%m-%d')
                dt = dt.replace(hour=15, minute=0, tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
        
        return None
    
    def fetch_closing_odds_for_bet(self, bet: Dict[str, Any]) -> Optional[float]:
        """
        Fetch closing odds for a specific bet.
        
        Uses The Odds API to get current market odds for the fixture/market.
        Prefers sharp bookmakers (Pinnacle, Betfair) when available.
        
        Args:
            bet: Dict with match_id, market, selection, home_team, away_team
            
        Returns:
            Closing odds as float, or None if unavailable
        """
        if not self.odds_api:
            return None
        
        try:
            match_id = bet.get('match_id')
            market = bet.get('market', '').lower()
            selection = bet.get('selection', '')
            home_team = bet.get('home_team', '')
            away_team = bet.get('away_team', '')
            open_odds = bet.get('open_odds', 0)

            if not self._is_supported_market(market):
                logger.debug(f"📊 CLV: Skipping unsupported market '{market}' for {home_team} vs {away_team}")
                return None

            sport_key = self._get_sport_key_for_league(bet.get('league', ''))
            if not sport_key:
                logger.debug(f"📊 CLV: No sport key for league '{bet.get('league', '')}', skipping")
                return None
            
            market_type = self._map_market_to_odds_api(market)
            if not market_type:
                return None
            
            odds_data = self.odds_api.get_live_odds(
                sport_key, 
                regions=['eu', 'uk'],
                markets=[market_type]
            )
            
            if not odds_data:
                return None
            
            for event in odds_data:
                if self._match_event(event, home_team, away_team):
                    closing_odds = self._extract_odds_for_selection(
                        event, market, selection, home_team, away_team
                    )
                    if closing_odds:
                        if open_odds and open_odds > 1.0:
                            drift = abs(closing_odds - open_odds) / open_odds
                            if drift > 0.50:
                                logger.warning(f"⚠️ CLV: Rejecting closing odds {closing_odds:.2f} for {home_team} vs {away_team} "
                                             f"(open={open_odds:.2f}, drift={drift*100:.0f}% > 50% threshold)")
                                return None
                        logger.info(f"📊 CLV: Found closing odds {closing_odds:.2f} for {home_team} vs {away_team} (open={open_odds:.2f})")
                        return closing_odds
            
            return None
            
        except Exception as e:
            logger.error(f"❌ CLV: Error fetching closing odds: {e}")
            return None
    
    def _get_sport_key_for_league(self, league: str) -> Optional[str]:
        """Map league name to Odds API sport key"""
        league_mapping = {
            'Premier League': 'soccer_epl',
            'La Liga': 'soccer_spain_la_liga',
            'Serie A': 'soccer_italy_serie_a',
            'Bundesliga': 'soccer_germany_bundesliga',
            'Ligue 1': 'soccer_france_ligue_one',
            'Champions League': 'soccer_uefa_champs_league',
            'Europa League': 'soccer_uefa_europa_league',
            'Eredivisie': 'soccer_netherlands_eredivisie',
            'Portuguese Primeira': 'soccer_portugal_primeira_liga',
            'Primeira Liga': 'soccer_portugal_primeira_liga',
            'Belgian First Division': 'soccer_belgium_first_div',
            'English Championship': 'soccer_efl_champ',
            'English League One': 'soccer_england_league1',
            'English League Two': 'soccer_england_league2',
            'Scottish Premiership': 'soccer_spl',
            'Turkish Super Lig': 'soccer_turkey_super_league',
            'Swiss Super League': 'soccer_switzerland_superleague',
            'Danish Superliga': 'soccer_denmark_superliga',
            'Norwegian Eliteserien': 'soccer_norway_eliteserien',
            'Swedish Allsvenskan': 'soccer_sweden_allsvenskan',
            'Greek Super League': 'soccer_greece_super_league',
            'Austrian Bundesliga': 'soccer_austria_bundesliga',
            'MLS': 'soccer_usa_mls',
            'Conference League': 'soccer_uefa_europa_conference_league',
            'Liga MX': 'soccer_mexico_ligamx',
            'Brazilian Serie A': 'soccer_brazil_serie_a',
            'Argentine Primera': 'soccer_argentina_primera_division',
            'J1 League': 'soccer_japan_j_league',
            'K League 1': 'soccer_korea_kleague1',
            'A-League': 'soccer_australia_aleague',
            'Superliga': 'soccer_denmark_superliga',
            'FA Cup': 'soccer_fa_cup',
            'Copa del Rey': 'soccer_spain_copa_del_rey',
            'DFB Pokal': 'soccer_germany_dfb_pokal',
            'Coppa Italia': 'soccer_italy_coppa_italia',
        }
        league_lower = league.lower()
        direct = league_mapping.get(league)
        if direct:
            return direct
        for key, value in league_mapping.items():
            if key.lower() in league_lower or league_lower in key.lower():
                return value
        return None
    
    UNSUPPORTED_MARKETS = {'corners', 'cards', 'shots', 'fouls', 'offsides', 'throw-ins',
                           'player props', 'player_props', 'props'}

    def _is_supported_market(self, market: str) -> bool:
        """Check if market is supported by The Odds API for CLV tracking"""
        market_lower = market.lower()
        for unsupported in self.UNSUPPORTED_MARKETS:
            if unsupported in market_lower:
                return False
        return True

    def _map_market_to_odds_api(self, market: str) -> Optional[str]:
        """Map internal market names to Odds API market types. Returns None for unsupported."""
        market_lower = market.lower()

        if not self._is_supported_market(market_lower):
            return None

        if 'over' in market_lower or 'under' in market_lower:
            return 'totals'
        elif 'btts' in market_lower or 'both teams' in market_lower:
            return 'btts'
        elif any(k in market_lower for k in ['1x2', 'home win', 'away win', 'draw',
                                              'double chance', 'value single', 'moneyline']):
            return 'h2h'
        elif 'asian' in market_lower or 'handicap' in market_lower:
            return 'spreads'
        else:
            return 'h2h'
    
    def _match_event(self, event: Dict, home_team: str, away_team: str) -> bool:
        """Check if Odds API event matches our bet's teams"""
        event_home = event.get('home_team', '').lower()
        event_away = event.get('away_team', '').lower()
        
        home_lower = home_team.lower()
        away_lower = away_team.lower()
        
        if event_home == home_lower and event_away == away_lower:
            return True
        
        home_words = set(home_lower.split())
        away_words = set(away_lower.split())
        event_home_words = set(event_home.split())
        event_away_words = set(event_away.split())
        
        home_match = len(home_words & event_home_words) >= 1
        away_match = len(away_words & event_away_words) >= 1
        
        return home_match and away_match
    
    def _extract_odds_for_selection(
        self, 
        event: Dict, 
        market: str, 
        selection: str,
        home_team: str,
        away_team: str
    ) -> Optional[float]:
        """Extract odds for specific selection from event data"""
        bookmakers = event.get('bookmakers', [])
        
        sharp_books = ['pinnacle', 'betfair', 'betfair_ex_eu']
        
        sorted_books = sorted(
            bookmakers,
            key=lambda b: 0 if b.get('key', '').lower() in sharp_books else 1
        )
        
        selection_lower = selection.lower()
        market_lower = market.lower()
        
        for bookmaker in sorted_books:
            markets = bookmaker.get('markets', [])
            
            for mkt in markets:
                outcomes = mkt.get('outcomes', [])
                
                for outcome in outcomes:
                    outcome_name = outcome.get('name', '').lower()
                    outcome_price = outcome.get('price')
                    
                    if self._selection_matches_outcome(selection_lower, outcome_name, home_team, away_team, market_lower):
                        if outcome_price:
                            return float(outcome_price)
        
        return None
    
    def _selection_matches_outcome(
        self, 
        selection: str, 
        outcome: str, 
        home_team: str, 
        away_team: str,
        market: str
    ) -> bool:
        """Check if our selection matches the outcome from Odds API"""
        selection_lower = selection.lower()
        outcome_lower = outcome.lower()
        home_lower = home_team.lower()
        away_lower = away_team.lower()
        
        if selection_lower == outcome_lower:
            return True
        
        if 'home' in selection_lower or home_lower in selection_lower:
            if home_lower in outcome_lower or outcome_lower == home_lower:
                return True
        
        if 'away' in selection_lower or away_lower in selection_lower:
            if away_lower in outcome_lower or outcome_lower == away_lower:
                return True
        
        if 'draw' in selection_lower and 'draw' in outcome_lower:
            return True
        
        if 'over' in selection_lower and 'over' in outcome_lower:
            sel_line = self._extract_line(selection_lower)
            out_line = self._extract_line(outcome_lower)
            if sel_line and out_line and abs(sel_line - out_line) < 0.01:
                return True
        
        if 'under' in selection_lower and 'under' in outcome_lower:
            sel_line = self._extract_line(selection_lower)
            out_line = self._extract_line(outcome_lower)
            if sel_line and out_line and abs(sel_line - out_line) < 0.01:
                return True
        
        if 'btts' in selection_lower or 'both teams' in selection_lower:
            if 'yes' in selection_lower and 'yes' in outcome_lower:
                return True
            if 'no' in selection_lower and 'no' in outcome_lower:
                return True
        
        return False
    
    def _extract_line(self, text: str) -> Optional[float]:
        """Extract numeric line from selection text like 'Over 2.5'"""
        import re
        match = re.search(r'(\d+\.?\d*)', text)
        if match:
            return float(match.group(1))
        return None
    
    def update_clv_for_bet(self, bet_id: int, closing_odds: float) -> bool:
        """
        Calculate and update CLV for a bet.
        
        CLV% = ((closing_odds - opening_odds) / opening_odds) * 100
        Positive CLV = closing odds shortened (you got better value)
        
        Args:
            bet_id: Database ID of the bet
            closing_odds: The closing line odds
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            row = db_helper.execute(
                "SELECT open_odds FROM football_opportunities WHERE id = %s",
                (bet_id,),
                fetch='one'
            )
            
            if not row or not row[0]:
                logger.warning(f"⚠️ CLV: No open_odds found for bet {bet_id}")
                return False
            
            open_odds = float(row[0])
            
            if closing_odds <= 1.0:
                logger.warning(f"⚠️ CLV: Invalid closing odds {closing_odds} for bet {bet_id}")
                return False
            
            clv_pct = ((closing_odds - open_odds) / open_odds) * 100.0
            
            db_helper.execute("""
                UPDATE football_opportunities 
                SET close_odds = %s, clv_pct = %s
                WHERE id = %s
            """, (closing_odds, clv_pct, bet_id))
            
            logger.info(f"✅ CLV: Updated bet {bet_id}: open={open_odds:.2f}, close={closing_odds:.2f}, CLV={clv_pct:+.2f}%")
            return True
            
        except Exception as e:
            logger.error(f"❌ CLV: Error updating bet {bet_id}: {e}")
            return False
    
    def run_clv_update_cycle(self) -> Dict[str, Any]:
        """
        Main CLV update cycle.
        
        1. Fetch candidate bets (close to kickoff)
        2. Try to fetch closing odds for each
        3. Update CLV where possible
        
        Returns:
            Dict with cycle statistics
        """
        logger.info("=" * 60)
        logger.info("📊 CLV UPDATE CYCLE STARTING")
        logger.info("=" * 60)
        
        stats = {
            'candidates': 0,
            'updated': 0,
            'failed': 0,
            'clv_values': [],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        candidates = self.get_candidates_for_closing_odds()
        stats['candidates'] = len(candidates)
        
        if not candidates:
            logger.info("📊 CLV: No candidates for closing odds update")
            return stats
        
        for bet in candidates:
            bet_id = bet['id']
            
            closing_odds = self.fetch_closing_odds_for_bet(bet)
            
            if closing_odds:
                if self.update_clv_for_bet(bet_id, closing_odds):
                    stats['updated'] += 1
                    open_odds = bet.get('open_odds', 0)
                    if open_odds and closing_odds > 1.0:
                        clv = ((closing_odds - open_odds) / open_odds) * 100.0
                        stats['clv_values'].append(clv)
                else:
                    stats['failed'] += 1
            else:
                stats['failed'] += 1
                logger.debug(f"📊 CLV: Could not fetch closing odds for bet {bet_id}")
        
        if stats['clv_values']:
            avg_clv = sum(stats['clv_values']) / len(stats['clv_values'])
            stats['avg_clv'] = avg_clv
            logger.info(f"📊 CLV CYCLE COMPLETE: {stats['updated']} updated, avg CLV: {avg_clv:+.2f}%")
        else:
            stats['avg_clv'] = None
            logger.info(f"📊 CLV CYCLE COMPLETE: {stats['updated']} updated, {stats['failed']} failed")
        
        logger.info("=" * 60)
        return stats


def get_clv_stats() -> Dict[str, Any]:
    """
    Get aggregated CLV statistics for dashboard/API.
    
    Returns:
        Dict with avg_clv_all, avg_clv_last_100, positive_share
    """
    stats = {
        'avg_clv_all': None,
        'avg_clv_last_100': None,
        'positive_share': None,
        'total_with_clv': 0
    }
    
    try:
        row = db_helper.execute("""
            SELECT 
                AVG(clv_pct) as avg_clv_all,
                COUNT(*) as total_with_clv,
                SUM(CASE WHEN clv_pct > 0 THEN 1 ELSE 0 END) as positive_count
            FROM football_opportunities
            WHERE clv_pct IS NOT NULL
              AND clv_pct BETWEEN -50 AND 50
        """, fetch='one')
        
        if row:
            stats['avg_clv_all'] = round(row[0], 2) if row[0] else None
            stats['total_with_clv'] = row[1] or 0
            if row[1] and row[1] > 0:
                stats['positive_share'] = round((row[2] or 0) / row[1] * 100, 1)
        
        row_100 = db_helper.execute("""
            SELECT AVG(clv_pct)
            FROM (
                SELECT clv_pct 
                FROM football_opportunities
                WHERE clv_pct IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 100
            ) as recent
        """, fetch='one')
        
        if row_100 and row_100[0]:
            stats['avg_clv_last_100'] = round(row_100[0], 2)
        
    except Exception as e:
        logger.error(f"❌ Error fetching CLV stats: {e}")
    
    return stats


def run_clv_update_cycle() -> Dict[str, Any]:
    """Convenience function to run CLV update cycle"""
    service = CLVService()
    return service.run_clv_update_cycle()


if __name__ == "__main__":
    print("🧪 Testing CLV Service...")
    
    clv_service = CLVService()
    candidates = clv_service.get_candidates_for_closing_odds()
    print(f"Found {len(candidates)} candidates")
    
    for c in candidates[:3]:
        print(f"  - {c['home_team']} vs {c['away_team']} | {c['market']} | {c['time_to_kickoff_min']:.1f}min to kickoff")
    
    stats = get_clv_stats()
    print(f"\nCLV Stats: {stats}")
    
    print(f"\nTest CLV calculation: open=2.00, close=1.80 => CLV = {((2.0-1.8)/1.8)*100:.2f}%")

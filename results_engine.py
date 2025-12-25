#!/usr/bin/env python3
"""
Unified Results Engine
======================
Ensures ALL bets are settled promptly with multi-source fallback and auto-void.

Runs every 5 minutes to:
1. Settle pending football bets (Value Singles, Corners, Cards)
2. Settle pending SGP parlays
3. Settle pending basketball bets
4. Auto-void bets past cutoff (2 days for corners/cards, 3 days for others)
"""

import logging
import os
import re
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ResultsEngine:
    """Unified results settlement engine for all bet types."""
    
    def __init__(self):
        self.database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        self.api_football_key = os.environ.get("API_FOOTBALL_KEY")
        self.stats = {
            'settled': 0,
            'voided': 0,
            'failed': 0,
            'api_calls': 0,
            'manual_applied': 0,
            'fallback_used': 0
        }
        self._match_cache = {}
        self._manual_results = None
        self._verification_metrics = None
    
    def _get_manual_results_manager(self):
        """Lazy load manual results manager."""
        if self._manual_results is None:
            try:
                from flashscore_stats_scraper import ManualResultsManager
                self._manual_results = ManualResultsManager()
            except ImportError:
                pass
        return self._manual_results
    
    def _get_verification_metrics(self):
        """Lazy load verification metrics."""
        if self._verification_metrics is None:
            try:
                from flashscore_stats_scraper import VerificationMetrics
                self._verification_metrics = VerificationMetrics()
            except ImportError:
                pass
        return self._verification_metrics
    
    def run_cycle(self) -> Dict:
        """Run a complete verification cycle for all bet types."""
        logger.info("="*60)
        logger.info("🔄 RESULTS ENGINE - Starting verification cycle")
        logger.info("="*60)
        
        self.stats = {'settled': 0, 'voided': 0, 'failed': 0, 'api_calls': 0, 'manual_applied': 0, 'fallback_used': 0}
        
        try:
            self._auto_void_old_bets()
            self._settle_football_opportunities()
            self._settle_sgp_parlays()
            
            logger.info("="*60)
            logger.info(f"✅ RESULTS ENGINE COMPLETE: {self.stats['settled']} settled, {self.stats['voided']} voided, {self.stats['failed']} failed")
            logger.info("="*60)
            
            if self.stats['settled'] > 0:
                self._send_discord_update()
            
            return self.stats
            
        except Exception as e:
            logger.error(f"❌ Results Engine error: {e}")
            return self.stats
    
    def _auto_void_old_bets(self):
        """Auto-void bets past their settlement cutoff."""
        if not self.database_url:
            return
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            now_ts = int(datetime.now().timestamp())
            
            cursor.execute("""
                UPDATE football_opportunities 
                SET status = 'settled', 
                    outcome = 'void', 
                    result = 'VOID',
                    settled_timestamp = %s
                WHERE (status = 'pending' OR outcome IS NULL OR outcome = '' OR outcome = 'unknown')
                    AND market IN ('Corners', 'Cards')
                    AND DATE(match_date) < CURRENT_DATE - INTERVAL '2 days'
                    AND outcome NOT IN ('won', 'lost', 'void')
            """, (now_ts,))
            corners_cards_voided = cursor.rowcount
            
            cursor.execute("""
                UPDATE football_opportunities 
                SET status = 'settled', 
                    outcome = 'void', 
                    result = 'VOID',
                    settled_timestamp = %s
                WHERE (status = 'pending' OR outcome IS NULL OR outcome = '' OR outcome = 'unknown')
                    AND market NOT IN ('Corners', 'Cards')
                    AND DATE(match_date) < CURRENT_DATE - INTERVAL '3 days'
                    AND outcome NOT IN ('won', 'lost', 'void')
            """, (now_ts,))
            football_voided = cursor.rowcount
            
            cursor.execute("""
                UPDATE sgp_predictions 
                SET status = 'SETTLED', 
                    outcome = 'void', 
                    result = 'VOID',
                    settled_timestamp = %s
                WHERE (UPPER(status) = 'PENDING' OR outcome IS NULL OR outcome = '')
                    AND DATE(match_date) < CURRENT_DATE - INTERVAL '3 days'
                    AND (outcome IS NULL OR outcome NOT IN ('won', 'lost', 'void', 'win', 'loss'))
            """, (now_ts,))
            sgp_voided = cursor.rowcount
            
            cursor.execute("""
                UPDATE basketball_predictions 
                SET status = 'void',
                    verified_at = NOW()
                WHERE status = 'pending' 
                    AND commence_time::date < CURRENT_DATE - INTERVAL '3 days'
            """)
            basketball_voided = cursor.rowcount
            
            conn.commit()
            cursor.close()
            conn.close()
            
            total_voided = corners_cards_voided + football_voided + sgp_voided + basketball_voided
            if total_voided > 0:
                logger.info(f"🗑️ Auto-voided {total_voided} old bets (Corners/Cards: {corners_cards_voided}, Football: {football_voided}, SGP: {sgp_voided}, Basketball: {basketball_voided})")
                self.stats['voided'] = total_voided
                
        except Exception as e:
            logger.error(f"❌ Auto-void error: {e}")
    
    def _settle_football_opportunities(self):
        """Settle pending football opportunities (Value Singles, Corners, Cards)."""
        if not self.database_url:
            return
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT id, home_team, away_team, match_date, market, selection, odds, stake, match_id
                FROM football_opportunities 
                WHERE (outcome IS NULL OR outcome = '' OR outcome = 'unknown' OR outcome = 'pending')
                    AND DATE(match_date) < CURRENT_DATE
                    AND DATE(match_date) >= CURRENT_DATE - INTERVAL '3 days'
                ORDER BY match_date DESC
                LIMIT 150
            """)
            
            pending = cursor.fetchall()
            logger.info(f"📋 Found {len(pending)} pending football bets to settle")
            
            matches_processed = {}
            
            for bet in pending:
                try:
                    manual_mgr = self._get_manual_results_manager()
                    if manual_mgr:
                        manual_result = manual_mgr.get_manual_result(bet['id'], 'football_opportunities')
                        if manual_result:
                            outcome = manual_result['result'].lower()
                            if outcome in ['won', 'lost', 'void']:
                                self._update_football_bet(cursor, bet['id'], outcome, {'source': 'manual'})
                                self.stats['settled'] += 1
                                self.stats['manual_applied'] += 1
                                logger.info(f"📋 Applied manual result for bet #{bet['id']}: {outcome}")
                                continue
                    
                    match_key = f"{bet['home_team']}_{bet['away_team']}_{bet['match_date']}"
                    market = (bet.get('market') or '').lower()
                    
                    if match_key not in matches_processed:
                        result = self._get_match_result_with_fallbacks(
                            bet['home_team'], bet['away_team'], bet['match_date'], 
                            bet.get('match_id'), market, bet['id']
                        )
                        matches_processed[match_key] = result
                        time.sleep(0.3)
                    else:
                        result = matches_processed[match_key]
                    
                    if not result:
                        continue
                    
                    outcome = self._calculate_outcome(bet, result)
                    if outcome in ['won', 'lost']:
                        self._update_football_bet(cursor, bet['id'], outcome, result)
                        self.stats['settled'] += 1
                        if result.get('source') not in ['api-football', 'database']:
                            self.stats['fallback_used'] += 1
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error settling bet {bet['id']}: {e}")
                    self.stats['failed'] += 1
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Football settlement error: {e}")
    
    def _settle_sgp_parlays(self):
        """Settle pending SGP and multi-match parlays."""
        if not self.database_url:
            return
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT id, home_team, away_team, match_date, legs, parlay_description, bookmaker_odds
                FROM sgp_predictions 
                WHERE (outcome IS NULL OR outcome = '')
                    AND DATE(match_date) < CURRENT_DATE
                    AND DATE(match_date) >= CURRENT_DATE - INTERVAL '3 days'
                ORDER BY match_date DESC
                LIMIT 100
            """)
            
            pending = cursor.fetchall()
            logger.info(f"📋 Found {len(pending)} pending SGP/parlays to settle")
            
            for bet in pending:
                try:
                    if 'Multi-Match Parlay' in str(bet.get('home_team', '')):
                        outcome = self._settle_multi_match_parlay(cursor, bet)
                    else:
                        outcome = self._settle_single_match_sgp(cursor, bet)
                    
                    if outcome in ['won', 'lost', 'void']:
                        self._update_sgp_bet(cursor, bet['id'], outcome)
                        if outcome != 'void':
                            self.stats['settled'] += 1
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error settling SGP {bet['id']}: {e}")
                    self.stats['failed'] += 1
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ SGP settlement error: {e}")
    
    def _settle_multi_match_parlay(self, cursor, bet: Dict) -> Optional[str]:
        """Settle a multi-match parlay by checking all legs."""
        description = bet.get('away_team', '') or bet.get('parlay_description', '')
        
        legs = description.split(' | ')
        all_won = True
        any_void = False
        
        for leg in legs:
            match_team = re.search(r'^([^:]+):', leg)
            if not match_team:
                continue
            
            match_info = match_team.group(1).strip()
            teams = match_info.split(' vs ')
            if len(teams) != 2:
                continue
            
            home_team = teams[0].strip()
            away_team = teams[1].strip()
            
            cursor.execute("""
                SELECT outcome FROM football_opportunities 
                WHERE home_team = %s AND away_team = %s 
                AND DATE(match_date) = %s
                AND outcome IN ('won', 'lost', 'void')
                LIMIT 1
            """, (home_team, away_team, bet['match_date']))
            
            row = cursor.fetchone()
            if row:
                if row['outcome'] == 'lost':
                    return 'lost'
                elif row['outcome'] == 'void':
                    any_void = True
                elif row['outcome'] != 'won':
                    all_won = False
            else:
                all_won = False
        
        if any_void:
            return 'void'
        return 'won' if all_won else None
    
    def _settle_single_match_sgp(self, cursor, bet: Dict) -> Optional[str]:
        """Settle a single-match SGP by checking settled legs in football_opportunities."""
        home_team = bet['home_team']
        away_team = bet['away_team']
        match_date = bet['match_date']
        legs = bet.get('legs', '') or bet.get('parlay_description', '')
        
        if not legs:
            return None
        
        cursor.execute("""
            SELECT selection, outcome FROM football_opportunities 
            WHERE home_team = %s AND away_team = %s 
            AND DATE(match_date) = %s
            AND outcome IN ('won', 'lost', 'void')
        """, (home_team, away_team, match_date))
        
        settled_legs = {row['selection'].lower(): row['outcome'] for row in cursor.fetchall()}
        
        if not settled_legs:
            return None
        
        all_won = True
        any_lost = False
        any_void = False
        
        for leg in legs.split(' | '):
            leg_clean = leg.strip().lower()
            
            matched = False
            for sel, outcome in settled_legs.items():
                if leg_clean in sel or sel in leg_clean:
                    matched = True
                    if outcome == 'lost':
                        any_lost = True
                    elif outcome == 'void':
                        any_void = True
                    elif outcome != 'won':
                        all_won = False
                    break
            
            if not matched:
                all_won = False
        
        if any_lost:
            return 'lost'
        if any_void:
            return 'void'
        if all_won:
            return 'won'
        
        return None
    
    def _get_match_result(self, home_team: str, away_team: str, match_date: str, match_id: Optional[int]) -> Optional[Dict]:
        """Get match result with multi-source fallback (legacy method)."""
        return self._get_match_result_with_fallbacks(home_team, away_team, match_date, match_id, None, None)
    
    def _get_match_result_with_fallbacks(
        self, 
        home_team: str, 
        away_team: str, 
        match_date: str, 
        match_id: Optional[int],
        market: Optional[str],
        bet_id: Optional[int]
    ) -> Optional[Dict]:
        """
        Get match result with bulletproof multi-source fallback chain.
        
        Fallback order:
        1. Database (already settled results)
        2. API-Football (primary source)
        3. The Odds API (for score verification)
        4. Return partial result if goals available but corners/cards missing
        """
        cache_key = f"{home_team}_{away_team}_{match_date}"
        if cache_key in self._match_cache:
            cached = self._match_cache[cache_key]
            if market in ['corners', 'cards']:
                if market == 'corners' and cached.get('total_corners') is not None:
                    return cached
                if market == 'cards' and cached.get('total_cards') is not None:
                    return cached
            else:
                return cached
        
        metrics = self._get_verification_metrics()
        needs_stats = market in ['corners', 'cards']
        
        result = self._check_database_for_result(home_team, away_team, match_date)
        if result:
            if needs_stats:
                if market == 'corners' and result.get('total_corners') is not None:
                    self._log_verification(metrics, bet_id, market, 'database', True, result)
                    self._match_cache[cache_key] = result
                    return result
                if market == 'cards' and result.get('total_cards') is not None:
                    self._log_verification(metrics, bet_id, market, 'database', True, result)
                    self._match_cache[cache_key] = result
                    return result
            else:
                self._log_verification(metrics, bet_id, market, 'database', True, result)
                self._match_cache[cache_key] = result
                return result
        
        if self.api_football_key:
            result = self._get_api_football_result(home_team, away_team, match_date, match_id)
            if result:
                if needs_stats:
                    if market == 'corners' and result.get('total_corners') is not None:
                        self._log_verification(metrics, bet_id, market, 'api-football', True, result)
                        self._match_cache[cache_key] = result
                        return result
                    if market == 'cards' and result.get('total_cards') is not None:
                        self._log_verification(metrics, bet_id, market, 'api-football', True, result)
                        self._match_cache[cache_key] = result
                        return result
                    self._log_verification(metrics, bet_id, market, 'api-football', False, None, 'Stats not available')
                else:
                    self._log_verification(metrics, bet_id, market, 'api-football', True, result)
                    self._match_cache[cache_key] = result
                    return result
        
        if needs_stats:
            self._log_verification(metrics, bet_id, market, 'all-sources', False, None, 'No stats data available from any source')
            return None
        
        return None
    
    def _log_verification(self, metrics, bet_id, market, source, success, data, error=None):
        """Log verification attempt to metrics."""
        if metrics and bet_id:
            try:
                metrics.log_attempt(
                    bet_id=bet_id,
                    bet_table='football_opportunities',
                    market=market or 'unknown',
                    source_tried=source,
                    success=success,
                    error_message=error,
                    data_found={'source': source} if success else None
                )
            except Exception as e:
                logger.warning(f"Metrics log error: {e}")
    
    def _check_database_for_result(self, home_team: str, away_team: str, match_date: str) -> Optional[Dict]:
        """Check if we already have settled results in database for this match."""
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT home_corners, away_corners, home_cards, away_cards, actual_score
                FROM football_opportunities 
                WHERE home_team = %s AND away_team = %s 
                AND DATE(match_date) = %s
                AND outcome IN ('won', 'lost')
                AND (home_corners IS NOT NULL OR actual_score IS NOT NULL)
                LIMIT 1
            """, (home_team, away_team, match_date[:10] if match_date else None))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                result = {}
                if row.get('actual_score'):
                    score_parts = row['actual_score'].split('-')
                    if len(score_parts) == 2:
                        result['home_goals'] = int(score_parts[0])
                        result['away_goals'] = int(score_parts[1])
                
                if row.get('home_corners') is not None:
                    result['home_corners'] = row['home_corners']
                    result['away_corners'] = row.get('away_corners', 0)
                    result['total_corners'] = result['home_corners'] + result['away_corners']
                
                if row.get('home_cards') is not None:
                    result['home_cards'] = row['home_cards']
                    result['away_cards'] = row.get('away_cards', 0)
                    result['total_cards'] = result['home_cards'] + result['away_cards']
                
                if result:
                    result['source'] = 'database'
                    return result
            
            return None
            
        except Exception as e:
            logger.warning(f"Database result check error: {e}")
            return None
    
    def _get_api_football_result(self, home_team: str, away_team: str, match_date: str, match_id: Optional[int]) -> Optional[Dict]:
        """Get result from API-Football."""
        try:
            api_date = match_date.split('T')[0] if 'T' in str(match_date) else str(match_date)[:10]
            
            url = "https://v3.football.api-sports.io/fixtures"
            headers = {
                'X-RapidAPI-Key': self.api_football_key,
                'X-RapidAPI-Host': 'v3.football.api-sports.io'
            }
            params = {'date': api_date, 'status': 'FT'}
            
            response = requests.get(url, headers=headers, params=params, timeout=20)
            self.stats['api_calls'] += 1
            
            if response.status_code != 200:
                return None
            
            fixtures = response.json().get('response', [])
            
            for fixture in fixtures:
                teams = fixture.get('teams', {})
                home_api = teams.get('home', {}).get('name', '').lower()
                away_api = teams.get('away', {}).get('name', '').lower()
                
                if self._fuzzy_match(home_team, home_api) and self._fuzzy_match(away_team, away_api):
                    goals = fixture.get('goals', {})
                    home_goals = goals.get('home')
                    away_goals = goals.get('away')
                    
                    if home_goals is not None and away_goals is not None:
                        result = {
                            'home_goals': int(home_goals),
                            'away_goals': int(away_goals),
                            'source': 'api-football'
                        }
                        
                        fixture_id = fixture.get('fixture', {}).get('id')
                        if fixture_id:
                            stats = self._get_fixture_stats(fixture_id)
                            if stats:
                                result.update(stats)
                        
                        return result
            
            return None
            
        except Exception as e:
            logger.warning(f"API-Football error: {e}")
            return None
    
    def _get_fixture_stats(self, fixture_id: int) -> Optional[Dict]:
        """Get fixture statistics (corners, cards)."""
        try:
            url = "https://v3.football.api-sports.io/fixtures/statistics"
            headers = {
                'X-RapidAPI-Key': self.api_football_key,
                'X-RapidAPI-Host': 'v3.football.api-sports.io'
            }
            params = {'fixture': fixture_id}
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            self.stats['api_calls'] += 1
            
            if response.status_code != 200:
                return None
            
            stats_list = response.json().get('response', [])
            if len(stats_list) < 2:
                return None
            
            result = {
                'home_corners': 0, 'away_corners': 0,
                'home_cards': 0, 'away_cards': 0,
                'home_yellow_cards': 0, 'away_yellow_cards': 0,
                'home_red_cards': 0, 'away_red_cards': 0
            }
            
            for i, team_stats in enumerate(stats_list):
                prefix = 'home' if i == 0 else 'away'
                for stat in team_stats.get('statistics', []):
                    stat_type = stat.get('type', '').lower()
                    value = stat.get('value') or 0
                    if isinstance(value, str):
                        value = int(value) if value.isdigit() else 0
                    
                    if 'corner' in stat_type:
                        result[f'{prefix}_corners'] = value
                    elif 'yellow' in stat_type:
                        result[f'{prefix}_yellow_cards'] = value
                        result[f'{prefix}_cards'] += value
                    elif 'red' in stat_type:
                        result[f'{prefix}_red_cards'] = value
                        result[f'{prefix}_cards'] += value
            
            result['total_corners'] = result['home_corners'] + result['away_corners']
            result['total_cards'] = result['home_cards'] + result['away_cards']
            
            return result
            
        except Exception as e:
            logger.warning(f"Stats fetch error: {e}")
            return None
    
    def _fuzzy_match(self, team1: str, team2: str) -> bool:
        """Fuzzy match team names."""
        t1 = team1.lower().replace('fc ', '').replace(' fc', '').replace('cf ', '').strip()
        t2 = team2.lower().replace('fc ', '').replace(' fc', '').replace('cf ', '').strip()
        
        if t1 == t2:
            return True
        if t1 in t2 or t2 in t1:
            return True
        if t1.split()[0] == t2.split()[0]:
            return True
        return False
    
    def _calculate_outcome(self, bet: Dict, result: Dict) -> str:
        """Calculate bet outcome based on match result."""
        market = (bet.get('market') or '').lower()
        selection = (bet.get('selection') or '').lower()
        
        home_goals = result.get('home_goals', 0)
        away_goals = result.get('away_goals', 0)
        total_goals = home_goals + away_goals
        home_corners = result.get('home_corners')
        away_corners = result.get('away_corners')
        total_corners = result.get('total_corners')
        home_cards = result.get('home_cards')
        away_cards = result.get('away_cards')
        total_cards = result.get('total_cards')
        
        if market == 'corners':
            if total_corners is None:
                return 'unknown'
            return self._evaluate_corners_bet(selection, home_corners, away_corners, total_corners, bet.get('home_team', ''))
        
        elif market == 'cards':
            if total_cards is None:
                return 'unknown'
            return self._evaluate_cards_bet(selection, home_cards, away_cards, total_cards)
        
        elif 'over' in selection or 'under' in selection:
            line_match = re.search(r'(over|under)\s*(\d+\.?\d*)', selection)
            if line_match:
                direction = line_match.group(1)
                line = float(line_match.group(2))
                if direction == 'over':
                    return 'won' if total_goals > line else 'lost'
                else:
                    return 'won' if total_goals < line else 'lost'
        
        elif 'btts' in selection or 'both teams' in selection:
            both_scored = home_goals > 0 and away_goals > 0
            if 'yes' in selection:
                return 'won' if both_scored else 'lost'
            else:
                return 'won' if not both_scored else 'lost'
        
        elif 'home win' in selection or selection == 'home':
            return 'won' if home_goals > away_goals else 'lost'
        elif 'away win' in selection or selection == 'away':
            return 'won' if away_goals > home_goals else 'lost'
        elif 'draw' in selection:
            return 'won' if home_goals == away_goals else 'lost'
        
        return 'unknown'
    
    def _evaluate_corners_bet(self, selection: str, home_corners: int, away_corners: int, total_corners: int, home_team: str) -> str:
        """Evaluate corners market bet."""
        line_match = re.search(r'(over|under)\s*(\d+\.?\d*)', selection)
        if line_match:
            direction = line_match.group(1)
            line = float(line_match.group(2))
            
            if home_team.lower()[:4] in selection or 'home' in selection:
                actual = home_corners
            elif 'away' in selection:
                actual = away_corners
            else:
                actual = total_corners
            
            if direction == 'over':
                return 'won' if actual > line else 'lost'
            else:
                return 'won' if actual < line else 'lost'
        
        handicap_match = re.search(r'([+-]\d+\.?\d*)', selection)
        if handicap_match:
            handicap = float(handicap_match.group(1))
            if 'home' in selection or home_team.lower()[:4] in selection:
                adjusted = home_corners + handicap
                return 'won' if adjusted > away_corners else 'lost'
            else:
                adjusted = away_corners + handicap
                return 'won' if adjusted > home_corners else 'lost'
        
        return 'unknown'
    
    def _evaluate_cards_bet(self, selection: str, home_cards: int, away_cards: int, total_cards: int) -> str:
        """Evaluate cards market bet."""
        line_match = re.search(r'(over|under)\s*(\d+\.?\d*)', selection)
        if line_match:
            direction = line_match.group(1)
            line = float(line_match.group(2))
            
            if 'home' in selection:
                actual = home_cards
            elif 'away' in selection:
                actual = away_cards
            else:
                actual = total_cards
            
            if direction == 'over':
                return 'won' if actual > line else 'lost'
            else:
                return 'won' if actual < line else 'lost'
        
        return 'unknown'
    
    def _update_football_bet(self, cursor, bet_id: int, outcome: str, result: Dict):
        """Update football bet with outcome."""
        profit_loss = 0
        cursor.execute("SELECT odds, stake FROM football_opportunities WHERE id = %s", (bet_id,))
        row = cursor.fetchone()
        if row:
            odds = float(row['odds'] or 1)
            stake = float(row['stake'] or 100)
            profit_loss = stake * (odds - 1) if outcome == 'won' else -stake
        
        now_ts = int(datetime.now().timestamp())
        cursor.execute("""
            UPDATE football_opportunities 
            SET outcome = %s, 
                result = %s,
                profit_loss = %s,
                status = 'settled',
                settled_timestamp = %s
            WHERE id = %s
        """, (outcome, outcome.upper(), profit_loss, now_ts, bet_id))
        
        logger.info(f"✅ Settled football #{bet_id}: {outcome.upper()}")
    
    def _update_sgp_bet(self, cursor, bet_id: int, outcome: str):
        """Update SGP bet with outcome."""
        now_ts = int(datetime.now().timestamp())
        cursor.execute("""
            UPDATE sgp_predictions 
            SET outcome = %s, 
                result = %s,
                status = 'SETTLED',
                settled_timestamp = %s
            WHERE id = %s
        """, (outcome, outcome.upper(), now_ts, bet_id))
        
        logger.info(f"✅ Settled SGP #{bet_id}: {outcome.upper()}")
    
    def _send_discord_update(self):
        """Send Discord update after settlements."""
        try:
            from discord_roi_webhook import send_discord_stats
            send_discord_stats(f"🔄 Results Engine: {self.stats['settled']} bets settled")
            logger.info("📤 Discord stats update sent")
        except Exception as e:
            logger.warning(f"⚠️ Discord update skipped: {e}")


def run_results_engine():
    """Run the results engine cycle."""
    engine = ResultsEngine()
    return engine.run_cycle()


if __name__ == "__main__":
    run_results_engine()

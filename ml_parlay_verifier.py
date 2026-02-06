#!/usr/bin/env python3
"""
ML PARLAY RESULT VERIFIER
=========================
Verifies and settles ML Parlay predictions based on match results.
"""

import logging
import json
import time
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from db_helper import db_helper
from bankroll_manager import get_bankroll_manager
from discord_notifier import send_result_to_discord
from verify_results import RealResultVerifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MLParlayVerifier:
    """Verifies ML Parlay results using match scores"""
    
    def __init__(self):
        self.api_key = os.environ.get('THE_ODDS_API_KEY')
        self._scores_cache = {}
        self._result_verifier = RealResultVerifier()
        logger.info("✅ ML Parlay Verifier initialized")
    
    def _fetch_from_api_football(self, home_team: str, away_team: str, match_date: str) -> Optional[Dict]:
        """Fetch result from API-Football using the main verifier"""
        try:
            result = self._result_verifier._get_api_football_result(home_team, away_team, match_date)
            if result:
                return {
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': result['home_goals'],
                    'away_score': result['away_goals'],
                    'completed': True
                }
            return None
        except Exception as e:
            logger.debug(f"API-Football lookup failed: {e}")
            return None
    
    def _fetch_scores(self, sport_key: str) -> Dict[str, Dict]:
        """Fetch completed match scores from The Odds API"""
        if sport_key in self._scores_cache:
            cache_entry = self._scores_cache[sport_key]
            if time.time() - cache_entry['timestamp'] < 300:
                return cache_entry['scores']
        
        try:
            if not self.api_key:
                logger.warning("⚠️ THE_ODDS_API_KEY not found")
                return {}
            
            url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/"
            params = {
                'apiKey': self.api_key,
                'daysFrom': 3,
                'dateFormat': 'iso'
            }
            
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                logger.debug(f"Scores API returned {resp.status_code} for {sport_key}")
                return {}
            
            matches = resp.json()
            scores = {}
            
            for match in matches:
                if not match.get('completed'):
                    continue
                
                match_id = match.get('id', '')
                home_team = match.get('home_team', '')
                away_team = match.get('away_team', '')
                
                home_score = None
                away_score = None
                
                for score_entry in match.get('scores', []):
                    if score_entry.get('name') == home_team:
                        home_score = int(score_entry.get('score', 0))
                    elif score_entry.get('name') == away_team:
                        away_score = int(score_entry.get('score', 0))
                
                if home_score is not None and away_score is not None:
                    scores[match_id] = {
                        'home_team': home_team,
                        'away_team': away_team,
                        'home_score': home_score,
                        'away_score': away_score,
                        'completed': True
                    }
                    
                    team_key = f"{home_team}_{away_team}"
                    scores[team_key] = scores[match_id]
            
            self._scores_cache[sport_key] = {
                'timestamp': time.time(),
                'scores': scores
            }
            
            return scores
            
        except Exception as e:
            logger.error(f"❌ Error fetching scores for {sport_key}: {e}")
            return {}
    
    def _fetch_from_cache(self, home_team: str, away_team: str) -> Optional[Dict]:
        """Fallback: Fetch match result from match_results_cache table"""
        try:
            def normalize_team(name):
                return name.lower().replace(' fc', '').replace('fc ', '').strip()
            
            results = db_helper.execute(
                """SELECT home_team, away_team, home_score, away_score
                   FROM match_results_cache
                   WHERE match_date::date >= CURRENT_DATE - INTERVAL '7 days'""",
                fetch='all'
            )
            
            if not results:
                return None
            
            home_norm = normalize_team(home_team)
            away_norm = normalize_team(away_team)
            
            for row in results:
                cache_home = normalize_team(row[0] or '')
                cache_away = normalize_team(row[1] or '')
                
                if (home_norm in cache_home or cache_home in home_norm) and \
                   (away_norm in cache_away or cache_away in away_norm):
                    return {
                        'home_team': row[0],
                        'away_team': row[1],
                        'home_score': row[2],
                        'away_score': row[3],
                        'completed': True
                    }
                # Also check reversed order (some sources swap home/away)
                if (away_norm in cache_home or cache_home in away_norm) and \
                   (home_norm in cache_away or cache_away in home_norm):
                    return {
                        'home_team': row[1],
                        'away_team': row[0],
                        'home_score': row[3],
                        'away_score': row[2],
                        'completed': True
                    }
            
            return None
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")
            return None
    
    def _determine_leg_result(self, leg: Dict, match_result: Dict) -> str:
        """
        Determine if a leg won or lost.
        
        Returns: 'won', 'lost', or 'push' (for DNB draws)
        """
        home_score = match_result['home_score']
        away_score = match_result['away_score']
        total_goals = home_score + away_score
        selection = leg.get('selection', '')
        market_type = leg.get('market_type', '')
        
        if market_type == '1X2' or market_type == 'ML':
            if selection == 'HOME':
                return 'won' if home_score > away_score else 'lost'
            elif selection == 'AWAY':
                return 'won' if away_score > home_score else 'lost'
            elif selection == 'DRAW':
                return 'won' if home_score == away_score else 'lost'
        
        elif market_type == 'DNB':
            if home_score == away_score:
                return 'push'
            elif 'HOME' in selection:
                return 'won' if home_score > away_score else 'lost'
            elif 'AWAY' in selection:
                return 'won' if away_score > home_score else 'lost'
        
        elif market_type == 'TOTALS':
            import re
            line_match = re.search(r'(\d+\.?\d*)', selection)
            if line_match:
                line = float(line_match.group(1))
                if 'Over' in selection:
                    return 'won' if total_goals > line else 'lost'
                elif 'Under' in selection:
                    return 'won' if total_goals < line else 'lost'
        
        elif market_type == 'BTTS':
            both_scored = home_score > 0 and away_score > 0
            if selection == 'BTTS_YES':
                return 'won' if both_scored else 'lost'
            elif selection == 'BTTS_NO':
                return 'won' if not both_scored else 'lost'
        
        elif market_type == 'DC':
            if '1X' in selection or 'Home or Draw' in selection:
                return 'won' if home_score >= away_score else 'lost'
            elif 'X2' in selection or 'Draw or Away' in selection:
                return 'won' if away_score >= home_score else 'lost'
            elif '12' in selection or 'Home or Away' in selection:
                return 'won' if home_score != away_score else 'lost'
        
        return 'lost'
    
    def _calculate_parlay_result(self, leg_results: List[str], legs: List[Dict]) -> tuple:
        """
        Calculate overall parlay result and adjusted odds.
        
        Returns: (outcome, adjusted_odds)
        - If all legs won: ('won', total_odds)
        - If any leg lost: ('lost', 0)
        - If push legs: recalculate odds excluding push legs
        """
        if 'lost' in leg_results:
            return 'lost', 0
        
        if 'push' in leg_results:
            adjusted_odds = 1.0
            for i, result in enumerate(leg_results):
                if result == 'won':
                    adjusted_odds *= legs[i].get('odds', 1.0)
            
            if adjusted_odds > 1.0:
                return 'won', adjusted_odds
            else:
                return 'push', 1.0
        
        if all(r == 'won' for r in leg_results):
            total_odds = 1.0
            for leg in legs:
                total_odds *= leg.get('odds', 1.0)
            return 'won', total_odds
        
        return 'pending', 0
    
    def verify_pending_parlays(self) -> Dict[str, int]:
        """
        Verify all pending ML parlays.
        
        Returns:
            Dict with verification stats
        """
        stats = {'verified': 0, 'failed': 0, 'pending': 0}
        
        try:
            pending = db_helper.execute(
                """SELECT parlay_id, legs, stake, total_odds 
                   FROM ml_parlay_predictions 
                   WHERE status = 'pending'
                   ORDER BY timestamp ASC
                   LIMIT 50""",
                fetch='all'
            )
            
            if not pending:
                logger.info("✅ No pending ML parlays to verify")
                return stats
            
            logger.info(f"🔍 Checking {len(pending)} pending ML parlays...")
            
            for row in pending:
                parlay_id = row[0]
                legs_json = row[1]
                stake = float(row[2] or 0)
                total_odds = float(row[3] or 1)
                
                try:
                    legs = json.loads(legs_json) if legs_json else []
                except:
                    legs = []
                
                if not legs:
                    stats['failed'] += 1
                    continue
                
                legs_data = db_helper.execute(
                    """SELECT match_id, home_team, away_team, league_key, 
                              market_type, selection, odds, kickoff_time
                       FROM ml_parlay_legs 
                       WHERE parlay_id = %s
                       ORDER BY leg_number""",
                    (parlay_id,),
                    fetch='all'
                )
                
                if legs_data:
                    legs = [
                        {
                            'match_id': l[0],
                            'home_team': l[1],
                            'away_team': l[2],
                            'league_key': l[3],
                            'market_type': l[4],
                            'selection': l[5],
                            'odds': l[6],
                            'kickoff_time': str(l[7]) if l[7] else None
                        }
                        for l in legs_data
                    ]
                
                leg_results = []
                all_legs_settled = True
                
                for leg in legs:
                    league_key = leg.get('league_key', '')
                    match_id = leg.get('match_id', '')
                    home_team = leg.get('home_team', '')
                    away_team = leg.get('away_team', '')
                    
                    scores = self._fetch_scores(league_key)
                    
                    match_result = scores.get(match_id)
                    if not match_result:
                        team_key = f"{home_team}_{away_team}"
                        match_result = scores.get(team_key)
                    
                    if not match_result:
                        for key, result in scores.items():
                            if (result.get('home_team', '').lower() == home_team.lower() and
                                result.get('away_team', '').lower() == away_team.lower()):
                                match_result = result
                                break
                    
                    # Fallback: Check match_results_cache table
                    if not match_result:
                        match_result = self._fetch_from_cache(home_team, away_team)
                    
                    # Fallback: Use API-Football (with improved team matching)
                    if not match_result:
                        # Use kickoff_time from the leg (correct match date)
                        match_date = leg.get('kickoff_time', '')
                        if match_date:
                            # Extract date portion (YYYY-MM-DD) from kickoff_time
                            match_date = str(match_date).split('T')[0][:10]
                        if match_date:
                            match_result = self._fetch_from_api_football(home_team, away_team, match_date)
                    
                    if match_result and match_result.get('completed'):
                        result = self._determine_leg_result(leg, match_result)
                        leg_results.append(result)
                        
                        actual_score = f"{match_result['home_score']}-{match_result['away_score']}"
                        db_helper.execute(
                            """UPDATE ml_parlay_legs 
                               SET leg_result = %s, actual_score = %s
                               WHERE parlay_id = %s AND match_id = %s""",
                            (result, actual_score, parlay_id, match_id)
                        )
                    else:
                        all_legs_settled = False
                        leg_results.append('pending')
                
                if not all_legs_settled:
                    stats['pending'] += 1
                    continue
                
                outcome, adjusted_odds = self._calculate_parlay_result(leg_results, legs)
                
                if outcome == 'won':
                    profit_loss = stake * (adjusted_odds - 1)
                    result = 'won'
                elif outcome == 'lost':
                    profit_loss = -stake
                    result = 'lost'
                elif outcome == 'push':
                    profit_loss = 0
                    result = 'push'
                else:
                    stats['pending'] += 1
                    continue
                
                db_helper.execute(
                    """UPDATE ml_parlay_predictions 
                       SET status = 'settled', outcome = %s, result = %s,
                           profit_loss = %s, settled_timestamp = %s
                       WHERE parlay_id = %s""",
                    (outcome, result, profit_loss, int(time.time()), parlay_id)
                )
                
                emoji = "✅" if outcome == 'won' else "❌" if outcome == 'lost' else "↩️"
                logger.info(f"{emoji} ML Parlay {parlay_id}: {outcome.upper()} | P/L: {profit_loss:+.2f} SEK")
                
                # Send Discord notification
                try:
                    parlay_desc = " + ".join([f"{l.get('home_team', '')} vs {l.get('away_team', '')}" for l in legs[:3]])
                    discord_info = {
                        'outcome': 'WIN' if outcome == 'won' else ('VOID' if outcome == 'push' else 'LOSS'),
                        'home_team': parlay_desc,
                        'away_team': '',
                        'selection': ' | '.join([l.get('selection', '') for l in legs]),
                        'actual_score': 'Parlay',
                        'odds': total_odds,
                        'profit_loss': profit_loss,
                        'product_type': 'ML_PARLAY',
                        'league': legs[0].get('league_key', '') if legs else ''
                    }
                    send_result_to_discord(discord_info, 'ML_PARLAY')
                except Exception as e:
                    logger.warning(f"⚠️ Discord notification failed: {e}")
                
                stats['verified'] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error verifying ML parlays: {e}")
            return stats


def run_verification():
    """Run a single verification cycle"""
    try:
        verifier = MLParlayVerifier()
        return verifier.verify_pending_parlays()
    except Exception as e:
        logger.error(f"❌ ML Parlay verification error: {e}")
        return {'verified': 0, 'failed': 0, 'pending': 0}


if __name__ == "__main__":
    run_verification()

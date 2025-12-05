"""
COLLEGE BASKETBALL RESULT VERIFIER
Automatically verifies College Basketball picks using The Odds API
With ESPN fallback when API quota is exhausted
"""

import os
import re
import requests
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import time
from db_helper import DatabaseHelper
from espn_basketball_scraper import ESPNBasketballScraper
from discord_notifier import send_result_to_discord

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CollegeBasketballResultVerifier:
    """Verifies College Basketball picks using The Odds API scores endpoint with ESPN fallback"""
    
    def __init__(self):
        self.api_key = os.getenv('THE_ODDS_API_KEY')
        if not self.api_key:
            raise ValueError("THE_ODDS_API_KEY environment variable is required")
        
        self.db = DatabaseHelper()
        self.espn_scraper = ESPNBasketballScraper()
        self.verified_count = 0
        self.failed_count = 0
        
    def verify_pending_picks(self) -> Dict[str, int]:
        """
        Main verification method - processes all pending NCAAB picks.
        Returns statistics about verification.
        """
        logger.info("🏀 Starting College Basketball result verification")
        
        try:
            pending_picks = self._get_pending_picks()
            logger.info(f"📊 Found {len(pending_picks)} picks pending verification")
            
            if not pending_picks:
                logger.info("✅ No pending picks to verify")
                return {"verified": 0, "failed": 0}
            
            completed_games = self._fetch_completed_games()
            logger.info(f"📊 Found {len(completed_games)} completed games from The Odds API")
            
            if not completed_games:
                logger.warning("⚠️ The Odds API returned no games - trying ESPN fallback...")
                completed_games = self._fetch_espn_fallback()
                logger.info(f"📊 Found {len(completed_games)} completed games from ESPN")
            
            if not completed_games:
                logger.warning("⚠️ No completed games found from any source")
                return {"verified": 0, "failed": 0}
            
            for pick in pending_picks:
                try:
                    self._verify_single_pick(pick, completed_games)
                except Exception as e:
                    logger.error(f"❌ Failed to verify pick {pick.get('id')}: {e}")
                    self.failed_count += 1
            
            logger.info(f"✅ Verification complete: {self.verified_count} verified, {self.failed_count} failed")
            
            return {
                "verified": self.verified_count,
                "failed": self.failed_count
            }
            
        except Exception as e:
            logger.error(f"❌ Verification error: {e}")
            return {"verified": 0, "failed": 0}
    
    def _fetch_espn_fallback(self) -> List[Dict]:
        """Fetch completed games from ESPN as fallback"""
        try:
            return self.espn_scraper.fetch_completed_games(days_back=2)
        except Exception as e:
            logger.error(f"❌ ESPN fallback error: {e}")
            return []
    
    def _get_pending_picks(self) -> List[Dict]:
        """Get all pending picks from database (excludes backtests)"""
        try:
            query = """
                SELECT id, match, market, selection, odds, is_parlay, parlay_legs, 
                       commence_time, created_at
                FROM basketball_predictions
                WHERE status = 'pending'
                  AND (commence_time < NOW() OR commence_time IS NULL)
                  AND created_at < NOW() - INTERVAL '2 hours'
                  AND UPPER(COALESCE(mode, 'PROD')) = 'PROD'
                ORDER BY created_at DESC
            """
            
            rows = self.db.execute(query, (), fetch='all')
            
            picks = []
            for row in rows:
                picks.append({
                    'id': row[0],
                    'match': row[1],
                    'market': row[2],
                    'selection': row[3],
                    'odds': float(row[4]),
                    'is_parlay': row[5],
                    'parlay_legs': row[6],
                    'commence_time': row[7],
                    'created_at': row[8]
                })
            
            return picks
            
        except Exception as e:
            logger.error(f"❌ Database error fetching pending picks: {e}")
            return []
    
    def _fetch_completed_games(self) -> List[Dict]:
        """Fetch completed games from The Odds API (last 2 days)"""
        try:
            url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores/"
            params = {
                "apiKey": self.api_key,
                "daysFrom": 2  # Check last 2 days
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            all_games = response.json()
            
            # Filter to only completed games with scores
            completed = []
            for game in all_games:
                if game.get('completed') and game.get('scores'):
                    completed.append(game)
            
            return completed
            
        except Exception as e:
            logger.error(f"❌ API error fetching completed games: {e}")
            return []
    
    def _verify_single_pick(self, pick: Dict, completed_games: List[Dict]) -> bool:
        """Verify a single pick against completed games"""
        try:
            # Handle parlays separately
            if pick['is_parlay']:
                return self._verify_parlay(pick, completed_games)
            else:
                return self._verify_single(pick, completed_games)
                
        except Exception as e:
            logger.error(f"❌ Error verifying pick {pick['id']}: {e}")
            return False
    
    def _verify_single(self, pick: Dict, completed_games: List[Dict]) -> bool:
        """Verify a single (non-parlay) pick"""
        try:
            # Find matching game
            game_result = self._find_matching_game(pick['match'], completed_games)
            
            if not game_result:
                logger.warning(f"⚠️ No result found for: {pick['match']}")
                return False
            
            # Determine outcome based on market type
            outcome = self._calculate_outcome(pick, game_result)
            
            if outcome is None:
                logger.warning(f"⚠️ Could not determine outcome for: {pick['match']}")
                return False
            
            # Calculate profit/loss
            profit_loss = self._calculate_profit_loss(pick['odds'], outcome)
            
            # Update database
            self._update_pick_status(pick['id'], outcome, profit_loss)
            
            status_emoji = "✅" if outcome == "won" else "❌"
            logger.info(f"{status_emoji} {pick['match']}: {pick['selection']} - {outcome.upper()} (P&L: ${profit_loss:.2f})")
            
            # Send Discord notification
            try:
                discord_info = {
                    'outcome': 'WIN' if outcome == 'won' else 'LOSS',
                    'home_team': pick['match'].split(' vs ')[0] if ' vs ' in pick['match'] else pick['match'],
                    'away_team': pick['match'].split(' vs ')[1] if ' vs ' in pick['match'] else '',
                    'selection': pick['selection'],
                    'actual_score': f"{game_result.get('home_score', '?')}-{game_result.get('away_score', '?')}",
                    'odds': pick['odds'],
                    'profit_loss': profit_loss * 10.8,  # Convert to SEK
                    'product_type': 'BASKETBALL',
                    'league': 'NCAAB'
                }
                send_result_to_discord(discord_info, 'BASKETBALL')
            except Exception as e:
                logger.warning(f"⚠️ Discord notification failed: {e}")
            
            self.verified_count += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ Error verifying single pick: {e}")
            return False
    
    def _verify_parlay(self, pick: Dict, completed_games: List[Dict]) -> bool:
        """Verify a parlay pick (all legs must win)"""
        try:
            # Extract individual legs from parlay
            # Format: "PARLAY: Team1 + Team2 + Team3"
            match_part = pick['match'].replace('PARLAY: ', '')
            teams = [t.strip() for t in match_part.split(' + ')]
            
            # Extract selections
            # Format: "Selection1 | Selection2 | Selection3"
            selections = [s.strip() for s in pick['selection'].split(' | ')]
            
            if len(teams) != len(selections):
                logger.error(f"❌ Parlay mismatch: {len(teams)} teams vs {len(selections)} selections")
                return False
            
            # Check each leg
            all_won = True
            for team, selection in zip(teams, selections):
                # Find the game for this leg
                leg_result = self._find_matching_game_by_team(team, completed_games)
                
                if not leg_result:
                    logger.warning(f"⚠️ No result found for parlay leg: {team}")
                    return False
                
                # Detect market type from selection string
                leg_market = self._detect_market_from_selection(selection)
                
                # Create a single pick object for this leg
                leg_pick = {
                    'match': team,
                    'selection': selection,
                    'market': leg_market
                }
                
                # Check if this leg won
                leg_outcome = self._calculate_outcome(leg_pick, leg_result)
                
                if leg_outcome != "won":
                    all_won = False
                    break
            
            # Determine parlay outcome
            outcome = "won" if all_won else "lost"
            profit_loss = self._calculate_profit_loss(pick['odds'], outcome)
            
            # Update database
            self._update_pick_status(pick['id'], outcome, profit_loss)
            
            status_emoji = "✅" if outcome == "won" else "❌"
            logger.info(f"{status_emoji} PARLAY {pick['match']}: {outcome.upper()} (P&L: ${profit_loss:.2f})")
            
            # Send Discord notification
            try:
                discord_info = {
                    'outcome': 'WIN' if outcome == 'won' else 'LOSS',
                    'home_team': pick['match'].replace('PARLAY: ', ''),
                    'away_team': '',
                    'selection': pick['selection'],
                    'actual_score': 'Parlay',
                    'odds': pick['odds'],
                    'profit_loss': profit_loss * 10.8,  # Convert to SEK
                    'product_type': 'BASKET_PARLAY',
                    'league': 'NCAAB'
                }
                send_result_to_discord(discord_info, 'BASKET_PARLAY')
            except Exception as e:
                logger.warning(f"⚠️ Discord notification failed: {e}")
            
            self.verified_count += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ Error verifying parlay: {e}")
            return False
    
    def _detect_market_from_selection(self, selection: str) -> str:
        """Detect market type from selection string"""
        selection_lower = selection.lower()
        
        # Check for totals (over/under)
        if 'over' in selection_lower or 'under' in selection_lower:
            return 'Totals'
        
        # Check for spread (contains +/- with a number)
        if re.search(r'[+-]\d+\.?\d*', selection):
            return 'Spread'
        
        # Default to moneyline
        return '1X2 Moneyline'
    
    def _find_matching_game(self, match_string: str, games: List[Dict]) -> Optional[Dict]:
        """Find matching game from completed games list"""
        try:
            # Parse match string: "Team1 vs Team2"
            parts = match_string.split(' vs ')
            if len(parts) != 2:
                return None
            
            team1, team2 = parts[0].strip(), parts[1].strip()
            
            # Search for matching game
            for game in games:
                home = game.get('home_team', '')
                away = game.get('away_team', '')
                
                # Check both possible orientations
                match1 = (team1 in home or home in team1) and (team2 in away or away in team2)
                match2 = (team2 in home or home in team2) and (team1 in away or away in team1)
                
                if match1 or match2:
                    return game
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error finding matching game: {e}")
            return None
    
    def _find_matching_game_by_team(self, team: str, games: List[Dict]) -> Optional[Dict]:
        """Find game where team is playing"""
        try:
            for game in games:
                home = game.get('home_team', '')
                away = game.get('away_team', '')
                
                if team in home or home in team or team in away or away in team:
                    return game
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error finding game by team: {e}")
            return None
    
    def _calculate_outcome(self, pick: Dict, game_result: Dict) -> Optional[str]:
        """Calculate if pick won or lost based on actual scores"""
        try:
            market = pick['market']
            selection = pick['selection']
            
            # Get scores from game result
            scores = game_result.get('scores', [])
            if not scores or len(scores) < 2:
                return None
            
            home_team = game_result.get('home_team')
            away_team = game_result.get('away_team')
            
            home_score = None
            away_score = None
            
            for score in scores:
                if score['name'] == home_team:
                    home_score = int(score['score'])
                elif score['name'] == away_team:
                    away_score = int(score['score'])
            
            if home_score is None or away_score is None:
                return None
            
            # Moneyline (1X2)
            if market == '1X2 Moneyline':
                if selection == 'Home Win':
                    return "won" if home_score > away_score else "lost"
                elif selection == 'Away Win':
                    return "won" if away_score > home_score else "lost"
                elif 'Win' in selection:
                    # Check if team name is in selection
                    if home_team in selection:
                        return "won" if home_score > away_score else "lost"
                    elif away_team in selection:
                        return "won" if away_score > home_score else "lost"
            
            # Spread
            elif market == 'Spread':
                # Extract team and spread value: "Team Name +10.5"
                if '+' in selection:
                    parts = selection.rsplit('+', 1)
                    team_name = parts[0].strip()
                    spread = float(parts[1].strip())
                    
                    # Determine if it's home or away
                    is_home = team_name in home_team or home_team in team_name
                    
                    if is_home:
                        covered_score = home_score + spread
                        return "won" if covered_score > away_score else "lost"
                    else:
                        covered_score = away_score + spread
                        return "won" if covered_score > home_score else "lost"
                        
                elif '-' in selection:
                    parts = selection.rsplit('-', 1)
                    team_name = parts[0].strip()
                    spread = float(parts[1].strip())
                    
                    is_home = team_name in home_team or home_team in team_name
                    
                    if is_home:
                        covered_score = home_score - spread
                        return "won" if covered_score > away_score else "lost"
                    else:
                        covered_score = away_score - spread
                        return "won" if covered_score > home_score else "lost"
            
            # Totals (Over/Under)
            elif market == 'Totals':
                total_points = home_score + away_score
                
                if 'Over' in selection:
                    line = float(selection.replace('Over', '').strip())
                    return "won" if total_points > line else "lost"
                elif 'Under' in selection:
                    line = float(selection.replace('Under', '').strip())
                    return "won" if total_points < line else "lost"
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error calculating outcome: {e}")
            return None
    
    def _calculate_profit_loss(self, odds: float, outcome: str) -> float:
        """Calculate profit/loss for 16 USD (173 SEK) stake"""
        stake = 173.0  # 16 USD × 10.8
        
        if outcome == "won":
            return (odds - 1.0) * stake
        else:
            return -stake
    
    def _update_pick_status(self, pick_id: int, outcome: str, profit_loss: float):
        """Update pick status in database"""
        try:
            query = """
                UPDATE basketball_predictions
                SET status = %s,
                    verified_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """
            
            self.db.execute(query, (outcome, pick_id), fetch='none')
            
        except Exception as e:
            logger.error(f"❌ Database update error: {e}")
            raise


def main():
    """Run verification"""
    try:
        verifier = CollegeBasketballResultVerifier()
        results = verifier.verify_pending_picks()
        
        print(f"\n{'='*60}")
        print(f"🏀 COLLEGE BASKETBALL VERIFICATION COMPLETE")
        print(f"{'='*60}")
        print(f"✅ Verified: {results['verified']}")
        print(f"❌ Failed: {results['failed']}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        raise


if __name__ == "__main__":
    main()

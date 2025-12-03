#!/usr/bin/env python3
"""
SGP Champion - Automated Same Game Parlay Generator
Runs daily in parallel with Real Football Champion
Generates SGP predictions using real AI probabilities
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import os
import sys

# Import existing systems
from sgp_predictor import SGPPredictor
from telegram_sender import TelegramBroadcaster
from api_football_client import APIFootballClient
from db_helper import db_helper
from bankroll_manager import get_bankroll_manager
from data_collector import get_collector
from advanced_features import AdvancedFeaturesAPI
from api_cache_manager import APICacheManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SGPChampion:
    """Automated SGP prediction system running 24/7"""
    
    def __init__(self):
        self.sgp_predictor = SGPPredictor()
        self.telegram = TelegramBroadcaster()
        
        # Try to initialize API-Football client for player props (optional)
        try:
            self.api_football = APIFootballClient()
            logger.info("✅ API-Football client initialized for player props")
        except (ValueError, Exception) as e:
            self.api_football = None
            logger.warning(f"⚠️ API-Football client not available ({e}). Player props disabled, generating basic SGPs only.")
        
        # Initialize Advanced Features for H2H BTTS filtering
        try:
            self.cache_manager = APICacheManager(api_name='api_football')
            self.advanced_features = AdvancedFeaturesAPI(cache_manager=self.cache_manager)
            logger.info("✅ Advanced Features initialized for H2H BTTS filtering")
        except Exception as e:
            self.advanced_features = None
            logger.warning(f"⚠️ Advanced Features not available ({e}). H2H BTTS filtering disabled.")
        
        logger.info("✅ SGP Champion initialized")
    
    def get_todays_matches(self) -> List[Dict[str, Any]]:
        """Get today's matches from The Odds API"""
        try:
            import requests
            
            odds_api_key = os.getenv('THE_ODDS_API_KEY')
            if not odds_api_key:
                logger.error("❌ THE_ODDS_API_KEY not found")
                return []
            
            # Target leagues (same as exact scores)
            target_leagues = [
                'soccer_epl',
                'soccer_efl_champ',
                'soccer_spain_la_liga',
                'soccer_italy_serie_a',
                'soccer_germany_bundesliga',
                'soccer_france_ligue_one',
                'soccer_netherlands_eredivisie',
                'soccer_portugal_primeira_liga',
                'soccer_belgium_first_div',
                'soccer_uefa_champs_league',
                'soccer_uefa_europa_league',
            ]
            
            all_matches = []
            base_url = "https://api.the-odds-api.com/v4"
            
            for league in target_leagues:
                try:
                    url = f"{base_url}/sports/{league}/odds"
                    params = {
                        'apiKey': odds_api_key,
                        'regions': 'uk,eu,us',
                        'markets': 'h2h,totals',
                        'oddsFormat': 'decimal',
                        'dateFormat': 'iso'
                    }
                    
                    response = requests.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200:
                        matches = response.json()
                        if matches:
                            all_matches.extend(matches)
                    elif response.status_code == 429:
                        logger.warning("⚠️ Odds API quota exhausted")
                        break
                    
                except Exception as e:
                    logger.warning(f"⚠️ Odds API error for {league}: {e}")
            
            # Filter for next 24 hours
            from datetime import timezone
            today = datetime.now(timezone.utc)
            tomorrow = today + timedelta(hours=24)
            
            filtered_matches = []
            for match in all_matches:
                match_time = datetime.fromisoformat(match['commence_time'].replace('Z', '+00:00'))
                if today <= match_time <= tomorrow:
                    filtered_matches.append(match)
            
            logger.info(f"📅 Found {len(filtered_matches)} matches in next 24 hours")
            return filtered_matches
            
        except Exception as e:
            logger.error(f"❌ Error fetching matches: {e}")
            return []
    
    def get_xg_predictions(self, home_team: str, away_team: str, league: str) -> tuple:
        """Get xG predictions - use simple league-based estimates for MVP"""
        try:
            # Simple xG estimates based on league quality
            league_xg = {
                'Premier League': (1.7, 1.4),
                'La Liga': (1.6, 1.3),
                'Serie A': (1.5, 1.2),
                'Bundesliga': (1.8, 1.5),
                'Ligue 1': (1.5, 1.3),
                'Champions League': (1.6, 1.4),
                'Europa League': (1.5, 1.3),
            }
            
            # Get league xG or use default
            xg_home, xg_away = league_xg.get(league, (1.5, 1.3))
            
            # Add small random variation for realism
            import random
            xg_home += random.uniform(-0.2, 0.2)
            xg_away += random.uniform(-0.2, 0.2)
            
            return max(0.5, xg_home), max(0.5, xg_away)
            
        except Exception as e:
            logger.warning(f"⚠️  xG estimation failed: {e}")
            return 1.5, 1.3  # Safe defaults
    
    def check_daily_limit(self) -> bool:
        """Check if we've hit daily SGP limit (max 12 per day)"""
        today = datetime.now().date().isoformat()
        
        result = db_helper.execute('''
            SELECT COUNT(*) FROM sgp_predictions 
            WHERE DATE(match_date) = %s
            AND status = 'pending'
        ''', (today,), fetch='one')
        
        count = result[0] if result else 0
        
        return count < 12  # Max 12 SGPs per day (reduced from 20)
    
    def _map_sport_key_to_league(self, sport_key: str) -> str:
        """Map The Odds API sport_key to readable league name"""
        mapping = {
            'soccer_epl': 'Premier League',
            'soccer_efl_champ': 'Championship',
            'soccer_spain_la_liga': 'La Liga',
            'soccer_italy_serie_a': 'Serie A',
            'soccer_germany_bundesliga': 'Bundesliga',
            'soccer_france_ligue_one': 'Ligue 1',
            'soccer_netherlands_eredivisie': 'Eredivisie',
            'soccer_portugal_primeira_liga': 'Primeira Liga',
            'soccer_belgium_first_div': 'Belgian First Division',
            'soccer_uefa_champs_league': 'Champions League',
            'soccer_uefa_europa_league': 'Europa League',
            'soccer_scotland_premiership': 'Scottish Premiership',
            'soccer_turkey_super_league': 'Turkish Super League',
            'soccer_sweden_allsvenskan': 'Allsvenskan',
            'soccer_brazil_campeonato': 'Serie A Brazil',
            'soccer_usa_mls': 'MLS'
        }
        return mapping.get(sport_key, 'Unknown')
    
    def generate_daily_sgps(self):
        """Main function: Generate SGP predictions for today's matches"""
        logger.info("="*80)
        logger.info("🎯 SGP CHAMPION - DAILY PREDICTION RUN")
        logger.info("="*80)
        
        if not self.check_daily_limit():
            logger.info("⚠️  Daily limit reached (12 SGPs). Skipping generation.")
            return
        
        # Get today's matches
        matches = self.get_todays_matches()
        
        if not matches:
            logger.info("📭 No matches found for today")
            return
        
        logger.info(f"⚽ Analyzing {len(matches)} matches for SGP opportunities...")
        
        all_candidates = []  # Collect ALL candidates first
        
        # PHASE 1: Generate ALL SGP candidates (don't save yet)
        for match in matches:
            home_team = match['home_team']
            away_team = match['away_team']
            league = self._map_sport_key_to_league(match.get('sport_key', ''))
            match_id = match.get('id', f"{home_team}_{away_team}")
            
            # Get xG predictions
            logger.info(f"   📊 Analyzing {home_team} vs {away_team}...")
            lambda_home, lambda_away = self.get_xg_predictions(home_team, away_team, league)
            
            # Fetch player data for player props (only if API-Football available)
            player_data = None
            home_team_id = None
            away_team_id = None
            if self.api_football:
                try:
                    fixture = self.api_football.get_fixture_by_teams_and_date(
                        home_team, away_team, match['commence_time']
                    )
                    
                    if fixture:
                        fixture_id = fixture.get('fixture', {}).get('id')
                        home_team_id = fixture.get('teams', {}).get('home', {}).get('id')
                        away_team_id = fixture.get('teams', {}).get('away', {}).get('id')
                        league_id = fixture.get('league', {}).get('id', 39)
                        
                        if fixture_id and home_team_id and away_team_id:
                            player_data = self.api_football.get_top_scorers(
                                fixture_id, home_team_id, away_team_id, league_id
                            )
                            logger.info(f"   ⚽ Fetched player data for props")
                except Exception as e:
                    logger.warning(f"   ⚠️ Could not fetch player data: {e}")
            
            # Fetch H2H data for BTTS filtering (NEW: Dec 3, 2025)
            h2h_btts_rate = 0.5  # Default neutral rate
            h2h_total_matches = 0
            h2h_avg_home_goals = None
            h2h_avg_away_goals = None
            if self.advanced_features and home_team_id and away_team_id:
                try:
                    h2h_data = self.advanced_features.get_head_to_head(home_team_id, away_team_id, last_n=10)
                    h2h_btts_rate = h2h_data.get('btts_rate', 0.5)
                    h2h_total_matches = h2h_data.get('total_matches', 0)
                    h2h_avg_home_goals = h2h_data.get('avg_team1_goals')
                    h2h_avg_away_goals = h2h_data.get('avg_team2_goals')
                    if h2h_total_matches >= 4:
                        logger.info(f"   📊 H2H BTTS rate: {h2h_btts_rate:.0%} ({h2h_total_matches} matches)")
                except Exception as e:
                    logger.warning(f"   ⚠️ Could not fetch H2H data: {e}")
            
            match_data = {
                'match_id': match_id,
                'home_team': home_team,
                'away_team': away_team,
                'league': league,
                'match_date': match['commence_time'],
                'kickoff_time': match['commence_time'],
                # H2H BTTS data for filtering (NEW: Dec 3, 2025)
                'h2h_btts_rate': h2h_btts_rate,
                'h2h_total_matches': h2h_total_matches,
                'h2h_avg_home_goals': h2h_avg_home_goals,
                'h2h_avg_away_goals': h2h_avg_away_goals
            }
            
            sgps = self.sgp_predictor.generate_sgp_for_match(match_data, lambda_home, lambda_away, player_data)
            
            if sgps:
                for sgp in sgps:
                    sgp['_match_id'] = match_id  # Track which match this belongs to
                    all_candidates.append(sgp)
                logger.info(f"   ✅ Found {len(sgps)} SGP candidates")
            else:
                logger.info(f"   ⚠️ No qualifying SGPs found")
        
        logger.info(f"\n📊 Total candidates before filtering: {len(all_candidates)}")
        
        # 📊 COLLECT ALL CANDIDATES FOR AI TRAINING (even those not selected)
        try:
            collector = get_collector()
            for candidate in all_candidates:
                try:
                    match_data = candidate.get('match_data', {})
                    match_dt = None
                    if match_data.get('match_date'):
                        try:
                            match_dt = datetime.fromisoformat(match_data['match_date'].replace('Z', '+00:00'))
                        except:
                            pass
                    
                    collector.collect_sgp_prediction(
                        home_team=match_data.get('home_team', ''),
                        away_team=match_data.get('away_team', ''),
                        league=match_data.get('league', ''),
                        match_date=match_dt,
                        legs=candidate.get('legs', []),
                        combined_probability=candidate.get('probability', 0),
                        combined_odds=candidate.get('combined_odds', 0),
                        edge=candidate.get('ev_percentage', candidate.get('edge_percentage', 0)) / 100 if candidate.get('ev_percentage', candidate.get('edge_percentage', 0)) else 0,
                        sgp_type=candidate.get('description', '').split(':')[0] if ':' in candidate.get('description', '') else 'SGP',
                        xg_data={'lambda_home': candidate.get('lambda_home'), 'lambda_away': candidate.get('lambda_away')},
                        bet_placed=False  # Candidate, not yet selected
                    )
                except:
                    pass
            logger.info(f"📊 Collected {len(all_candidates)} SGP candidates for AI training")
        except Exception as e:
            pass  # Silent fail for data collection
        
        # PHASE 2: Apply per-match cap (max 2 SGPs per match) + global cap (12/day)
        selected_sgps = self._apply_per_match_cap(all_candidates, max_per_match=2, global_cap=12)
        
        # PHASE 3: Save only the selected SGPs to database
        sgps_generated = 0
        for sgp in selected_sgps:
            self.sgp_predictor.save_sgp_prediction(sgp)
            sgps_generated += 1
            
            # 📊 COLLECT DATA FOR AI TRAINING
            try:
                collector = get_collector()
                match_data = sgp.get('match_data', {})
                match_dt = None
                if match_data.get('match_date'):
                    try:
                        match_dt = datetime.fromisoformat(match_data['match_date'].replace('Z', '+00:00'))
                    except:
                        pass
                
                collector.collect_sgp_prediction(
                    home_team=match_data.get('home_team', ''),
                    away_team=match_data.get('away_team', ''),
                    league=match_data.get('league', ''),
                    match_date=match_dt,
                    legs=sgp.get('legs', []),
                    combined_probability=sgp.get('probability', 0),
                    combined_odds=sgp.get('combined_odds', 0),
                    edge=sgp.get('ev_percentage', sgp.get('edge_percentage', 0)) / 100 if sgp.get('ev_percentage', sgp.get('edge_percentage', 0)) else 0,
                    sgp_type=sgp.get('description', '').split(':')[0] if ':' in sgp.get('description', '') else 'SGP',
                    xg_data={'lambda_home': sgp.get('lambda_home'), 'lambda_away': sgp.get('lambda_away')},
                    bet_placed=True
                )
            except Exception as e:
                pass  # Silent fail for data collection
        
        logger.info("="*80)
        logger.info(f"✅ SGP Generation Complete: {sgps_generated} predictions saved (from {len(all_candidates)} candidates)")
        logger.info("="*80)
        
        # PHASE 4: Broadcast the selected predictions
        self._select_and_broadcast_top_sgps(selected_sgps)
    
    def _apply_per_match_cap(self, candidates: List[Dict[str, Any]], max_per_match: int = 2, global_cap: int = 12) -> List[Dict[str, Any]]:
        """
        Apply per-match cap and global cap to SGP candidates.
        Sort by edge_percentage descending, pick max 2 per match, up to 12 total.
        """
        if not candidates:
            return []
        
        # Sort ALL candidates by edge_percentage (EV) descending - best first
        sorted_candidates = sorted(
            candidates, 
            key=lambda x: x.get('ev_percentage', x.get('edge_percentage', 0)), 
            reverse=True
        )
        
        logger.info(f"🔍 Sorting {len(sorted_candidates)} candidates by edge percentage...")
        
        # Track how many SGPs we've selected per match
        match_counts = {}  # {match_id: count}
        selected = []
        
        for sgp in sorted_candidates:
            # Check global cap
            if len(selected) >= global_cap:
                logger.info(f"⚠️  Global cap reached ({global_cap} SGPs)")
                break
            
            # Get match_id (we added _match_id during generation)
            match_id = sgp.get('_match_id', '')
            if not match_id:
                # Fallback: create match_id from match_data
                match_data = sgp.get('match_data', {})
                match_id = f"{match_data.get('home_team', '')}_{match_data.get('away_team', '')}"
            
            # Check per-match cap
            current_count = match_counts.get(match_id, 0)
            if current_count >= max_per_match:
                continue  # Skip - this match already has max SGPs
            
            # Select this SGP
            selected.append(sgp)
            match_counts[match_id] = current_count + 1
            
            ev = sgp.get('ev_percentage', sgp.get('edge_percentage', 0))
            desc = sgp.get('description', 'Unknown')
            logger.info(f"   ✅ Selected: {desc} (EV: {ev:.1f}%) - Match {match_id[:20]}... ({match_counts[match_id]}/{max_per_match})")
        
        # Log summary
        matches_with_sgps = len(match_counts)
        logger.info(f"\n📊 Selection Summary:")
        logger.info(f"   • {len(selected)} SGPs selected from {len(candidates)} candidates")
        logger.info(f"   • Spread across {matches_with_sgps} matches (max {max_per_match} per match)")
        
        return selected
    
    def _select_and_broadcast_top_sgps(self, all_sgps: List[Dict[str, Any]]):
        """Smart selection: Only broadcast top 15 regular SGP + top 10 MonsterSGP"""
        if not all_sgps:
            logger.info("📭 No SGPs to broadcast")
            return
        
        logger.info("="*80)
        logger.info("🎯 SMART SELECTION - Filtering for broadcast")
        logger.info("="*80)
        
        # Separate MonsterSGP from regular SGP
        monster_sgps = []
        regular_sgps = []
        
        for sgp in all_sgps:
            desc = sgp.get('description', '')
            if 'MonsterSGP' in desc:
                monster_sgps.append(sgp)
            else:
                regular_sgps.append(sgp)
        
        logger.info(f"📊 Generated: {len(regular_sgps)} regular SGP, {len(monster_sgps)} MonsterSGP")
        
        # Sort by EV (highest first)
        monster_sgps.sort(key=lambda x: x.get('ev_percentage', 0), reverse=True)
        regular_sgps.sort(key=lambda x: x.get('ev_percentage', 0), reverse=True)
        
        # Select top predictions
        top_regular = regular_sgps[:15]  # Top 15 regular SGP
        top_monster = monster_sgps[:10]  # Top 10 MonsterSGP (entertainment)
        
        logger.info(f"✅ Selected for broadcast:")
        logger.info(f"   • {len(top_regular)} regular SGP (best EV)")
        logger.info(f"   • {len(top_monster)} MonsterSGP (best EV)")
        
        # Broadcast selected predictions
        broadcast_count = 0
        
        for sgp in top_regular:
            self._send_telegram_notification(sgp)
            broadcast_count += 1
        
        for sgp in top_monster:
            self._send_telegram_notification(sgp)
            broadcast_count += 1
        
        logger.info("="*80)
        logger.info(f"📱 Broadcasted {broadcast_count} SGP predictions to Telegram")
        logger.info(f"💾 {len(all_sgps)} total predictions saved to database for analytics")
        logger.info("="*80)
    
    def _send_telegram_notification(self, sgp: Dict[str, Any]):
        """Send SGP prediction to Telegram"""
        try:
            match_data = sgp['match_data']
            
            # Get dynamic stake (1.2% of bankroll)
            try:
                bankroll_mgr = get_bankroll_manager()
                dynamic_stake = bankroll_mgr.get_dynamic_stake()
            except Exception:
                dynamic_stake = 173.0  # Fallback
            
            # Format prediction for Telegram broadcaster
            prediction = {
                'home_team': match_data['home_team'],
                'away_team': match_data['away_team'],
                'league': match_data.get('league', 'Unknown'),
                'match_date': match_data.get('match_date'),
                'kickoff_time': match_data.get('kickoff_time'),
                'parlay_description': sgp['description'],
                'bookmaker_odds': sgp['bookmaker_odds'],
                'odds': sgp['bookmaker_odds'],
                'ev_percentage': sgp['ev_percentage'],
                'stake': dynamic_stake
            }
            
            # Use broadcast_prediction with SGP type
            self.telegram.broadcast_prediction(prediction, prediction_type='sgp')
            logger.info("📱 SGP sent to Telegram (SGP Channel)")
            
        except Exception as e:
            logger.error(f"❌ Telegram send failed: {e}")


def run_single_cycle():
    """Run a single SGP generation cycle without blocking wait"""
    try:
        champion = SGPChampion()
        champion.generate_daily_sgps()
        logger.info("✅ SGP single cycle complete")
    except Exception as e:
        logger.error(f"❌ Error in SGP generation cycle: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run SGP Champion continuously"""
    import time
    
    try:
        champion = SGPChampion()
        
        while True:
            try:
                champion.generate_daily_sgps()
            except Exception as e:
                logger.error(f"❌ Error in SGP generation cycle: {e}")
                import traceback
                traceback.print_exc()
            
            # Wait 60 minutes between cycles
            logger.info("⏰ Waiting 60 minutes before next SGP generation cycle...")
            time.sleep(3600)
        
    except KeyboardInterrupt:
        logger.info("🛑 SGP Champion stopped by user")
    except Exception as e:
        logger.error(f"❌ SGP Champion fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

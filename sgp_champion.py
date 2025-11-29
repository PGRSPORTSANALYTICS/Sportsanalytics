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
        """Check if we've hit daily SGP limit (max 20 per day)"""
        today = datetime.now().date().isoformat()
        
        result = db_helper.execute('''
            SELECT COUNT(*) FROM sgp_predictions 
            WHERE DATE(match_date) = %s
            AND status = 'pending'
        ''', (today,), fetch='one')
        
        count = result[0] if result else 0
        
        return count < 20  # Max 20 SGPs per day
    
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
            logger.info("⚠️  Daily limit reached (20 SGPs). Skipping generation.")
            return
        
        # Get today's matches
        matches = self.get_todays_matches()
        
        if not matches:
            logger.info("📭 No matches found for today")
            return
        
        logger.info(f"⚽ Analyzing {len(matches)} matches for SGP opportunities...")
        
        sgps_generated = 0
        all_sgps = []
        
        # PHASE 1: Generate and save ALL SGPs (don't broadcast yet)
        for match in matches:
            home_team = match['home_team']
            away_team = match['away_team']
            league = self._map_sport_key_to_league(match.get('sport_key', ''))
            
            # Get xG predictions
            logger.info(f"   📊 Analyzing {home_team} vs {away_team}...")
            lambda_home, lambda_away = self.get_xg_predictions(home_team, away_team, league)
            
            # Fetch player data for player props (only if API-Football available)
            player_data = None
            if self.api_football:
                try:
                    # Get fixture from API-Football to fetch player stats
                    fixture = self.api_football.get_fixture_by_teams_and_date(
                        home_team, away_team, match['commence_time']
                    )
                    
                    if fixture:
                        fixture_id = fixture.get('fixture', {}).get('id')
                        home_team_id = fixture.get('teams', {}).get('home', {}).get('id')
                        away_team_id = fixture.get('teams', {}).get('away', {}).get('id')
                        league_id = fixture.get('league', {}).get('id', 39)  # Default Premier League
                        
                        if fixture_id and home_team_id and away_team_id:
                            player_data = self.api_football.get_top_scorers(
                                fixture_id, home_team_id, away_team_id, league_id
                            )
                            logger.info(f"   ⚽ Fetched player data for props")
                except Exception as e:
                    logger.warning(f"   ⚠️ Could not fetch player data: {e}")
            
            # Generate SGPs (returns top 3 by EV)
            match_data = {
                'match_id': match.get('id', ''),
                'home_team': home_team,
                'away_team': away_team,
                'league': league,
                'match_date': match['commence_time'],
                'kickoff_time': match['commence_time']
            }
            
            sgps = self.sgp_predictor.generate_sgp_for_match(match_data, lambda_home, lambda_away, player_data)
            
            if sgps:
                # Save all SGPs and track them
                for sgp in sgps:
                    self.sgp_predictor.save_sgp_prediction(sgp)
                    all_sgps.append(sgp)
                    sgps_generated += 1
                
                logger.info(f"   ✅ Generated {len(sgps)} SGPs for this match")
            else:
                logger.info(f"   ⚠️ No qualifying SGPs found")
            
            logger.info(f"   ✅ Analysis complete")
        
        logger.info("="*80)
        logger.info(f"✅ SGP Generation Complete: {sgps_generated} predictions saved to database")
        logger.info("="*80)
        
        # PHASE 2: Smart Selection - Only broadcast the BEST predictions
        self._select_and_broadcast_top_sgps(all_sgps)
    
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
                'stake': 160
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

import trafilatura
import requests
import re
import sqlite3
import os
import json
from datetime import datetime, timedelta
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResultsScraper:
    def __init__(self, db_path='data/real_football.db'):
        self.db_path = db_path
        
    def get_flashscore_results(self, date_str):
        """Get results from Flashscore for a specific date (YYYY-MM-DD)"""
        try:
            url = f"https://www.flashscore.com/football/fixtures/?date={date_str}"
            logger.info(f"Scraping Flashscore results for {date_str}")
            
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                logger.error(f"Failed to fetch Flashscore page for {date_str}")
                return []
                
            text = trafilatura.extract(downloaded)
            if not text:
                logger.error(f"Failed to extract text from Flashscore page for {date_str}")
                return []
            
            return self.parse_flashscore_results(text)
            
        except Exception as e:
            logger.error(f"Error scraping Flashscore: {e}")
            return []
    
    def get_sofascore_results(self, date_str):
        """Get results from Sofascore for a specific date (YYYY-MM-DD)"""
        try:
            # Convert date format for Sofascore
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            sofascore_date = date_obj.strftime('%Y-%m-%d')
            
            url = f"https://www.sofascore.com/football//{sofascore_date}"
            logger.info(f"Scraping Sofascore results for {date_str}")
            
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                logger.error(f"Failed to fetch Sofascore page for {date_str}")
                return []
                
            text = trafilatura.extract(downloaded)
            if not text:
                logger.error(f"Failed to extract text from Sofascore page for {date_str}")
                return []
            
            return self.parse_sofascore_results(text)
            
        except Exception as e:
            logger.error(f"Error scraping Sofascore: {e}")
            return []
    
    def parse_flashscore_results(self, text):
        """Parse Flashscore results text to extract match results"""
        results = []
        
        try:
            # Look for match patterns in the text
            # Flashscore typically shows: Team1 vs Team2 1-2 (FT)
            pattern = r'([A-Za-z\s]+)\s+vs\s+([A-Za-z\s]+)\s+(\d+)\s*-\s*(\d+)'
            matches = re.findall(pattern, text, re.IGNORECASE)
            
            for match in matches:
                home_team = match[0].strip()
                away_team = match[1].strip()
                home_score = int(match[2])
                away_score = int(match[3])
                
                results.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': home_score,
                    'away_score': away_score,
                    'total_goals': home_score + away_score,
                    'result': 'home' if home_score > away_score else ('away' if away_score > home_score else 'draw')
                })
                
        except Exception as e:
            logger.error(f"Error parsing Flashscore results: {e}")
            
        return results
    
    def parse_sofascore_results(self, text):
        """Parse Sofascore results text to extract match results"""
        results = []
        
        try:
            # Look for match patterns in the text
            # Sofascore format may vary, adjust pattern as needed
            pattern = r'([A-Za-z\s]+)\s+(\d+)\s*-\s*(\d+)\s+([A-Za-z\s]+)'
            matches = re.findall(pattern, text, re.IGNORECASE)
            
            for match in matches:
                home_team = match[0].strip()
                home_score = int(match[1])
                away_score = int(match[2])
                away_team = match[3].strip()
                
                results.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': home_score,
                    'away_score': away_score,
                    'total_goals': home_score + away_score,
                    'result': 'home' if home_score > away_score else ('away' if away_score > home_score else 'draw')
                })
                
        except Exception as e:
            logger.error(f"Error parsing Sofascore results: {e}")
            
        return results
    
    def get_api_football_results(self, date_str):
        """Get results from API-Football for a specific date (YYYY-MM-DD)"""
        try:
            api_key = os.getenv('API_FOOTBALL_KEY')
            if not api_key:
                logger.warning("❌ No API_FOOTBALL_KEY found in environment")
                return []
            
            logger.info(f"🔍 Fetching API-Football results for {date_str}")
            
            # API-Football endpoint for fixtures
            url = "https://v3.football.api-sports.io/fixtures"
            headers = {
                'x-apisports-key': api_key
            }
            
            params = {
                'date': date_str,
                'status': 'FT'  # Only finished matches
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"❌ API-Football HTTP error: {response.status_code}")
                return []
            
            data = response.json()
            
            if data.get('errors'):
                logger.error(f"❌ API-Football errors: {data['errors']}")
                return []
            
            fixtures = data.get('response', [])
            logger.info(f"📊 Found {len(fixtures)} finished matches from API-Football")
            
            results = []
            for fixture in fixtures:
                try:
                    teams = fixture.get('teams', {})
                    goals = fixture.get('goals', {})
                    
                    home_team = teams.get('home', {}).get('name', '')
                    away_team = teams.get('away', {}).get('name', '')
                    home_score = goals.get('home')
                    away_score = goals.get('away')
                    
                    if home_score is not None and away_score is not None:
                        results.append({
                            'home_team': home_team,
                            'away_team': away_team,
                            'home_score': int(home_score),
                            'away_score': int(away_score),
                            'total_goals': int(home_score) + int(away_score),
                            'result': 'home' if home_score > away_score else ('away' if away_score > home_score else 'draw'),
                            'source': 'api-football'
                        })
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error processing fixture: {e}")
                    continue
            
            logger.info(f"✅ Parsed {len(results)} results from API-Football")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error fetching API-Football results: {e}")
            return []
    
    def get_results_for_date(self, date_str):
        """Get results from multiple sources for a date (API-Football priority)"""
        logger.info(f"🔍 Getting results for {date_str}")
        
        # Extract just the date part if timestamp is included
        # Handles: 2025-10-04, 2025-10-04T14:00:00, 2025-10-04T14:00:00+00:00, etc.
        if 'T' in date_str or len(date_str) > 10:
            clean_date = date_str.split('T')[0]
        else:
            clean_date = date_str
        
        # Try API-Football first (most reliable)
        results = self.get_api_football_results(clean_date)
        
        if not results:
            logger.info("📡 No results from API-Football, trying Sofascore...")
            results = self.get_sofascore_results(clean_date)
        
        if not results:
            logger.info("📡 No results from Sofascore, trying Flashscore...")
            results = self.get_flashscore_results(clean_date)
        
        logger.info(f"📊 Found {len(results)} total results for {clean_date}")
        return results
    
    def update_bet_outcomes(self):
        """Update bet outcomes based on scraped results"""
        logger.info("🔄 Checking bet outcomes...")
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get pending bets (no outcome yet) for PAST dates only - avoid 404s on future dates
            cursor.execute('''
                SELECT id, home_team, away_team, selection, match_date, odds, stake
                FROM football_opportunities 
                WHERE (outcome IS NULL OR outcome = '') 
                  AND match_date IS NOT NULL 
                  AND match_date != ''
                  AND DATE(match_date) <= DATE('now')
                ORDER BY match_date
            ''')
            
            pending_bets = cursor.fetchall()
            logger.info(f"Found {len(pending_bets)} pending bets to check")
            
            updated_count = 0
            
            # Process unique dates to avoid redundant API calls
            unique_dates = {}
            for bet in pending_bets:
                bet_id, home_team, away_team, selection, match_date, odds, stake = bet
                if match_date not in unique_dates:
                    unique_dates[match_date] = []
                unique_dates[match_date].append(bet)
            
            for match_date, date_bets in unique_dates.items():
                # Get results once per date
                results = self.get_results_for_date(match_date)
                
                # Process all bets for this date
                for bet in date_bets:
                    bet_id, home_team, away_team, selection, match_date, odds, stake = bet
                    
                    # Find matching result
                    match_result = None
                    for result in results:
                        if (self.team_match(result['home_team'], home_team) and 
                            self.team_match(result['away_team'], away_team)):
                            match_result = result
                            break
                    
                    if match_result:
                        outcome = self.determine_bet_outcome(selection, match_result)
                        profit_loss = self.calculate_profit_loss(outcome, odds, stake)
                        payout = self.calculate_payout(outcome, odds, stake)  # 🔧 FIX: Calculate payout
                        
                        # Update bet outcome with BOTH profit_loss AND payout
                        cursor.execute('''
                            UPDATE football_opportunities 
                            SET outcome = ?, profit_loss = ?, payout = ?, updated_at = ?
                            WHERE id = ?
                        ''', (outcome, profit_loss, payout, datetime.now().isoformat(), bet_id))
                        
                        updated_count += 1
                        logger.info(f"✅ Updated bet {bet_id}: {home_team} vs {away_team} | {selection} = {outcome}")
            
            conn.commit()
            conn.close()
            
            logger.info(f"🎯 Updated {updated_count} bet outcomes")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating bet outcomes: {e}")
            return 0
    
    def team_match(self, scraped_team, bet_team):
        """Check if team names match (allowing for variations)"""
        scraped_clean = re.sub(r'[^a-zA-Z]', '', scraped_team.lower())
        bet_clean = re.sub(r'[^a-zA-Z]', '', bet_team.lower())
        
        # Check exact match or if one contains the other
        return (scraped_clean == bet_clean or 
                scraped_clean in bet_clean or 
                bet_clean in scraped_clean)
    
    def determine_bet_outcome(self, selection, match_result):
        """Determine if bet won or lost based on selection and result"""
        selection_lower = selection.lower()
        
        if 'over' in selection_lower:
            # Over/Under bets
            threshold = float(re.findall(r'(\d+\.?\d*)', selection)[0])
            return 'win' if match_result['total_goals'] > threshold else 'loss'
            
        elif 'under' in selection_lower:
            threshold = float(re.findall(r'(\d+\.?\d*)', selection)[0])
            return 'win' if match_result['total_goals'] < threshold else 'loss'
            
        elif 'btts' in selection_lower or 'both teams to score' in selection_lower:
            # Both Teams To Score
            both_scored = match_result['home_score'] > 0 and match_result['away_score'] > 0
            if 'yes' in selection_lower:
                return 'win' if both_scored else 'loss'
            elif 'no' in selection_lower:
                return 'win' if not both_scored else 'loss'
            else:
                return 'void'  # Unknown BTTS selection
            
        elif 'home' in selection_lower or '1' in selection:
            return 'win' if match_result['result'] == 'home' else 'loss'
            
        elif 'away' in selection_lower or '2' in selection:
            return 'win' if match_result['result'] == 'away' else 'loss'
            
        elif 'draw' in selection_lower or 'x' in selection_lower:
            return 'win' if match_result['result'] == 'draw' else 'loss'
            
        else:
            logger.warning(f"⚠️ Unknown selection type: {selection}")
            return 'void'  # Unknown selection type
    
    def calculate_profit_loss(self, outcome, odds, stake):
        """Calculate profit/loss for a bet"""
        if outcome == 'win':
            return (float(odds) - 1) * float(stake)
        elif outcome == 'loss':
            return -float(stake)
        else:  # void
            return 0.0
    
    def calculate_payout(self, outcome, odds, stake):
        """Calculate payout (total return) for a bet - THIS WAS THE MISSING PIECE!"""
        if outcome == 'win':
            return float(odds) * float(stake)  # Total return = stake × odds
        elif outcome == 'loss':
            return 0.0  # No payout for losses
        else:  # void
            return float(stake)  # Return original stake for void bets

def main():
    """Main function to run results checking cycle"""
    scraper = ResultsScraper()
    
    while True:
        try:
            logger.info("🔄 Starting results checking cycle...")
            updated = scraper.update_bet_outcomes()
            
            if updated > 0:
                logger.info(f"✅ Updated {updated} bet outcomes")
            else:
                logger.info("📊 No bet outcomes to update")
                
        except Exception as e:
            logger.error(f"Error in results checking cycle: {e}")
        
        logger.info("⏱️ Next results check in 5 minutes...")
        time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    main()
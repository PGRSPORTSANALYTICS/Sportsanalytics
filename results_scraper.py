import trafilatura
import requests
import re
import sqlite3
import os
import json
from datetime import datetime, timedelta
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResultsScraper:
    def __init__(self, db_path='data/real_football.db'):
        self.db_path = db_path
        
    def get_flashscore_results(self, date_str):
        """Get results from Flashscore for a specific date using Selenium (YYYY-MM-DD)"""
        driver = None
        try:
            logger.info(f"🌐 Scraping Flashscore results for {date_str} with Selenium")
            
            # Configure Chrome for headless mode
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # Initialize driver
            driver = webdriver.Chrome(options=chrome_options)
            
            # Set page load timeout to prevent hanging (20 seconds max)
            driver.set_page_load_timeout(20)
            
            # Navigate to Flashscore date-specific URL
            url = f"https://www.flashscore.com/football/?d={date_str}"
            logger.info(f"📡 Loading: {url}")
            
            try:
                driver.get(url)
            except TimeoutException:
                logger.warning("⏱️ Page load timeout, continuing with partial content...")
            
            # Try to dismiss cookie banner if present
            try:
                cookie_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
                )
                cookie_button.click()
                logger.info("✅ Dismissed cookie banner")
            except:
                pass  # Banner not present or already dismissed
            
            # Wait for match elements to appear (max 10 seconds)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "event__match"))
                )
                logger.info("✅ Match elements loaded")
            except TimeoutException:
                logger.warning("⏱️ No match elements found, parsing what's available...")
            
            # Get page source after JS rendering
            html_content = driver.page_source
            
            # Parse results from rendered HTML
            results = self.parse_flashscore_html(html_content, date_str)
            
            logger.info(f"✅ Found {len(results)} matches from Flashscore")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error scraping Flashscore with Selenium: {e}")
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def parse_flashscore_html(self, html_content, date_str):
        """Parse Flashscore HTML to extract finished match results"""
        results = []
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Flashscore uses specific classes for match elements
            # Look for finished matches with scores
            match_elements = soup.find_all('div', class_=re.compile(r'event__match|sportName'))
            
            # Also try to find score patterns in text
            text_content = soup.get_text()
            
            # Pattern: Team1 0 - 1 Team2 or Team1 2 Team2 3
            score_pattern = r'([A-Za-z\s\.]+?)\s+(\d+)\s*[-:]\s*(\d+)\s+([A-Za-z\s\.]+?)(?:\n|$|[A-Z])'
            matches = re.findall(score_pattern, text_content)
            
            for match in matches:
                home_team = match[0].strip()
                home_score = int(match[1])
                away_score = int(match[2])
                away_team = match[3].strip()
                
                # Skip if team names are too short (likely noise)
                if len(home_team) < 3 or len(away_team) < 3:
                    continue
                
                # Skip if contains numbers (likely noise)
                if any(char.isdigit() for char in home_team + away_team):
                    continue
                
                results.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': home_score,
                    'away_score': away_score,
                    'score': f"{home_score}-{away_score}",
                    'total_goals': home_score + away_score,
                    'result': 'home' if home_score > away_score else ('away' if away_score > home_score else 'draw'),
                    'source': 'flashscore'
                })
            
            # Remove duplicates
            unique_results = []
            seen = set()
            for result in results:
                key = (result['home_team'], result['away_team'], result['score'])
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)
            
            return unique_results
            
        except Exception as e:
            logger.error(f"Error parsing Flashscore HTML: {e}")
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
            
            # Major European leagues to check (covers 95% of matches)
            EUROPEAN_LEAGUES = [
                39, 40, 41, 42,  # England (EPL, Championship, League One, Two)
                61,  # France Ligue 1
                78,  # Germany Bundesliga
                135,  # Italy Serie A
                140,  # Spain La Liga
                88,  # Netherlands Eredivisie
                94,  # Portugal Primeira Liga
                106,  # Poland Ekstraklasa
                119,  # Denmark Superliga
                144,  # Belgium Pro League
                203,  # Turkey Super Lig
                2, 3, 848,  # Champions League, Europa League, Conference League
                113,  # Scottish Premiership
                179,  # Swedish Allsvenskan
                71,  # Brazilian Serie A
                253  # MLS (USA)
            ]
            
            all_results = []
            
            # Try both current and next season to handle transition periods
            for season in [2024, 2025]:
                for league_id in EUROPEAN_LEAGUES:
                    try:
                        params = {
                            'date': date_str,
                            'league': league_id,
                            'season': season,
                            'status': 'FT'  # Only finished matches
                        }
                        
                        response = requests.get(url, headers=headers, params=params, timeout=10)
                        
                        if response.status_code == 200:
                            data = response.json()
                            fixtures = data.get('response', [])
                            
                            for fixture in fixtures:
                                teams = fixture.get('teams', {})
                                goals = fixture.get('goals', {})
                                
                                home_team = teams.get('home', {}).get('name', '')
                                away_team = teams.get('away', {}).get('name', '')
                                home_score = goals.get('home')
                                away_score = goals.get('away')
                                
                                if home_score is not None and away_score is not None:
                                    all_results.append({
                                        'home_team': home_team,
                                        'away_team': away_team,
                                        'home_score': int(home_score),
                                        'away_score': int(away_score),
                                        'score': f"{int(home_score)}-{int(away_score)}",
                                        'total_goals': int(home_score) + int(away_score),
                                        'result': 'home' if home_score > away_score else ('away' if away_score > home_score else 'draw'),
                                        'source': 'api-football'
                                    })
                    except Exception as e:
                        continue  # Skip failed leagues
            
            # Remove duplicates (same match might appear in multiple seasons)
            unique_results = []
            seen = set()
            for result in all_results:
                key = (result['home_team'], result['away_team'], result['home_score'], result['away_score'])
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)
            
            logger.info(f"📊 Found {len(unique_results)} finished matches from API-Football")
            return unique_results
            
        except Exception as e:
            logger.error(f"❌ Error fetching API-Football results: {e}")
            return []
    
    def get_odds_api_results(self, date_str):
        """Get results from The Odds API scores endpoint for a specific date (YYYY-MM-DD)"""
        try:
            api_key = os.getenv('THE_ODDS_API_KEY')
            if not api_key:
                logger.warning("❌ No THE_ODDS_API_KEY found in environment")
                return []
            
            logger.info(f"🎯 Fetching The Odds API scores for {date_str}")
            
            # The Odds API sports to check
            sports = [
                'soccer_epl', 'soccer_efl_champ', 'soccer_spain_la_liga',
                'soccer_italy_serie_a', 'soccer_germany_bundesliga',
                'soccer_france_ligue_one', 'soccer_netherlands_eredivisie',
                'soccer_portugal_primeira_liga', 'soccer_belgium_first_div',
                'soccer_uefa_champs_league', 'soccer_uefa_europa_league'
            ]
            
            all_results = []
            
            for sport in sports:
                try:
                    url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores/"
                    params = {
                        'apiKey': api_key,
                        'daysFrom': 3,  # Check last 3 days
                        'dateFormat': 'iso'
                    }
                    
                    response = requests.get(url, params=params, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        for event in data:
                            # Only include completed events from the specific date
                            if event.get('completed', False):
                                commence_time = event.get('commence_time', '')
                                event_date = commence_time.split('T')[0] if 'T' in commence_time else ''
                                
                                # Match the requested date
                                if event_date == date_str:
                                    scores = event.get('scores', [])
                                    if len(scores) >= 2:
                                        home_team = scores[0].get('name', '')
                                        away_team = scores[1].get('name', '')
                                        home_score = scores[0].get('score')
                                        away_score = scores[1].get('score')
                                        
                                        if home_score is not None and away_score is not None:
                                            all_results.append({
                                                'home_team': home_team,
                                                'away_team': away_team,
                                                'home_score': int(home_score),
                                                'away_score': int(away_score),
                                                'score': f"{int(home_score)}-{int(away_score)}",
                                                'total_goals': int(home_score) + int(away_score),
                                                'result': 'home' if home_score > away_score else ('away' if away_score > home_score else 'draw'),
                                                'source': 'odds-api'
                                            })
                except Exception as e:
                    logger.debug(f"No scores from {sport}: {e}")
                    continue
            
            # Remove duplicates
            unique_results = []
            seen = set()
            for result in all_results:
                key = (result['home_team'], result['away_team'], result['home_score'], result['away_score'])
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)
            
            logger.info(f"🎯 Found {len(unique_results)} finished matches from The Odds API")
            return unique_results
            
        except Exception as e:
            logger.error(f"❌ Error fetching The Odds API scores: {e}")
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
            logger.info("📡 No results from API-Football, trying The Odds API...")
            results = self.get_odds_api_results(clean_date)
        
        if not results:
            logger.info("📡 No results from The Odds API, trying Sofascore...")
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
        # Normalize both teams - remove special chars, extra spaces, common prefixes
        def normalize(team):
            team = team.lower()
            # Remove common prefixes
            team = re.sub(r'^(fc|afc|bfc|cfc|dfc|ssc|sfc|ac|as|cd|cf|sd|us|sv|vfb|fk|hsk|nk|sk|gks|mks|ks|lks|standard|royal|racing|sporting|athletic)\s+', '', team)
            # Remove special characters but keep letters and numbers
            team = re.sub(r'[^a-z0-9]', '', team)
            return team
        
        scraped_norm = normalize(scraped_team)
        bet_norm = normalize(bet_team)
        
        # Exact match after normalization
        if scraped_norm == bet_norm:
            return True
        
        # One contains the other (handles shortened names)
        if scraped_norm in bet_norm or bet_norm in scraped_norm:
            return True
        
        # Check if main city/club name matches (first significant word)
        def get_main_name(team):
            words = team.lower().split()
            # Skip common prefixes
            skip_words = ['fc', 'afc', 'bfc', 'ac', 'as', 'cd', 'cf', 'sd', 'us', 'sv', 'vfb', 'fk', 'standard', 'royal', 'racing', 'sporting']
            for word in words:
                if word not in skip_words and len(word) > 2:
                    return word
            return words[0] if words else ''
        
        scraped_main = get_main_name(scraped_team)
        bet_main = get_main_name(bet_team)
        
        if scraped_main and bet_main and scraped_main == bet_main:
            return True
        
        return False
    
    def determine_bet_outcome(self, selection, match_result):
        """Determine if bet won or lost based on selection and result"""
        selection_lower = selection.lower()
        
        # Exact Score predictions
        if 'exact score' in selection_lower or 'correct score' in selection_lower:
            # Extract predicted score (e.g., "Exact Score: 2-1" -> 2, 1)
            score_match = re.search(r'(\d+)-(\d+)', selection)
            if score_match:
                predicted_home = int(score_match.group(1))
                predicted_away = int(score_match.group(2))
                actual_home = match_result['home_score']
                actual_away = match_result['away_score']
                
                # Win if exact match, loss otherwise
                if predicted_home == actual_home and predicted_away == actual_away:
                    logger.info(f"✅ EXACT SCORE WIN: Predicted {predicted_home}-{predicted_away}, Actual {actual_home}-{actual_away}")
                    return 'win'
                else:
                    logger.info(f"❌ EXACT SCORE LOSS: Predicted {predicted_home}-{predicted_away}, Actual {actual_home}-{actual_away}")
                    return 'loss'
            else:
                logger.warning(f"⚠️ Could not parse exact score from: {selection}")
                return 'void'
        
        elif 'over' in selection_lower:
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
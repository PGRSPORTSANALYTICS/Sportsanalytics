import trafilatura
import requests
import re
import psycopg2
import os
import json
from datetime import datetime, timedelta
import time
import logging
from typing import Optional, List
from db_helper import db_helper
from team_name_mapper import TeamNameMapper
from telegram_sender import TelegramBroadcaster
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def normalize_result(raw_result: Optional[str]) -> str:
    """
    Normalize all possible result variants to: WON, LOST, PENDING, VOID.
    Supports English and Swedish terminology.
    """
    if raw_result is None:
        return "PENDING"

    s = raw_result.strip().lower()

    win_keywords = [
        "won", "win", "wins", "winner",
        "vinst", "vunnit", "vinna", "green",
        "success"
    ]

    loss_keywords = [
        "lost", "loss", "förlust",
        "förlorat", "red"
    ]

    void_keywords = [
        "void", "push", "refunded",
        "money back", "pushed", "voided",
        "tie", "draw", "oavgjort"
    ]

    if any(k in s for k in win_keywords):
        return "WON"
    if any(k in s for k in loss_keywords):
        return "LOST"
    if any(k in s for k in void_keywords):
        return "VOID"

    if s in ["pending", "open", "not settled", "running", "live", ""]:
        return "PENDING"

    return "PENDING"

class ResultsScraper:
    def __init__(self, db_path='data/real_football.db'):
        self.db_path = db_path
        self.team_mapper = TeamNameMapper()
        self._init_cache_db()
        self._init_verification_tracking()
        self._init_telegram()
        self.settled_bets_buffer: List[dict] = []
    
    def _init_telegram(self):
        """Initialize Telegram broadcaster for result notifications"""
        try:
            self.telegram = TelegramBroadcaster()
            self.telegram_channel = self.telegram.get_channel('exact_score')
            logger.info(f"✅ Telegram initialized for result notifications (channel: {self.telegram_channel})")
        except Exception as e:
            logger.warning(f"⚠️ Telegram not available: {e}")
            self.telegram = None
            self.telegram_channel = None
    
    def _send_result_notification(self, bet_info: dict):
        """Send Telegram notification when a bet is settled"""
        if not self.telegram or not self.telegram_channel:
            return
        
        try:
            outcome = bet_info.get('outcome', '').upper()
            home_team = bet_info.get('home_team', 'Unknown')
            away_team = bet_info.get('away_team', 'Unknown')
            selection = bet_info.get('selection', '')
            actual_score = bet_info.get('actual_score', '?-?')
            odds = bet_info.get('odds', 0)
            stake = bet_info.get('stake', 0)
            profit_loss = bet_info.get('profit_loss', 0)
            
            if outcome == 'WIN':
                emoji = "✅"
                status = "WON"
                color_emoji = "🟢"
            else:
                emoji = "❌"
                status = "LOST"
                color_emoji = "🔴"
            
            message = f"""{emoji} RESULT: {status}

⚽ {home_team} vs {away_team}
📊 Final Score: {actual_score}
🎯 Our Pick: {selection}
💰 Odds: {odds:.2f}

{color_emoji} P/L: ${profit_loss/10.8:+.0f} ({profit_loss:+.0f} SEK)
"""
            self.telegram.send_message(self.telegram_channel, message)
            logger.info(f"📱 Sent result notification: {home_team} vs {away_team} = {status}")
        except Exception as e:
            logger.error(f"❌ Failed to send result notification: {e}")
    
    def _send_batch_results(self):
        """Send batch summary of all settled bets"""
        if not self.telegram or not self.telegram_channel or not self.settled_bets_buffer:
            return
        
        try:
            wins = [b for b in self.settled_bets_buffer if b.get('outcome', '').upper() == 'WIN']
            losses = [b for b in self.settled_bets_buffer if b.get('outcome', '').upper() == 'LOSS']
            
            total_profit = sum(b.get('profit_loss', 0) for b in self.settled_bets_buffer)
            total_profit_usd = total_profit / 10.8
            
            message = f"""📊 RESULTS UPDATE

✅ Wins: {len(wins)}
❌ Losses: {len(losses)}

💰 Session P/L: ${total_profit_usd:+.0f} ({total_profit:+.0f} SEK)

"""
            for bet in self.settled_bets_buffer:
                outcome = bet.get('outcome', '').upper()
                emoji = "✅" if outcome == 'WIN' else "❌"
                home = bet.get('home_team', '')[:15]
                away = bet.get('away_team', '')[:15]
                score = bet.get('actual_score', '?-?')
                message += f"{emoji} {home} vs {away}: {score}\n"
            
            self.telegram.send_message(self.telegram_channel, message)
            logger.info(f"📱 Sent batch results: {len(self.settled_bets_buffer)} bets")
            self.settled_bets_buffer = []
        except Exception as e:
            logger.error(f"❌ Failed to send batch results: {e}")
    
    def _init_cache_db(self):
        """Initialize results cache database (PostgreSQL version)"""
        logger.info("✅ Match results cache initialized")
    
    def _init_verification_tracking(self):
        """Initialize verification tracking to avoid redundant checks (PostgreSQL version)"""
        logger.info("✅ Verification tracking initialized")
    
    def _get_cached_match_result(self, home_team, away_team, date_str):
        """Get cached result for a specific match if available and fresh"""
        try:
            # Normalize team names for cache lookup
            home_norm = self._normalize_team_for_cache(home_team)
            away_norm = self._normalize_team_for_cache(away_team)
            
            row = db_helper.execute('''
                SELECT home_score, away_score, source, cached_at
                FROM match_results_cache
                WHERE home_team = %s AND away_team = %s AND match_date = %s
            ''', (home_norm, away_norm, date_str), fetch='one')
            
            if row:
                home_score, away_score, source, cached_at = row
                cached_time = datetime.fromisoformat(cached_at)
                age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                
                # Cache is valid for 24 hours
                if age_hours < 24:
                    return {
                        'home_team': home_team,
                        'away_team': away_team,
                        'home_score': home_score,
                        'away_score': away_score,
                        'score': f"{home_score}-{away_score}",
                        'total_goals': home_score + away_score,
                        'result': 'home' if home_score > away_score else ('away' if away_score > home_score else 'draw'),
                        'source': f'{source}-cached'
                    }
            
            return None
        except Exception as e:
            logger.error(f"Error reading match cache: {e}")
            return None
    
    def _save_match_result(self, match_result, date_str, source):
        """Save individual match result to cache"""
        try:
            home_norm = self._normalize_team_for_cache(match_result['home_team'])
            away_norm = self._normalize_team_for_cache(match_result['away_team'])
            
            db_helper.execute('''
                INSERT INTO match_results_cache 
                (home_team, away_team, match_date, home_score, away_score, cached_at, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (home_team, away_team, match_date) 
                DO UPDATE SET home_score = EXCLUDED.home_score, 
                              away_score = EXCLUDED.away_score, 
                              cached_at = EXCLUDED.cached_at,
                              source = EXCLUDED.source
            ''', (home_norm, away_norm, date_str, 
                  match_result['home_score'], match_result['away_score'],
                  datetime.now().isoformat(), source))
        except Exception as e:
            logger.error(f"Error saving match cache: {e}")
    
    def _normalize_team_for_cache(self, team_name):
        """Normalize team name for cache key consistency using centralized mapper"""
        return self.team_mapper.standardize(team_name)
    
    def _should_check_bet(self, bet_id):
        """Check if enough time has passed since last verification (5 min cooldown for faster results)"""
        try:
            row = db_helper.execute('''
                SELECT last_checked_at FROM verification_tracking WHERE bet_id = %s
            ''', (bet_id,), fetch='one')
            
            if row:
                last_checked = datetime.fromisoformat(row[0])
                minutes_since = (datetime.now() - last_checked).total_seconds() / 60
                
                # 5 minute cooldown (reduced from 30 for faster result fetching)
                if minutes_since < 5:
                    logger.debug(f"⏭️ Skipping bet {bet_id} (checked {minutes_since:.1f}m ago)")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Error checking verification tracking: {e}")
            return True  # Check on error to be safe
    
    def _mark_bet_checked(self, bet_id):
        """Mark bet as checked"""
        try:
            db_helper.execute('''
                INSERT INTO verification_tracking (bet_id, last_checked_at)
                VALUES (%s, %s)
                ON CONFLICT (bet_id) DO UPDATE SET last_checked_at = EXCLUDED.last_checked_at
            ''', (bet_id, datetime.now().isoformat()))
        except Exception as e:
            logger.error(f"Error marking bet checked: {e}")
        
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
        """Get results from Sofascore JSON API for a specific date (YYYY-MM-DD)"""
        try:
            logger.info(f"Scraping Sofascore results for {date_str}")
            
            url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Origin': 'https://www.sofascore.com',
                'Referer': 'https://www.sofascore.com/'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Sofascore API returned status {response.status_code}")
                return []
            
            data = response.json()
            events = data.get('events', [])
            
            results = []
            for event in events:
                # Only process finished matches
                if event.get('status', {}).get('type') != 'finished':
                    continue
                
                home_team = event.get('homeTeam', {}).get('name', '')
                away_team = event.get('awayTeam', {}).get('name', '')
                home_score = event.get('homeScore', {}).get('current')
                away_score = event.get('awayScore', {}).get('current')
                
                if home_score is not None and away_score is not None:
                    results.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'home_score': home_score,
                        'away_score': away_score,
                        'score': f"{home_score}-{away_score}",
                        'total_goals': home_score + away_score,
                        'result': 'home' if home_score > away_score else ('away' if away_score > home_score else 'draw'),
                        'source': 'sofascore'
                    })
            
            logger.info(f"📊 Found {len(results)} finished matches from Sofascore")
            return results
            
        except Exception as e:
            logger.error(f"Error fetching Sofascore results: {e}")
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
        """Get results from multiple sources for a date - OPTIMIZED FOR SPEED"""
        logger.info(f"⚡ FAST getting results for {date_str}")
        
        # Extract just the date part if timestamp is included
        if 'T' in date_str or len(date_str) > 10:
            clean_date = date_str.split('T')[0]
        else:
            clean_date = date_str
        
        # PRIORITY 1: The Odds API (FASTEST - single request per sport, returns immediately)
        results = self.get_odds_api_results(clean_date)
        
        if results:
            logger.info(f"⚡ Got {len(results)} results from The Odds API (fast path)")
            return results
        
        # PRIORITY 2: Sofascore API (fast JSON endpoint)
        logger.info("📡 The Odds API empty, trying Sofascore...")
        results = self.get_sofascore_results(clean_date)
        
        if results:
            logger.info(f"📊 Got {len(results)} results from Sofascore")
            return results
        
        # PRIORITY 3: API-Football (slower - loops through leagues, uses quota)
        logger.info("📡 Sofascore empty, trying API-Football...")
        results = self.get_api_football_results(clean_date)
        
        logger.info(f"📊 Found {len(results)} total results for {clean_date}")
        return results
    
    def update_bet_outcomes(self):
        """Update bet outcomes based on scraped results"""
        logger.info("🔄 Checking bet outcomes...")
        
        try:
            # Use db_helper for fetching pending bets
            pending_bets = db_helper.execute('''
                SELECT id, home_team, away_team, selection, match_date, odds, stake
                FROM football_opportunities 
                WHERE (outcome IS NULL OR outcome = '') 
                  AND match_date IS NOT NULL 
                  AND match_date != ''
                  AND DATE(match_date) <= CURRENT_DATE
                ORDER BY match_date
            ''', fetch='all')
            logger.info(f"Found {len(pending_bets)} pending bets to check")
            
            updated_count = 0
            
            # Filter bets using cooldown (don't check same bet within 30 min)
            bets_to_check = []
            skipped_count = 0
            for bet in pending_bets:
                bet_id = bet[0]
                if self._should_check_bet(bet_id):
                    bets_to_check.append(bet)
                else:
                    skipped_count += 1
            
            if skipped_count > 0:
                logger.info(f"⏭️ Skipped {skipped_count} bets (checked recently)")
            
            if not bets_to_check:
                logger.info("✅ No bets need checking right now (all on cooldown)")
                return 0
            
            logger.info(f"🔍 Checking {len(bets_to_check)} bets")
            
            # Process bets with per-match caching and smart fallback
            cache_hits = 0
            bets_needing_fetch = {}  # Group by date for efficient fetching
            
            for bet in bets_to_check:
                bet_id, home_team, away_team, selection, match_date, odds, stake = bet
                clean_date = match_date.split('T')[0] if 'T' in match_date else match_date
                
                # Check per-match cache first
                cached_result = self._get_cached_match_result(home_team, away_team, clean_date)
                
                if cached_result:
                    # Cache hit - update immediately
                    cache_hits += 1
                    outcome = self.determine_bet_outcome(selection, cached_result)
                    profit_loss = self.calculate_profit_loss(outcome, odds, stake)
                    payout = self.calculate_payout(outcome, odds, stake)
                    
                    actual_score = f"{cached_result.get('home_score', 0)}-{cached_result.get('away_score', 0)}"
                    db_helper.execute('''
                        UPDATE football_opportunities 
                        SET outcome = %s, result = %s, profit_loss = %s, payout = %s, 
                            actual_score = %s, status = 'settled', updated_at = %s
                        WHERE id = %s
                    ''', (outcome, outcome, profit_loss, payout, actual_score, datetime.now().isoformat(), bet_id))
                    
                    updated_count += 1
                    self._mark_bet_checked(bet_id)  # Mark cooldown after success
                    logger.info(f"✅ Updated bet {bet_id} from cache: {home_team} vs {away_team} | {selection} = {outcome} (Score: {actual_score})")
                    
                    # Send Telegram notification
                    self._send_result_notification({
                        'outcome': outcome,
                        'home_team': home_team,
                        'away_team': away_team,
                        'selection': selection,
                        'actual_score': actual_score,
                        'odds': odds,
                        'stake': stake,
                        'profit_loss': profit_loss
                    })
                else:
                    # Cache miss - need to fetch
                    if clean_date not in bets_needing_fetch:
                        bets_needing_fetch[clean_date] = []
                    bets_needing_fetch[clean_date].append(bet)
            
            if cache_hits > 0:
                logger.info(f"💾 {cache_hits} bets resolved from cache (saved API calls)")
            
            # Fetch results only for cache misses
            for match_date, date_bets in bets_needing_fetch.items():
                logger.info(f"🌐 Fetching results for {match_date} ({len(date_bets)} bets)")
                results = self.get_results_for_date(match_date)
                
                # Process each bet
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
                        # Cache this result for future use
                        self._save_match_result(match_result, match_date.split('T')[0], match_result.get('source', 'unknown'))
                        
                        outcome = self.determine_bet_outcome(selection, match_result)
                        profit_loss = self.calculate_profit_loss(outcome, odds, stake)
                        payout = self.calculate_payout(outcome, odds, stake)
                        actual_score = f"{match_result.get('home_score', 0)}-{match_result.get('away_score', 0)}"
                        
                        db_helper.execute('''
                            UPDATE football_opportunities 
                            SET outcome = %s, result = %s, profit_loss = %s, payout = %s,
                                actual_score = %s, status = 'settled', updated_at = %s
                            WHERE id = %s
                        ''', (outcome, outcome, profit_loss, payout, actual_score, datetime.now().isoformat(), bet_id))
                        
                        updated_count += 1
                        self._mark_bet_checked(bet_id)  # Mark cooldown only after success
                        logger.info(f"✅ Updated bet {bet_id}: {home_team} vs {away_team} | {selection} = {outcome} (Score: {actual_score})")
                        
                        # Send Telegram notification
                        self._send_result_notification({
                            'outcome': outcome,
                            'home_team': home_team,
                            'away_team': away_team,
                            'selection': selection,
                            'actual_score': actual_score,
                            'odds': odds,
                            'stake': stake,
                            'profit_loss': profit_loss
                        })
                    else:
                        # No result found - mark checked to avoid immediate retry
                        self._mark_bet_checked(bet_id)
                        logger.debug(f"⏭️ No result yet for bet {bet_id}: {home_team} vs {away_team}")
            
            logger.info(f"🎯 Updated {updated_count} bet outcomes")
            
            # Update training data with results
            self._update_training_data_results()
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating bet outcomes: {e}")
            return 0
    
    def _update_training_data_results(self):
        """Update training_data table with actual match results for AI learning"""
        try:
            # Find training records that need results (match already played)
            pending_training = db_helper.execute('''
                SELECT id, home_team, away_team, match_date, predicted_score
                FROM training_data 
                WHERE actual_score IS NULL
                  AND match_date IS NOT NULL
                  AND match_date::date <= CURRENT_DATE
                ORDER BY match_date
                LIMIT 100
            ''', fetch='all')
            
            if not pending_training:
                return
            
            logger.info(f"🧠 Updating {len(pending_training)} training data records with results...")
            
            updated_count = 0
            for record in pending_training:
                record_id, home_team, away_team, match_date, predicted_score = record
                clean_date = str(match_date).split('T')[0] if match_date else ''
                
                # Check cache for result
                cached_result = self._get_cached_match_result(home_team, away_team, clean_date)
                
                if cached_result:
                    home_score = cached_result.get('home_score', 0)
                    away_score = cached_result.get('away_score', 0)
                    actual_score = f"{home_score}-{away_score}"
                    
                    # Check if prediction was correct
                    prediction_correct = (predicted_score == actual_score) if predicted_score else False
                    
                    db_helper.execute('''
                        UPDATE training_data 
                        SET actual_home_goals = %s,
                            actual_away_goals = %s,
                            actual_score = %s,
                            prediction_correct = %s
                        WHERE id = %s
                    ''', (home_score, away_score, actual_score, prediction_correct, record_id))
                    
                    updated_count += 1
            
            if updated_count > 0:
                logger.info(f"🧠 AI LEARNING: Updated {updated_count} training records with actual results")
                
        except Exception as e:
            logger.warning(f"⚠️ Training data update error: {e}")
    
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
"""
SofaScore Web Scraper for H2H and Recent Form Data
Provides fallback when API-Football is unavailable
"""

import requests
import sqlite3
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class SofaScoreScraper:
    """Scrapes H2H and recent form data from SofaScore"""
    
    BASE_URL = "https://api.sofascore.com/api/v1"
    
    LEAGUE_IDS = {
        'Premier League': 17,
        'La Liga': 8,
        'Serie A': 23,
        'Bundesliga': 35,
        'Ligue 1': 34,
        'Champions League': 7
    }
    
    def __init__(self, db_path: str = "data/real_football.db"):
        self.db_path = db_path
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Origin': 'https://www.sofascore.com',
            'Referer': 'https://www.sofascore.com/'
        }
        self.last_request_time = 0
        self._init_cache_db()
        
    def _init_cache_db(self):
        """Initialize cache database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sofascore_h2h_cache (
                team1 TEXT,
                team2 TEXT,
                league TEXT,
                match_date TEXT,
                home_team TEXT,
                away_team TEXT,
                home_score INTEGER,
                away_score INTEGER,
                tournament TEXT,
                scraped_at TEXT,
                PRIMARY KEY (team1, team2, match_date)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sofascore_form_cache (
                team TEXT,
                league TEXT,
                match_date TEXT,
                opponent TEXT,
                home_away TEXT,
                score TEXT,
                result TEXT,
                scraped_at TEXT,
                PRIMARY KEY (team, match_date)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sofascore_team_ids (
                team_name TEXT PRIMARY KEY,
                team_id INTEGER,
                league TEXT,
                cached_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ SofaScore cache database initialized")
    
    def _rate_limit(self, min_delay: float = 2.0):
        """Rate limiting to avoid getting blocked"""
        elapsed = time.time() - self.last_request_time
        if elapsed < min_delay:
            sleep_time = min_delay - elapsed
            logger.debug(f"💤 Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def _make_request(self, endpoint: str, retry_count: int = 3) -> Optional[dict]:
        """Make API request with retries and error handling"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        for attempt in range(retry_count):
            try:
                self._rate_limit()
                response = requests.get(url, headers=self.headers, timeout=10)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"⚠️ Not found: {endpoint}")
                    return None
                elif response.status_code == 403:
                    logger.warning(f"⚠️ Blocked by Cloudflare, waiting longer...")
                    time.sleep(5 * (attempt + 1))
                else:
                    logger.warning(f"⚠️ Status {response.status_code} for {endpoint}")
                    
            except Exception as e:
                logger.warning(f"⚠️ Request failed (attempt {attempt + 1}): {e}")
                if attempt < retry_count - 1:
                    time.sleep(2 * (attempt + 1))
        
        return None
    
    def get_team_id(self, team_name: str, league: str, use_cache: bool = True) -> Optional[int]:
        """Get SofaScore team ID by name"""
        
        if use_cache:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT team_id FROM sofascore_team_ids WHERE team_name = ? AND league = ?',
                (team_name, league)
            )
            result = cursor.fetchone()
            conn.close()
            
            if result:
                logger.debug(f"📦 Using cached team ID for {team_name}: {result[0]}")
                return result[0]
        
        endpoint = f"search/{team_name.replace(' ', '%20')}"
        data = self._make_request(endpoint)
        
        if data and 'results' in data:
            for result in data['results']:
                if result.get('type') == 'team':
                    team_id = result['entity']['id']
                    
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO sofascore_team_ids (team_name, team_id, league, cached_at)
                        VALUES (?, ?, ?, ?)
                    ''', (team_name, team_id, league, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                    conn.commit()
                    conn.close()
                    
                    logger.info(f"✅ Found team ID for {team_name}: {team_id}")
                    return team_id
        
        logger.warning(f"⚠️ Could not find team ID for {team_name}")
        return None
    
    def get_h2h_data(self, team1: str, team2: str, league: str, use_cache: bool = True) -> List[Dict]:
        """Get head-to-head match history between two teams"""
        
        if use_cache:
            cached = self._get_cached_h2h(team1, team2, max_age_hours=24)
            if cached:
                logger.info(f"📦 Using cached H2H data for {team1} vs {team2} ({len(cached)} matches)")
                return cached
        
        team1_form = self.get_team_form(team1, league, last_n=20, use_cache=use_cache)
        team2_form = self.get_team_form(team2, league, last_n=20, use_cache=use_cache)
        
        h2h_matches = []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        scraped_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for match1 in team1_form:
            if match1['opponent'] == team2:
                home_team = team1 if match1['home_away'] == 'H' else team2
                away_team = team2 if match1['home_away'] == 'H' else team1
                score_parts = match1['score'].split('-')
                
                if match1['home_away'] == 'H':
                    home_score = int(score_parts[0])
                    away_score = int(score_parts[1])
                else:
                    home_score = int(score_parts[1])
                    away_score = int(score_parts[0])
                
                h2h_match = {
                    'date': match1['date'],
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': home_score,
                    'away_score': away_score,
                    'tournament': league
                }
                h2h_matches.append(h2h_match)
                
                cursor.execute('''
                    INSERT OR REPLACE INTO sofascore_h2h_cache 
                    (team1, team2, league, match_date, home_team, away_team, home_score, away_score, tournament, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (team1, team2, league, h2h_match['date'], home_team, away_team,
                      home_score, away_score, league, scraped_at))
        
        conn.commit()
        conn.close()
        
        h2h_matches.sort(key=lambda x: x['date'], reverse=True)
        logger.info(f"✅ Found {len(h2h_matches)} H2H matches for {team1} vs {team2}")
        return h2h_matches
    
    def _get_cached_h2h(self, team1: str, team2: str, max_age_hours: int = 24) -> List[Dict]:
        """Get cached H2H data if fresh enough"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cutoff_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            SELECT match_date, home_team, away_team, home_score, away_score, tournament
            FROM sofascore_h2h_cache
            WHERE ((team1 = ? AND team2 = ?) OR (team1 = ? AND team2 = ?))
            AND scraped_at > ?
            ORDER BY match_date DESC
        ''', (team1, team2, team2, team1, cutoff_str))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            return []
        
        matches = []
        for row in results:
            matches.append({
                'date': row[0],
                'home_team': row[1],
                'away_team': row[2],
                'home_score': row[3],
                'away_score': row[4],
                'tournament': row[5]
            })
        
        return matches
    
    def get_team_form(self, team: str, league: str, last_n: int = 5, use_cache: bool = True) -> List[Dict]:
        """Get team's recent form (last N matches)"""
        
        if use_cache:
            cached = self._get_cached_form(team, max_age_hours=12)
            if cached and len(cached) >= last_n:
                logger.info(f"📦 Using cached form data for {team} ({len(cached)} matches)")
                return cached[:last_n]
        
        team_id = self.get_team_id(team, league)
        if not team_id:
            logger.error(f"❌ Could not find team ID for {team}")
            return []
        
        endpoint = f"team/{team_id}/events/last/{last_n * 2}"
        data = self._make_request(endpoint)
        
        if not data or 'events' not in data:
            logger.warning(f"⚠️ No form data found for {team}")
            return []
        
        matches = []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        scraped_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for event in data['events'][:last_n]:
            home_team = event.get('homeTeam', {}).get('name', '')
            away_team = event.get('awayTeam', {}).get('name', '')
            home_score = event.get('homeScore', {}).get('current', 0)
            away_score = event.get('awayScore', {}).get('current', 0)
            
            is_home = home_team == team
            opponent = away_team if is_home else home_team
            
            if is_home:
                result = 'W' if home_score > away_score else 'D' if home_score == away_score else 'L'
            else:
                result = 'W' if away_score > home_score else 'D' if home_score == away_score else 'L'
            
            match = {
                'date': datetime.fromtimestamp(event.get('startTimestamp')).strftime('%Y-%m-%d'),
                'opponent': opponent,
                'home_away': 'H' if is_home else 'A',
                'score': f"{home_score}-{away_score}",
                'result': result
            }
            
            if event.get('status', {}).get('type') == 'finished':
                matches.append(match)
                
                cursor.execute('''
                    INSERT OR REPLACE INTO sofascore_form_cache 
                    (team, league, match_date, opponent, home_away, score, result, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (team, league, match['date'], opponent, match['home_away'], 
                      match['score'], result, scraped_at))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Scraped {len(matches)} recent matches for {team}")
        return matches
    
    def _get_cached_form(self, team: str, max_age_hours: int = 12) -> List[Dict]:
        """Get cached form data if fresh enough"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cutoff_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            SELECT match_date, opponent, home_away, score, result
            FROM sofascore_form_cache
            WHERE team = ? AND scraped_at > ?
            ORDER BY match_date DESC
        ''', (team, cutoff_str))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            return []
        
        matches = []
        for row in results:
            matches.append({
                'date': row[0],
                'opponent': row[1],
                'home_away': row[2],
                'score': row[3],
                'result': row[4]
            })
        
        return matches
    
    def get_league_standings(self, league: str, use_cache: bool = True) -> List[Dict]:
        """Get current league standings"""
        
        league_id = self.LEAGUE_IDS.get(league)
        if not league_id:
            logger.warning(f"⚠️ Unknown league: {league}")
            return []
        
        endpoint = f"unique-tournament/{league_id}/season/current/standings/total"
        data = self._make_request(endpoint)
        
        if not data or 'standings' not in data:
            logger.warning(f"⚠️ No standings found for {league}")
            return []
        
        standings = []
        for standing_group in data['standings']:
            for row in standing_group.get('rows', []):
                team_data = {
                    'position': row.get('position'),
                    'team': row.get('team', {}).get('name', ''),
                    'played': row.get('matches', 0),
                    'wins': row.get('wins', 0),
                    'draws': row.get('draws', 0),
                    'losses': row.get('losses', 0),
                    'goals_for': row.get('scoresFor', 0),
                    'goals_against': row.get('scoresAgainst', 0),
                    'goal_difference': row.get('scoresFor', 0) - row.get('scoresAgainst', 0),
                    'points': row.get('points', 0)
                }
                standings.append(team_data)
        
        logger.info(f"✅ Scraped standings for {league} ({len(standings)} teams)")
        return standings
    
    def clear_old_cache(self, days: int = 30):
        """Clear cached data older than specified days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('DELETE FROM sofascore_h2h_cache WHERE scraped_at < ?', (cutoff_str,))
        h2h_deleted = cursor.rowcount
        
        cursor.execute('DELETE FROM sofascore_form_cache WHERE scraped_at < ?', (cutoff_str,))
        form_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"🗑️ Cleared {h2h_deleted} old H2H records and {form_deleted} old form records")
        return h2h_deleted + form_deleted
    
    def get_upcoming_fixtures(self, days_ahead: int = 7) -> List[Dict]:
        """
        Emergency fallback: Scrape upcoming fixtures from SofaScore
        Used when API quotas are exhausted
        """
        all_fixtures = []
        today = datetime.now()
        
        logger.info(f"🌐 EMERGENCY FALLBACK: Scraping fixtures from SofaScore (next {days_ahead} days)")
        
        for league_name, league_id in self.LEAGUE_IDS.items():
            try:
                endpoint = f"unique-tournament/{league_id}/season/current/events/next/0"
                data = self._make_request(endpoint)
                
                if not data or 'events' not in data:
                    continue
                
                for event in data['events']:
                    try:
                        start_timestamp = event.get('startTimestamp', 0)
                        match_time = datetime.fromtimestamp(start_timestamp)
                        
                        if match_time > today + timedelta(days=days_ahead):
                            continue
                        
                        home_team = event.get('homeTeam', {}).get('name', '')
                        away_team = event.get('awayTeam', {}).get('name', '')
                        
                        if not home_team or not away_team:
                            continue
                        
                        fixture = {
                            'id': event.get('id'),
                            'sport_key': f'sofascore_{league_id}',
                            'sport_title': league_name,
                            'league_name': league_name,
                            'commence_time': match_time.isoformat(),
                            'home_team': home_team,
                            'away_team': away_team,
                            'bookmakers': [],
                            'formatted_date': match_time.strftime('%Y-%m-%d'),
                            'formatted_time': match_time.strftime('%H:%M'),
                            'source': 'sofascore_scraper'
                        }
                        
                        all_fixtures.append(fixture)
                        
                    except Exception as e:
                        logger.debug(f"⚠️ Error parsing event: {e}")
                        continue
                
                logger.info(f"✅ Scraped {len([f for f in all_fixtures if f['league_name'] == league_name])} fixtures from {league_name}")
                
            except Exception as e:
                logger.warning(f"⚠️ Error scraping {league_name}: {e}")
                continue
        
        logger.info(f"🌐 EMERGENCY SCRAPING COMPLETE: {len(all_fixtures)} total fixtures")
        return all_fixtures


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    scraper = SofaScoreScraper()
    
    print("\n=== Testing H2H Data ===")
    h2h = scraper.get_h2h_data("Liverpool", "Manchester City", "Premier League")
    for match in h2h[:5]:
        print(f"{match['date']}: {match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']}")
    
    print("\n=== Testing Team Form ===")
    form = scraper.get_team_form("Liverpool", "Premier League", last_n=5)
    for match in form:
        print(f"{match['date']} ({match['home_away']}): vs {match['opponent']} - {match['score']} ({match['result']})")

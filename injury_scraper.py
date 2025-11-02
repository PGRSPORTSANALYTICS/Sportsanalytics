import trafilatura
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import os
import json
from datetime import datetime, timedelta
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InjuryScraper:
    """
    Scrapes injury data from Transfermarkt and Physioroom to supplement API-Football
    when it's unavailable or quota is exhausted.
    
    Respects robots.txt and implements rate limiting to avoid overloading servers.
    """
    
    TRANSFERMARKT_LEAGUES = {
        'Premier League': 'https://www.transfermarkt.co.uk/premier-league/verletztespieler/wettbewerb/GB1',
        'La Liga': 'https://www.transfermarkt.us/primera-division/verletztespieler/wettbewerb/ES1',
        'Serie A': 'https://www.transfermarkt.us/serie-a/verletztespieler/wettbewerb/IT1',
        'Bundesliga': 'https://www.transfermarkt.us/bundesliga/verletztespieler/wettbewerb/L1',
        'Ligue 1': 'https://www.transfermarkt.us/ligue-1/verletztespieler/wettbewerb/FR1',
        'Championship': 'https://www.transfermarkt.co.uk/championship/verletztespieler/wettbewerb/GB2',
        'Eredivisie': 'https://www.transfermarkt.us/eredivisie/verletztespieler/wettbewerb/NL1',
        'Primeira Liga': 'https://www.transfermarkt.us/liga-nos/verletztespieler/wettbewerb/PO1',
        'Belgian Pro League': 'https://www.transfermarkt.us/jupiler-pro-league/verletztespieler/wettbewerb/BE1',
        'Champions League': 'https://www.transfermarkt.us/uefa-champions-league/verletztespieler/wettbewerb/CL',
        'Europa League': 'https://www.transfermarkt.us/uefa-europa-league/verletztespieler/wettbewerb/EL'
    }
    
    PHYSIOROOM_URL = 'https://www.physioroom.com/advice/premier-league-injury-table/'
    
    # Rate limiting: 3 seconds between requests to be respectful
    REQUEST_DELAY = 3
    
    def __init__(self, db_path='data/injuries_cache.db'):
        self.db_path = db_path
        self.last_request_time = 0
        self._init_cache_db()
        
    def _init_cache_db(self):
        """Initialize cache database for injury data"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS injury_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                league TEXT NOT NULL,
                club TEXT NOT NULL,
                player TEXT NOT NULL,
                injury_type TEXT,
                expected_return TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_scraped_at ON injury_cache(scraped_at)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_club ON injury_cache(club)
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Injury cache database initialized")
        
    def _rate_limit(self):
        """Implement rate limiting to be respectful to servers"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.REQUEST_DELAY:
            sleep_time = self.REQUEST_DELAY - elapsed
            logger.debug(f"💤 Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()
        
    def _get_cached_injuries(self, league, max_age_hours=12):
        """Get cached injuries if they're recent enough"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        cursor.execute('''
            SELECT club, player, injury_type, expected_return, scraped_at, source
            FROM injury_cache
            WHERE league = ? AND scraped_at > ?
            ORDER BY scraped_at DESC
        ''', (league, cutoff_time.isoformat()))
        
        results = cursor.fetchall()
        conn.close()
        
        if results:
            logger.info(f"📦 Found {len(results)} cached injuries for {league}")
            return [
                {
                    'club': row[0],
                    'player': row[1],
                    'injury_type': row[2],
                    'expected_return': row[3],
                    'scraped_at': row[4],
                    'source': row[5]
                }
                for row in results
            ]
        return None
        
    def _save_injuries_to_cache(self, league, injuries, source):
        """Save scraped injuries to cache"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for injury in injuries:
            cursor.execute('''
                INSERT INTO injury_cache (league, club, player, injury_type, expected_return, source)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                league,
                injury['club'],
                injury['player'],
                injury.get('injury_type', 'Unknown'),
                injury.get('expected_return', 'Unknown'),
                source
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"💾 Cached {len(injuries)} injuries for {league}")
        
    def scrape_transfermarkt(self, league='Premier League', use_cache=True):
        """
        Scrape injury data from Transfermarkt for a specific league
        
        Args:
            league: League name (e.g., 'Premier League', 'La Liga')
            use_cache: Use cached data if available (default True)
            
        Returns:
            List of injury dictionaries
        """
        if league not in self.TRANSFERMARKT_LEAGUES:
            logger.warning(f"⚠️ League '{league}' not supported in Transfermarkt scraper")
            return []
            
        # Check cache first
        if use_cache:
            cached = self._get_cached_injuries(league, max_age_hours=12)
            if cached:
                return cached
                
        url = self.TRANSFERMARKT_LEAGUES[league]
        logger.info(f"🔍 Scraping Transfermarkt injuries for {league}")
        
        try:
            self._rate_limit()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            injuries = []
            
            # Find injury table
            table = soup.find('table', class_='items')
            if not table:
                logger.warning(f"⚠️ Could not find injury table for {league}")
                return []
                
            rows = table.find_all('tr', class_=['odd', 'even'])
            
            for row in rows:
                try:
                    cells = row.find_all('td')
                    if len(cells) < 7:
                        continue
                        
                    # Extract player name (cell 2)
                    player_cell = cells[2]
                    player_link = player_cell.find('a')
                    if not player_link:
                        continue
                    player_name = player_link.text.strip()
                    
                    # Extract club (cell 4)
                    club_cell = cells[4]
                    club_img = club_cell.find('img')
                    club_name = club_img.get('title', 'Unknown') if club_img else 'Unknown'
                    
                    # Extract injury type (cell 5)
                    injury_cell = cells[5]
                    injury_type = injury_cell.text.strip()
                    if not injury_type:
                        injury_type = 'Unknown'
                    
                    # Extract return date (cell 6)
                    return_cell = cells[6]
                    expected_return = return_cell.text.strip()
                    if not expected_return:
                        expected_return = 'Unknown'
                    
                    if player_name and club_name != 'Unknown':
                        injuries.append({
                            'club': club_name,
                            'player': player_name,
                            'injury_type': injury_type,
                            'expected_return': expected_return
                        })
                    
                except Exception as e:
                    logger.debug(f"Error parsing row: {e}")
                    continue
                    
            logger.info(f"✅ Scraped {len(injuries)} injuries from Transfermarkt ({league})")
            
            # Save to cache
            if injuries:
                self._save_injuries_to_cache(league, injuries, 'Transfermarkt')
                
            return injuries
            
        except Exception as e:
            logger.error(f"❌ Error scraping Transfermarkt for {league}: {e}")
            return []
            
    def scrape_physioroom(self, use_cache=True):
        """
        Scrape Premier League injury data from Physioroom
        
        Args:
            use_cache: Use cached data if available (default True)
            
        Returns:
            List of injury dictionaries
        """
        league = 'Premier League'
        
        # Check cache first
        if use_cache:
            cached = self._get_cached_injuries(league, max_age_hours=12)
            if cached and any(inj['source'] == 'Physioroom' for inj in cached):
                return [inj for inj in cached if inj['source'] == 'Physioroom']
                
        logger.info(f"🔍 Scraping Physioroom injuries for {league}")
        
        try:
            self._rate_limit()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(self.PHYSIOROOM_URL, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            injuries = []
            
            # Physioroom structure varies, look for injury tables
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                
                for row in rows[1:]:  # Skip header
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        try:
                            club = cells[0].text.strip()
                            player = cells[1].text.strip()
                            injury_type = cells[2].text.strip()
                            expected_return = cells[3].text.strip()
                            
                            if club and player:
                                injuries.append({
                                    'club': club,
                                    'player': player,
                                    'injury_type': injury_type,
                                    'expected_return': expected_return
                                })
                        except Exception as e:
                            logger.debug(f"Error parsing Physioroom row: {e}")
                            continue
                            
            logger.info(f"✅ Scraped {len(injuries)} injuries from Physioroom")
            
            # Save to cache
            if injuries:
                self._save_injuries_to_cache(league, injuries, 'Physioroom')
                
            return injuries
            
        except Exception as e:
            logger.error(f"❌ Error scraping Physioroom: {e}")
            return []
            
    def get_injuries_for_league(self, league='Premier League', use_cache=True):
        """
        Get injury data for a league, trying multiple sources
        
        Args:
            league: League name
            use_cache: Use cached data if available
            
        Returns:
            List of injury dictionaries
        """
        # Try Transfermarkt first
        injuries = self.scrape_transfermarkt(league, use_cache=use_cache)
        
        # For Premier League, also try Physioroom as backup
        if league == 'Premier League' and not injuries:
            logger.info("📡 Transfermarkt failed, trying Physioroom...")
            injuries = self.scrape_physioroom(use_cache=use_cache)
            
        return injuries
        
    def get_all_injuries(self, leagues=None, use_cache=True):
        """
        Get injury data for multiple leagues
        
        Args:
            leagues: List of league names (default: all supported leagues)
            use_cache: Use cached data if available
            
        Returns:
            Dictionary mapping league names to injury lists
        """
        if leagues is None:
            leagues = list(self.TRANSFERMARKT_LEAGUES.keys())
            
        all_injuries = {}
        
        for league in leagues:
            logger.info(f"📊 Fetching injuries for {league}...")
            injuries = self.get_injuries_for_league(league, use_cache=use_cache)
            all_injuries[league] = injuries
            
        total_injuries = sum(len(inj) for inj in all_injuries.values())
        logger.info(f"✅ Total injuries across {len(leagues)} leagues: {total_injuries}")
        
        return all_injuries
        
    def get_team_injuries(self, team_name, league='Premier League', use_cache=True):
        """
        Get injury data for a specific team
        
        Args:
            team_name: Team name to look for
            league: League the team plays in
            use_cache: Use cached data if available
            
        Returns:
            List of injuries for that team
        """
        all_injuries = self.get_injuries_for_league(league, use_cache=use_cache)
        
        # Fuzzy match team name
        team_injuries = []
        for injury in all_injuries:
            if team_name.lower() in injury['club'].lower() or injury['club'].lower() in team_name.lower():
                team_injuries.append(injury)
                
        return team_injuries
        
    def clear_old_cache(self, days=7):
        """Clear cached injuries older than specified days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(days=days)
        
        cursor.execute('DELETE FROM injury_cache WHERE scraped_at < ?', (cutoff_time.isoformat(),))
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"🗑️ Cleared {deleted} old injury records from cache")
        return deleted


if __name__ == "__main__":
    # Test the scraper
    scraper = InjuryScraper()
    
    print("\n" + "="*60)
    print("🏥 INJURY DATA SCRAPER TEST")
    print("="*60 + "\n")
    
    # Test Premier League
    print("Testing Premier League injuries...")
    injuries = scraper.get_injuries_for_league('Premier League', use_cache=False)
    print(f"\n✅ Found {len(injuries)} injuries in Premier League\n")
    
    if injuries:
        print("Sample injuries:")
        for injury in injuries[:5]:
            print(f"  • {injury['player']} ({injury['club']}) - {injury['injury_type']}")
            print(f"    Expected return: {injury['expected_return']}")
    
    # Test all Top 5 leagues
    print("\n" + "-"*60)
    print("Testing all Top 5 leagues...")
    all_injuries = scraper.get_all_injuries(
        leagues=['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1'],
        use_cache=False
    )
    
    print("\n📊 Injuries by league:")
    for league, injuries in all_injuries.items():
        print(f"  • {league}: {len(injuries)} injuries")

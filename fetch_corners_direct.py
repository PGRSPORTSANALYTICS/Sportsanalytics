"""
Directly fetch corner stats from API-Football for specific voided matches
"""

import os
import requests
import logging
from db_helper import db_helper
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.getenv('API_FOOTBALL_KEY')
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}

MAJOR_MATCHES = [
    ('Aston Villa', 'Manchester United', '2025-12-21'),
    ('Genoa', 'Atalanta BC', '2025-12-21'),
    ('Girona', 'Atlético Madrid', '2025-12-21'),
    ('Real Betis', 'Getafe', '2025-12-21'),
    ('Villarreal', 'Barcelona', '2025-12-21'),
    ('Sassuolo', 'Torino', '2025-12-21'),
    ('Feyenoord', 'FC Twente Enschede', '2025-12-21'),
    ('Club Brugge', 'Gent', '2025-12-21'),
    ('Cagliari', 'Pisa', '2025-12-21'),
]

def get_fixtures_for_date(date_str):
    """Get all fixtures for a date"""
    url = f"{BASE_URL}/fixtures"
    response = requests.get(url, headers=HEADERS, params={'date': date_str}, timeout=15)
    if response.status_code == 200:
        return response.json().get('response', [])
    return []

def get_fixture_statistics(fixture_id):
    """Get detailed statistics for a fixture including corners"""
    url = f"{BASE_URL}/fixtures/statistics"
    response = requests.get(url, headers=HEADERS, params={'fixture': fixture_id}, timeout=15)
    if response.status_code == 200:
        return response.json().get('response', [])
    return []

def parse_corners_from_stats(stats_response):
    """Extract corner counts from statistics response"""
    home_corners = None
    away_corners = None
    
    for team_stats in stats_response:
        team_name = team_stats.get('team', {}).get('name', '')
        statistics = team_stats.get('statistics', [])
        
        for stat in statistics:
            if stat.get('type') == 'Corner Kicks':
                value = stat.get('value')
                if value is not None:
                    if home_corners is None:
                        home_corners = int(value)
                    else:
                        away_corners = int(value)
    
    if home_corners is not None and away_corners is not None:
        return home_corners, away_corners
    return None, None

def find_fixture_id(fixtures, home_team, away_team):
    """Find fixture ID by team names (fuzzy match)"""
    home_lower = home_team.lower()
    away_lower = away_team.lower()
    
    for fixture in fixtures:
        teams = fixture.get('teams', {})
        api_home = teams.get('home', {}).get('name', '').lower()
        api_away = teams.get('away', {}).get('name', '').lower()
        
        # Fuzzy match
        if (home_lower in api_home or api_home in home_lower) and \
           (away_lower in api_away or api_away in away_lower):
            return fixture.get('fixture', {}).get('id')
    
    return None

def settle_bet(bet_id, outcome):
    """Mark bet as won or lost"""
    db_helper.execute('''
        UPDATE football_opportunities 
        SET outcome = %s, status = 'settled', 
            settled_timestamp = %s
        WHERE id = %s
    ''', (outcome, int(datetime.now().timestamp()), bet_id))

def evaluate_corner_bet(selection, home_corners, away_corners):
    """Evaluate corner bet outcome based on selection"""
    total = home_corners + away_corners
    selection_lower = selection.lower()
    
    # Total corners over/under
    if 'corners over' in selection_lower:
        try:
            threshold = float(selection_lower.split('over')[-1].strip().split()[0])
            return 'won' if total > threshold else 'lost'
        except:
            pass
    
    if 'corners under' in selection_lower:
        try:
            threshold = float(selection_lower.split('under')[-1].strip().split()[0])
            return 'won' if total < threshold else 'lost'
        except:
            pass
    
    # Team corners over/under
    for team_name, team_corners in [('home', home_corners), ('away', away_corners)]:
        pass  # Would need team name matching
    
    # Team handicaps
    if '+0.5' in selection_lower or '+1.5' in selection_lower or '+2.5' in selection_lower:
        # Parse team and handicap
        pass
    
    if '-0.5' in selection_lower or '-1.5' in selection_lower:
        pass
    
    return None

def main():
    # Get all fixtures for Dec 21
    logger.info("Fetching fixtures for 2025-12-21...")
    fixtures = get_fixtures_for_date('2025-12-21')
    logger.info(f"Found {len(fixtures)} fixtures")
    
    results = {}
    
    for home_team, away_team, date in MAJOR_MATCHES:
        logger.info(f"\n🔍 {home_team} vs {away_team}")
        
        fixture_id = find_fixture_id(fixtures, home_team, away_team)
        
        if fixture_id:
            logger.info(f"   Found fixture ID: {fixture_id}")
            stats = get_fixture_statistics(fixture_id)
            
            if stats:
                home_corners, away_corners = parse_corners_from_stats(stats)
                if home_corners is not None:
                    total = home_corners + away_corners
                    logger.info(f"   ✅ Corners: {home_team} {home_corners} - {away_corners} {away_team} (Total: {total})")
                    results[(home_team, away_team)] = {
                        'home': home_corners,
                        'away': away_corners,
                        'total': total
                    }
                else:
                    logger.warning(f"   ⚠️ No corner data in statistics")
            else:
                logger.warning(f"   ⚠️ No statistics available")
        else:
            logger.warning(f"   ❌ Fixture not found")
    
    # Print summary
    print("\n" + "="*60)
    print("CORNER RESULTS FOUND:")
    print("="*60)
    for (home, away), data in results.items():
        print(f"{home} {data['home']} - {data['away']} {away} (Total: {data['total']})")

if __name__ == "__main__":
    main()

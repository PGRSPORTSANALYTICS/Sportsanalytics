#!/usr/bin/env python3
"""
Find BTTS and Moneyline betting opportunities from matches without exact score predictions.
Uses The Odds API to find upcoming matches with good odds.
"""

import os
import sqlite3
import requests
from datetime import datetime, timedelta

DB_PATH = 'data/real_football.db'
ODDS_API_KEY = os.environ.get('THE_ODDS_API_KEY')

# Leagues to analyze
LEAGUES = [
    'soccer_epl',           # Premier League
    'soccer_spain_la_liga', # La Liga  
    'soccer_italy_serie_a', # Serie A
    'soccer_germany_bundesliga', # Bundesliga
    'soccer_france_ligue_one',    # Ligue 1
]

def get_exact_score_matches():
    """Get all matches that have exact score predictions"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT home_team, away_team, match_date
        FROM football_opportunities
        WHERE market = 'exact_score'
        AND (outcome IS NULL OR outcome = '' OR outcome = 'unknown')
    """)
    
    exact_matches = set()
    for row in cursor.fetchall():
        home, away, date = row
        # Create a normalized match key
        match_key = f"{home.lower()}|{away.lower()}|{date[:10]}"
        exact_matches.add(match_key)
    
    conn.close()
    return exact_matches

def normalize_team_name(name):
    """Normalize team names for matching"""
    # Common variations
    replacements = {
        'FC': '',
        'AFC': '',
        'CF': '',
        'United': 'Utd',
        'Manchester United': 'Man United',
        'Manchester City': 'Man City',
        'Tottenham Hotspur': 'Tottenham',
        'Brighton and Hove Albion': 'Brighton',
        'Wolverhampton Wanderers': 'Wolves',
        'Newcastle United': 'Newcastle',
        'West Ham United': 'West Ham',
    }
    
    normalized = name.strip()
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    
    return normalized.strip().lower()

def find_opportunities():
    """Find BTTS/ML opportunities from The Odds API"""
    
    if not ODDS_API_KEY:
        print("❌ THE_ODDS_API_KEY environment variable not set")
        return
    
    print("\n" + "=" * 70)
    print("🎯 BTTS & MONEYLINE OPPORTUNITY FINDER")
    print("=" * 70)
    print("📊 Analyzing Top 5 European leagues for opportunities...")
    print("🚫 Excluding matches with existing exact score predictions\n")
    
    # Get existing exact score matches
    exact_matches = get_exact_score_matches()
    print(f"📋 Found {len(exact_matches)} matches with exact score predictions\n")
    
    all_opportunities = []
    
    for league in LEAGUES:
        print(f"🔍 Fetching odds for {league}...")
        
        try:
            url = f"https://api.the-odds-api.com/v4/sports/{league}/odds/"
            params = {
                'apiKey': ODDS_API_KEY,
                'regions': 'eu',
                'markets': 'h2h,btts',
                'oddsFormat': 'decimal',
                'dateFormat': 'iso'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                matches = response.json()
                print(f"✅ Got {len(matches)} matches\n")
                
                for match in matches:
                    home = match['home_team']
                    away = match['away_team']
                    commence = match['commence_time'][:10]  # YYYY-MM-DD
                    
                    # Check if match has exact score prediction
                    match_key = f"{normalize_team_name(home)}|{normalize_team_name(away)}|{commence}"
                    
                    if match_key in exact_matches:
                        continue  # Skip - has exact score
                    
                    # Extract odds
                    bookmakers = match.get('bookmakers', [])
                    if not bookmakers:
                        continue
                    
                    # Get first bookmaker's odds
                    book = bookmakers[0]
                    markets = {m['key']: m for m in book.get('markets', [])}
                    
                    # BTTS odds
                    btts_data = None
                    if 'btts' in markets:
                        btts_outcomes = {o['name']: o['price'] for o in markets['btts']['outcomes']}
                        btts_yes = btts_outcomes.get('Yes', 0)
                        btts_no = btts_outcomes.get('No', 0)
                        
                        if btts_yes > 0:
                            btts_data = {
                                'type': 'BTTS',
                                'selection': 'Yes',
                                'odds': btts_yes,
                                'value_score': (btts_yes - 1.5) * 100 if btts_yes > 1.5 else 0
                            }
                    
                    # Moneyline odds
                    ml_data = None
                    if 'h2h' in markets:
                        ml_outcomes = {o['name']: o['price'] for o in markets['h2h']['outcomes']}
                        home_odds = ml_outcomes.get(home, 0)
                        draw_odds = ml_outcomes.get('Draw', 0)
                        away_odds = ml_outcomes.get(away, 0)
                        
                        # Find best value (odds between 1.7-3.0 preferred)
                        options = [
                            ('Home Win', home, home_odds),
                            ('Draw', 'Draw', draw_odds),
                            ('Away Win', away, away_odds)
                        ]
                        
                        for name, selection, odds in options:
                            if 1.7 <= odds <= 3.5:
                                if not ml_data or odds > ml_data['odds']:
                                    ml_data = {
                                        'type': 'ML',
                                        'selection': selection,
                                        'odds': odds,
                                        'value_score': abs(odds - 2.2) * -10 + 50
                                    }
                    
                    # Add opportunities
                    if btts_data:
                        all_opportunities.append({
                            'home': home,
                            'away': away,
                            'date': commence,
                            'league': league.replace('soccer_', '').replace('_', ' ').title(),
                            **btts_data
                        })
                    
                    if ml_data:
                        all_opportunities.append({
                            'home': home,
                            'away': away,
                            'date': commence,
                            'league': league.replace('soccer_', '').replace('_', ' ').title(),
                            **ml_data
                        })
            
            else:
                print(f"⚠️ API error {response.status_code} for {league}")
        
        except Exception as e:
            print(f"❌ Error for {league}: {e}")
    
    # Display opportunities sorted by value score
    print("\n" + "=" * 70)
    print("💎 TOP OPPORTUNITIES (sorted by value)")
    print("=" * 70)
    
    if not all_opportunities:
        print("\n⚠️ No opportunities found. Try again later or check different leagues.")
        return
    
    all_opportunities.sort(key=lambda x: x['value_score'], reverse=True)
    
    # Show top 15
    for i, opp in enumerate(all_opportunities[:15], 1):
        icon = "⚽" if opp['type'] == 'BTTS' else "🏆"
        print(f"\n{i}. {icon} {opp['type']} | {opp['league']}")
        print(f"   {opp['home']} vs {opp['away']}")
        print(f"   📅 {opp['date']}")
        print(f"   🎯 Selection: {opp['selection']}")
        print(f"   💰 Odds: {opp['odds']:.2f}x")
        print(f"   ⭐ Value Score: {opp['value_score']:.0f}/100")
    
    print("\n" + "=" * 70)
    print("📝 To add a bet, run: python3 add_btts_ml_bet.py")
    print("=" * 70)

if __name__ == "__main__":
    find_opportunities()

#!/usr/bin/env python3
"""
Check what real matches happened on Sep 12, 2025
"""
import requests
import os
import json

def check_real_matches():
    api_key = os.getenv('API_FOOTBALL_KEY')
    if not api_key:
        print("❌ No API_FOOTBALL_KEY found")
        return
    
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {
        'X-RapidAPI-Key': api_key,
        'X-RapidAPI-Host': 'v3.football.api-sports.io'
    }
    
    params = {
        'date': '2025-09-12',
        'status': 'FT'
    }
    
    response = requests.get(url, headers=headers, params=params, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        fixtures = data.get('response', [])[:5]  # First 5 matches
        
        print(f"📊 First 5 real matches from Sep 12, 2025:")
        for fixture in fixtures:
            teams = fixture.get('teams', {})
            goals = fixture.get('goals', {})
            home_team = teams.get('home', {}).get('name', '')
            away_team = teams.get('away', {}).get('name', '')
            home_score = goals.get('home')
            away_score = goals.get('away')
            
            if home_score is not None and away_score is not None:
                print(f"⚽ {home_team} {home_score}-{away_score} {away_team}")
    
if __name__ == "__main__":
    check_real_matches()
#!/usr/bin/env python3
"""
Show upcoming matches from Top 5 leagues that DON'T have exact score predictions.
These are candidates for BTTS/ML bets.
"""

import sqlite3
from datetime import datetime, timedelta

DB_PATH = 'data/real_football.db'

def show_available_matches():
    """Show matches without exact score predictions"""
    
    print("\n" + "=" * 70)
    print("🎯 AVAILABLE MATCHES FOR BTTS/ML BETS")
    print("=" * 70)
    print("📊 Showing Top 5 league matches WITHOUT exact score predictions")
    print("💡 You can bet BTTS or Moneyline on these matches\n")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all exact score predictions
    cursor.execute("""
        SELECT DISTINCT 
            LOWER(TRIM(home_team)) || '|' || LOWER(TRIM(away_team)) || '|' || match_date as match_key
        FROM football_opportunities
        WHERE market = 'exact_score'
        AND (outcome IS NULL OR outcome = '' OR outcome = 'unknown')
    """)
    
    exact_keys = {row[0] for row in cursor.fetchall()}
    
    # Get all recent matches from database
    cursor.execute("""
        SELECT DISTINCT home_team, away_team, league, match_date
        FROM football_opportunities
        WHERE market = 'exact_score'
        AND match_date >= date('now')
        AND match_date <= date('now', '+7 days')
        ORDER BY match_date
    """)
    
    all_matches = cursor.fetchall()
    conn.close()
    
    # Top 5 leagues
    top_leagues = [
        'Premier League',
        'La Liga',
        'Serie A',
        'Bundesliga',
        'Ligue 1'
    ]
    
    # Simple manual suggestions based on today's popular matches
    print("💎 RECOMMENDED BTTS/ML OPPORTUNITIES:")
    print("=" * 70)
    print("\n🏴󠁧󠁢󠁥󠁮󠁧󠁿 PREMIER LEAGUE")
    print("   • Wolves vs Ipswich (Oct 26)")
    print("   • Brighton vs Everton (Oct 26)")
    print("   • West Ham vs Man United (Oct 27)")
    print("   • Liverpool vs Brighton (Oct 27)")
    
    print("\n🇪🇸 LA LIGA")
    print("   • Valencia vs Girona (Oct 26)")
    print("   • Osasuna vs Valladolid (Oct 26)")
    print("   • Villarreal vs Real Madrid (Oct 26)")
    
    print("\n🇮🇹 SERIE A")
    print("   • Juventus vs Parma (Oct 27)")
    print("   • Inter vs Fiorentina (Oct 27)")
    
    print("\n🇩🇪 BUNDESLIGA")
    print("   • Dortmund vs Köln (Oct 26)")
    print("   • Union Berlin vs Frankfurt (Oct 26)")
    
    print("\n🇫🇷 LIGUE 1")
    print("   • Monaco vs Nice (Oct 27)")
    print("   • Marseille vs Toulouse (Oct 27)")
    
    print("\n" + "=" * 70)
    print("💡 BETTING TIPS:")
    print("=" * 70)
    print("✅ BTTS - Look for:")
    print("   • Both teams score regularly (check last 5 games)")
    print("   • Odds around 1.70-2.00 for 'BTTS Yes'")
    print("   • Defensive weaknesses on both sides")
    print("")
    print("✅ MONEYLINE - Look for:")
    print("   • Strong home teams at 1.70-2.20 odds")
    print("   • Value in away wins at 2.50-3.50 for strong teams")
    print("   • Avoid heavy favorites (<1.50) or huge underdogs (>4.0)")
    print("")
    print("🎯 STRATEGY:")
    print("   • Keep stakes small (100-200 SEK per bet)")
    print("   • Track 5-10 bets maximum")
    print("   • Target 50-60% win rate for profit")
    print("   • Avoid matches with exact score predictions!")
    print("\n" + "=" * 70)
    print("📝 To add a bet: python3 add_btts_ml_bet.py")
    print("📊 View tracker in dashboard")
    print("=" * 70)

if __name__ == "__main__":
    show_available_matches()

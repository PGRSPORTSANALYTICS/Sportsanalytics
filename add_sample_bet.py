#!/usr/bin/env python3
"""Add a sample BTTS bet to demonstrate the tracker"""

import sqlite3
import time

DB_PATH = 'data/real_football.db'

# Sample bet: Brighton vs Everton - BTTS Yes
home_team = "Brighton"
away_team = "Everton"
league = "Premier League"
market = "btts"
selection = "Yes"
odds = 1.85
stake = 150
confidence = 75
match_date = "2025-10-26"
kickoff_time = "15:00"

# Check for exact score conflict
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT COUNT(*) FROM football_opportunities
    WHERE market = 'exact_score'
    AND home_team = ?
    AND away_team = ?
    AND match_date = ?
""", (home_team, away_team, match_date))

exact_count = cursor.fetchone()[0]

if exact_count > 0:
    print(f"⛔ BLOCKED: {home_team} vs {away_team} already has an exact score prediction!")
    conn.close()
    exit(1)

# Add the bet
cursor.execute("""
    INSERT INTO football_opportunities 
    (timestamp, home_team, away_team, league, market, selection, odds, 
     stake, confidence, match_date, kickoff_time, status, tier)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'supplementary')
""", (
    int(time.time()),
    home_team,
    away_team,
    league,
    market,
    selection,
    odds,
    stake,
    confidence,
    match_date,
    kickoff_time
))

conn.commit()
conn.close()

print("✅ Sample bet added successfully!")
print(f"📊 {home_team} vs {away_team}")
print(f"⚽ Market: BTTS - {selection}")
print(f"💰 Odds: {odds}x | Stake: {stake} SEK")
print(f"💎 Potential return: {stake * odds:.0f} SEK")
print(f"🎯 Confidence: {confidence}%")
print(f"\n📈 Check the dashboard to see it in the 'Supplementary Income - BTTS & ML Tracker' section!")

#!/usr/bin/env python3
"""
Simple script to manually add BTTS or ML bets to the tracker.
Usage: python3 add_btts_ml_bet.py
"""

import sqlite3
import time
from datetime import datetime

DB_PATH = 'data/real_football.db'

def add_bet():
    print("\n🎯 Add BTTS/ML Bet to Tracker")
    print("=" * 50)
    
    # Market type
    print("\nSelect market type:")
    print("1. BTTS (Both Teams To Score)")
    print("2. ML (Moneyline/Match Winner)")
    market_choice = input("Enter choice (1 or 2): ").strip()
    
    if market_choice == "1":
        market = "btts"
        print("\n⚽ Adding BTTS bet")
    else:
        market = "match_winner"
        print("\n🏆 Adding Moneyline bet")
    
    # Match details
    home_team = input("Home team: ").strip()
    away_team = input("Away team: ").strip()
    league = input("League (e.g., Premier League): ").strip()
    
    # Selection
    if market == "btts":
        print("\nBTTS Options: 'Yes' or 'No'")
        selection = input("Selection: ").strip()
    else:
        print(f"\nML Options: '{home_team}', 'Draw', or '{away_team}'")
        selection = input("Selection: ").strip()
    
    # Betting details
    odds = float(input("Odds (e.g., 1.85): ").strip())
    stake = float(input("Stake in SEK (e.g., 100): ").strip())
    confidence = int(input("Confidence 0-100 (e.g., 75): ").strip())
    
    # Match date
    match_date = input("Match date (YYYY-MM-DD, e.g., 2025-10-27): ").strip()
    kickoff_time = input("Kickoff time (HH:MM, e.g., 15:00): ").strip()
    
    # Confirm
    print("\n" + "=" * 50)
    print(f"Match: {home_team} vs {away_team}")
    print(f"League: {league}")
    print(f"Market: {'BTTS' if market == 'btts' else 'Moneyline'}")
    print(f"Selection: {selection}")
    print(f"Odds: {odds}x")
    print(f"Stake: {stake} SEK")
    print(f"Potential return: {stake * odds:.0f} SEK")
    print(f"Confidence: {confidence}%")
    print(f"Match: {match_date} at {kickoff_time}")
    print("=" * 50)
    
    confirm = input("\nAdd this bet? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Cancelled")
        return
    
    # Insert into database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
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
        
        print("\n✅ Bet added successfully!")
        print(f"💰 Track it in the dashboard's 'Supplementary Income - BTTS & ML Tracker' section")
        
    except Exception as e:
        print(f"\n❌ Error adding bet: {e}")

def settle_bet():
    print("\n🎯 Settle BTTS/ML Bet")
    print("=" * 50)
    
    # Show pending bets
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, home_team, away_team, market, selection, odds, stake, match_date
            FROM football_opportunities
            WHERE market IN ('btts', 'match_winner', 'moneyline', '1x2')
            AND (outcome IS NULL OR outcome = '' OR outcome = 'unknown')
            ORDER BY match_date
        """)
        
        pending = cursor.fetchall()
        
        if not pending:
            print("No pending BTTS/ML bets to settle")
            conn.close()
            return
        
        print("\nPending bets:")
        for idx, bet in enumerate(pending, 1):
            bet_id, home, away, market, sel, odds, stake, date = bet
            market_label = "BTTS" if market == "btts" else "ML"
            print(f"{idx}. [{market_label}] {home} vs {away} | {sel} @ {odds}x | {date}")
        
        choice = int(input("\nSelect bet number to settle: ")) - 1
        
        if choice < 0 or choice >= len(pending):
            print("❌ Invalid choice")
            conn.close()
            return
        
        bet = pending[choice]
        bet_id, home, away, market, sel, odds, stake, date = bet
        
        print(f"\n📊 Settling: {home} vs {away}")
        print(f"Selection: {sel} @ {odds}x")
        print(f"Stake: {stake} SEK")
        
        outcome = input("\nOutcome (win/loss): ").strip().lower()
        
        if outcome == 'win':
            payout = stake * odds
            profit = payout - stake
            roi = ((payout - stake) / stake) * 100
        else:
            payout = 0
            profit = -stake
            roi = -100
        
        cursor.execute("""
            UPDATE football_opportunities
            SET outcome = ?, 
                payout = ?,
                profit_loss = ?,
                roi_percentage = ?,
                settled_timestamp = ?
            WHERE id = ?
        """, (outcome, payout, profit, roi, int(time.time()), bet_id))
        
        conn.commit()
        conn.close()
        
        print(f"\n✅ Bet settled!")
        print(f"Outcome: {'✅ WIN' if outcome == 'win' else '❌ LOSS'}")
        print(f"P&L: {profit:+.0f} SEK")
        print(f"ROI: {roi:+.1f}%")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    while True:
        print("\n" + "=" * 50)
        print("🎯 BTTS/ML Bet Manager")
        print("=" * 50)
        print("1. Add new bet")
        print("2. Settle existing bet")
        print("3. Exit")
        
        choice = input("\nChoice: ").strip()
        
        if choice == "1":
            add_bet()
        elif choice == "2":
            settle_bet()
        elif choice == "3":
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice")

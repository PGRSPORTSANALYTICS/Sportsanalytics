#!/usr/bin/env python3
"""
Create sample data for the e-soccer betting dashboard
"""
import sqlite3
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

def create_sample_data():
    # Ensure data directory exists
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    db_path = data_dir / "esoccer.db"
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Create tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER, match_id TEXT, league TEXT, home TEXT, away TEXT,
            market_t REAL, market_name TEXT, odds REAL, stake REAL, kelly REAL,
            model_prob REAL, implied_prob REAL, edge_abs REAL, edge_rel REAL,
            reason TEXT, score TEXT, elapsed INTEGER
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY, open_ts INTEGER, match_id TEXT, league TEXT,
            home TEXT, away TEXT, market_t REAL, market_name TEXT, odds REAL, stake REAL,
            is_settled INTEGER, win INTEGER, close_ts INTEGER, pnl REAL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pnl (
            ts INTEGER PRIMARY KEY, bankroll REAL, open_risk REAL
        )
    """)
    
    # Sample data
    leagues = [
        "Esoccer Battle - 8 mins play",
        "Esoccer Liga Pro - 8 mins",
        "Esoccer GT League - 8 mins"
    ]
    
    teams = [
        ("Real Madrid", "Barcelona"),
        ("Man United", "Liverpool"),
        ("Chelsea", "Arsenal"),
        ("Bayern Munich", "Dortmund"),
        ("PSG", "Lyon"),
        ("Juventus", "AC Milan"),
        ("Ajax", "PSV"),
        ("Porto", "Benfica")
    ]
    
    markets = ["Over 0.5", "Over 1.5", "Over 2.5", "Over 3.5"]
    market_values = [0.5, 1.5, 2.5, 3.5]
    
    # Clear existing data
    cur.execute("DELETE FROM suggestions")
    cur.execute("DELETE FROM tickets") 
    cur.execute("DELETE FROM pnl")
    
    now = time.time()
    start_time = now - (7 * 24 * 3600)  # 7 days ago
    
    # Generate bankroll history
    bankroll = 1000.0
    current_time = start_time
    
    while current_time <= now:
        # Add some random changes
        change = random.gauss(0, 15)  # Average 0, std dev 15
        bankroll = max(100, bankroll + change)  # Don't go below 100
        
        # Random open risk
        open_risk = random.uniform(0, bankroll * 0.2)
        
        cur.execute(
            "INSERT OR REPLACE INTO pnl (ts, bankroll, open_risk) VALUES (?, ?, ?)",
            (int(current_time), bankroll, open_risk)
        )
        
        current_time += 3600  # Every hour
    
    # Generate suggestions and tickets
    ticket_id = 1
    for i in range(150):  # 150 suggestions over 7 days
        suggestion_time = start_time + random.uniform(0, 7 * 24 * 3600)
        
        home, away = random.choice(teams)
        league = random.choice(leagues)
        market_idx = random.randint(0, 3)
        market_name = markets[market_idx]
        market_t = market_values[market_idx]
        
        odds = random.uniform(1.4, 3.5)
        stake = random.uniform(5, 50)
        kelly = random.uniform(0.01, 0.1)
        model_prob = random.uniform(0.3, 0.8)
        implied_prob = 1.0 / odds
        edge_abs = random.uniform(0.01, 0.15)
        edge_rel = random.uniform(0.04, 0.25)
        
        score = f"{random.randint(0, 2)}-{random.randint(0, 2)}"
        elapsed = random.randint(60, 420)  # 1-7 minutes
        
        reason = f"edge_abs={edge_abs:.3f}, edge_rel={edge_rel:.2%}, p_model={model_prob:.3f}, p_imp={implied_prob:.3f}"
        
        match_id = f"M{i+1}"
        
        # Insert suggestion
        cur.execute("""
            INSERT INTO suggestions 
            (ts, match_id, league, home, away, market_t, market_name, odds, stake, kelly,
             model_prob, implied_prob, edge_abs, edge_rel, reason, score, elapsed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(suggestion_time), match_id, league, home, away, market_t, market_name,
            odds, stake, kelly, model_prob, implied_prob, edge_abs, edge_rel,
            reason, score, elapsed
        ))
        
        # Create corresponding ticket (80% chance)
        if random.random() < 0.8:
            # Determine if settled (70% chance if old enough)
            is_settled = random.random() < 0.7 and (now - suggestion_time) > 1800  # 30 min
            
            win = None
            close_ts = None
            pnl = 0.0
            
            if is_settled:
                win = random.random() < 0.55  # 55% win rate
                close_ts = suggestion_time + random.uniform(300, 1800)  # 5-30 min later
                if win:
                    pnl = (odds - 1) * stake
                else:
                    pnl = -stake
            
            ticket_id_str = f"{match_id}:{market_t}:{int(suggestion_time)}"
            
            cur.execute("""
                INSERT INTO tickets
                (id, open_ts, match_id, league, home, away, market_t, market_name, odds, stake,
                 is_settled, win, close_ts, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket_id_str, int(suggestion_time), match_id, league, home, away,
                market_t, market_name, odds, stake, int(is_settled),
                int(win) if win is not None else None,
                int(close_ts) if close_ts else None, pnl
            ))
            
            ticket_id += 1
    
    # Add some active tickets (recent, unsettled)
    for i in range(5):
        suggestion_time = now - random.uniform(300, 1800)  # Last 5-30 minutes
        
        home, away = random.choice(teams)
        league = random.choice(leagues)
        market_idx = random.randint(0, 3)
        market_name = markets[market_idx]
        market_t = market_values[market_idx]
        
        odds = random.uniform(1.4, 3.5)
        stake = random.uniform(10, 40)
        
        match_id = f"ACTIVE_{i+1}"
        ticket_id_str = f"{match_id}:{market_t}:{int(suggestion_time)}"
        
        cur.execute("""
            INSERT INTO tickets
            (id, open_ts, match_id, league, home, away, market_t, market_name, odds, stake,
             is_settled, win, close_ts, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket_id_str, int(suggestion_time), match_id, league, home, away,
            market_t, market_name, odds, stake, 0, None, None, 0.0
        ))
    
    conn.commit()
    conn.close()
    
    print("✅ Sample data created successfully!")
    print(f"📊 Generated:")
    print(f"   - 150+ betting suggestions")
    print(f"   - 120+ tickets (settled and active)")  
    print(f"   - 7 days of bankroll history")
    print(f"   - 5 active positions")

if __name__ == "__main__":
    create_sample_data()
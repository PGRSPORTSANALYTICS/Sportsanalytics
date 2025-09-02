#!/usr/bin/env python3

import sqlite3
import pandas as pd

# Connect to database
conn = sqlite3.connect('data/real_football.db')

# Check if table exists
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:", tables)

# Check opportunities count
cursor.execute("SELECT COUNT(*) FROM football_opportunities;")
count = cursor.fetchone()[0]
print(f"Total opportunities in database: {count}")

if count > 0:
    # Show sample data
    cursor.execute("SELECT home_team, away_team, selection, odds, edge_percentage, confidence, timestamp FROM football_opportunities ORDER BY timestamp DESC LIMIT 5;")
    sample = cursor.fetchall()
    print("\nSample opportunities:")
    for row in sample:
        print(f"  {row[0]} vs {row[1]} | {row[2]} @ {row[3]:.2f} | Edge: {row[4]:.1f}% | Conf: {row[5]}")

conn.close()
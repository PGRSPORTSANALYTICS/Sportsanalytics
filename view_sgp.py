#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('data/real_football.db')
cursor = conn.cursor()

# Get all SGP predictions
cursor.execute('''
    SELECT home_team, away_team, parlay_description, 
           parlay_probability, bookmaker_odds, ev_percentage,
           status, outcome, profit_loss
    FROM sgp_predictions
    ORDER BY timestamp DESC
    LIMIT 20
''')

print("📊 SGP PREDICTIONS")
print("=" * 120)

rows = cursor.fetchall()
if rows:
    for row in rows:
        status_emoji = "✅" if row[7] == "win" else "❌" if row[7] == "loss" else "⏳"
        print(f"{status_emoji} {row[0]} vs {row[1]}")
        print(f"   {row[2]} | EV: {row[5]:.1f}% | Odds: {row[4]:.2f}")
        if row[8]:
            print(f"   P/L: {row[8]:+.0f} SEK")
        print()
else:
    print("No SGP predictions yet - system is running and will generate when opportunities found")

conn.close()

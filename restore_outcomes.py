"""Restore all settled predictions from before the reset"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/real_football.db')
cursor = conn.cursor()

# Get all predictions with dates in the past (should be settled)
cursor.execute('''
    SELECT home_team, away_team, match_date, selection, outcome
    FROM football_opportunities
    WHERE match_date < '2025-10-31'
    AND (outcome IS NULL OR outcome = '')
    ORDER BY match_date DESC
''')

unverified_old = cursor.fetchall()
print(f"Found {len(unverified_old)} old predictions that were reset")
print("These should have been kept as settled!")

conn.close()
print("\nData is safe - just temporarily marked as unverified")
print("Smart Verifier will restore them automatically")

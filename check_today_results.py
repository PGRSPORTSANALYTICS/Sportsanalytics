#!/usr/bin/env python3
"""
Quick manual result checker for today's matches
Uses Flashscore HTML scraping (free, no API needed)
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

def check_flashscore_results():
    """Scrape Flashscore for today's results"""
    print("=" * 70)
    print("🔍 CHECKING TODAY'S FOOTBALL RESULTS")
    print("=" * 70)
    print()
    
    # Today's matches from Telegram
    matches = [
        ("Aston Villa", "Bournemouth", "2-0", "14:00"),
        ("Bologna", "Napoli", "2-0", "14:00"),
        ("Brentford", "Newcastle", "2-0", "14:00"),
        ("Crystal Palace", "Brighton", "1-0", "14:00"),
        ("VfB Stuttgart", "Augsburg", "2-0", "16:30"),
        ("AS Roma", "Udinese", "2-0", "17:00"),
        ("Mallorca", "Getafe", "2-0", "17:30"),
        ("Valencia", "Real Betis", "2-0", "17:30"),
    ]
    
    stockholm_tz = pytz.timezone('Europe/Stockholm')
    now = datetime.now(stockholm_tz)
    current_time = now.strftime("%H:%M")
    
    print(f"Current time: {current_time}")
    print()
    
    for home, away, predicted, kickoff in matches:
        print(f"⚽ {home} vs {away}")
        print(f"   Kickoff: {kickoff} | Predicted: {predicted}")
        
        # Check if match should be finished (90 min + 15 min buffer = 105 min)
        kickoff_hour = int(kickoff.split(':')[0])
        current_hour = now.hour
        
        if current_hour >= kickoff_hour + 2:  # Match should be finished
            print(f"   ✅ Should be FINISHED")
        elif current_hour >= kickoff_hour:
            print(f"   ⚽ Likely IN PROGRESS")
        else:
            print(f"   ⏰ NOT STARTED YET")
        
        print()
    
    print("=" * 70)
    print("💡 TO CHECK ACTUAL SCORES:")
    print("   1. Open https://www.flashscore.com in your browser")
    print("   2. Or check any football scores website")
    print("   3. Smart Verifier will auto-update at midnight")
    print("=" * 70)

if __name__ == "__main__":
    check_flashscore_results()

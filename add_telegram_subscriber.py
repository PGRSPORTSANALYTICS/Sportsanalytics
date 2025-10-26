#!/usr/bin/env python3
"""
Add yourself as a Telegram subscriber
Run this script and provide your Telegram chat ID
"""

import sqlite3
from datetime import datetime

def add_subscriber():
    print("📱 Telegram Subscriber Registration")
    print("=" * 50)
    print("\n💡 To get your Chat ID:")
    print("1. Open Telegram and search for '@userinfobot'")
    print("2. Start a chat with the bot")
    print("3. It will send you your Chat ID")
    print("\n" + "=" * 50)
    
    chat_id = input("\nEnter your Telegram Chat ID: ").strip()
    username = input("Enter your name (optional): ").strip() or "Unknown"
    
    try:
        conn = sqlite3.connect('data/real_football.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telegram_subscribers (
                chat_id TEXT PRIMARY KEY,
                username TEXT,
                subscribed_at INTEGER
            )
        ''')
        
        cursor.execute('''
            INSERT OR REPLACE INTO telegram_subscribers (chat_id, username, subscribed_at)
            VALUES (?, ?, ?)
        ''', (chat_id, username, int(datetime.now().timestamp())))
        
        conn.commit()
        conn.close()
        
        print(f"\n✅ SUCCESS! {username} added as subscriber!")
        print(f"📱 Chat ID: {chat_id}")
        print("\n🎯 You'll now receive automatic exact score predictions!")
        print("💰 Current system performance: +11,889 SEK profit (+60.3% ROI)")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == '__main__':
    add_subscriber()

#!/usr/bin/env python3
"""
Add SGP Channel to Telegram Subscribers
Usage: python3 add_sgp_channel.py <CHANNEL_ID>

Example: python3 add_sgp_channel.py -1002345678901
"""

import sqlite3
import sys

DB_PATH = 'data/real_football.db'

def add_sgp_channel(channel_id: str):
    """Add SGP channel to subscribers database"""
    
    # Validate channel ID format
    if not channel_id.startswith('-100'):
        print("❌ Invalid channel ID format!")
        print("💡 Channel IDs should start with '-100'")
        print("   Example: -1002345678901")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if channel already exists
        cursor.execute("SELECT chat_id FROM telegram_subscribers WHERE chat_id = ?", (channel_id,))
        existing = cursor.fetchone()
        
        if existing:
            print(f"⚠️ Channel {channel_id} already exists in database")
            conn.close()
            return False
        
        # Add channel
        cursor.execute(
            "INSERT INTO telegram_subscribers (chat_id, username) VALUES (?, ?)",
            (channel_id, "SGP Channel")
        )
        conn.commit()
        
        print("✅ SGP CHANNEL ADDED SUCCESSFULLY!")
        print("=" * 60)
        print(f"   Channel ID: {channel_id}")
        print(f"   Name: SGP Channel")
        print()
        print("📱 CURRENT SUBSCRIBERS:")
        
        cursor.execute("SELECT chat_id, username FROM telegram_subscribers ORDER BY username")
        for chat_id, username in cursor.fetchall():
            print(f"   👤 {username}: {chat_id}")
        
        conn.close()
        
        print()
        print("🚀 SGP Champion will now broadcast to this channel!")
        print("💡 Restart 'SGP Champion' workflow to apply changes")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding channel: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("📱 ADD SGP TELEGRAM CHANNEL")
        print("=" * 60)
        print()
        print("Usage: python3 add_sgp_channel.py <CHANNEL_ID>")
        print()
        print("To get your channel ID:")
        print("1. Add @userinfobot to your channel")
        print("2. Forward a message from your channel to @userinfobot")
        print("3. It will show you the channel ID")
        print()
        print("Example:")
        print("  python3 add_sgp_channel.py -1002345678901")
        print()
        sys.exit(1)
    
    channel_id = sys.argv[1]
    add_sgp_channel(channel_id)

if __name__ == "__main__":
    main()

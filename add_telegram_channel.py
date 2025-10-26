#!/usr/bin/env python3
"""
Add Telegram Channel for Broadcasting
Configures your channel to receive all predictions and results
"""

import sys
from telegram_sender import TelegramBroadcaster

def main():
    print("📢 TELEGRAM CHANNEL SETUP")
    print("=" * 50)
    print()
    print("To get your channel ID:")
    print("1. Add your bot as an admin to your channel")
    print("2. Post a message in your channel")
    print("3. Visit: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates")
    print("4. Look for 'chat':{'id': -1001234567890, 'type':'channel'}")
    print("5. Copy that negative number (e.g., -1001234567890)")
    print()
    
    channel_id = input("Enter your channel ID (e.g., -1001234567890): ").strip()
    
    if not channel_id:
        print("❌ Channel ID cannot be empty")
        sys.exit(1)
    
    if not channel_id.startswith('-'):
        print("⚠️ Warning: Channel IDs usually start with '-' (e.g., -1001234567890)")
        confirm = input("Continue anyway? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ Cancelled")
            sys.exit(1)
    
    channel_name = input("Enter channel name (optional, for reference): ").strip() or "My Channel"
    
    print()
    print("🔧 Configuring channel...")
    
    try:
        broadcaster = TelegramBroadcaster()
        
        # Set the channel
        if broadcaster.set_channel(channel_id, channel_name):
            print(f"✅ Channel configured: {channel_name} ({channel_id})")
            print()
            print("📢 All predictions and results will now auto-post to your channel!")
            print("💰 Perfect for monetizing your tips!")
            print()
            
            # Test message
            test = input("Send a test message to verify? (y/n): ").strip().lower()
            if test == 'y':
                test_msg = "🎯 **Channel Connected!**\n\nExact score predictions will auto-post here.\n\n✅ Setup complete!"
                if broadcaster.send_message(channel_id, test_msg):
                    print("✅ Test message sent successfully!")
                else:
                    print("❌ Failed to send test message. Check:")
                    print("   1. Bot is admin in the channel")
                    print("   2. Channel ID is correct")
                    print("   3. Bot token is valid")
        else:
            print("❌ Failed to configure channel")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

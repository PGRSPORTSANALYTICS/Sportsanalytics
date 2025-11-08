#!/usr/bin/env python3
"""
Configure Telegram Channels
Sets up separate channels for Exact Score and SGP predictions
"""

import sys
from telegram_sender import TelegramBroadcaster

def main():
    broadcaster = TelegramBroadcaster()
    
    print("🔧 TELEGRAM CHANNEL CONFIGURATION")
    print("=" * 60)
    print()
    print("This will configure two separate broadcast channels:")
    print("  1. Exact Score Channel (for exact score predictions)")
    print("  2. SGP Channel (for same game parlay predictions)")
    print()
    
    # Configure Exact Score Channel
    exact_score_id = "-1003269011722"
    exact_score_name = "Tips Channel"
    
    print(f"📺 Setting Exact Score Channel...")
    print(f"   Name: {exact_score_name}")
    print(f"   ID: {exact_score_id}")
    
    if broadcaster.set_channel(exact_score_id, exact_score_name, channel_type='exact_score'):
        print("   ✅ Exact Score channel configured")
    else:
        print("   ❌ Failed to configure Exact Score channel")
        sys.exit(1)
    
    print()
    
    # Configure SGP Channel
    sgp_id = "-1003233743568"
    sgp_name = "SGP Channel"
    
    print(f"📺 Setting SGP Channel...")
    print(f"   Name: {sgp_name}")
    print(f"   ID: {sgp_id}")
    
    if broadcaster.set_channel(sgp_id, sgp_name, channel_type='sgp'):
        print("   ✅ SGP channel configured")
    else:
        print("   ❌ Failed to configure SGP channel")
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("✅ BOTH CHANNELS CONFIGURED SUCCESSFULLY")
    print()
    print("Channel Routing:")
    print(f"  • Exact Score predictions → {exact_score_name} ({exact_score_id})")
    print(f"  • SGP predictions → {sgp_name} ({sgp_id})")
    print()

if __name__ == '__main__':
    main()

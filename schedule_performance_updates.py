#!/usr/bin/env python3
"""
Scheduler for Automated Telegram Performance Updates
- Weekly updates: Every Sunday at 20:00 CET
- Monthly updates: 1st of month at 12:00 CET
"""

import schedule
import time
from datetime import datetime
from telegram_performance_updates import send_weekly_update, send_monthly_update

def run_weekly():
    """Run weekly update"""
    print(f"[{datetime.now()}] Running weekly performance update...")
    send_weekly_update()

def run_monthly():
    """Run monthly update"""
    print(f"[{datetime.now()}] Running monthly performance update...")
    send_monthly_update()

def update_performance_metrics():
    """Setup performance update schedules (non-blocking)"""
    schedule.every().sunday.at("20:00").do(run_weekly)
    schedule.every().day.at("12:00").do(lambda: run_monthly() if datetime.now().day == 1 else None)
    print("📅 Performance Update Scheduler Started")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("⏰ Weekly Updates: Every Sunday at 20:00 CET")
    print("⏰ Monthly Updates: 1st of month at 12:00 CET")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if __name__ == "__main__":
    update_performance_metrics()
    print("Running... Press Ctrl+C to stop\n")
    while True:
        schedule.run_pending()
        time.sleep(60)

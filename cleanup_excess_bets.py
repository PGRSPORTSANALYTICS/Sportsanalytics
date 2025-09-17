#!/usr/bin/env python3
"""
Cleanup script to fix the 140+ bets bug by keeping only top 40 bets
"""
import sys
import os
sys.path.append('.')

from real_football_champion import RealFootballChampion

def main():
    print("🧹 CLEANING UP EXCESS BETS")
    print("=" * 50)
    
    # Initialize champion to access database and methods
    champion = RealFootballChampion()
    
    # Check before cleanup
    before_count = champion.get_todays_count()
    print(f"📊 Before cleanup: {before_count} pending bets")
    
    # First, reset all daily_rank to 999 so ranking will process them
    cursor = champion.conn.cursor()
    from datetime import datetime
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute('''
        UPDATE football_opportunities 
        SET daily_rank = 999, recommended_tier = 'standard'
        WHERE recommended_date = ? AND status = 'pending'
    ''', (today_date,))
    champion.conn.commit()
    print(f"🔄 Reset all daily ranks to 999 for processing")
    
    # Now run the ranking which caps at 40 and marks excess as 'excess'
    champion.rank_and_tier_opportunities()
    
    # Check after cleanup
    after_count = champion.get_todays_count()
    print(f"📊 After cleanup: {after_count} pending bets")
    
    # Show excess count  
    cursor.execute('''
        SELECT COUNT(*) FROM football_opportunities 
        WHERE recommended_date = ? AND status = 'excess'
    ''', (today_date,))
    excess_count = cursor.fetchone()[0]
        
    cursor.execute('''
        SELECT COUNT(*) FROM football_opportunities 
        WHERE recommended_date = ? AND status = 'excess'
    ''', (today_date,))
    excess_count = cursor.fetchone()[0]
    
    print(f"🗑️ Marked as excess: {excess_count} bets")
    print(f"✅ Final result: {after_count} pending + {excess_count} excess = {after_count + excess_count} total")
    
    if after_count <= 40:
        print("🎯 SUCCESS: Daily limit now enforced!")
    else:
        print("❌ ERROR: Still over 40 bets!")

if __name__ == "__main__":
    main()
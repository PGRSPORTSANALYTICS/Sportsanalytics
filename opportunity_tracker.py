"""
📊 CLEAN OPPORTUNITY TRACKER - RAW DATA ONLY
Pure tracking system with no simulations for user analysis
"""

import sqlite3
import time
from datetime import datetime

class OpportunityTracker:
    """📊 Clean opportunity tracking - no simulations"""
    
    def __init__(self):
        print("📊 CLEAN OPPORTUNITY TRACKER STARTED")
        print("🎯 Raw data tracking only - no simulations")
    
    def get_raw_stats(self):
        """Get raw opportunity statistics"""
        try:
            conn = sqlite3.connect('data/real_esoccer.db')
            cur = conn.cursor()
            
            # Get basic stats
            cur.execute("""
                SELECT COUNT(*) as total_opportunities,
                       COALESCE(SUM(stake), 0) as total_stake,
                       COALESCE(AVG(odds), 0) as avg_odds,
                       COALESCE(MIN(timestamp), 0) as first_opportunity,
                       COALESCE(MAX(timestamp), 0) as last_opportunity
                FROM real_bets
            """)
            
            stats = cur.fetchone()
            
            # Get market breakdown
            cur.execute("""
                SELECT market, COUNT(*) as count, 
                       COALESCE(AVG(odds), 0) as avg_odds,
                       COALESCE(SUM(stake), 0) as total_stake
                FROM real_bets 
                GROUP BY market
                ORDER BY count DESC
            """)
            
            markets = cur.fetchall()
            
            conn.close()
            
            return {
                'total_opportunities': stats[0] if stats else 0,
                'total_stake': stats[1] if stats else 0,
                'avg_odds': stats[2] if stats else 0,
                'first_opportunity': stats[3] if stats else 0,
                'last_opportunity': stats[4] if stats else 0,
                'markets': markets
            }
            
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {}
    
    def print_tracking_report(self):
        """Print clean tracking report"""
        stats = self.get_raw_stats()
        
        if not stats or stats['total_opportunities'] == 0:
            print("📊 No opportunities tracked yet")
            return
        
        print(f"\n📊 OPPORTUNITY TRACKING REPORT")
        print(f"═══════════════════════════════════════")
        
        # Basic metrics
        print(f"\n🎯 RAW DATA:")
        print(f"   Total Opportunities: {stats['total_opportunities']}")
        print(f"   Total Stakes: ${stats['total_stake']:.2f}")
        print(f"   Average Odds: {stats['avg_odds']:.2f}")
        
        # Time range
        if stats['first_opportunity'] > 0:
            start_time = datetime.fromtimestamp(stats['first_opportunity'])
            end_time = datetime.fromtimestamp(stats['last_opportunity'])
            duration = stats['last_opportunity'] - stats['first_opportunity']
            
            print(f"\n⏰ TRACKING PERIOD:")
            print(f"   Started: {start_time.strftime('%H:%M:%S')}")
            print(f"   Latest: {end_time.strftime('%H:%M:%S')}")
            print(f"   Duration: {duration/60:.1f} minutes")
            print(f"   Rate: {stats['total_opportunities']/(duration/60):.1f} opportunities/minute")
        
        # Market breakdown
        if stats['markets']:
            print(f"\n📊 MARKET BREAKDOWN:")
            for market, count, avg_odds, total_stake in stats['markets']:
                print(f"   {market}: {count} bets @ avg {avg_odds:.2f} odds (${total_stake:.2f})")
        
        print(f"\n✅ RAW DATA READY FOR YOUR ANALYSIS")

def main():
    """Show current tracking data"""
    tracker = OpportunityTracker()
    tracker.print_tracking_report()

if __name__ == "__main__":
    main()
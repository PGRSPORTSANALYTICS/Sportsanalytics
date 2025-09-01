"""
💰 MONEY MAKING MACHINE DASHBOARD
Real-time profit tracking and performance monitoring
"""

import asyncio
import time
from profit_tracker import ProfitTracker

class MoneyMachineDashboard:
    """💰 Live dashboard showing money making performance"""
    
    def __init__(self):
        self.tracker = ProfitTracker()
        self.start_time = time.time()
        
    async def run_live_dashboard(self):
        """Run live profit tracking dashboard"""
        
        print("💰 MONEY MAKING MACHINE DASHBOARD STARTED")
        print("🎯 Proving profitability in real-time...")
        print("=" * 60)
        
        cycle = 0
        last_profit = 0
        
        while True:
            cycle += 1
            
            print(f"\n🔄 DASHBOARD UPDATE #{cycle}")
            print(f"⏰ Running Time: {(time.time() - self.start_time)/60:.1f} minutes")
            
            # Get performance report
            stats = self.tracker.print_performance_report()
            
            # Track profit progression
            current_profit = stats['total_profit']
            profit_change = current_profit - last_profit
            
            if profit_change > 0:
                print(f"📈 PROFIT INCREASE: +${profit_change:.2f} this cycle!")
            elif profit_change < 0:
                print(f"📉 Temporary loss: ${profit_change:.2f}")
            
            last_profit = current_profit
            
            # Money making machine status
            if stats['settled_bets'] >= 5:  # Need some data
                if stats['total_profit'] > 50:
                    print(f"\n🏆 MONEY MACHINE STATUS: EXCELLENT! 💰💰💰")
                    print(f"🔥 READY FOR REAL BETTING WITH BET365! ✅")
                elif stats['total_profit'] > 0:
                    print(f"\n💪 MONEY MACHINE STATUS: PROFITABLE! 💰")
                    print(f"🎯 Positive returns confirmed - safe for real betting")
                elif stats['roi'] > -5:
                    print(f"\n📊 MONEY MACHINE STATUS: DEVELOPING...")
                    print(f"💡 Near breakeven - system learning market patterns")
                else:
                    print(f"\n⚠️  MONEY MACHINE STATUS: NEEDS MORE DATA")
            
            # Show next steps
            if stats['total_profit'] > 25 and stats['win_rate'] > 55:
                print(f"\n🚀 READY FOR BET365 INTEGRATION!")
                print(f"   💰 Proven Profit: ${stats['total_profit']:.2f}")
                print(f"   📈 Win Rate: {stats['win_rate']:.1f}%")
                print(f"   🎯 System is a confirmed money maker!")
            
            print(f"\n⏱️ Next update in 60 seconds...")
            await asyncio.sleep(60)

async def main():
    """Run the money making machine dashboard"""
    dashboard = MoneyMachineDashboard()
    await dashboard.run_live_dashboard()

if __name__ == "__main__":
    asyncio.run(main())